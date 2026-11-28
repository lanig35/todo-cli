"""Commande `doctor` : diagnostic de la base, du stockage et de la configuration, et réparations sûres (`--fix`).

Le diagnostic lit les entrées **brutes** de la base : la lecture normale (`stockage._normaliser_tache`) corrige en silence
ce qu'elle peut (priorité invalide -> medium, récurrence invalide -> aucune…), ce qui cacherait justement les anomalies.

Chaque constat a un niveau (`erreur`, `avertissement`, `info`), un code stable (voir le README), une portée (projet ou
`environnement`), éventuellement l'identifiant de la tâche, et `reparable` s'il peut être corrigé par `--fix`.

`--fix` ne fait que des réparations qui ne perdent aucune information utile (valeur invalide déjà ignorée à la lecture,
dépendance vers une tâche qui n'existe plus…). Elle prend le verrou exclusif, sauvegarde avant et après (`undo` revient
en arrière) et ne touche jamais aux entrées illisibles, aux dates, aux statuts ni aux cycles de dépendances : ceux-là
se corrigent à la main (`task edit`, `data import --update`).
"""
import contextlib
import dbm
import difflib
import glob
import io
import json
import os
import shlex
import shutil
import sys
import urllib.parse
from datetime import datetime

from . import config, couleurs, journal, reglages, vues
from .config import PRIORITES, STATUT_A_FAIRE, STATUT_TERMINE
from .dates import _parse_date, _parser_recurrence, lire_instant
from .echange import _DATE, _DATE_HEURE
from .formats import imprimer_plain, tableau
from .sauvegardes import _noms_sauvegardes, sauvegarder_base
from .stockage import _normaliser_tache

NIVEAUX = ("erreur", "avertissement", "info")
ESPACE_MINIMAL = 50 * 1024 * 1024          # en dessous, avertissement : les sauvegardes copient la base à chaque modification
_VARIABLES_PARTICULIERES = {"TODO_NO_REMIND", "TODO_CONFIG", "TODO_IN_HOOK"}


def constat(niveau, code, message, portee, projet=None, id=None, titre=None, reparable=False):
    return {"niveau": niveau, "code": code, "portee": portee, "projet": projet, "id": id, "titre": titre,
            "message": message, "reparable": reparable}


# ---------------------------------------------------------------------------------------------- tâches (entrées brutes)
def corrections(r, ids_connus):
    """(copie corrigée, [(code, message)]) d'une tâche brute : uniquement les réparations sans perte d'information utile.

    `ids_connus` : identifiants de toutes les tâches (liste et archive) ; une dépendance qui n'y figure pas ne bloque plus personne.
    """
    nouveau, changements = dict(r), []

    priorite = r.get("priorite")
    if priorite not in (None, "") and str(priorite).lower() not in PRIORITES:
        nouveau["priorite"] = "medium"
        changements.append(("invalid_priority", f"priorité invalide {priorite!r} : remplacée par medium (valeur déjà utilisée à la lecture)"))

    demarree = r.get("demarree")
    if demarree and not (isinstance(demarree, str) and lire_instant(demarree)):
        nouveau["demarree"] = None
        changements.append(("invalid_started", f"instant de démarrage invalide {demarree!r} : retiré (déjà ignoré à la lecture)"))

    if (r.get("statut") or STATUT_A_FAIRE) == STATUT_A_FAIRE and r.get("date_terminee"):
        nouveau["date_terminee"] = None
        changements.append(("todo_with_done_date", f"tâche à faire avec une date de fin ({r['date_terminee']}) : date retirée"))

    tags = r.get("tags")
    if tags is not None and not (isinstance(tags, list) and all(isinstance(x, str) for x in tags)):
        nouveau["tags"] = [x for x in tags if isinstance(x, str)] if isinstance(tags, list) else []
        changements.append(("invalid_tags", "tags : liste de chaînes attendue ; éléments invalides retirés"))

    apres = r.get("apres")
    if apres is not None:
        valides = [x for x in apres if isinstance(x, str) and x] if isinstance(apres, list) else []
        if valides != apres:
            nouveau["apres"] = valides
            changements.append(("invalid_dependencies", "apres : liste d'identifiants attendue ; éléments invalides retirés"))
        absentes = [x for x in valides if x not in ids_connus]
        if absentes:
            nouveau["apres"] = [x for x in valides if x in ids_connus]
            changements.append(("missing_dependency", "dépend de " + ", ".join(x[:8] for x in absentes)
                                + " qui n'existe plus (ne bloque plus) : dépendance retirée"))
    return nouveau, changements


