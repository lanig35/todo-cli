"""Hooks : une commande de votre choix lancée après une modification (notification, synchro, journal perso…).

Réglages ([hooks] du fichier de configuration, ou variables TODO_HOOKS_ON_DONE…) :
  on_add, on_done, on_undone, on_start, on_unstart, on_edit, on_postpone, on_remove, on_move
      commande lancée pour CHAQUE tâche touchée par la commande correspondante ;
  on_change
      commande lancée après toute commande qui modifie quelque chose (en plus de la précédente), une seule fois
      si la commande ne vise aucune tâche (import, undo, archive…) ;
  timeout (10 s), enabled (true).

La commande est découpée comme le fait un shell (shlex) mais n'est PAS passée à un shell : pour des variables ou des
pipes, écrire `sh -c '…'`. Rien n'est jamais inséré dans la commande : les données passent par l'environnement
(TODO_EVENT, TODO_ID, TODO_TITLE, TODO_PROJECT, TODO_COUNT, TODO_IDS, TODO_VERSION) et par l'entrée standard (la tâche en
JSON, comme `show --format json`, ou `{"id", "titre"}` si elle n'existe plus ou a changé de projet) : un titre
malicieux ne peut donc pas injecter de commande.

Garde-fous : un hook ne change jamais le résultat de la commande (échec, délai dépassé et commande introuvable ne
produisent qu'un avertissement sur stderr et dans le journal) ; sa sortie standard est renvoyée sur stderr pour ne pas
polluer `--format json` ; un hook qui lance `todo` ne déclenche pas de hook (TODO_IN_HOOK) ; plus de 20 tâches touchées :
une seule exécution, avec TODO_COUNT et TODO_IDS.
"""
import dbm
import json
import os
import shlex
import subprocess
import sys

from . import config, couleurs, journal, reglages, verrou, webhook
from .stockage import _normaliser_tache

EVENEMENTS = ("add", "done", "undone", "start", "unstart", "edit", "postpone", "remove", "move")
MAX_EXECUTIONS = 20


def _commande(reglage):
    texte = reglages.obtenir('hooks', reglage)
    if not texte:
        return None
    try:
        return shlex.split(texte)
    except ValueError as e:
        _avertir(reglage, f"commande invalide ({e})")
        return None


_avertir = webhook.avertir


def _tache(identifiant, titre):
    """(id complet, JSON de la tâche) depuis la base du projet courant ; à défaut (supprimée, déplacée), ce que le journal sait d'elle.

    Recherche silencieuse : un hook ne doit jamais écrire de message d'erreur ni noter d'échec à la place de la commande.
    """
    try:
        if os.path.exists(config.DB_NAME) or os.path.exists(config.DB_NAME + ".db"):
            with dbm.open(config.DB_NAME, 'r') as db:
                cles = [k for k in db.keys() if k.decode('utf-8', errors='replace').startswith(identifiant)]
                if len(cles) == 1:
                    t = _normaliser_tache(db[cles[0]])
                    t['id'] = cles[0].decode('utf-8', errors='replace')
                    return t['id'], t
    except Exception:
        pass
    return identifiant, {"id": identifiant, "titre": titre or ""}


def _environnement(reglage, evenement, id_complet, titre, nombre, ids, projet, phase="after"):
    env = dict(os.environ)
    env.update(TODO_EVENT=evenement, TODO_ID=id_complet or "", TODO_TITLE=titre or "", TODO_PROJECT=projet,
               TODO_COUNT=str(nombre), TODO_IDS=",".join(ids), TODO_IN_HOOK="1", TODO_HOOK=reglage, TODO_PHASE=phase)
    return env


def _lancer(reglage, commande, evenement, id_complet, titre, nombre, ids, projet, entree):
    env = _environnement(reglage, evenement, id_complet, titre, nombre, ids, projet)
    try:
        sys.stdout.flush()
        resultat = subprocess.run(commande, input=json.dumps(entree, ensure_ascii=False).encode(), env=env,
                                  stdout=sys.stderr, timeout=reglages.obtenir('hooks', 'timeout'))
        if resultat.returncode != 0:
            _avertir(reglage, f"« {commande[0]} » a retourné le code {resultat.returncode}")
    except subprocess.TimeoutExpired:
        _avertir(reglage, f"« {commande[0]} » interrompue après {reglages.obtenir('hooks', 'timeout')} s")
    except OSError as e:
        _avertir(reglage, f"impossible de lancer « {commande[0]} » : {e.strerror or e}")


AVANT = ("add", "done")                  # événements qui ont un hook « avant »


def _refuser(reglage, raison, message, **champs):
    rouge, raz = couleurs._couleurs_erreur()
    print(f" {rouge}❌ Refusé par le hook {reglage} :{raz} {message}", file=sys.stderr)
    journal.echec(raison, hook=reglage, **champs)
    return False


