"""Archivage : ranger les tâches terminées hors de la liste courante, les consulter, les récupérer.

Les tâches archivées vivent dans une base DBM séparée (`todo_archive`, même dossier que la base
principale) : `list`, `agenda` et `stats` ne les voient pas. Elles sont sauvegardées et restaurées
avec la base principale.
"""
import dbm
import json
import re
import sys
from datetime import datetime
from . import couleurs, journal
from .filtres import garder
from .affichage import CHAMPS_RECHERCHE, _afficher_texte, correspond_recherche
from .config import PRIORITES, STATUT_A_FAIRE, STATUT_TERMINE
from . import config
from .dates import _decaler, _parse_date
from .formats import sortie_taches
from . import pieces_jointes
from .sauvegardes import sauvegarder_base
from .stockage import _afficher_bilan_lot, _archive_existe, _base_existe, _charger_taches, _lire_archive, _normaliser_tache, _resoudre_ids

_MOTIF_ANCIENNETE = re.compile(r"^(\d+)([dwmy])$")
MSG_FORMAT_ANCIENNETE = "un entier suivi de d, w, m ou y (ex. 30d, 2w, 6m, 1y)"


def _parser_anciennete(texte):
    """'30d' -> (30, 'd'), ou None si le format est invalide ou nul."""
    m = _MOTIF_ANCIENNETE.match(texte.strip().lower())
    if not m or int(m.group(1)) == 0:
        return None
    return int(m.group(1)), m.group(2)


def _sans_id(t):
    """Copie de la tâche prête à être stockée (la clé DBM est l'identifiant)."""
    return {k: v for k, v in t.items() if k != 'id'}


def archiver_taches(ids=None, anciennete=None, tags=None, silencieux=False, bilan=None):
    """Déplace des tâches terminées vers l'archive.

    ids        : préfixes d'identifiants à archiver (ils doivent désigner des tâches terminées).
    anciennete : (n, unité) ; ne retient que les tâches terminées depuis au moins cette durée.
    tags       : (sans ids) ne retient que les tâches terminées portant TOUS ces tags ; les tâches à faire
                 qui les portent restent en place (signalé).
    Sans ids, toutes les tâches terminées (éventuellement filtrées par ancienneté et tags) sont archivées.
    silencieux : n'affiche rien ; bilan : dict rempli avec `archivees` (nombre de tâches déplacées).
    Retourne True si aucun identifiant n'a posé problème.

    Chaque tâche est écrite dans l'archive AVANT d'être retirée de la base principale : une
    interruption laisse un doublon récupérable plutôt qu'une tâche perdue.
    """
    if not _base_existe():
        if not silencieux:
            print(f" 📋 {couleurs.CLR_DIM}La liste est vide, rien à archiver.{couleurs.CLR_RESET}")
        return not ids

    maintenant = datetime.now()
    horodatage = maintenant.strftime("%Y-%m-%d %H:%M")
    nb_ok, echecs, sans_date, restent_a_faire = 0, 0, 0, 0
    with dbm.open(config.ARCHIVE_NAME, 'c') as archive, dbm.open(config.DB_NAME, 'w') as db:
        if ids:
            cles, echecs = _resoudre_ids(db, ids)
            a_traiter = []
            for cle in cles:
                try:
                    t = _normaliser_tache(db[cle])
                except ValueError:
                    journal.echec("corrupted_entry")
                    print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Cette entrée est corrompue et ne peut pas être archivée.")
                    echecs += 1
                    continue
                if t['statut'] != STATUT_TERMINE:
                    journal.echec("not_done")
                    print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} La tâche '{t['titre']}' n'est pas terminée : "
                          f"seules les tâches terminées s'archivent.")
                    echecs += 1
                    continue
                a_traiter.append((cle, t))
        else:
            limite = _decaler(maintenant.date(), -anciennete[0], anciennete[1]) if anciennete else None
            a_traiter = []
            for t in _charger_taches(db):
                if tags and not all(x in t['tags'] for x in tags):
                    continue
                if t['statut'] != STATUT_TERMINE:
                    restent_a_faire += 1 if t['statut'] == STATUT_A_FAIRE else 0
                    continue
                if limite is not None:
                    date_fin = _parse_date((t['date_terminee'] or "")[:10])
                    if date_fin is None:
                        sans_date += 1  # ancienne tâche sans date de complétion : âge inconnu
                        continue
                    if date_fin > limite:
                        continue
                a_traiter.append((t['id'].encode('utf-8'), t))

        for cle, t in a_traiter:
            archive[cle] = json.dumps({**_sans_id(t), 'date_archivage': horodatage})
            del db[cle]
            nb_ok += 1
            journal.noter(ids=[cle], titres=[t['titre']], modifie=True)
            if ids and not silencieux:
                print(f" 📦 Tâche archivée : '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}'.")

    if bilan is not None:
        bilan['archivees'] = nb_ok
    if not ids and not silencieux:
        if nb_ok:
            print(f" 📦 {couleurs.CLR_DONE}{nb_ok} tâche(s) archivée(s).{couleurs.CLR_RESET}")
        else:
            qualif = f" depuis au moins {anciennete[0]}{anciennete[1]}" if anciennete else ""
            marque = f" portant {'+'.join('#' + x for x in tags)}" if tags else ""
            print(f" {couleurs.CLR_DIM}Aucune tâche terminée{qualif}{marque} à archiver.{couleurs.CLR_RESET}")
        if tags and restent_a_faire:
            print(f" {couleurs.CLR_DIM}ℹ️  {restent_a_faire} tâche(s) à faire portant ce(s) tag(s) restent dans la liste : "
                  f"seules les tâches terminées s'archivent.{couleurs.CLR_RESET}")
        if sans_date:
            print(f" {couleurs.CLR_DIM}ℹ️  {sans_date} tâche(s) terminée(s) sans date de complétion ignorée(s) : "
                  f"âge inconnu (archivez-les par identifiant).{couleurs.CLR_RESET}")

    # Une seule sauvegarde pour tout le lot, APRÈS fermeture des deux bases
    if nb_ok:
        sauvegarder_base()
    if ids and not silencieux:
        _afficher_bilan_lot(len(ids), nb_ok, "archivée(s)", echecs)
    return echecs == 0