def verifications(r, archive):
    """[(niveau, code, message)] des anomalies d'une tâche brute que `--fix` ne corrige pas."""
    res = []
    titre = r.get("titre")
    if not isinstance(titre, str) or not titre.strip():
        res.append(("avertissement", "missing_title", "titre absent ou vide (affiché « (sans titre) »)"))
    statut = r.get("statut") or STATUT_A_FAIRE
    if statut not in (STATUT_A_FAIRE, STATUT_TERMINE):
        res.append(("erreur", "invalid_status", f"statut inconnu : {statut!r} (« {STATUT_A_FAIRE} » ou « {STATUT_TERMINE} » attendu)"))
    echeance = r.get("date_echeance")
    if echeance and not (isinstance(echeance, str) and _DATE.fullmatch(echeance) and _parse_date(echeance)):
        res.append(("avertissement", "invalid_due", f"échéance invalide : {echeance!r} (AAAA-MM-JJ attendu) ; `task edit` la corrige"))
    recurrence = r.get("recurrence")
    if recurrence and _parser_recurrence(str(recurrence)) is None:
        res.append(("avertissement", "invalid_recurrence", f"récurrence invalide : {recurrence!r} (ignorée à la lecture)"))
    elif recurrence and not echeance:
        res.append(("avertissement", "recurrence_without_due", "tâche récurrente sans échéance : aucune occurrence ne sera calculée"))
    for champ in ("date_creation", "date_terminee", "date_archivage"):
        valeur = r.get(champ)
        if valeur and not (isinstance(valeur, str) and _DATE_HEURE.fullmatch(valeur)):
            res.append(("avertissement", "invalid_dates", f"{champ} invalide : {valeur!r}"))
    if statut == STATUT_TERMINE and not r.get("date_terminee"):
        res.append(("info", "done_without_date", "tâche terminée sans date de fin (anciennes versions)"))
    if archive and statut != STATUT_TERMINE:
        res.append(("avertissement", "archived_not_done", "tâche archivée qui n'est pas terminée"))
    return res


def _cycles(graphe):
    """Un identifiant par cycle de dépendances (graphe {id: [ids]}) : ceux qui s'attendent eux-mêmes, directement ou non."""
    etat, trouves = {}, []
    for depart in graphe:
        if depart in etat:
            continue
        pile = [(depart, iter(graphe.get(depart, ())))]
        etat[depart] = 1
        while pile:
            noeud, suivants = pile[-1]
            for s in suivants:
                if s not in graphe:
                    continue
                if etat.get(s) == 1:
                    trouves.append(s)
                elif s not in etat:
                    etat[s] = 1
                    pile.append((s, iter(graphe[s])))
                    break
            else:
                etat[noeud] = 2
                pile.pop()
    return list(dict.fromkeys(trouves))


def _lire_brutes(chemin):
    """({id: octets}, erreur) d'une base DBM ; ({}, None) si elle n'existe pas. Ne crée jamais rien."""
    if not glob.glob(f"{chemin}*"):
        return {}, None
    try:
        with dbm.open(chemin, "r") as db:
            return {k.decode("utf-8", errors="replace"): db[k] for k in list(db.keys())}, None
    except (*dbm.error, OSError) as e:
        return {}, str(e) or type(e).__name__


def _decoder(octets):
    """Objet JSON d'une entrée brute, ou None si elle est illisible."""
    try:
        r = json.loads(octets.decode("utf-8"))
    except ValueError:
        return None
    return r if isinstance(r, dict) else None


