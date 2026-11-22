"""Hooks : une commande de votre choix lancée après une modification (notification, synchro, journal perso…).

Réglages ([hooks] du fichier de configuration, ou variables TODO_HOOKS_ON_DONE…) :
  on_add, on_done, on_undone, on_start, on_unstart, on_edit, on_postpone, on_remove, on_move
      commande lancée pour CHAQUE tâche touchée par la commande correspondante ;
  on_change
      commande lancée après toute commande qui modifie quelque chose (en plus de la précédente), une seule fois
      si la commande ne vise aucune tâche (import, undo, archive…) ;
  timeout (10 s), enabled (true).

La commande est découpée comme le fait un shell (shlex) mais n'est PAS passée à un shell : pour des variables ou des
pipes, écrire `sh -c '…'`. Rien n'est jamais inséré dans la commande : les données passent par l'environnement
(TODO_EVENT, TODO_ID, TODO_TITLE, TODO_PROJECT, TODO_COUNT, TODO_IDS, TODO_VERSION) et par l'entrée standard (la tâche en
JSON, comme `show --format json`, ou `{"id", "titre"}` si elle n'existe plus ou a changé de projet) : un titre
malicieux ne peut donc pas injecter de commande.

Garde-fous : un hook ne change jamais le résultat de la commande (échec, délai dépassé et commande introuvable ne
produisent qu'un avertissement sur stderr et dans le journal) ; sa sortie standard est renvoyée sur stderr pour ne pas
polluer `--format json` ; un hook qui lance `todo` ne déclenche pas de hook (TODO_IN_HOOK) ; plus de 20 tâches touchées :
une seule exécution, avec TODO_COUNT et TODO_IDS.
"""
import dbm
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__, config, couleurs, journal, reglages
from .stockage import _normaliser_tache

EVENEMENTS = ("add", "done", "undone", "start", "unstart", "edit", "postpone", "remove", "move")
MAX_EXECUTIONS = 20


def _commande(reglage):
    texte = reglages.obtenir('hooks', reglage)
    if not texte:
        return None
    try:
        return shlex.split(texte)
    except ValueError as e:
        _avertir(reglage, f"commande invalide ({e})")
        return None


def _avertir(reglage, message):
    rouge, raz = couleurs._couleurs_erreur()
    print(f" {rouge}⚠️{raz} Hook {reglage} : {message}", file=sys.stderr)
    journal.avertir("hook", hook=reglage, detail=message)


def _tache(identifiant, titre):
    """(id complet, JSON de la tâche) depuis la base du projet courant ; à défaut (supprimée, déplacée), ce que le journal sait d'elle.

    Recherche silencieuse : un hook ne doit jamais écrire de message d'erreur ni noter d'échec à la place de la commande.
    """
    try:
        if os.path.exists(config.DB_NAME) or os.path.exists(config.DB_NAME + ".db"):
            with dbm.open(config.DB_NAME, 'r') as db:
                cles = [k for k in db.keys() if k.decode('utf-8', errors='replace').startswith(identifiant)]
                if len(cles) == 1:
                    t = _normaliser_tache(db[cles[0]])
                    t['id'] = cles[0].decode('utf-8', errors='replace')
                    return t['id'], t
    except Exception:
        pass
    return identifiant, {"id": identifiant, "titre": titre or ""}


def _lancer(reglage, commande, evenement, id_complet, titre, nombre, ids, projet, entree):
    env = dict(os.environ)
    env.update(TODO_EVENT=evenement, TODO_ID=id_complet or "", TODO_TITLE=titre or "", TODO_PROJECT=projet,
               TODO_COUNT=str(nombre), TODO_IDS=",".join(ids), TODO_IN_HOOK="1", TODO_HOOK=reglage)
    try:
        sys.stdout.flush()
        resultat = subprocess.run(commande, input=json.dumps(entree, ensure_ascii=False).encode(), env=env,
                                  stdout=sys.stderr, timeout=reglages.obtenir('hooks', 'timeout'))
        if resultat.returncode != 0:
            _avertir(reglage, f"« {commande[0]} » a retourné le code {resultat.returncode}")
    except subprocess.TimeoutExpired:
        _avertir(reglage, f"« {commande[0]} » interrompue après {reglages.obtenir('hooks', 'timeout')} s")
    except OSError as e:
        _avertir(reglage, f"impossible de lancer « {commande[0]} » : {e.strerror or e}")