def archivage_automatique(jours):
    """Réglage [archive] auto_days : archive les tâches terminées depuis au moins `jours` jours.

    Au plus une fois par jour (la date du dernier passage est gardée dans `archive_auto`). Le bilan, une
    ligne, va sur stderr pour ne pas polluer la sortie des pipes. Retourne le nombre de tâches archivées.
    Sans effet si `jours` vaut 0 ou si l'état ne peut pas être lu ou écrit (jamais bloquant).
    """
    if not jours:
        return 0
    aujourdhui = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(config.ARCHIVE_AUTO_LAST, encoding="utf-8") as f:
            if f.read().strip() == aujourdhui:
                return 0
    except OSError:
        pass
    bilan = {}
    try:
        archiver_taches(anciennete=(jours, 'd'), silencieux=True, bilan=bilan)
        with open(config.ARCHIVE_AUTO_LAST, "w", encoding="utf-8") as f:
            f.write(aujourdhui + "\n")
    except (OSError, *dbm.error):
        return bilan.get('archivees', 0)
    nombre = bilan.get('archivees', 0)
    if nombre:
        print(f" 📦 {nombre} tâche(s) terminée(s) depuis plus de {jours} jour(s) archivée(s) automatiquement "
              f"([archive] auto_days).", file=sys.stderr)
    return nombre


