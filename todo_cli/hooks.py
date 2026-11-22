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

from . import config, couleurs, journal, reglages
from .stockage import _normaliser_tache, _resoudre_id

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


def _avertir(reglage, message):
    rouge, raz = couleurs._couleurs_erreur()
    print(f" {rouge}⚠️{raz} Hook {reglage} : {message}", file=sys.stderr)
    journal.avertir("hook", hook=reglage, detail=message)


def _tache(id_court, titre):
    """(id complet, JSON de la tâche) depuis la base du projet courant ; à défaut, ce que le journal sait d'elle."""
    try:
        if os.path.exists(config.DB_NAME) or os.path.exists(config.DB_NAME + ".db"):
            with dbm.open(config.DB_NAME, 'r') as db:
                cle = _resoudre_id(db, id_court)
                if cle is not None:
                    t = _normaliser_tache(db[cle])
                    t['id'] = cle.decode('utf-8', errors='replace')
                    return t['id'], t
    except Exception:
        pass
    return id_court, {"id": id_court, "titre": titre or ""}


def _lancer(reglage, commande, evenement, id_complet, titre, nombre, ids, projet, entree):
    env = dict(os.environ)
    env.update(TODO_EVENT=evenement, TODO_ID=id_complet or "", TODO_TITLE=titre or "", TODO_PROJECT=projet,
               TODO_COUNT=str(nombre), TODO_IDS=",".join(ids), TODO_IN_HOOK="1", TODO_HOOK=reglage)
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


def declencher():
    """Lance les hooks de la commande qui vient de s'exécuter, si elle a modifié quelque chose. Ne lève jamais."""
    try:
        bilan = journal.bilan()
        if (not bilan["modifie"] or os.environ.get("TODO_IN_HOOK") or not reglages.obtenir('hooks', 'enabled')
                or not bilan["commande"]):
            return
        evenement, ids, titres = bilan["commande"], bilan["ids"], bilan["titres"]
        specifique = _commande("on_" + evenement) if evenement in EVENEMENTS and ids else None
        general = _commande("on_change")
        if not specifique and not general:
            return
        projet = config.projet()
        a_lancer = [(nom, cmd) for nom, cmd in (("on_" + evenement, specifique), ("on_change", general)) if cmd]
        if not ids:
            for nom, cmd in a_lancer:
                _lancer(nom, cmd, evenement, "", "", 0, [], projet, {"event": evenement})
            return
        if len(ids) > MAX_EXECUTIONS:
            for nom, cmd in a_lancer:
                _lancer(nom, cmd, evenement, "", "", len(ids), ids, projet, {"event": evenement, "ids": ids})
            return
        alignes = len(titres) == len(ids)
        for i, court in enumerate(ids):
            complet, tache = _tache(court, titres[i] if alignes else "")
            for nom, cmd in a_lancer:
                _lancer(nom, cmd, evenement, complet, tache.get('titre', ""), len(ids), ids, projet, tache)
    except Exception:
        pass