def controler_taches(brutes, archivees, projet, reparer=False, simuler=False):
    """(constats, réparations) des tâches de la liste (`brutes`) et de l'archive (`archivees`) d'un projet.

    Avec `reparer` et sans `simuler`, les corrections sont écrites par `_ecrire` (voir `diagnostiquer`) : ici on renvoie
    seulement, pour chaque entrée à corriger, la nouvelle valeur (dans `reparations`).
    """
    constats, reparations = [], []
    ids_connus = set(brutes) | set(archivees)
    graphe = {}

    def ajouter(niveau, code, message, id_, titre, reparable=False):
        constats.append(constat(niveau, code, f"{message}", projet, projet, id_, titre, reparable))

    for archive, source in ((False, brutes), (True, archivees)):
        for id_, octets in sorted(source.items()):
            r = _decoder(octets)
            if r is None:
                ajouter("erreur", "unreadable_entry", "entrée illisible (JSON invalide) : elle est ignorée par todo ; `data import --update` ou `undo` peuvent la remplacer", id_, None)
                continue
            titre = r.get("titre") if isinstance(r.get("titre"), str) else None
            for niveau, code, message in verifications(r, archive):
                ajouter(niveau, code, message, id_, titre)
            nouveau, changements = corrections(r, ids_connus)
            for code, message in changements:
                niveau = "info" if code == "missing_dependency" else "avertissement"
                ajouter(niveau, code, message, id_, titre, reparable=True)
            if changements:
                reparations.append((archive, id_, nouveau, [c for c, _ in changements], titre))
            if not archive:
                apres = nouveau.get("apres") or []
                graphe[id_] = [x for x in apres if isinstance(x, str)]
                if id_ in graphe[id_]:
                    ajouter("erreur", "self_dependency", "la tâche dépend d'elle-même (`task edit --after none` la corrige)", id_, titre)
                suivante = r.get("suivante")
                if suivante and suivante not in ids_connus:
                    ajouter("info", "missing_next", f"occurrence suivante {str(suivante)[:8]} introuvable (supprimée ou purgée)", id_, titre)
    graphe_sans_boucle = {k: [x for x in v if x != k] for k, v in graphe.items()}
    for id_ in _cycles(graphe_sans_boucle):
        r = _decoder(brutes[id_]) or {}
        ajouter("erreur", "dependency_cycle", "dépendance circulaire : cette tâche s'attend elle-même par d'autres tâches", id_,
                r.get("titre") if isinstance(r.get("titre"), str) else None)
    for id_ in sorted(set(brutes) & set(archivees)):
        r = _decoder(brutes[id_]) or {}
        ajouter("avertissement", "duplicate_in_archive", "présente à la fois dans la liste et dans l'archive", id_,
                r.get("titre") if isinstance(r.get("titre"), str) else None)
    return constats, reparations


# ---------------------------------------------------------------------------------------------- un projet
def _moteur(chemin):
    """Nom du moteur DBM d'une base existante ('' si elle n'existe pas ; None si le format est inconnu)."""
    if not glob.glob(f"{chemin}*"):
        return ""
    return dbm.whichdb(chemin) or None


def _pieces(brutes, archivees, projet):
    """Constats des pièces jointes (copies et liens manquants ou modifiés, fichiers orphelins) du projet courant de `config`."""
    from . import pieces_jointes
    taches = []
    for source in (brutes, archivees):
        for id_, octets in source.items():
            try:
                t = _normaliser_tache(octets)
            except ValueError:
                continue
            t["id"] = id_
            taches.append(t)
    constats = []
    for t in sorted(taches, key=lambda t: t["id"]):
        for numero, p in enumerate(t["pieces_jointes"], 1):
            etat, detail = pieces_jointes._etat(t, p)
            if etat == "manquant":
                constats.append(constat("erreur", "attachment_missing", f"pièce {numero} « {p['nom']} » : {detail}", projet, projet, t["id"], t["titre"]))
            elif etat == "modifie":
                constats.append(constat("avertissement", "attachment_modified", f"pièce {numero} « {p['nom']} » : {detail}", projet, projet, t["id"], t["titre"]))
            elif etat == "en_corbeille":
                constats.append(constat("info", "attachment_in_trash", f"pièce {numero} « {p['nom']} » : {detail}", projet, projet, t["id"], t["titre"]))
    for id_, nom, chemin in pieces_jointes._orphelins(taches):
        constats.append(constat("avertissement", "attachment_orphan", f"fichier {chemin} : aucune pièce ne le référence (`attachment gc`, ou à supprimer à la main)", projet, projet, id_, None))
    return constats