def purger_archive(ids=None, anciennete=None, confirmer=True):
    """Supprime DÉFINITIVEMENT des tâches de l'archive, après confirmation.

    ids        : préfixes d'identifiants de tâches archivées ; sans ids, toute l'archive est visée.
    anciennete : (n, unité) ; ne retient que les tâches terminées depuis au moins cette durée.
    Les cibles sont choisies et confirmées AVANT toute écriture ; une sauvegarde suit la purge, donc
    `undo` la rétablit. Retourne True si aucun identifiant n'a posé problème (annuler n'est pas un échec).
    """
    if not _archive_existe():
        print(f" 📦 {couleurs.CLR_DIM}L'archive est vide, rien à purger.{couleurs.CLR_RESET}")
        return not ids

    sans_date = 0
    echecs = 0
    with dbm.open(config.ARCHIVE_NAME, 'r') as archive:
        cibles = []                                 # (clé, titre)
        if ids:
            cles, echecs = _resoudre_ids(archive, ids)
            for cle in cles:
                try:
                    titre = _normaliser_tache(archive[cle])['titre']
                except ValueError:
                    titre = "(entrée illisible)"    # une entrée corrompue doit pouvoir être supprimée
                cibles.append((cle, titre))
        else:
            limite = _decaler(datetime.now().date(), -anciennete[0], anciennete[1]) if anciennete else None
            for t in _lire_archive():
                if limite is not None:
                    date_fin = _parse_date((t['date_terminee'] or "")[:10])
                    if date_fin is None:
                        sans_date += 1
                        continue
                    if date_fin > limite:
                        continue
                cibles.append((t['id'].encode('utf-8'), t['titre']))

    if sans_date:
        print(f" {couleurs.CLR_DIM}ℹ️  {sans_date} tâche(s) sans date de complétion ignorée(s) : âge inconnu "
              f"(purgez-les par identifiant).{couleurs.CLR_RESET}")
    if not cibles:
        qualif = f" terminée depuis au moins {anciennete[0]}{anciennete[1]}" if anciennete else ""
        if not ids:
            print(f" 📦 {couleurs.CLR_DIM}Aucune tâche archivée{qualif} à purger.{couleurs.CLR_RESET}")
        _afficher_bilan_lot(len(ids or []), 0, "purgée(s)", echecs)
        return echecs == 0

    if confirmer:
        apercu = ", ".join(f"'{titre}'" for _, titre in cibles[:5]) + (" …" if len(cibles) > 5 else "")
        try:
            reponse = input(f" {couleurs.CLR_DEL}⚠️ DANGER :{couleurs.CLR_RESET} Supprimer définitivement {len(cibles)} tâche(s) "
                            f"de l'archive ({apercu}) ? L'état actuel est sauvegardé avant (`undo`). (y/N) : ").strip().lower()
        except EOFError:
            reponse = ""
        if reponse != 'y':
            print(" ❌ Opération annulée.")
            return True

    with dbm.open(config.ARCHIVE_NAME, 'w') as archive:
        for cle, titre in cibles:
            del archive[cle]
            pieces_jointes.mettre_a_la_corbeille(cle.decode('utf-8', errors='replace'))
            journal.noter(ids=[cle], titres=[titre], modifie=True)
    journal.noter(purged=len(cibles))
    sauvegarder_base()                              # APRÈS fermeture de l'archive : la purge reste annulable
    print(f" {couleurs.CLR_DEL}🗑️{couleurs.CLR_RESET} {len(cibles)} tâche(s) supprimée(s) de l'archive.")
    if ids:
        _afficher_bilan_lot(len(ids), len(cibles), "purgée(s)", echecs)
    return echecs == 0


def desarchiver_taches(ids):
    """Remet des tâches archivées dans la liste courante. Retourne True si aucun id n'a posé problème."""
    if not _archive_existe():
        print(f" 📦 {couleurs.CLR_DIM}L'archive est vide, rien à récupérer.{couleurs.CLR_RESET}")
        return False

    nb_ok = 0
    with dbm.open(config.ARCHIVE_NAME, 'w') as archive, dbm.open(config.DB_NAME, 'c') as db:
        cles, echecs = _resoudre_ids(archive, ids)
        for cle in cles:
            try:
                t = _normaliser_tache(archive[cle])
            except ValueError:
                journal.echec("corrupted_entry")
                print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Cette entrée d'archive est corrompue et ne peut pas être récupérée.")
                echecs += 1
                continue
            if cle in db:
                journal.echec("duplicate_id")
                print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Une tâche portant déjà cet identifiant existe dans la liste : '{t['titre']}' non récupérée.")
                echecs += 1
                continue
            t.pop('date_archivage', None)
            db[cle] = json.dumps(t)
            del archive[cle]
            journal.noter(ids=[cle], titres=[t['titre']], modifie=True)
            print(f" 📤 Tâche récupérée : '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}'.")
            nb_ok += 1

    if nb_ok:
        sauvegarder_base()
    _afficher_bilan_lot(len(ids), nb_ok, "récupérée(s)", echecs)
    return echecs == 0


