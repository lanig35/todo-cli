"""Webhook HTTP : un POST JSON par commande qui modifie quelque chose, avec file d'attente et signature.

Livraison « au moins une fois » : un envoi qui échoue pour une raison passagère (serveur arrêté, réseau coupé, délai dépassé,
HTTP 5xx, 408, 425, 429, ou 401/403/404 qui se corrigent en changeant le jeton ou l'URL) n'est pas perdu : l'événement est mis
dans la file du projet (`webhook_queue.json`) et renvoyé, dans l'ordre, à la prochaine commande qui modifie quelque chose ou par
`todo hooks flush`. Les autres refus (400, 413, 422…) sont définitifs : l'événement est abandonné avec un avertissement.

  - Attente croissante entre deux tentatives (30 s, 1 min, 2 min… 1 h) : une panne ne ralentit pas chaque commande de `timeout` s.
  - Au plus `webhook_queue_max` événements gardés (les plus anciens sautent) et `webhook_retention` jours.
  - Chaque événement a un identifiant `delivery` (corps et en-tête `X-Todo-Delivery`) identique à chaque nouvel essai : le
    récepteur s'en sert pour ignorer un doublon. `X-Todo-Attempt` donne le numéro de la tentative.
  - `webhook_secret` : en-tête `X-Todo-Signature: sha256=<HMAC-SHA256 du corps>`, que le récepteur recalcule pour vérifier l'origine.
"""
import contextlib
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

try:
    import fcntl
except ImportError:                      # plateforme sans fcntl : pas de verrou de file
    fcntl = None

from . import __version__, config, couleurs, journal, reglages

EVENEMENTS = ("add", "done", "undone", "start", "unstart", "edit", "postpone", "remove", "move")
MAX_TACHES = 20                          # au-delà : ni `tasks` dans le corps, ni une exécution par tâche
VIDAGE_AUTO = 50                         # événements renvoyés au plus par commande ordinaire (`hooks flush` : tous)
ATTENTE_MIN, ATTENTE_MAX = 30, 3600      # secondes
STATUTS_A_REESSAYER = {401, 403, 404, 408, 425, 429}


def avertir(nom, message):
    rouge, raz = couleurs._couleurs_erreur()
    print(f" {rouge}⚠️{raz} Hook {nom} : {message}", file=sys.stderr)
    journal.avertir("hook", hook=nom, detail=message)


# ---------------------------------------------------------------------------------------------- réglages
def url_configuree():
    return reglages.obtenir('hooks', 'webhook_url').strip()


def _url_valide(url):
    analyse = urllib.parse.urlsplit(url)
    if analyse.scheme not in ("http", "https") or not analyse.hostname:
        avertir("webhook_url", f"URL invalide « {url} » (attendu : http://hôte[:port]/chemin ou https://…)")
        return None
    return analyse


def evenements_voulus():
    """Événements demandés par `webhook_events` (None = tous) ; les noms inconnus sont signalés."""
    noms = [n for n in re.split(r"[,\s]+", reglages.obtenir('hooks', 'webhook_events').lower()) if n]
    if not noms:
        return None
    inconnus = [n for n in noms if n not in EVENEMENTS and n != "change"]
    if inconnus:
        avertir("webhook_events", f"événement(s) inconnu(s) : {', '.join(inconnus)} (attendus : {', '.join(EVENEMENTS)}, change)")
    return set(noms)


