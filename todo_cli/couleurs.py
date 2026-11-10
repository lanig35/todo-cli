"""Codes couleur ANSI et décision de les écrire ou non (terminal, NO_COLOR, --color).

Les constantes CLR_* sont vidées par `configurer_couleurs()` : les autres modules les lisent à l'appel
(`couleurs.CLR_BOLD`), jamais par `from … import`, sinon ils garderaient une copie périmée."""
import os
import sys


CLR_RESET   = "\033[0m"
CLR_BOLD    = "\033[1m"
CLR_DIM     = "\033[2m"
CLR_TODO    = "\033[93m"  # Jaune
CLR_DONE    = "\033[92m"  # Vert
CLR_DEL     = "\033[91m"  # Rouge
CLR_CYAN    = "\033[96m"  # Cyan (Bordures et en-têtes)
CLR_TAG     = "\033[95m"  # Violet pour les tags (#tag)
CLR_P_HIGH  = "\033[91m"  # Rouge (Priorité haute)
CLR_P_MED   = "\033[94m"  # Bleu (Priorité moyenne)
CLR_P_LOW   = "\033[90m"  # Gris (Priorité basse)

# Palette d'origine, conservée à part : _configurer_couleurs() vide les constantes CLR_* pour
# désactiver les couleurs, et _PALETTE permet de les restaurer ou de les réutiliser (stderr).
_PALETTE = {nom: valeur for nom, valeur in list(globals().items()) if nom.startswith("CLR_")}

# Choix explicite de l'utilisateur ('auto', 'always', 'never' ou None), fixé par main().
_mode_couleur = None

def _couleurs_activees(mode=None, flux=None):
    """Décide si les codes couleur doivent être écrits sur `flux` (stdout par défaut).

    'always' / 'never' : choix explicite, prioritaire sur tout le reste (y compris NO_COLOR).
    'auto' ou None     : couleurs seulement si le flux est un terminal, si la variable
                         d'environnement NO_COLOR n'est pas définie (valeur non vide, voir
                         no-color.org) et si TERM n'est pas 'dumb'.
    """
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    flux = flux or sys.stdout
    try:
        return bool(flux.isatty())
    except (AttributeError, ValueError):  # flux sans isatty() ou déjà fermé
        return False

def _configurer_couleurs(mode=None):
    """Active ou désactive les couleurs (stdout) en vidant ou restaurant les constantes CLR_*."""
    global _mode_couleur
    _mode_couleur = mode
    actives = _couleurs_activees(mode)
    for nom, valeur in _PALETTE.items():
        globals()[nom] = valeur if actives else ""

def _couleurs_erreur():
    """Couple (rouge, raz) pour un avertissement écrit sur stderr : sa couleur dépend de stderr, pas de stdout."""
    if _couleurs_activees(_mode_couleur, sys.stderr):
        return _PALETTE["CLR_DEL"], _PALETTE["CLR_RESET"]
    return "", ""
