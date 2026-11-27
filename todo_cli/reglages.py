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

from .formats import CHAMPS_TACHES, COLONNES_DEFAUT, colonnes_tache


COMPLETION = bool(os.environ.get("_ARGCOMPLETE"))   # le shell complète une ligne : rien ne doit s'afficher


class Reglage(NamedTuple):
    section: str
    cle: str
    type: str                 # "bool", "int", "choix", "chemin", "texte", "colonnes" ou "projet"
    defaut: object
    aide: str
    choix: Optional[tuple] = None
    minimum: Optional[int] = None
    maximum: Optional[int] = None


REGLAGES = (
    Reglage("general", "db_dir", "chemin", "~/.local/share/todo",
            "Dossier de stockage : base, archive, sauvegardes et état du rappel."),
    Reglage("general", "project", "projet", "default",
            "Projet courant (liste de tâches) : default, ou un projet créé avec `todo project create`. "
            "`todo project use NOM` l'écrit ici."),
    Reglage("general", "color", "choix", "auto",
            "Couleurs : auto (seulement dans un terminal, sauf NO_COLOR), always ou never.",
            choix=("auto", "always", "never")),
    Reglage("general", "format", "choix", "auto",
            "Format de sortie par défaut : auto (text dans un terminal, plain dans un pipe), text, table ou plain.",
            choix=("auto", "text", "table", "plain")),
    Reglage("general", "columns", "colonnes", ",".join(COLONNES_DEFAUT),
            "Colonnes par défaut des formats table et plain (list, next, archive list), séparées par des virgules : "
            + ", ".join(CHAMPS_TACHES) + ". L'id est toujours présent."),
    Reglage("general", "pager", "bool", True,
            "Utiliser un pager (less, ou $PAGER) quand un affichage dépasse l'écran."),
    Reglage("general", "keep_backups", "int", 5,
            "Nombre de sauvegardes conservées (au moins 2, pour que undo reste possible).", minimum=2),
    Reglage("general", "lock_timeout", "int", 10,
            "Secondes d'attente du verrou de la base si une autre instance de todo l'utilise ; 0 = échouer tout de suite.",
            minimum=0),
    Reglage("general", "batch_confirm", "int", 5,
            "Actions en lot par filtre (done --tag x…) : confirmation demandée à partir de ce nombre de tâches ; 0 = jamais (-y la passe).",
            minimum=0),
    Reglage("list", "limit", "int", 0,
            "Nombre maximal de tâches affichées par list ; 0 = pas de limite.", minimum=0),
    Reglage("list", "overdue_first", "bool", True,
            "Placer les tâches en retard en tête de list."),
    Reglage("add", "priority", "choix", "medium",
            "Priorité des nouvelles tâches quand elle n'est précisée ni par --prio ni dans le titre.",
            choix=("low", "medium", "high")),
    Reglage("add", "date_prefix", "choix", "optional",
            "Saisie rapide : optional (`demain` et `@demain` sont des dates) ou required (seule `@demain` en est une ; `demain` reste dans le titre).",
            choix=("optional", "required")),
    Reglage("archive", "auto_days", "int", 0,
            "Archivage automatique : archive les tâches terminées depuis au moins N jours, une fois par jour, à la première "
            "commande de modification ; 0 = désactivé.", minimum=0),
    Reglage("agenda", "days", "int", 7,
            "Nombre de jours affichés par agenda.", minimum=1, maximum=366),
    Reglage("next", "count", "int", 1,
            "Nombre de tâches affichées par next.", minimum=1),
    Reglage("remind", "enabled", "bool", True,
            "Activer les rappels (remind). Désactivés aussi par `todo reminder disable` ou TODO_NO_REMIND."),
    Reglage("remind", "limit", "int", 5,
            "Nombre maximal de tâches listées par remind.", minimum=1),
    Reglage("remind", "soon", "int", 0,
            "Signaler aussi les échéances des N prochains jours ; 0 = retards et aujourd'hui seulement.", minimum=0),
    Reglage("review", "days", "int", 7,
            "Durée de la revue hebdomadaire (report review), en jours : semaine écoulée et semaine à venir.", minimum=1, maximum=90),
    Reglage("review", "stale", "texte", "30d",
            "Âge à partir duquel une tâche sans échéance « traîne » dans la revue (ex. 30d, 6w, 2025-01-01)."),
    Reglage("review", "limit", "int", 10,
            "Nombre maximal de tâches par section de la revue (texte seulement).", minimum=1),
    Reglage("review", "day", "choix", "",
            "Jour de la revue (mon … sun) : `todo reminder check` le signale ce jour-là ; vide = pas de rappel de revue.",
            choix=("", "mon", "tue", "wed", "thu", "fri", "sat", "sun")),
    Reglage("attachments", "max_size", "int", 10,
            "Taille maximale d'une pièce jointe, en Mo (todo attachment add) ; 0 = pas de limite.", minimum=0),
    Reglage("attachments", "opener", "texte", "",
            "Commande qui ouvre une pièce jointe (`todo attachment open`), par exemple `less` ou `evince` ; vide = xdg-open dans une "
            "session graphique, sinon le chemin du fichier est seulement affiché."),
    Reglage("client", "url", "texte", "http://127.0.0.1:8765", "Adresse du serveur `todo serve` pour la TUI (`todo tui`)."),
    Reglage("client", "token", "texte", "",
            "Jeton de l'API pour `todo tui` (à défaut : [server] token / TODO_SERVER_TOKEN) ; de préférence via TODO_CLIENT_TOKEN."),
    Reglage("client", "timeout", "int", 15, "Secondes d'attente d'une réponse du serveur.", minimum=1),
    Reglage("server", "host", "texte", "127.0.0.1",
            "Adresse d'écoute de `todo serve` (API REST) ; 127.0.0.1 = cette machine seulement."),
    Reglage("server", "port", "int", 8765, "Port d'écoute de `todo serve`.", minimum=1, maximum=65535),
    Reglage("server", "token", "texte", "",
            "Jeton obligatoire de l'API (en-tête `Authorization: Bearer …`) ; de préférence via TODO_SERVER_TOKEN "
            "plutôt que dans le fichier de configuration."),
    Reglage("server", "web", "bool", True, "Sert aussi l'interface web (connexion par le jeton) ; false = API seule."),
    Reglage("server", "proxy", "bool", False,
            "Derrière un proxy HTTPS de confiance (nginx, Caddy…) : lit X-Forwarded-For/Proto/Host et marque le cookie de session « Secure »."),
    Reglage("server", "timeout", "int", 30, "Secondes accordées à une requête avant de l'interrompre (erreur 504).", minimum=1),
    Reglage("server", "max_body", "int", 65536, "Taille maximale du corps d'une requête, en octets.", minimum=1024),
    Reglage("hooks", "enabled", "bool", True,
            "Activer les hooks (commandes lancées après une modification) ; désactive tout sans effacer les réglages."),
    Reglage("hooks", "timeout", "int", 10,
            "Secondes accordées à un hook avant de l'interrompre (avertissement, la commande todo n'est pas affectée).", minimum=1),
    *(Reglage("hooks", f"on_{evt}", "texte", "",
              f"Commande lancée pour chaque tâche touchée par `{cmd}` (voir README : variables TODO_* et JSON sur l'entrée "
              "standard ; pas de shell, utiliser `sh -c '…'` pour des variables ou des pipes).")
      for evt, cmd in (("add", "add"), ("done", "done"), ("undone", "task undone"), ("start", "task start"),
                       ("unstart", "task unstart"), ("edit", "task edit"), ("postpone", "postpone"),
                       ("remove", "task remove"), ("move", "task move"))),
    Reglage("hooks", "before_add", "texte", "",
            "Commande lancée AVANT `add` : un code de sortie non nul refuse l'ajout (la tâche à créer est sur l'entrée standard)."),
    Reglage("hooks", "before_done", "texte", "",
            "Commande lancée AVANT `done`, pour chaque tâche : un code de sortie non nul refuse de la terminer."),
    Reglage("hooks", "on_change", "texte", "",
            "Commande lancée après toute commande qui modifie quelque chose (en plus du hook propre à la commande) ; "
            "une seule fois si la commande ne vise aucune tâche (import, undo, archive…)."),
    Reglage("hooks", "webhook_url", "texte", "",
            "Adresse http(s) qui reçoit un POST JSON après chaque modification (ex. http://localhost:8080/todo) ; vide = désactivé."),
    Reglage("hooks", "webhook_events", "texte", "",
            "Événements envoyés au webhook, séparés par des virgules (add, done, undone, start, unstart, edit, postpone, remove, "
            "move ; `change` = tout) ; vide = tout."),
    Reglage("hooks", "webhook_token", "texte", "",
            "Jeton envoyé dans l'en-tête `Authorization: Bearer …` du webhook ; vide = aucun en-tête."),
    Reglage("hooks", "webhook_secret", "texte", "",
            "Secret de signature du webhook : en-tête `X-Todo-Signature: sha256=<HMAC-SHA256 du corps>` ; vide = non signé."),
    Reglage("hooks", "webhook_retry", "bool", True,
            "Garder dans une file (webhook_queue.json) les événements dont l'envoi échoue, et les renvoyer plus tard."),
    Reglage("hooks", "webhook_queue_max", "int", 500,
            "Nombre maximal d'événements gardés dans la file du webhook (les plus anciens sont abandonnés).", minimum=1),
    Reglage("hooks", "webhook_retention", "int", 7,
            "Jours pendant lesquels un événement reste dans la file du webhook avant d'être abandonné.", minimum=1),
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


def _arguments():
    """Arguments de la commande ; pendant une complétion du shell, ceux de la ligne en cours de saisie."""
    if COMPLETION:
        try:
            import shlex
            return shlex.split(os.environ.get("COMP_LINE", ""))[1:]
        except ValueError:
            return []
    return sys.argv[1:]


FICHIER_OPTION = _option_config(_arguments())    # fichier imposé par --config (prioritaire sur TODO_CONFIG)


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
    if not COMPLETION:
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
    if reglage.type == "colonnes":
        return ",".join(colonnes_tache(brut))      # forme normalisée : id en tête s'il manquait, sans doublon
    if reglage.type == "projet":
        from .config import valider_nom
        return valider_nom(brut)
    if reglage.type == "texte":
        return brut
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
