"""Sauvegardes automatiques, rotation, restauration et remise à zéro de la base."""
import dbm
import glob
import os
import re
import shutil
import sys
from datetime import datetime
from .config import ARCHIVE_NAME, BACKUP_DIR, DB_DIR, DB_NAME, NB_BACKUPS_MAX
from . import couleurs, journal
from .stockage import _base_existe, _charger_taches, _lire_archive, _lire_taches


# Chaque sauvegarde est un sous-dossier horodaté : backups/AAAAMMJJ_HHMMSS_µs/
_MOTIF_BACKUP = re.compile(r"^\d{8}_\d{6}_\d{6}$")

def _noms_sauvegardes():
    """Noms des dossiers de sauvegarde, du plus ancien au plus récent."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    return sorted(
        d for d in os.listdir(BACKUP_DIR)
        if _MOTIF_BACKUP.match(d) and os.path.isdir(os.path.join(BACKUP_DIR, d))
    )

def sauvegarder_base(rotation=True):
    """Crée un instantané daté de la base DBM (et de la base d'archive) dans son propre dossier
    et, si rotation=True, ne conserve que les NB_BACKUPS_MAX plus récents.

    Doit être appelée une fois la base fermée, sinon les dernières écritures
    pourraient ne pas encore être sur le disque.
    Retourne le chemin du dossier créé (ou None s'il n'y a rien à sauvegarder).
    """
    fichiers_base = [f for f in glob.glob(f"{DB_NAME}*") + glob.glob(f"{ARCHIVE_NAME}*") if os.path.isfile(f)]
    if not fichiers_base:
        return None

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dossier = os.path.join(BACKUP_DIR, horodatage)
    os.makedirs(dossier, exist_ok=True)

    # Duplication de l'ensemble des sous-fichiers DBM (.db, .pag, .dir selon OS)
    for fichier in fichiers_base:
        shutil.copy2(fichier, os.path.join(dossier, os.path.basename(fichier)))

    # --- Rotation : on supprime les dossiers les plus anciens ---
    if rotation:
        for ancien in _noms_sauvegardes()[:-NB_BACKUPS_MAX]:
            shutil.rmtree(os.path.join(BACKUP_DIR, ancien), ignore_errors=True)
    return dossier

def reinitialiser_base():
    """Remise à zéro complète après confirmation et sauvegarde ultime."""
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La base de données est déjà vide.{couleurs.CLR_RESET}")
        return

    with dbm.open(DB_NAME, 'r') as db:
        if len(db) == 0:
            print(f" 📋 {couleurs.CLR_DIM}La base de données est déjà vide.{couleurs.CLR_RESET}")
            return

    try:
        reponse = input(f" {couleurs.CLR_DEL}⚠️ DANGER :{couleurs.CLR_RESET} Purger intégralement la base ? (y/N) : ").strip().lower()
    except EOFError:
        reponse = ""
    if reponse != 'y':
        print(" ❌ Opération annulée.")
        return

    sauvegarder_base()  # Sauvegarde de l'état AVANT purge (base fermée)
    with dbm.open(DB_NAME, 'w') as db:
        for key in list(db.keys()):
            del db[key]
    journal.noter(modifie=True)
    print(f" {couleurs.CLR_DONE}🗑️ Base réinitialisée.{couleurs.CLR_RESET}")

# 6 bis. RESTAURATION À PARTIR DES SAUVEGARDES
def _infos_sauvegarde(nom):
    """Retourne (date lisible, nombre de tâches ou None) pour un dossier de sauvegarde."""
    try:
        date_txt = datetime.strptime(nom[:15], "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        date_txt = nom
    try:
        with dbm.open(os.path.join(BACKUP_DIR, nom, "todo_db"), 'r') as db:
            nb = len(db)
    except (dbm.error, OSError):
        nb = None
    return date_txt, nb

def _resoudre_sauvegarde(reference, noms_recents_d_abord):
    """Retrouve un dossier de sauvegarde par numéro (1 = la plus récente) ou par préfixe d'horodatage."""
    reference = reference.strip()
    if reference.isdigit() and len(reference) <= 3:
        n = int(reference)
        if 1 <= n <= len(noms_recents_d_abord):
            return noms_recents_d_abord[n - 1]
        journal.echec("invalid_backup_number")
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Numéro de sauvegarde invalide : {reference} (1 à {len(noms_recents_d_abord)}).")
        return None

    correspondances = [d for d in noms_recents_d_abord if d.startswith(reference)] if reference else []
    if not correspondances:
        journal.echec("unknown_backup")
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Aucune sauvegarde ne correspond à '{reference}'.")
        return None
    if len(correspondances) > 1:
        journal.echec("ambiguous_backup")
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Référence ambiguë '{reference}' ({len(correspondances)} sauvegardes). Utilisez le numéro affiché par 'restore'.")
        return None
    return correspondances[0]

def lister_sauvegardes():
    """Affiche les sauvegardes disponibles (la plus récente en premier)."""
    noms = _noms_sauvegardes()[::-1]
    if not noms:
        print(f" 📦 {couleurs.CLR_DIM}Aucune sauvegarde disponible.{couleurs.CLR_RESET}")
        return

    print(f"\n {couleurs.CLR_CYAN}─── 📦 SAUVEGARDES DISPONIBLES ───{couleurs.CLR_RESET}")
    for i, nom in enumerate(noms, start=1):
        date_txt, nb = _infos_sauvegarde(nom)
        detail = f"{nb} tâche(s)" if nb is not None else f"{couleurs.CLR_DEL}illisible{couleurs.CLR_RESET}"
        print(f"  {couleurs.CLR_BOLD}{i}{couleurs.CLR_RESET}. {date_txt}  {couleurs.CLR_DIM}({detail}){couleurs.CLR_RESET}")
    print(f" {couleurs.CLR_CYAN}──────────────────────────────────{couleurs.CLR_RESET}")
    print(f" {couleurs.CLR_DIM}Restaurer : todo restore <numéro>   (1 = la plus récente){couleurs.CLR_RESET}\n")

def restaurer_base(reference=None, confirmer=True):
    """Liste les sauvegardes (sans argument) ou restaure celle désignée.

    L'état actuel est sauvegardé juste avant la restauration, ce qui la rend réversible.
    """
    if reference is None:
        lister_sauvegardes()
        return

    noms = _noms_sauvegardes()[::-1]
    if not noms:
        print(f" 📦 {couleurs.CLR_DIM}Aucune sauvegarde disponible.{couleurs.CLR_RESET}")
        return

    nom = _resoudre_sauvegarde(reference, noms)
    if nom is None:
        return

    date_txt, nb = _infos_sauvegarde(nom)
    if nb is None:
        journal.echec("unreadable_backup")
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} La sauvegarde du {date_txt} est illisible : restauration annulée.")
        return

    if confirmer:
        try:
            reponse = input(f" {couleurs.CLR_DEL}⚠️ Restaurer{couleurs.CLR_RESET} la sauvegarde du {couleurs.CLR_BOLD}{date_txt}{couleurs.CLR_RESET} ({nb} tâche(s)) ? "
                            f"L'état actuel sera sauvegardé avant. (y/N) : ").strip().lower()
        except EOFError:
            reponse = ""
        if reponse != 'y':
            print(" ❌ Opération annulée.")
            return

    dossier_source = os.path.join(BACKUP_DIR, nom)
    fichiers_source = [f for f in glob.glob(os.path.join(dossier_source, "*")) if os.path.isfile(f)]

    # 1. Filet de sécurité : sauvegarde de l'état actuel SANS rotation, pour que
    #    la sauvegarde choisie ne puisse pas être supprimée avant d'être copiée.
    filet = sauvegarder_base(rotation=False)

    # 2. Remplacement des fichiers de la base par ceux de la sauvegarde
    try:
        # La base ET l'archive reviennent à l'état de la sauvegarde : sans cela, une tâche
        # archivée depuis pourrait exister à la fois dans la liste restaurée et dans l'archive.
        for f in glob.glob(f"{DB_NAME}*") + glob.glob(f"{ARCHIVE_NAME}*"):
            if os.path.isfile(f):
                os.remove(f)
        for f in fichiers_source:
            shutil.copy2(f, os.path.join(DB_DIR, os.path.basename(f)))
    except OSError as e:
        journal.echec("restore_error", detail=str(e))
        print(f" {couleurs.CLR_DEL}❌ Erreur pendant la restauration :{couleurs.CLR_RESET} {e}")
        if filet:
            print(f"    L'état précédent est conservé dans : {filet}")
        sys.exit(1)

    # 3. Nouvelle sauvegarde de l'état restauré (avec rotation)
    sauvegarder_base()
    journal.noter(modifie=True, backup=nom)
    print(f" {couleurs.CLR_DONE}♻️  Base restaurée{couleurs.CLR_RESET} depuis la sauvegarde du {couleurs.CLR_BOLD}{date_txt}{couleurs.CLR_RESET} ({nb} tâche(s)).")
    if filet:
        print(f"    {couleurs.CLR_DIM}L'état précédent a été sauvegardé : 'restore' permet de le retrouver (le plus récent juste après celui-ci).{couleurs.CLR_RESET}")