def lister_archive(recherche=None, fmt="text", pager=True, champs=CHAMPS_RECHERCHE, filtres=None,
                   tri=None, limite=None, debut=None, colonnes=None):
    """Affiche l'archive (la plus récemment terminée en premier), éventuellement filtrée.

    recherche / champs : texte cherché ; filtres : options de
    `filtres.garder` ; tri : done (défaut), archived, alpha ou priority ; limite / debut : tranche
    (debut commence à 1), appliquée après filtres et tri.
    """
    taches = _lire_archive_triee()
    filtre = bool(recherche or filtres or limite or debut)
    if recherche:
        taches = [t for t in taches if correspond_recherche(t, recherche, champs)]
    if filtres:
        taches = [t for t in taches if garder(t, **filtres)]
    if tri == "archived":
        taches.sort(key=lambda t: t.get('date_archivage') or "", reverse=True)
    elif tri == "alpha":
        taches.sort(key=lambda t: t['titre'].lower())
    elif tri == "priority":
        taches.sort(key=lambda t: -PRIORITES.index(t['priorite']))
    total = len(taches)
    if limite or debut:
        taches = taches[(debut or 1) - 1:][:limite or None]

    if fmt == "json":
        print(json.dumps(taches, indent=2, ensure_ascii=False))
        return
    if fmt == "plain" or (fmt == "table" and taches):
        sortie_taches(fmt, taches, colonnes)
        return
    if not taches:
        vide = "Aucune tâche archivée ne correspond à vos critères." if filtre else "L'archive est vide."
        print(f" 📦 {couleurs.CLR_DIM}{vide}{couleurs.CLR_RESET}")
        return

    lignes = [f"\n {couleurs.CLR_CYAN}─── 📦 ARCHIVE ───{couleurs.CLR_RESET}"]
    for t in taches:
        tags = f" {couleurs.CLR_TAG}" + " ".join(f"#{tg}" for tg in t['tags']) + couleurs.CLR_RESET if t['tags'] else ""
        dates = []
        if t['date_terminee']:
            dates.append(f"terminée le {t['date_terminee'][:10]}")
        if t.get('date_archivage'):
            dates.append(f"archivée le {t['date_archivage'][:10]}")
        detail = f" {couleurs.CLR_DIM}· {' · '.join(dates)}{couleurs.CLR_RESET}" if dates else ""
        lignes.append(f"  {couleurs.CLR_DONE}[✅]{couleurs.CLR_RESET} {couleurs.CLR_DIM}{t['titre']}{couleurs.CLR_RESET}{tags}{detail} "
                      f"{couleurs.CLR_DIM}(id: {t['id'][:8]}){couleurs.CLR_RESET}")
        if t['description']:
            lignes.append(f"      {couleurs.CLR_DIM}↳ {t['description']}{couleurs.CLR_RESET}")
    lignes.append(f" {couleurs.CLR_CYAN}──────────────────────────────────────{couleurs.CLR_RESET}")
    tranche = f" sur {total}" if len(taches) < total else ""
    lignes.append(f" {couleurs.CLR_DIM}{len(taches)}{tranche} tâche(s) archivée(s) · récupérer : todo archive restore <id>{couleurs.CLR_RESET}\n")
    _afficher_texte("\n".join(lignes), pager)


def _lire_archive_triee():
    taches = _lire_archive()
    taches.sort(key=lambda t: t['id'])
    taches.sort(key=lambda t: t['date_terminee'] or "", reverse=True)
    return taches
