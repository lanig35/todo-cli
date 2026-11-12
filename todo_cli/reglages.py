"""Réglages : valeurs par défaut, fichier de configuration INI, variables d'environnement.

Priorité (de la plus forte à la plus faible) :
    1. option de la ligne de commande
    2. variable d'environnement
    3. fichier de configuration
    4. valeur par défaut du programme

Fichier : $TODO_CONFIG, sinon $XDG_CONFIG_HOME/todo/config.ini, sinon ~/.config/todo/config.ini.
Un fichier absent n'est pas une erreur. Une clé inconnue ou une valeur invalide (fichier ou variable
d'environnement) est signalée sur stderr, avec son origine, puis ignorée : une faute de frappe ne
doit pas empêcher d'utiliser le programme.

Ce module ne dépend d'aucun autre module du paquet : `config.py` l'utilise dès l'import pour
déterminer l'emplacement du stockage.
"""
import configparser
import difflib
import os
import sys
from typing import NamedTuple, Optional, Tuple


class Reglage(NamedTuple):
    section: str
    cle: str
    type: str                 # "bool", "int", "choix" ou "chemin"
    defaut: object
    aide: str
    choix: Optional[tuple] = None
    minimum: Optional[int] = None
    maximum: Optional[int] = None


REGLAGES = (
    Reglage("general", "db_dir", "chemin", "~/.local/share/todo",
            "Dossier de stockage : base, archive, sauvegardes et état du rappel."),
    Reglage("general", "color", "choix", "auto",
            "Couleurs : auto (seulement dans un terminal, sauf NO_COLOR), always ou never.",
            choix=("auto", "always", "never")),
    Reglage("general", "pager", "bool", True,
            "Utiliser un pager (less, ou $PAGER) quand un affichage dépasse l'écran."),
    Reglage("general", "keep_backups", "int", 5,
            "Nombre de sauvegardes conservées (au moins 2, pour que undo reste possible).", minimum=2),
    Reglage("list", "limit", "int", 0,
            "Nombre maximal de tâches affichées par list ; 0 = pas de limite.", minimum=0),
    Reglage("list", "overdue_first", "bool", True,
            "Placer les tâches en retard en tête de list."),
    Reglage("add", "priority", "choix", "medium",
            "Priorité des nouvelles tâches quand elle n'est précisée ni par --prio ni dans le titre.",
            choix=("low", "medium", "high")),
    Reglage("agenda", "days", "int", 7,
            "Nombre de jours affichés par agenda.", minimum=1, maximum=366),
    Reglage("next", "count", "int", 1,
            "Nombre de tâches affichées par next.", minimum=1),
    Reglage("remind", "enabled", "bool", True,
            "Activer les rappels (remind). Désactivés aussi par `todo remind --disable` ou TODO_NO_REMIND."),
    Reglage("remind", "limit", "int", 5,
            "Nombre maximal de tâches listées par remind.", minimum=1),
    Reglage("remind", "soon", "int", 0,
            "Signaler aussi les échéances des N prochains jours ; 0 = retards et aujourd'hui seulement.", minimum=0),
)
_PAR_CLE = {(r.section, r.cle): r for r in REGLAGES}
SECTIONS = tuple(dict.fromkeys(r.section for r in REGLAGES))

_VRAI = {"1", "true", "yes", "on", "oui", "vrai"}
_FAUX = {"0", "false", "no", "off", "non", "faux"}


def nom_variable(section, cle):
    """Nom de la variable d'environnement d'un réglage : TODO_DB_DIR (section general), TODO_LIST_LIMIT…"""
    return "TODO_" + (cle if section == "general" else f"{section}_{cle}").upper()


def chemin_config():
    """Chemin du fichier de configuration (qu'il existe ou non)."""
    explicite = os.environ.get("TODO_CONFIG")
    if explicite:
        return os.path.abspath(os.path.expanduser(explicite))
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "todo", "config.ini")


def _avertir(message):
    print(f" ⚠️  {message}", file=sys.stderr)


def convertir(reglage, texte):
    """Convertit un texte en valeur du type du réglage ; lève ValueError (message lisible) sinon."""
    brut = texte.strip()
    if reglage.type == "bool":
        if brut.lower() in _VRAI:
            return True
        if brut.lower() in _FAUX:
            return False
        raise ValueError(f"'{brut}' n'est pas un booléen (true/false, yes/no, on/off, 1/0)")
    if reglage.type == "int":
        try:
            n = int(brut)
        except ValueError:
            raise ValueError(f"'{brut}' n'est pas un entier") from None
        if reglage.minimum is not None and n < reglage.minimum:
            raise ValueError(f"{n} est inférieur au minimum ({reglage.minimum})")
        if reglage.maximum is not None and n > reglage.maximum:
            raise ValueError(f"{n} est supérieur au maximum ({reglage.maximum})")
        return n
    if reglage.type == "choix":
        if brut.lower() not in reglage.choix:
            raise ValueError(f"'{brut}' n'est pas dans : {', '.join(reglage.choix)}")
        return brut.lower()
    if not brut:
        raise ValueError("valeur vide")
    return os.path.abspath(os.path.expanduser(brut))  # chemin


