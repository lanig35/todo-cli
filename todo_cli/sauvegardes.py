"""Sauvegardes automatiques, rotation, restauration et remise à zéro de la base."""
import dbm
import glob
import os
import re
import shutil
import sys
from datetime import datetime
from .config import BACKUP_DIR, DB_DIR, DB_NAME, NB_BACKUPS_MAX
from . import couleurs
from .stockage import _base_existe


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
    """Crée un instantané daté de la base DBM dans son propre dossier
    et, si rotation=True, ne conserve que les NB_BACKUPS_MAX plus récents.

    Doit être appelée une fois la base fermée, sinon les dernières écritures
    pourraient ne pas encore être sur le disque.
    Retourne le chemin du dossier créé (ou None s'il n'y a rien à sauvegarder).
    """
    fichiers_base = [f for f in glob.glob(f"{DB_NAME}*") if os.path.isfile(f)]
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
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Numéro de sauvegarde invalide : {reference} (1 à {len(noms_recents_d_abord)}).")
        return None

    correspondances = [d for d in noms_recents_d_abord if d.startswith(reference)] if reference else []
    if not correspondances:
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Aucune sauvegarde ne correspond à '{reference}'.")
        return None
    if len(correspondances) > 1:
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
        for f in glob.glob(f"{DB_NAME}*"):
            if os.path.isfile(f):
                os.remove(f)
        for f in fichiers_source:
            shutil.copy2(f, os.path.join(DB_DIR, os.path.basename(f)))
    except OSError as e:
        print(f" {couleurs.CLR_DEL}❌ Erreur pendant la restauration :{couleurs.CLR_RESET} {e}")
        if filet:
            print(f"    L'état précédent est conservé dans : {filet}")
        sys.exit(1)

    # 3. Nouvelle sauvegarde de l'état restauré (avec rotation)
    sauvegarder_base()
    print(f" {couleurs.CLR_DONE}♻️  Base restaurée{couleurs.CLR_RESET} depuis la sauvegarde du {couleurs.CLR_BOLD}{date_txt}{couleurs.CLR_RESET} ({nb} tâche(s)).")
    if filet:
        print(f"    {couleurs.CLR_DIM}L'état précédent a été sauvegardé : 'restore' permet de le retrouver (le plus récent juste après celui-ci).{couleurs.CLR_RESET}")