# 6 ter. ANNULATION DE LA DERNIÈRE MODIFICATION
def _taches_sauvegarde(nom, base):
    """Tâches d'un fichier DBM d'un dossier de sauvegarde ('todo_db' ou 'todo_archive'), {id: tâche}."""
    chemin = os.path.join(BACKUP_DIR, nom, base)
    if not glob.glob(f"{chemin}*"):
        return {}
    with dbm.open(chemin, 'r') as db:
        return {t['id']: t for t in _charger_taches(db)}

def _resume_differences(actuel, cible, vers_la_liste=True):
    """Phrases décrivant ce que changerait le passage de l'état `actuel` à l'état `cible` ({id: tâche})."""
    def noms(ids, source):
        affiches = [f"'{source[i]['titre']}'" for i in sorted(ids)[:5]]
        return ", ".join(affiches) + (f" et {len(ids) - 5} autre(s)" if len(ids) > 5 else "")
    retirees = set(actuel) - set(cible)
    retablies = set(cible) - set(actuel)
    modifiees = {i for i in set(actuel) & set(cible) if actuel[i] != cible[i]}
    cadre = "" if vers_la_liste else " (archive)"
    phrases = []
    if retirees:
        phrases.append(f"retirer{cadre} {noms(retirees, actuel)}")
    if retablies:
        phrases.append(f"rétablir{cadre} {noms(retablies, cible)}")
    if modifiees:
        phrases.append(f"remettre{cadre} dans leur état précédent {noms(modifiees, cible)}")
    return phrases

