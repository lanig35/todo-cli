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
import re
import shutil
import time
from . import reglages

# Constantes métier (elles, ne dépendent d'aucun réglage)
STATUT_A_FAIRE = "A FAIRE"
STATUT_TERMINE = "TERMINE"
PRIORITES = ("low", "medium", "high")

PROJET_DEFAUT = "default"
_MOTIF_PROJET = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_SOUS_DOSSIER = "projects"      # les projets autres que `default` : <stockage>/projects/<nom>/
_CORBEILLE = ".trash"           # projets supprimés, récupérables : <stockage>/.trash/<nom>-<horodatage>/

# Fichiers propres à un projet, relatifs au dossier du projet
_FICHIERS = {
    "BACKUP_DIR": "backups",
    "DB_NAME": "todo_db",                  # chemin de base pour le moteur DBM
    "ARCHIVE_NAME": "todo_archive",        # tâches terminées rangées hors de la liste courante
    "ARCHIVE_AUTO_LAST": "archive_auto",   # date du dernier archivage automatique
    "LOCK_FILE": "todo.lock",              # verrou de la base
    "VIEWS_FILE": "views.json",            # vues enregistrées (hors base : ni sauvegardé ni touché par restore/reset/undo)
}
# Fichiers communs à tous les projets, relatifs à la racine du stockage
_FICHIERS_RACINE = {
    "REMIND_OFF": "remind_off",            # présent = rappels désactivés (hors base : ni sauvegardé ni touché par restore/reset)
    "REMIND_LAST": "remind_last",          # date du dernier rappel affiché (--once-a-day)
    "REMIND_STATUS": "remind_status",      # résumé d'une ligne écrit par --write-status
}

_dossier = None            # dossier de stockage courant (None : pas encore résolu)
_projet = None             # projet courant (None : pas encore résolu)
_origine_projet = None
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


# ------------------------------------------------------------------------------------------ projets
def valider_nom(nom):
    """Nom de projet valide : minuscules, chiffres, `_` et `-`, 32 caractères au plus, commence par une lettre ou un chiffre.

    Retourne le nom, ou lève ValueError avec un message lisible.
    """
    if not isinstance(nom, str) or not _MOTIF_PROJET.match(nom):
        raise ValueError(f"nom de projet invalide : '{nom}' (minuscules, chiffres, - et _, 32 caractères au plus, "
                         f"commence par une lettre ou un chiffre)")
    return nom


def definir_projet(nom, origine="option"):
    """Désigne le projet courant (nom déjà validé)."""
    global _projet, _origine_projet
    _projet, _origine_projet = nom, origine


def projet():
    """Projet courant : option --project, TODO_PROJECT, `[general] project`, sinon `default` (résolu au premier appel)."""
    if _projet is None:
        valeur, origine = reglages.obtenir_avec_origine("general", "project")
        definir_projet(valeur, origine)
    return _projet


def origine_projet():
    """D'où vient le projet courant : 'option', 'variable TODO_PROJECT', 'fichier' ou 'défaut'."""
    projet()
    return _origine_projet


def dossier_du_projet(nom):
    """Dossier d'un projet : la racine du stockage pour `default`, sinon <racine>/projects/<nom>."""
    return dossier() if nom == PROJET_DEFAUT else os.path.join(dossier(), _SOUS_DOSSIER, nom)


def existe(nom):
    """Le projet existe-t-il ? (`default` existe toujours.)"""
    return nom == PROJET_DEFAUT or os.path.isdir(dossier_du_projet(nom))


def projets():
    """Noms des projets existants, `default` en tête, les autres par ordre alphabétique."""
    base = os.path.join(dossier(), _SOUS_DOSSIER)
    autres = sorted(d for d in (os.listdir(base) if os.path.isdir(base) else [])
                    if _MOTIF_PROJET.match(d) and os.path.isdir(os.path.join(base, d)))
    return [PROJET_DEFAUT] + [d for d in autres if d != PROJET_DEFAUT]


def creer_projet(nom):
    """Crée le dossier d'un projet (et ses sauvegardes) ; ValueError s'il existe déjà."""
    if existe(nom):
        raise ValueError(f"le projet '{nom}' existe déjà")
    os.makedirs(os.path.join(dossier_du_projet(nom), _FICHIERS["BACKUP_DIR"]))


def renommer_projet(ancien, nouveau):
    os.rename(dossier_du_projet(ancien), dossier_du_projet(nouveau))


def mettre_a_la_corbeille(nom):
    """Déplace un projet dans <racine>/.trash/<nom>-<horodatage>/ (récupérable à la main) ; retourne le nouveau chemin."""
    cible = os.path.join(dossier(), _CORBEILLE, f"{nom}-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(os.path.dirname(cible), exist_ok=True)
    shutil.move(dossier_du_projet(nom), cible)
    return cible


def preparer():
    """Crée le dossier de stockage et, pour le projet courant s'il existe, celui des sauvegardes.

    Compléter une ligne de commande (Tab) ne doit rien créer ni échouer : rien n'est fait dans ce cas.
    Un projet inexistant n'est jamais créé ici : seul `project create` le fait.
    """
    if reglages.COMPLETION:
        return
    os.makedirs(dossier(), exist_ok=True)
    if existe(projet()):
        os.makedirs(os.path.join(dossier_du_projet(projet()), _FICHIERS["BACKUP_DIR"]), exist_ok=True)


def __getattr__(nom):
    """Chemins du stockage et réglages dérivés, calculés à chaque accès (PEP 562)."""
    global _nb_sauvegardes
    if nom == "DB_DIR":                              # dossier du projet courant
        return dossier_du_projet(projet())
    if nom in _FICHIERS:
        return os.path.join(dossier_du_projet(projet()), _FICHIERS[nom])
    if nom in _FICHIERS_RACINE:
        return os.path.join(dossier(), _FICHIERS_RACINE[nom])
    if nom == "NB_BACKUPS_MAX":                     # nombre maximal de sauvegardes conservées
        if _nb_sauvegardes is None:
            _nb_sauvegardes = reglages.obtenir("general", "keep_backups")
        return _nb_sauvegardes
    raise AttributeError(f"module {__name__!r} n'a pas d'attribut {nom!r}")
