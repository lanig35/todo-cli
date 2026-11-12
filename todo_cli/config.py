"""Configuration : emplacement du stockage et constantes métier."""
import os

# Base de données et dossiers de sauvegarde localisés dans le répertoire utilisateur.
# La variable d'environnement TODO_DB_DIR permet de rediriger le stockage (tests, etc.).
DB_DIR = os.environ.get("TODO_DB_DIR") or os.path.expanduser("~/.local/share/todo")
BACKUP_DIR = os.path.join(DB_DIR, "backups")

# Création récursive des répertoires s'ils n'existent pas encore
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Chemin absolu de base pour le moteur DBM
DB_NAME = os.path.join(DB_DIR, "todo_db")

# Base d'archive (tâches terminées rangées hors de la liste courante), même dossier
ARCHIVE_NAME = os.path.join(DB_DIR, "todo_archive")

# Fichiers d'état du rappel (hors base : ni sauvegardés ni touchés par restore/reset)
REMIND_OFF = os.path.join(DB_DIR, "remind_off")        # présent = rappels désactivés
REMIND_LAST = os.path.join(DB_DIR, "remind_last")      # date du dernier rappel affiché (--once-a-day)
REMIND_STATUS = os.path.join(DB_DIR, "remind_status")  # résumé d'une ligne écrit par --write-status

# Nombre maximal de sauvegardes conservées
NB_BACKUPS_MAX = 5
STATUT_A_FAIRE = "A FAIRE"
STATUT_TERMINE = "TERMINE"
PRIORITES = ("low", "medium", "high")
