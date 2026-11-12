"""Journal des actions et des erreurs, lisible avec `journalctl -t todo`.

Destinations (réglage [log] target) :
  journal   journald : champs structurés si le module `systemd` (paquet python3-systemd) est présent,
            sinon via le socket syslog (/dev/log), que journald écoute
  file      fichier tournant (~/.local/state/todo/todo.log)
  auto      journal si disponible, sinon fichier (défaut) ; off : rien

Principes :
  - jamais bloquant : si le journal est injoignable, la commande se déroule normalement ;
  - discret : par défaut, ni titres ni descriptions, seulement des identifiants ;
  - les lectures (list, show, stats…) ne sont tracées qu'au niveau debug ; remind, lancée à chaque
    ouverture du terminal, ne produit donc rien en usage normal ;
  - le logger n'est construit qu'à la première émission : une commande qui n'écrit rien ne paie rien.

Une commande produit au plus : un message par refus ou erreur (WARNING, `echec`), un message de
synthèse quand elle a modifié quelque chose (INFO), un message si elle sort en erreur (WARNING).
"""
import json
import os
import stat
import sys
import traceback
from . import reglages

_NIVEAUX = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}
_MAX_IDS = 20   # au-delà, on indique seulement le nombre (seed, archive de masse…)

_etat = {}


def _remettre_a_zero():
    _etat.clear()
    _etat.update(commande=None, ids=[], titres=[], champs={}, modifie=False, echecs=0,
                 niveau=None, titres_actifs=False, logger=None, avertissements_emis=False)


_remettre_a_zero()


# --------------------------------------------------------------------------- configuration
def initialiser():
    """Lit les réglages [log] (sans rien ouvrir) ; l'option --log-level s'ajoute ensuite avec `regler_niveau`."""
    _etat["niveau"] = reglages.obtenir("log", "level")
    _etat["titres_actifs"] = reglages.obtenir("log", "titles")


def regler_niveau(niveau_cli):
    """Applique --log-level (priorité sur la variable d'environnement et le fichier)."""
    if niveau_cli is not None:
        _etat["niveau"] = niveau_cli


def definir_commande(nom):
    _etat["commande"] = nom


def _numerique(niveau):
    return {"off": 100}.get(niveau, _NIVEAUX.get(niveau, 20))


# --------------------------------------------------------------------------- destinations
def _handler_journald():
    """Handler journald : python-systemd (champs structurés) sinon socket syslog ; None si indisponible."""
    try:
        from systemd.journal import JournalHandler   # paquet python3-systemd, facultatif
        return JournalHandler(SYSLOG_IDENTIFIER="todo")
    except Exception:
        pass
    import logging
    import logging.handlers
    socket_syslog = reglages.obtenir("log", "socket")
    try:
        if not stat.S_ISSOCK(os.stat(socket_syslog).st_mode):
            return None
        h = logging.handlers.SysLogHandler(address=socket_syslog, facility=logging.handlers.SysLogHandler.LOG_USER)
    except OSError:
        return None
    h.ident = f"todo[{os.getpid()}]: "     # journald en tire SYSLOG_IDENTIFIER=todo et _PID
    h.setFormatter(logging.Formatter("%(message)s"))
    return h