def analyser_projet(nom, avec_pieces=True):
    """(constats, statistiques, réparations) d'un projet. Le projet courant de `config` doit être `nom`."""
    constats = []
    brutes, e1 = _lire_brutes(config.DB_NAME)
    archivees, e2 = _lire_brutes(config.ARCHIVE_NAME)
    for fichier, erreur in (("base", e1), ("archive", e2)):
        if erreur:
            constats.append(constat("erreur", "unknown_db_format", f"{fichier} illisible : {erreur}", nom, nom))
    moteur = {}
    for fichier, chemin in (("base", config.DB_NAME), ("archive", config.ARCHIVE_NAME)):
        m = _moteur(chemin)
        moteur[fichier] = m
        if m is None and not (e1 if fichier == "base" else e2):
            constats.append(constat("erreur", "unknown_db_format", f"{fichier} : format de base DBM non reconnu sur cette machine", nom, nom))
        elif m == "dbm.dumb":
            constats.append(constat("info", "dbm_dumb", f"{fichier} : moteur dbm.dumb (lent, peu robuste) : installer le module gdbm ou ndbm de Python rend la base plus sûre", nom, nom))
    c, reparations = controler_taches(brutes, archivees, nom)
    constats += c
    if avec_pieces:
        constats += _pieces(brutes, archivees, nom)
    try:
        vues.charger()
    except vues.ErreurVue as e:
        constats.append(constat("erreur", "views_file_invalid", str(e), nom, nom))
    constats += _file_webhook(nom)
    if (brutes or archivees) and not _noms_sauvegardes():
        constats.append(constat("info", "no_backup", "aucune sauvegarde : `undo` et `restore` n'ont rien à restaurer (la prochaine modification en crée une)", nom, nom))
    stats = {"projet": nom, "taches": len(brutes), "archive": len(archivees), "moteur": moteur["base"] or moteur["archive"] or None,
             "sauvegardes": len(_noms_sauvegardes())}
    return constats, stats, reparations


def _file_webhook(projet):
    """File d'attente du webhook, lue sans la modifier (`webhook.charger` met de côté un fichier illisible)."""
    try:
        with open(config.WEBHOOK_QUEUE, encoding="utf-8") as f:
            donnees = json.load(f)
        entrees = donnees["entries"]
        if not isinstance(entrees, list):
            raise ValueError("structure inattendue")
    except FileNotFoundError:
        return []
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [constat("avertissement", "webhook_queue_unreadable", f"file du webhook illisible ({e}) ; elle sera mise de côté au prochain envoi", projet, projet)]
    if entrees:
        return [constat("info", "webhook_queue_pending", f"{len(entrees)} événement(s) du webhook en attente d'envoi (`hooks flush` les renvoie)", projet, projet)]
    return []


# ---------------------------------------------------------------------------------------------- environnement
def analyser_environnement():
    """Constats communs à tous les projets : stockage, configuration, variables d'environnement, hooks."""
    c = []
    dossier = config.dossier()
    if os.path.isdir(dossier):
        mode = os.stat(dossier).st_mode & 0o777
        if mode & 0o022:
            c.append(constat("avertissement", "storage_group_writable", f"le dossier de stockage {dossier} est modifiable par d'autres comptes (droits {mode:o}) ; `chmod go-w` le protège", "environnement"))
        try:
            libre = shutil.disk_usage(dossier).free
            if libre < ESPACE_MINIMAL:
                c.append(constat("avertissement", "low_disk_space", f"espace libre faible : {libre // (1024 * 1024)} Mo (une sauvegarde est copiée à chaque modification)", "environnement"))
        except OSError:
            pass
        sous = os.path.join(dossier, config._SOUS_DOSSIER)
        if os.path.isdir(sous):
            for nom in sorted(os.listdir(sous)):
                if os.path.isdir(os.path.join(sous, nom)) and not config._MOTIF_PROJET.match(nom):
                    c.append(constat("avertissement", "invalid_project_dir", f"dossier {os.path.join(sous, nom)} : nom de projet invalide, ignoré par todo", "environnement"))

    # Configuration : les avertissements de lecture (section ou clé inconnue, valeur invalide) sont déjà collectés par `reglages`
    with contextlib.redirect_stderr(io.StringIO()):
        reglages._charger_fichier()
        for r in reglages.REGLAGES:
            reglages.obtenir_avec_origine(r.section, r.cle)
    for message in dict.fromkeys(reglages.AVERTISSEMENTS):
        c.append(constat("avertissement", "config_warning", message, "environnement"))

    connues = {reglages.nom_variable(r.section, r.cle) for r in reglages.REGLAGES} | _VARIABLES_PARTICULIERES
    for nom in sorted(k for k in os.environ if k.startswith("TODO_") and k not in connues):
        proche = difflib.get_close_matches(nom, connues, n=1)
        c.append(constat("avertissement", "unknown_env_var", f"variable {nom} inconnue (ignorée)" + (f" ; vouliez-vous dire {proche[0]} ?" if proche else ""), "environnement"))

    for r in reglages.REGLAGES:
        if r.section == "hooks" and (r.cle.startswith("on_") or r.cle.startswith("before_")):
            commande = reglages.obtenir("hooks", r.cle)
            if commande:
                if not _commande_trouvee(commande):
                    c.append(constat("avertissement", "hook_command_not_found", f"[hooks] {r.cle} : commande introuvable ou non exécutable : {commande}", "environnement"))
    url = reglages.obtenir("hooks", "webhook_url")
    if url and not _url_http(url):
        c.append(constat("avertissement", "invalid_webhook_url", f"[hooks] webhook_url : adresse invalide : {url}", "environnement"))
    return c