def _evenements_webhook():
    """Événements demandés par `webhook_events` (None = tous) ; les noms inconnus sont signalés."""
    texte = reglages.obtenir('hooks', 'webhook_events')
    noms = [n for n in re.split(r"[,\s]+", texte.lower()) if n]
    if not noms:
        return None
    inconnus = [n for n in noms if n not in EVENEMENTS and n != "change"]
    if inconnus:
        _avertir("webhook_events", f"événement(s) inconnu(s) : {', '.join(inconnus)} (attendus : {', '.join(EVENEMENTS)}, change)")
    return set(noms)


def _webhook(evenement, ids, taches, projet):
    """Un POST JSON par commande vers `webhook_url` ; tout échec (réseau, HTTP ≥ 400, délai) est un simple avertissement."""
    url = reglages.obtenir('hooks', 'webhook_url').strip()
    if not url:
        return
    analyse = urllib.parse.urlsplit(url)
    if analyse.scheme not in ("http", "https") or not analyse.hostname:
        _avertir("webhook_url", f"URL invalide « {url} » (attendu : http://hôte[:port]/chemin ou https://…)")
        return
    voulus = _evenements_webhook()
    if voulus is not None and evenement not in voulus and "change" not in voulus:
        return
    liste = taches() if len(ids) <= MAX_EXECUTIONS else []
    corps = {"event": evenement, "project": projet, "count": len(ids), "ids": [t["id"] for t in liste] or ids,
             "version": __version__, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if len(ids) <= MAX_EXECUTIONS:
        corps["tasks"] = liste
    en_tetes = {"Content-Type": "application/json", "User-Agent": f"todo-cli/{__version__}", "X-Todo-Event": evenement}
    jeton = reglages.obtenir('hooks', 'webhook_token')
    if jeton:
        en_tetes["Authorization"] = f"Bearer {jeton}"
    delai = reglages.obtenir('hooks', 'timeout')
    requete = urllib.request.Request(url, data=json.dumps(corps, ensure_ascii=False).encode("utf-8"), headers=en_tetes, method="POST")
    try:
        with urllib.request.urlopen(requete, timeout=delai) as reponse:
            reponse.read(1024)
    except urllib.error.HTTPError as e:
        _avertir("webhook_url", f"{analyse.netloc} a répondu {e.code} {e.reason}")
    except (urllib.error.URLError, OSError, ValueError) as e:       # refus de connexion, DNS, délai dépassé…
        cause = getattr(e, "reason", e)
        _avertir("webhook_url", f"envoi impossible vers {analyse.netloc} : {cause}")


def declencher():
    """Lance les hooks de la commande qui vient de s'exécuter, si elle a modifié quelque chose. Ne lève jamais."""
    try:
        bilan = journal.bilan()
        if (not bilan["modifie"] or os.environ.get("TODO_IN_HOOK") or not reglages.obtenir('hooks', 'enabled')
                or not bilan["commande"]):
            return
        if bilan["commande"].startswith("view_"):          # les vues sont des préférences, pas des tâches
            return
        evenement, ids, titres, complets = bilan["commande"], bilan["ids"], bilan["titres"], bilan["ids_complets"]
        if len(complets) == len(ids):                      # identifiants complets quand le journal les a (tâche supprimée comprise)
            ids = complets
        specifique = _commande("on_" + evenement) if evenement in EVENEMENTS and ids else None
        general = _commande("on_change")
        if not specifique and not general and not reglages.obtenir('hooks', 'webhook_url').strip():
            return
        projet = config.projet()
        a_lancer = [(nom, cmd) for nom, cmd in (("on_" + evenement, specifique), ("on_change", general)) if cmd]
        alignes = len(titres) == len(ids)
        resolues = None

        def taches():
            nonlocal resolues
            if resolues is None:
                resolues = [_tache(court, titres[i] if alignes else "") for i, court in enumerate(ids)]
            return resolues

        if not ids:
            for nom, cmd in a_lancer:
                _lancer(nom, cmd, evenement, "", "", 0, [], projet, {"event": evenement})
        elif len(ids) > MAX_EXECUTIONS:
            for nom, cmd in a_lancer:
                _lancer(nom, cmd, evenement, "", "", len(ids), ids, projet, {"event": evenement, "ids": ids})
        else:
            for complet, tache in taches():
                for nom, cmd in a_lancer:
                    _lancer(nom, cmd, evenement, complet, tache.get('titre', ""), len(ids), ids, projet, tache)
        _webhook(evenement, ids, lambda: [t for _, t in taches()], projet)
    except Exception:
        pass