def annuler_derniere_action():
    """Revient à l'état précédant la dernière modification.

    Une sauvegarde est faite après chaque modification : la plus récente décrit normalement l'état
    actuel, la précédente l'état d'avant, qui est donc la cible. Si l'état actuel diffère de la
    sauvegarde la plus récente (`reset`, qui sauvegarde AVANT de vider, ou fichier modifié hors du
    programme), c'est cette dernière qui est la cible : on rétablit ce qui a été perdu.
    Comme `restaurer_base`, l'annulation sauvegarde l'état actuel avant de le remplacer : un second
    `undo` rétablit donc ce qui vient d'être annulé.
    Retourne True si une annulation a été faite.
    """
    noms = _noms_sauvegardes()[::-1]
    if not noms:
        print(f" ↩️  {couleurs.CLR_DIM}Rien à annuler : aucun état antérieur n'est sauvegardé.{couleurs.CLR_RESET}")
        return False

    actuel = ({t['id']: t for t in _lire_taches()}, {t['id']: t for t in _lire_archive()})
    plus_recent = (_taches_sauvegarde(noms[0], "todo_db"), _taches_sauvegarde(noms[0], "todo_archive"))
    if actuel == plus_recent:
        if len(noms) < 2:
            print(f" ↩️  {couleurs.CLR_DIM}Rien à annuler : aucun état antérieur n'est sauvegardé.{couleurs.CLR_RESET}")
            return False
        numero, cible = "2", (_taches_sauvegarde(noms[1], "todo_db"), _taches_sauvegarde(noms[1], "todo_archive"))
    else:
        numero, cible = "1", plus_recent

    phrases = (_resume_differences(actuel[0], cible[0]) + _resume_differences(actuel[1], cible[1], vers_la_liste=False))
    print(f" ↩️  Annulation de la dernière modification : "
          + (" ; ".join(phrases) if phrases else "aucune différence visible dans les tâches") + ".")
    restaurer_base(numero, confirmer=False)
    print(f"    {couleurs.CLR_DIM}Relancez 'undo' pour rétablir ce qui vient d'être annulé.{couleurs.CLR_RESET}")
    return True