def _url_http(url):
    """Adresse http(s) avec un hôte (sans l'avertissement que `webhook._url_valide` affiche)."""
    analyse = urllib.parse.urlsplit(url)
    return analyse.scheme in ("http", "https") and bool(analyse.hostname)


def _commande_trouvee(commande):
    try:
        mots = shlex.split(commande)
    except ValueError:
        return False
    if not mots:
        return False
    programme = mots[0]
    if os.sep in programme:
        return os.path.isfile(programme) and os.access(programme, os.X_OK)
    return shutil.which(programme) is not None


# ---------------------------------------------------------------------------------------------- réparation
def _ecrire(nom_base, reparations):
    """Écrit les entrées corrigées dans une base DBM déjà existante (clé -> JSON, comme le reste du programme)."""
    if not reparations:
        return
    with dbm.open(nom_base, "w") as db:
        for id_, nouveau in reparations:
            db[id_] = json.dumps(nouveau)


def reparer(reparations):
    """Applique les réparations [(archive, id, nouvelle valeur, codes, titre)] : sauvegarde avant et après (`undo` annule)."""
    sauvegarder_base()
    _ecrire(config.DB_NAME, [(r[1], r[2]) for r in reparations if not r[0]])
    _ecrire(config.ARCHIVE_NAME, [(r[1], r[2]) for r in reparations if r[0]])
    sauvegarder_base()


# ---------------------------------------------------------------------------------------------- commande
def _bilan(constats):
    b = {n: sum(1 for c in constats if c["niveau"] == n) for n in NIVEAUX}
    return {"erreurs": b["erreur"], "avertissements": b["avertissement"], "infos": b["info"],
            "reparables": sum(1 for c in constats if c["reparable"])}


def _afficher_texte(constats, stats, environnement, bilan, reparations_faites, simule):
    icones = {"erreur": f"{couleurs.CLR_DEL}❌{couleurs.CLR_RESET}", "avertissement": "⚠️ ", "info": f"{couleurs.CLR_DIM}ℹ️ {couleurs.CLR_RESET}"}
    print(f" 🩺 {couleurs.CLR_BOLD}Diagnostic de todo-cli{couleurs.CLR_RESET} {couleurs.CLR_DIM}(stockage : {config.dossier()}){couleurs.CLR_RESET}")
    for s in stats:
        moteur = f", moteur {s['moteur']}" if s["moteur"] else ""
        print(f"\n {couleurs.CLR_BOLD}── projet {s['projet']}{couleurs.CLR_RESET} {couleurs.CLR_DIM}({s['taches']} tâche(s), {s['archive']} archivée(s){moteur}){couleurs.CLR_RESET}")
        propres = [c for c in constats if c["projet"] == s["projet"]]
        if not propres:
            print(f"   {couleurs.CLR_DONE}✔{couleurs.CLR_RESET} rien à signaler")
        for c in propres:
            _ligne(icones, c)
    if environnement is not None:
        print(f"\n {couleurs.CLR_BOLD}── environnement{couleurs.CLR_RESET}")
        if not environnement:
            print(f"   {couleurs.CLR_DONE}✔{couleurs.CLR_RESET} rien à signaler")
        for c in environnement:
            _ligne(icones, c)
    if reparations_faites is not None:
        print(f"\n {couleurs.CLR_BOLD}── réparations{couleurs.CLR_RESET}{' (simulation : rien n’a été modifié)' if simule else ''}")
        for id_, titre, codes in reparations_faites:
            print(f"   🔧 {id_[:8]} {couleurs.CLR_DIM}{titre or ''}{couleurs.CLR_RESET} : {', '.join(codes)}")
    print()
    morceaux = f"{bilan['erreurs']} erreur(s) · {bilan['avertissements']} avertissement(s) · {bilan['infos']} info(s)"
    if bilan["erreurs"]:
        print(f" {couleurs.CLR_DEL}✘{couleurs.CLR_RESET} {morceaux}.")
    elif bilan["avertissements"]:
        print(f" ⚠️  {morceaux}.")
    else:
        print(f" {couleurs.CLR_DONE}✔{couleurs.CLR_RESET} Aucun problème ({morceaux}).")
    if bilan["reparables"] and reparations_faites is None:
        print(f" {couleurs.CLR_DIM}{bilan['reparables']} constat(s) réparable(s) : `todo admin doctor --fix` (sauvegarde avant, `todo undo` annule).{couleurs.CLR_RESET}")