def _handler_fichier():
    import logging
    import logging.handlers
    chemin = reglages.obtenir("log", "file")
    try:
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        h = logging.handlers.RotatingFileHandler(chemin, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
    except OSError:
        return None
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s todo[%(process)d]: %(message)s", "%Y-%m-%d %H:%M:%S"))
    return h


def _logger():
    """Construit le logger à la première utilisation ; None si aucune destination n'est utilisable."""
    if _etat["logger"] is not None:
        return _etat["logger"] or None
    _etat["logger"] = False
    cible = reglages.obtenir("log", "target")
    if cible == "off":
        return None
    import logging
    logging.raiseExceptions = False          # un journal en panne ne doit jamais salir la sortie
    handler = None
    if cible in ("auto", "journal"):
        handler = _handler_journald()
        if handler is None and cible == "journal":
            print(" ⚠️  Journal système introuvable : repli sur le fichier de log.", file=sys.stderr)
    if handler is None:
        handler = _handler_fichier()
    if handler is None:
        return None
    logger = logging.Logger("todo", level=logging.DEBUG)   # filtré par nous, selon [log] level
    logger.addHandler(handler)
    _etat["logger"] = logger
    return logger


# --------------------------------------------------------------------------- émission
class _Brut(str):
    """Texte déjà formaté (JSON), à écrire tel quel, sans guillemets supplémentaires."""


def _texte(valeur):
    if isinstance(valeur, _Brut):
        return str(valeur)
    if isinstance(valeur, (list, tuple)):
        return ",".join(str(v) for v in valeur)
    texte = str(valeur)
    return json.dumps(texte, ensure_ascii=False) if (not texte or any(c in texte for c in ' "=\n')) else texte


def _emettre(niveau, evenement, champs, trace=None):
    """Écrit un message si le niveau est retenu. N'échoue jamais."""
    try:
        if _numerique(niveau) < _numerique(_etat["niveau"] or "info"):
            return
        logger = _logger()
        if logger is None:
            return
        commande = _etat["commande"] or "todo"
        morceaux = [commande] + ([evenement] if evenement else [])
        morceaux += [f"{k}={_texte(v)}" for k, v in champs.items() if v not in (None, "", [], ())]
        message = " ".join(morceaux) + (f"\n{trace}" if trace else "")
        extra = {"TODO_COMMAND": commande, "TODO_EVENT": evenement or "action"}
        extra.update({f"TODO_{k.upper()}": _texte(v) for k, v in champs.items() if v not in (None, "", [], ())})
        logger.log(_NIVEAUX[niveau], message, extra=extra)
    except Exception:
        pass


def _emettre_avertissements_de_configuration():
    if _etat["avertissements_emis"]:
        return
    _etat["avertissements_emis"] = True
    for texte in reglages.AVERTISSEMENTS:
        _emettre("warning", "config", {"detail": texte})


def id_court(cle):
    """Identifiant abrégé (8 caractères) depuis une clé DBM (bytes) ou une chaîne."""
    if isinstance(cle, (bytes, bytearray)):
        cle = cle.decode("utf-8", "replace")
    return str(cle)[:8]


# --------------------------------------------------------------------------- API
def noter(ids=None, titres=None, modifie=False, **champs):
    """Retient des informations sur l'action en cours ; elles sont écrites par `terminer`.

    `modifie=True` signale qu'une modification a eu lieu : `terminer` écrira alors un message INFO.
    Les identifiants et titres s'accumulent ; les autres champs remplacent leur valeur précédente.
    """
    if ids:
        _etat["ids"].extend(id_court(i) for i in ids)
    if titres:
        _etat["titres"].extend(titres)
    if modifie:
        _etat["modifie"] = True
    _etat["champs"].update({k: v for k, v in champs.items() if v is not None})


def echec(raison, **champs):
    """Refus ou erreur d'utilisation (WARNING), au moment où le message d'erreur est affiché."""
    _etat["echecs"] += 1
    _emettre("warning", "refus", {"reason": raison, **champs})


def terminer(code=0):
    """Écrit le message de synthèse de la commande ; à appeler une fois, à la sortie."""
    try:
        _emettre_avertissements_de_configuration()
        if _etat["modifie"]:
            champs = {}
            ids = _etat["ids"]
            if len(ids) > _MAX_IDS:
                champs["ids"], champs["count"] = ids[:_MAX_IDS], len(ids)
            else:
                champs["ids"] = ids
            if _etat["titres_actifs"] and _etat["titres"]:
                champs["titres"] = _Brut(json.dumps(_etat["titres"][:_MAX_IDS], ensure_ascii=False))
            champs.update(_etat["champs"])
            champs["exit"] = code
            _emettre("info" if code == 0 else "warning", "", champs)
        elif code == 0:
            _emettre("debug", "", {"exit": code})
        if code != 0 and not _etat["echecs"] and not _etat["modifie"]:
            _emettre("warning", "sortie", {"exit": code})     # sortie en erreur sans refus détaillé avant
    except Exception:
        pass


def critique():
    """Exception inattendue (CRITICAL) avec sa trace complète ; à appeler dans un `except Exception`."""
    _emettre("critical", "exception",
             {"type": sys.exc_info()[0].__name__ if sys.exc_info()[0] else None},
             trace=traceback.format_exc().rstrip())
