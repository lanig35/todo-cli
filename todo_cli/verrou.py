"""Verrou de la base : une seule instance de todo écrit à la fois (flock sur `todo.lock`).

DBM n'est pas conçu pour des écritures concurrentes : deux commandes lancées en même temps (cron, deux
terminaux, un outil de synchronisation) pouvaient s'écraser ou échouer. Chaque commande qui touche à la
base prend donc, au démarrage, un verrou sur un fichier du dossier de stockage :

  - **partagé** pour les commandes de lecture (`list`, `show`, `next`, `agenda`, `stats`, `export`…) :
    elles peuvent s'exécuter ensemble ;
  - **exclusif** pour toutes les autres : elles attendent la fin des lectures et des autres écritures.

Le verrou est libéré par le système à la fin du processus, même après un plantage ou un Ctrl+C : il n'y
a jamais de verrou périmé à supprimer à la main. L'attente est bornée par [general] lock_timeout
(10 s par défaut) ; au-delà, la commande échoue proprement (code 1) au lieu de rester bloquée.
Le verrou est consultatif et propre à une machine : il ne protège pas un dossier partagé en réseau
dont le système de fichiers ne gère pas flock.
"""
import os
import sys
import time

try:
    import fcntl
except ImportError:               # plateforme sans fcntl (Windows) : pas de verrou
    fcntl = None

from . import couleurs, journal
from . import config

PARTAGE, EXCLUSIF = "shared", "exclusive"

_descripteur = None               # le verrou vit autant que le processus


def prendre(mode, delai):
    """Prend le verrou `mode` (PARTAGE ou EXCLUSIF), en attendant au plus `delai` secondes.

    Sort avec le code 1 si le verrou n'est pas obtenu à temps. Sans fcntl, ou si le fichier de verrou
    ne peut pas être créé (dossier en lecture seule), la commande continue sans verrou.
    """
    global _descripteur
    if fcntl is None or _descripteur is not None:
        return
    try:
        fd = os.open(config.LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return
    drapeau = fcntl.LOCK_SH if mode == PARTAGE else fcntl.LOCK_EX
    limite = time.monotonic() + max(0, delai)
    while True:
        try:
            fcntl.flock(fd, drapeau | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= limite:
                os.close(fd)
                journal.echec("db_locked", timeout=delai, mode=mode)
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} la base est utilisée par une autre instance de todo "
                      f"(attente de {delai} s dépassée). Réessayez, ou augmentez le réglage general.lock_timeout.",
                      file=sys.stderr)
                sys.exit(1)
            time.sleep(0.05)
        except OSError:           # flock non pris en charge par ce système de fichiers : on continue sans
            os.close(fd)
            return
    _descripteur = fd


def liberer():
    """Relâche le verrou (utile aux tests ; le système le fait de toute façon à la fin du processus)."""
    global _descripteur
    if _descripteur is not None:
        os.close(_descripteur)
        _descripteur = None