# ---------------------------------------------------------------------------------------------- envoi d'un événement
def envoyer(url, entree, tentative):
    """Un POST. Retourne ("ok" | "retry" | "drop", message)."""
    corps = json.dumps(entree["body"], ensure_ascii=False).encode("utf-8")
    en_tetes = {"Content-Type": "application/json", "User-Agent": f"todo-cli/{__version__}",
                "X-Todo-Event": entree["body"]["event"], "X-Todo-Delivery": entree["delivery"], "X-Todo-Attempt": str(tentative)}
    jeton = reglages.obtenir('hooks', 'webhook_token')
    if jeton:
        en_tetes["Authorization"] = f"Bearer {jeton}"
    secret = reglages.obtenir('hooks', 'webhook_secret')
    if secret:
        en_tetes["X-Todo-Signature"] = "sha256=" + hmac.new(secret.encode("utf-8"), corps, hashlib.sha256).hexdigest()
    hote = urllib.parse.urlsplit(url).netloc
    requete = urllib.request.Request(url, data=corps, headers=en_tetes, method="POST")
    try:
        with urllib.request.urlopen(requete, timeout=reglages.obtenir('hooks', 'timeout')) as reponse:
            reponse.read(1024)
        return "ok", ""
    except urllib.error.HTTPError as e:
        statut = "retry" if e.code >= 500 or e.code in STATUTS_A_REESSAYER else "drop"
        return statut, f"{hote} a répondu {e.code} {e.reason}"
    except (urllib.error.URLError, OSError, ValueError) as e:       # refus de connexion, DNS, délai dépassé…
        return "retry", f"envoi impossible vers {hote} : {getattr(e, 'reason', e)}"


