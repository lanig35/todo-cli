"""Réglages : valeurs par défaut, fichier de configuration INI, variables d'environnement.

Priorité (de la plus forte à la plus faible) :
    1. option de la ligne de commande
    2. variable d'environnement
    3. fichier de configuration
    4. valeur par défaut du programme

Fichier : option --config, sinon $TODO_CONFIG, sinon $XDG_CONFIG_HOME/todo/config.ini, sinon
~/.config/todo/config.ini.
Un fichier absent n'est pas une erreur. Une clé inconnue ou une valeur invalide (fichier ou variable
d'environnement) est signalée sur stderr, avec son origine, puis ignorée : une faute de frappe ne
doit pas empêcher d'utiliser le programme.

Ce module ne dépend d'aucun autre module du paquet : `config.py` l'utilise dès l'import pour
déterminer l'emplacement du stockage.
"""
import configparser
import difflib
import os
import re
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
    Reglage("general", "format", "choix", "auto",
            "Format de sortie par défaut : auto (text dans un terminal, plain dans un pipe), text, table ou plain.",
            choix=("auto", "text", "table", "plain")),
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
    Reglage("log", "level", "choix", "info",
            "Niveau du journal : off, error, warning, info (actions et erreurs) ou debug (ajoute les lectures).",
            choix=("off", "error", "warning", "info", "debug")),
    Reglage("log", "target", "choix", "auto",
            "Destination : auto (journald/syslog si disponible, sinon fichier), journal, file ou off.",
            choix=("auto", "journal", "file", "off")),
    Reglage("log", "file", "chemin", lambda: os.path.join(os.environ.get("XDG_STATE_HOME") or "~/.local/state", "todo", "todo.log"),
            "Fichier de log (destination file, ou repli quand il n'y a pas de journal système)."),
    Reglage("log", "socket", "chemin", "/dev/log",
            "Socket syslog utilisé pour atteindre journald (rarement à changer)."),
    Reglage("log", "titles", "bool", False,
            "Inclure les titres des tâches dans le journal (par défaut : identifiants seulement, par discrétion)."),
)
_PAR_CLE = {(r.section, r.cle): r for r in REGLAGES}
SECTIONS = tuple(dict.fromkeys(r.section for r in REGLAGES))

_VRAI = {"1", "true", "yes", "on", "oui", "vrai"}
_FAUX = {"0", "false", "no", "off", "non", "faux"}


def nom_variable(section, cle):
    """Nom de la variable d'environnement d'un réglage : TODO_DB_DIR (section general), TODO_LIST_LIMIT…"""
    return "TODO_" + (cle if section == "general" else f"{section}_{cle}").upper()


def _option_config(argv):
    """Valeur de `--config` dans la ligne de commande (`--config F` ou `--config=F`), ou None.

    Lue ici, à l'import, parce que le stockage (`config.py`) interroge les réglages dès qu'il est importé,
    donc avant l'analyse des arguments : l'option doit déjà être connue à ce moment-là.
    """
    for i, a in enumerate(argv):
        if a == "--":
            break
        if a == "--config" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--config="):
            return a[len("--config="):]
    return None


FICHIER_OPTION = _option_config(sys.argv[1:])    # fichier imposé par --config (prioritaire sur TODO_CONFIG)


def definir_fichier(chemin):
    """Impose le fichier de configuration (option --config) et oublie ce qui avait été lu."""
    global FICHIER_OPTION, _cache
    FICHIER_OPTION, _cache = chemin, None


def origine_chemin_config():
    """D'où vient le chemin du fichier : 'option --config', 'variable TODO_CONFIG' ou 'défaut'."""
    if FICHIER_OPTION:
        return "option --config"
    return "variable TODO_CONFIG" if os.environ.get("TODO_CONFIG") else "défaut"


def chemin_config():
    """Chemin du fichier de configuration (qu'il existe ou non)."""
    explicite = FICHIER_OPTION or os.environ.get("TODO_CONFIG")
    if explicite:
        return os.path.abspath(os.path.expanduser(explicite))
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "todo", "config.ini")


AVERTISSEMENTS = []   # messages déjà affichés, relus par `journal` une fois le journal initialisé


def _avertir(message):
    AVERTISSEMENTS.append(message)
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
    defaut = reglage.defaut() if callable(reglage.defaut) else reglage.defaut
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
            defaut = r.defaut() if callable(r.defaut) else r.defaut
            defaut = str(defaut).lower() if r.type == "bool" else defaut
            lignes.append(f"# {r.cle} = {defaut}")
            lignes.append("")
    return "\n".join(lignes)