def avant(evenement, identifiant, tache, nombre=1, ids=()):
    """Hook « before_<événement> » : lancé AVANT que la commande modifie quoi que ce soit.

    Retourne True si l'action peut avoir lieu, False si elle est refusée (le message est déjà affiché et l'échec noté au journal).
    Un code de sortie non nul refuse l'action ; un hook introuvable, mal écrit ou trop lent la refuse aussi (par précaution :
    `TODO_HOOKS_ENABLED=0` permet de passer outre en cas de besoin). Rien n'est lancé sans hook défini, ni pour un hook qui
    appelle `todo` lui-même (TODO_IN_HOOK), ni quand `[hooks] enabled` est faux.
    """
    reglage = "before_" + evenement

    def texte_de(x):
        return x.decode("utf-8", errors="replace") if isinstance(x, (bytes, bytearray)) else str(x)

    try:
        texte = reglages.obtenir('hooks', reglage)
        if not texte or os.environ.get("TODO_IN_HOOK") or not reglages.obtenir('hooks', 'enabled'):
            return True
        try:
            commande = shlex.split(texte)
        except ValueError as e:
            return _refuser(reglage, "hook_invalid", f"commande invalide ({e}).")
        if not commande:
            return True
        identifiant = texte_de(identifiant)
        tache = {**tache, "id": identifiant}
        env = _environnement(reglage, evenement, identifiant, tache.get('titre', ""), nombre,
                             [texte_de(i) for i in ids] or [identifiant], config.projet(), phase="before")
        delai = reglages.obtenir('hooks', 'timeout')
        sys.stdout.flush()
        try:
            resultat = subprocess.run(commande, input=json.dumps(tache, ensure_ascii=False).encode(), env=env,
                                      stdout=sys.stderr, timeout=delai)
        except subprocess.TimeoutExpired:
            return _refuser(reglage, "hook_timeout", f"« {commande[0]} » interrompue après {delai} s, action refusée par précaution "
                            f"(TODO_HOOKS_ENABLED=0 pour passer outre).", timeout=delai)
        except OSError as e:
            return _refuser(reglage, "hook_unavailable", f"impossible de lancer « {commande[0]} » : {e.strerror or e} "
                            f"(TODO_HOOKS_ENABLED=0 pour passer outre).")
        if resultat.returncode != 0:
            return _refuser(reglage, "hook_refused", f"« {commande[0]} » a retourné le code {resultat.returncode}.", code=resultat.returncode)
        return True
    except Exception as e:                                  # un bug ici ne doit pas laisser passer une action qu'un hook devait contrôler
        return _refuser(reglage, "hook_error", f"erreur interne ({e}).")


def declencher():
    """Lance les hooks de la commande qui vient de s'exécuter, si elle a modifié quelque chose. Ne lève jamais."""
    try:
        bilan = journal.bilan()
        if (not bilan["modifie"] or os.environ.get("TODO_IN_HOOK") or not reglages.obtenir('hooks', 'enabled')
                or not bilan["commande"]):
            return
        if bilan["commande"].startswith("view_"):          # les vues sont des préférences, pas des tâches
            return
        evenement, ids, titres, complets = bilan["commande"], bilan["ids"], bilan["titres"], bilan["ids_complets"]
        if len(complets) == len(ids):                      # identifiants complets quand le journal les a (tâche supprimée comprise)
            ids = complets
        specifique = _commande("on_" + evenement) if evenement in EVENEMENTS and ids else None
        general = _commande("on_change")
        if not specifique and not general and not webhook.url_configuree():
            return
        verrou.liberer()          # la commande a fini avec la base : un hook qui appelle `todo` ne doit pas attendre ce verrou
        projet = config.projet()
        a_lancer = [(nom, cmd) for nom, cmd in (("on_" + evenement, specifique), ("on_change", general)) if cmd]
        alignes = len(titres) == len(ids)
        resolues = None

        def taches():
            nonlocal resolues
            if resolues is None:
                resolues = [_tache(court, titres[i] if alignes else "") for i, court in enumerate(ids)]
            return resolues

        if not ids:
            for nom, cmd in a_lancer:
                _lancer(nom, cmd, evenement, "", "", 0, [], projet, {"event": evenement})
        elif len(ids) > MAX_EXECUTIONS:
            for nom, cmd in a_lancer:
                _lancer(nom, cmd, evenement, "", "", len(ids), ids, projet, {"event": evenement, "ids": ids})
        else:
            for complet, tache in taches():
                for nom, cmd in a_lancer:
                    _lancer(nom, cmd, evenement, complet, tache.get('titre', ""), len(ids), ids, projet, tache)
        webhook.traiter(evenement, ids, lambda: [t for _, t in taches()], projet)
    except Exception:
        pass