# --------------------------------------------------------------------------- fichier
_cache = None


def _charger_fichier():
    """Lit le fichier une seule fois : {(section, cle): valeur convertie}. Signale les problèmes sur stderr."""
    global _cache
    if _cache is not None:
        return _cache
    _cache = {}
    chemin = chemin_config()
    if not os.path.isfile(chemin):
        return _cache
    lecteur = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#", ";"), strict=False)
    try:
        with open(chemin, encoding="utf-8") as f:
            lecteur.read_file(f)
    except (configparser.Error, OSError, UnicodeDecodeError) as e:
        _avertir(f"Configuration {chemin} ignorée : {' '.join(str(e).split())}")
        return _cache

    for section in lecteur.sections():
        nom_section = section.strip().lower()
        if nom_section not in SECTIONS:
            proche = difflib.get_close_matches(nom_section, SECTIONS, n=1)
            _avertir(f"Configuration {chemin} : section inconnue [{section}] ignorée"
                     + (f" (vouliez-vous dire [{proche[0]}] ?)" if proche else "") + ".")
            continue
        for cle, valeur in lecteur.items(section):
            reglage = _PAR_CLE.get((nom_section, cle))
            if reglage is None:
                proches = difflib.get_close_matches(cle, [r.cle for r in REGLAGES if r.section == nom_section], n=1)
                _avertir(f"Configuration {chemin} : clé inconnue '{cle}' dans [{section}] ignorée"
                         + (f" (vouliez-vous dire '{proches[0]}' ?)" if proches else "") + ".")
                continue
            try:
                _cache[(nom_section, cle)] = convertir(reglage, valeur)
            except ValueError as e:
                _avertir(f"Configuration {chemin} : [{section}] {cle} ignorée : {e}.")
    return _cache


# --------------------------------------------------------------------------- résolution
def obtenir_avec_origine(section, cle, cli=None) -> Tuple[object, str]:
    """Valeur effective d'un réglage et son origine : 'option', 'variable X', 'fichier' ou 'défaut'.

    `cli` est la valeur de l'option de la ligne de commande, ou None si elle n'a pas été donnée.
    Cas particuliers : color tient compte de NO_COLOR (entre TODO_COLOR et le fichier) ;
    remind.enabled est coupé par TODO_NO_REMIND, quoi qu'il arrive.
    """
    reglage = _PAR_CLE[(section, cle)]
    if cli is not None:
        return cli, "option"

    if (section, cle) == ("remind", "enabled") and os.environ.get("TODO_NO_REMIND"):
        return False, "variable TODO_NO_REMIND"

    variable = nom_variable(section, cle)
    texte = os.environ.get(variable)
    if texte:
        try:
            return convertir(reglage, texte), f"variable {variable}"
        except ValueError as e:
            _avertir(f"Variable {variable} ignorée : {e}.")

    if (section, cle) == ("general", "color") and os.environ.get("NO_COLOR"):
        return "never", "variable NO_COLOR"

    fichier = _charger_fichier()
    if (section, cle) in fichier:
        return fichier[(section, cle)], "fichier"
    defaut = reglage.defaut
    return (convertir(reglage, defaut) if reglage.type == "chemin" else defaut), "défaut"


def obtenir(section, cle, cli=None):
    """Valeur effective d'un réglage (voir `obtenir_avec_origine`)."""
    return obtenir_avec_origine(section, cle, cli)[0]


def modele_fichier():
    """Contenu d'un fichier de configuration modèle : toutes les valeurs par défaut, en commentaire."""
    lignes = ["# Configuration de todo-cli (format INI).",
              "#",
              "# Priorité : option de la ligne de commande > variable d'environnement > ce fichier > défaut.",
              "# Les lignes ci-dessous sont en commentaire et montrent les valeurs par défaut :",
              "# décommentez-en une et changez sa valeur pour l'appliquer.",
              "# Booléens : true/false, yes/no, on/off, 1/0.", ""]
    for section in SECTIONS:
        lignes.append(f"[{section}]")
        for r in (r for r in REGLAGES if r.section == section):
            lignes.append(f"# {r.aide}")
            lignes.append(f"# Variable d'environnement : {nom_variable(r.section, r.cle)}")
            defaut = str(r.defaut).lower() if r.type == "bool" else r.defaut
            lignes.append(f"# {r.cle} = {defaut}")
            lignes.append("")
    return "\n".join(lignes)