def _ligne(icones, c):
    ref = f" {couleurs.CLR_DIM}[{c['id'][:8]}{' ' + c['titre'] if c['titre'] else ''}]{couleurs.CLR_RESET}" if c["id"] else ""
    marque = f" {couleurs.CLR_DIM}(réparable){couleurs.CLR_RESET}" if c["reparable"] else ""
    print(f"   {icones[c['niveau']]} {couleurs.CLR_DIM}{c['code']}{couleurs.CLR_RESET}{ref} {c['message']}{marque}")


def diagnostiquer(projets, reparation=False, simuler=False, oui=False, strict=False, avec_pieces=True, fmt="text"):
    """Diagnostic de `projets` (liste de noms) et de l'environnement ; retourne True s'il n'y a rien de bloquant.

    Bloquant : une erreur, ou un avertissement avec `strict`. Avec `reparation`, un seul projet est accepté (verrou exclusif
    pris par l'appelant) ; la réparation est précédée d'une confirmation sauf `oui` ou `simuler`.
    """
    origine = (config.projet(), config.origine_projet())
    constats, stats, reparations = [], [], {}
    try:
        for nom in projets:
            config.definir_projet(nom, "doctor")
            c, s, r = analyser_projet(nom, avec_pieces)
            constats += c
            stats.append(s)
            reparations[nom] = r
        environnement = analyser_environnement()

        faites = None
        if reparation:
            nom = projets[0]
            a_faire = reparations[nom]
            faites = [(r[1], r[4], r[3]) for r in a_faire]
            if a_faire and not simuler:
                if not oui and fmt in ("text", "table"):
                    try:
                        reponse = input(f" {couleurs.CLR_DEL}⚠️{couleurs.CLR_RESET} Réparer {len(a_faire)} tâche(s) du projet '{nom}' "
                                        f"(sauvegarde avant et après) ? (y/N) : ").strip().lower()
                    except EOFError:
                        reponse = ""
                    if reponse != "y":
                        print(" ❌ Opération annulée.")
                        faites = None
                        a_faire = []
                elif not oui:
                    journal.echec("confirmation_required")
                    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --fix demande une confirmation : ajoutez --yes (ou --dry-run).", file=sys.stderr)
                    return False
                if a_faire:
                    config.definir_projet(nom, "doctor")
                    reparer(a_faire)
                    journal.noter(modifie=True, repaired=len(a_faire))
                    constats, s, _ = analyser_projet(nom, avec_pieces)
                    stats = [s]
            reparation_simulee = simuler
        else:
            reparation_simulee = False
    finally:
        config.definir_projet(*origine)

    bilan = _bilan(constats + environnement)
    bloquant = bilan["erreurs"] + (bilan["avertissements"] if strict else 0)
    journal.noter(problems=bilan["erreurs"] + bilan["avertissements"])
    if bloquant:
        journal.echec("doctor_problems", erreurs=bilan["erreurs"], avertissements=bilan["avertissements"])
    toutes = constats + environnement

    if fmt == "json":
        document = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "stockage": config.dossier(), "ok": not bloquant, "bilan": bilan,
                    "projets": stats, "constats": toutes}
        if faites is not None:
            document["reparations"] = {"simulation": reparation_simulee, "taches": [{"id": i, "titre": t, "codes": codes} for i, t, codes in faites]}
        print(json.dumps(document, indent=2, ensure_ascii=False))
    elif fmt == "plain":
        imprimer_plain([(c["niveau"], c["code"], c["portee"], c["id"] or "", c["message"]) for c in toutes])
    elif fmt == "table":
        if toutes:
            print(tableau(("NIVEAU", "CODE", "PORTÉE", "ID", "MESSAGE"), [(c["niveau"], c["code"], c["portee"], (c["id"] or "")[:8], c["message"]) for c in toutes]))
    else:
        _afficher_texte(constats, stats, environnement, bilan, faites, reparation_simulee)
    return not bloquant

