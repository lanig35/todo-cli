"""Configuration : emplacement du stockage et constantes métier.

Les chemins du stockage (base, archive, sauvegardes, fichiers d'état, verrou) ne sont **pas** des
constantes calculées à l'import : ils se résolvent à la demande (`config.DB_NAME`, `config.BACKUP_DIR`…),
à partir du dossier de stockage courant. Ce dossier vient de `reglages` (TODO_DB_DIR, fichier de
configuration, sinon défaut) tant qu'aucun autre n'a été désigné avec `definir_dossier()`. Il est lu au
premier usage puis mémorisé pour la durée du processus.

Les modules lisent donc toujours ces chemins par `from . import config` puis `config.DB_NAME`, jamais par
`from .config import DB_NAME` (qui figerait la valeur à l'import et empêcherait de changer de dossier).
"""
import os
from . import reglages

# Constantes métier (elles, ne dépendent d'aucun réglage)
STATUT_A_FAIRE = "A FAIRE"
STATUT_TERMINE = "TERMINE"
PRIORITES = ("low", "medium", "high")

# Nom des fichiers et dossiers du stockage, relatifs au dossier de stockage
_FICHIERS = {
    "BACKUP_DIR": "backups",
    "DB_NAME": "todo_db",                  # chemin de base pour le moteur DBM
    "ARCHIVE_NAME": "todo_archive",        # tâches terminées rangées hors de la liste courante
    "REMIND_OFF": "remind_off",            # présent = rappels désactivés (hors base : ni sauvegardé ni touché par restore/reset)
    "REMIND_LAST": "remind_last",          # date du dernier rappel affiché (--once-a-day)
    "ARCHIVE_AUTO_LAST": "archive_auto",   # date du dernier archivage automatique
    "REMIND_STATUS": "remind_status",      # résumé d'une ligne écrit par --write-status
    "LOCK_FILE": "todo.lock",              # verrou de la base
}

_dossier = None            # dossier de stockage courant (None : pas encore résolu)
_nb_sauvegardes = None


def definir_dossier(chemin):
    """Désigne le dossier de stockage à utiliser, à la place de celui des réglages."""
    global _dossier
    _dossier = chemin


def dossier():
    """Dossier de stockage courant (résolu au premier appel, puis mémorisé)."""
    global _dossier
    if _dossier is None:
        _dossier = reglages.obtenir("general", "db_dir")
    return _dossier


def preparer():
    """Crée le dossier de stockage et celui des sauvegardes s'ils n'existent pas encore.

    Compléter une ligne de commande (Tab) ne doit rien créer ni échouer : rien n'est fait dans ce cas.
    """
    if reglages.COMPLETION:
        return
    os.makedirs(dossier(), exist_ok=True)
    os.makedirs(os.path.join(dossier(), _FICHIERS["BACKUP_DIR"]), exist_ok=True)


def __getattr__(nom):
    """Chemins du stockage et réglages dérivés, calculés à chaque accès (PEP 562)."""
    global _nb_sauvegardes
    if nom == "DB_DIR":
        return dossier()
    if nom in _FICHIERS:
        return os.path.join(dossier(), _FICHIERS[nom])
    if nom == "NB_BACKUPS_MAX":                     # nombre maximal de sauvegardes conservées
        if _nb_sauvegardes is None:
            _nb_sauvegardes = reglages.obtenir("general", "keep_backups")
        return _nb_sauvegardes
    raise AttributeError(f"module {__name__!r} n'a pas d'attribut {nom!r}")
