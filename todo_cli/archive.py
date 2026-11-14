"""Archivage : ranger les tâches terminées hors de la liste courante, les consulter, les récupérer.

Les tâches archivées vivent dans une base DBM séparée (`todo_archive`, même dossier que la base
principale) : `list`, `agenda` et `stats` ne les voient pas. Elles sont sauvegardées et restaurées
avec la base principale.
"""
import dbm
import json
import re
from datetime import datetime
from . import couleurs, journal
from .affichage import _afficher_texte, _texte_recherche
from .config import ARCHIVE_NAME, DB_NAME, STATUT_TERMINE
from .dates import _decaler, _parse_date
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


def archiver_taches(ids=None, anciennete=None):
    """Déplace des tâches terminées vers l'archive.

    ids        : préfixes d'identifiants à archiver (ils doivent désigner des tâches terminées).
    anciennete : (n, unité) ; ne retient que les tâches terminées depuis au moins cette durée.
    Sans ids, toutes les tâches terminées (éventuellement filtrées par ancienneté) sont archivées.
    Retourne True si aucun identifiant n'a posé problème.

    Chaque tâche est écrite dans l'archive AVANT d'être retirée de la base principale : une
    interruption laisse un doublon récupérable plutôt qu'une tâche perdue.
    """
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, rien à archiver.{couleurs.CLR_RESET}")
        return not ids

    maintenant = datetime.now()
    horodatage = maintenant.strftime("%Y-%m-%d %H:%M")
    nb_ok, echecs, sans_date = 0, 0, 0
    with dbm.open(ARCHIVE_NAME, 'c') as archive, dbm.open(DB_NAME, 'w') as db:
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
                if t['statut'] != STATUT_TERMINE:
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
            if ids:
                print(f" 📦 Tâche archivée : '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}'.")

    if not ids:
        if nb_ok:
            print(f" 📦 {couleurs.CLR_DONE}{nb_ok} tâche(s) archivée(s).{couleurs.CLR_RESET}")
        else:
            qualif = f" depuis au moins {anciennete[0]}{anciennete[1]}" if anciennete else ""
            print(f" {couleurs.CLR_DIM}Aucune tâche terminée{qualif} à archiver.{couleurs.CLR_RESET}")
        if sans_date:
            print(f" {couleurs.CLR_DIM}ℹ️  {sans_date} tâche(s) terminée(s) sans date de complétion ignorée(s) : "
                  f"âge inconnu (archivez-les par identifiant).{couleurs.CLR_RESET}")

    # Une seule sauvegarde pour tout le lot, APRÈS fermeture des deux bases
    if nb_ok:
        sauvegarder_base()
    if ids:
        _afficher_bilan_lot(len(ids), nb_ok, "archivée(s)", echecs)
    return echecs == 0


def desarchiver_taches(ids):
    """Remet des tâches archivées dans la liste courante. Retourne True si aucun id n'a posé problème."""
    if not _archive_existe():
        print(f" 📦 {couleurs.CLR_DIM}L'archive est vide, rien à récupérer.{couleurs.CLR_RESET}")
        return False

    nb_ok = 0
    with dbm.open(ARCHIVE_NAME, 'w') as archive, dbm.open(DB_NAME, 'c') as db:
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


def lister_archive(recherche=None, fmt="table", pager=True):
    """Affiche l'archive (la plus récemment terminée en premier), éventuellement filtrée par texte."""
    taches = _lire_archive_triee()
    if recherche:
        motif = recherche.lower()
        taches = [t for t in taches if motif in _texte_recherche(t)]

    if fmt == "json":
        print(json.dumps(taches, indent=2, ensure_ascii=False))
        return
    if not taches:
        vide = "Aucune tâche archivée ne correspond à votre recherche." if recherche else "L'archive est vide."
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
    lignes.append(f" {couleurs.CLR_DIM}{len(taches)} tâche(s) archivée(s) · récupérer : todo unarchive <id>{couleurs.CLR_RESET}\n")
    _afficher_texte("\n".join(lignes), pager)


def _lire_archive_triee():
    taches = _lire_archive()
    taches.sort(key=lambda t: t['id'])
    taches.sort(key=lambda t: t['date_terminee'] or "", reverse=True)
    return taches