# --------------------------------------------------------------------------- lecture et écriture d'un réglage
def cles():
    """Les clés « section.clé » de tous les réglages."""
    return [f"{r.section}.{r.cle}" for r in REGLAGES]


def trouver(cle):
    """Le réglage de la clé « section.clé » ; ValueError (avec suggestion) si elle est inconnue."""
    section, _, nom = cle.strip().lower().partition(".")
    reglage = _PAR_CLE.get((section, nom))
    if reglage is None:
        proche = difflib.get_close_matches(cle.strip().lower(), cles(), n=1)
        raise ValueError(f"réglage inconnu '{cle}'" + (f" (vouliez-vous dire '{proche[0]}' ?)" if proche else "")
                         + " ; `todo config show` les liste")
    return reglage


def valeur_du_fichier(reglage):
    """La valeur du réglage dans le fichier de configuration, ou None s'il n'y figure pas."""
    return _charger_fichier().get((reglage.section, reglage.cle))


def texte_a_ecrire(reglage, texte):
    """Valide `texte` et renvoie sa forme écrite dans le fichier ; ValueError si la valeur est invalide."""
    valeur = convertir(reglage, texte)
    if reglage.type == "bool":
        return "true" if valeur else "false"
    return texte.strip() if reglage.type == "chemin" else str(valeur)


_SECTION = re.compile(r"^\s*\[(?P<nom>[^\]]+)\]")


def _reperer(lignes, section, cle):
    """(début de la section ou None, fin de la section, lignes actives de la clé, ligne du modèle commenté ou None).

    Les lignes de continuation d'une valeur (indentées) sont rattachées à la ligne de la clé.
    """
    debut, fin, actives, commentee = None, len(lignes), [], None
    ligne_cle = re.compile(rf"^{re.escape(cle)}\s*[=:]", re.IGNORECASE)
    ligne_modele = re.compile(rf"^\s*[#;]\s*{re.escape(cle)}\s*[=:]", re.IGNORECASE)
    for i, ligne in enumerate(lignes):
        m = _SECTION.match(ligne)
        if m:
            if debut is not None:
                fin = i
                break
            if m.group("nom").strip().lower() == section:
                debut = i
            continue
        if debut is None:
            continue
        if ligne_cle.match(ligne):
            actives.append([i, i])
        elif actives and ligne[:1] in (" ", "\t") and ligne.strip() and not ligne.lstrip().startswith(("#", ";")) \
                and actives[-1][1] == i - 1:
            actives[-1][1] = i
        elif ligne_modele.match(ligne):
            commentee = i
    return debut, fin, actives, commentee


def modifier_texte(contenu, section, cle, valeur):
    """Contenu du fichier avec le réglage fixé à `valeur` (ou supprimé si `valeur` est None).

    Seules les lignes du réglage sont touchées : commentaires, ordre et autres clés restent tels quels.
    Retourne (nouveau contenu, ancien texte de la valeur ou None).
    """
    lignes = contenu.split("\n")
    debut, fin, actives, commentee = _reperer(lignes, section, cle)
    ancien = None
    if actives:
        premiere = lignes[actives[-1][0]]
        sep = min((premiere.find(c) for c in "=:" if c in premiere), default=-1)
        ancien = premiere[sep + 1:].strip() if sep >= 0 else None
    if valeur is None:
        for debut_a, fin_a in reversed(actives):
            del lignes[debut_a:fin_a + 1]
        return "\n".join(lignes), ancien
    nouvelle = f"{cle} = {valeur}"
    if actives:
        (premier, _), *reste = actives
        for debut_a, fin_a in reversed(reste):         # doublons : la dernière occurrence l'emportait déjà
            del lignes[debut_a:fin_a + 1]
        fin_p = actives[0][1]
        lignes[premier:fin_p + 1] = [nouvelle]
    elif debut is not None:
        if commentee is not None:                      # juste sous la valeur par défaut commentée du modèle
            lignes.insert(commentee + 1, nouvelle)
        else:                                          # sinon à la fin de la section, avant les lignes vides finales
            pos = fin
            while pos - 1 > debut and not lignes[pos - 1].strip():
                pos -= 1
            lignes.insert(pos, nouvelle)
    else:
        while lignes and not lignes[-1].strip():
            lignes.pop()
        lignes += ([""] if lignes else []) + [f"[{section}]", nouvelle, ""]
    return "\n".join(lignes), ancien