# ---------------------------------------------------------------------------------------------- file d'attente
@contextlib.contextmanager
def _verrou():
    """Verrou exclusif sur la file (plusieurs `todo` peuvent tourner en même temps) ; None si on ne l'obtient pas en 5 s."""
    if fcntl is None:
        yield True
        return
    os.makedirs(os.path.dirname(config.WEBHOOK_QUEUE), exist_ok=True)
    try:
        fd = os.open(config.WEBHOOK_QUEUE + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        yield None
        return
    limite = time.monotonic() + 5
    obtenu = False
    while not obtenu:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            obtenu = True
        except BlockingIOError:
            if time.monotonic() >= limite:
                break
            time.sleep(0.05)
    try:
        yield True if obtenu else None
    finally:
        os.close(fd)


def charger():
    """{"fails", "next_retry", "entries": [...]} ; file vide si le fichier manque ou est illisible (l'événement courant passe avant tout)."""
    vide = {"fails": 0, "next_retry": 0.0, "entries": []}
    try:
        with open(config.WEBHOOK_QUEUE, encoding="utf-8") as f:
            donnees = json.load(f)
        entrees = [e for e in donnees["entries"] if isinstance(e, dict) and isinstance(e.get("body"), dict) and e.get("delivery")]
        return {"fails": int(donnees.get("fails", 0)), "next_retry": float(donnees.get("next_retry", 0)), "entries": entrees}
    except FileNotFoundError:
        return vide
    except (OSError, ValueError, KeyError, TypeError):
        try:
            os.replace(config.WEBHOOK_QUEUE, config.WEBHOOK_QUEUE + ".corrompu")
        except OSError:
            pass
        avertir("webhook_url", f"file d'attente illisible, mise de côté dans {config.WEBHOOK_QUEUE}.corrompu")
        return vide


def ecrire(file):
    """Atomique, 0600 ; fichier supprimé quand la file est vide."""
    if not file["entries"] and not file["fails"]:
        try:
            os.remove(config.WEBHOOK_QUEUE)
        except FileNotFoundError:
            pass
        return
    dossier = os.path.dirname(config.WEBHOOK_QUEUE)
    os.makedirs(dossier, exist_ok=True)
    tmp = f"{config.WEBHOOK_QUEUE}.{os.getpid()}.tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        json.dump({"version": 1, **file}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, config.WEBHOOK_QUEUE)


def _purger(file, maintenant):
    """Retire les événements trop vieux ou en trop ; retourne le nombre abandonné."""
    limite = maintenant - reglages.obtenir('hooks', 'webhook_retention') * 86400
    avant = len(file["entries"])
    file["entries"] = [e for e in file["entries"] if e.get("created", maintenant) >= limite]
    perimes = avant - len(file["entries"])
    maxi = reglages.obtenir('hooks', 'webhook_queue_max')
    trop = max(0, len(file["entries"]) - maxi)
    if trop:
        file["entries"] = file["entries"][trop:]
    if perimes or trop:
        avertir("webhook_url", f"{perimes + trop} événement(s) abandonné(s) de la file ({perimes} trop ancien(s), {trop} au-delà de "
                               f"webhook_queue_max={maxi})")
        journal.avertir("webhook_abandon", perimes=perimes, trop=trop)
    return perimes + trop


def _attente(echecs):
    return min(ATTENTE_MAX, ATTENTE_MIN * 2 ** max(0, echecs - 1))


def vider(file, url, maintenant, limite=None):
    """Renvoie les événements dans l'ordre jusqu'au premier échec passager. Retourne (envoyes, abandonnes) ; `file` est mis à jour."""
    envoyes = abandonnes = 0
    while file["entries"] and (limite is None or envoyes + abandonnes < limite):
        e = file["entries"][0]
        statut, message = envoyer(url, e, e.get("attempts", 0) + 1)
        if statut == "retry":
            e["attempts"] = e.get("attempts", 0) + 1
            e["last_error"] = message
            file["fails"] += 1
            file["next_retry"] = maintenant + _attente(file["fails"])
            avertir("webhook_url", f"{message} ; {len(file['entries'])} événement(s) en file d'attente, nouvel essai à la prochaine "
                                   f"modification après {time.strftime('%H:%M:%S', time.localtime(file['next_retry']))} ou par `todo hooks flush`")
            return envoyes, abandonnes
        file["entries"].pop(0)
        file["fails"], file["next_retry"] = 0, 0.0
        if statut == "ok":
            envoyes += 1
        else:
            abandonnes += 1
            avertir("webhook_url", f"{message} : événement {e['body']['event']} abandonné (refus définitif)")
    return envoyes, abandonnes


def _nouvelle_entree(evenement, ids, taches, projet):
    liste = taches() if len(ids) <= MAX_TACHES else []
    delivery = uuid.uuid4().hex
    corps = {"event": evenement, "project": projet, "count": len(ids), "ids": [t["id"] for t in liste] or ids,
             "version": __version__, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "delivery": delivery}
    if len(ids) <= MAX_TACHES:
        corps["tasks"] = liste
    return {"delivery": delivery, "body": corps, "created": time.time(), "attempts": 0, "last_error": ""}


def traiter(evenement, ids, taches, projet):
    """Appelé après une commande qui a modifié quelque chose : renvoie la file si c'est le moment, puis envoie l'événement
    (ou le met en file). Ne lève jamais d'erreur d'envoi : avertissement seulement."""
    url = url_configuree()
    if not url or _url_valide(url) is None:
        return
    voulus = evenements_voulus()
    voulu = voulus is None or evenement in voulus or "change" in voulus
    entree = _nouvelle_entree(evenement, ids, taches, projet) if voulu else None
    if not reglages.obtenir('hooks', 'webhook_retry'):
        if entree is not None:
            statut, message = envoyer(url, entree, 1)
            if statut != "ok":
                avertir("webhook_url", message)
        return
    with _verrou() as obtenu:
        if not obtenu:                                          # verrou introuvable : un essai sans file, comme avant
            if entree is not None:
                statut, message = envoyer(url, entree, 1)
                if statut != "ok":
                    avertir("webhook_url", message)
            return
        maintenant = time.time()
        file = charger()
        _purger(file, maintenant)
        if file["entries"] and maintenant >= file["next_retry"]:
            vider(file, url, maintenant, VIDAGE_AUTO)
        if entree is not None:
            if file["entries"]:                                 # file non vide (attente en cours ou limite atteinte) : l'ordre prime
                file["entries"].append(entree)
            else:
                statut, message = envoyer(url, entree, 1)
                if statut == "retry":
                    entree["attempts"], entree["last_error"] = 1, message
                    file["entries"].append(entree)
                    file["fails"] = 1
                    file["next_retry"] = maintenant + _attente(1)
                    avertir("webhook_url", f"{message} ; mis en file d'attente, nouvel essai à la prochaine modification après "
                                           f"{time.strftime('%H:%M:%S', time.localtime(file['next_retry']))} ou par `todo hooks flush`")
                elif statut == "drop":
                    avertir("webhook_url", f"{message} : événement {evenement} abandonné (refus définitif)")
        ecrire(file)


# ---------------------------------------------------------------------------------------------- commandes `todo hooks …`
def _date(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) if t else ""


def commande_file(fmt="text"):
    """`hooks queue` : état de la file du projet."""
    from .formats import imprimer_plain, tableau
    with _verrou():
        file = charger()
    entrees = file["entries"]
    if fmt == "json":
        print(json.dumps({"project": config.projet(), "webhook_url": url_configuree() or None, "pending": len(entrees),
                          "consecutive_failures": file["fails"], "next_retry": _date(file["next_retry"]) or None,
                          "entries": [{"delivery": e["delivery"], "event": e["body"]["event"], "created": _date(e.get("created")),
                                       "attempts": e.get("attempts", 0), "last_error": e.get("last_error", "")} for e in entrees]},
                         indent=2, ensure_ascii=False))
        return True
    lignes = [(e["delivery"][:8], e["body"]["event"], _date(e.get("created")), str(e.get("attempts", 0)), e.get("last_error", ""))
              for e in entrees]
    if fmt == "plain":
        imprimer_plain(lignes)
    elif fmt == "table":
        print(tableau(("LIVRAISON", "ÉVÉNEMENT", "CRÉÉ", "ESSAIS", "DERNIÈRE ERREUR"), lignes))
    elif not entrees:
        print(f" 📭 {couleurs.CLR_DIM}Aucun événement en attente dans le projet '{config.projet()}'.{couleurs.CLR_RESET}")
    else:
        print(f"\n {couleurs.CLR_CYAN}─── 📬 FILE DU WEBHOOK · {config.projet()} ───{couleurs.CLR_RESET}")
        print(f"  {len(entrees)} événement(s) en attente · {file['fails']} échec(s) consécutif(s)"
              + (f" · prochaine tentative automatique après {_date(file['next_retry'])}" if file["next_retry"] else ""))
        for ident, evt, cree, essais, erreur in lignes:
            print(f"  {couleurs.CLR_BOLD}{evt:<9}{couleurs.CLR_RESET} {couleurs.CLR_DIM}{ident}  {cree}  essais : {essais}{couleurs.CLR_RESET}"
                  + (f"\n            {couleurs.CLR_DEL}{erreur}{couleurs.CLR_RESET}" if erreur else ""))
        print(f"\n  {couleurs.CLR_DIM}`todo hooks flush` réessaie tout de suite ; `todo hooks clear` vide la file.{couleurs.CLR_RESET}\n")
    return True


def commande_vider(fmt="text"):
    """`hooks flush` : renvoie toute la file maintenant, sans attendre la prochaine tentative. Échec (code 1) s'il en reste."""
    url = url_configuree()
    if not url:
        journal.echec("webhook_not_configured")
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} aucun webhook configuré (réglage hooks.webhook_url).", file=sys.stderr)
        return False
    if _url_valide(url) is None:
        journal.echec("invalid_webhook_url")
        return False
    with _verrou() as obtenu:
        if not obtenu:
            journal.echec("webhook_queue_locked")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} la file est utilisée par une autre instance de todo ; réessayez.",
                  file=sys.stderr)
            return False
        file = charger()
        _purger(file, time.time())
        envoyes, abandonnes = vider(file, url, time.time())
        ecrire(file)
    restant = len(file["entries"])
    journal.informer("webhook_flush", sent=envoyes, dropped=abandonnes, pending=restant)
    if fmt == "json":
        print(json.dumps({"ok": restant == 0, "sent": envoyes, "dropped": abandonnes, "pending": restant}, indent=2))
    elif fmt != "plain":
        print(f" {'✅' if not restant else '⚠️ '} {envoyes} événement(s) envoyé(s), {abandonnes} abandonné(s), {restant} en attente.")
    return restant == 0


def commande_purger(fmt="text"):
    """`hooks clear` : supprime la file sans rien envoyer."""
    with _verrou():
        n = len(charger()["entries"])
        try:
            os.remove(config.WEBHOOK_QUEUE)
        except FileNotFoundError:
            pass
    if fmt == "json":
        print(json.dumps({"cleared": n}))
    elif fmt != "plain":
        print(f" 🗑️  {n} événement(s) supprimé(s) de la file du projet '{config.projet()}'.")
    return True
