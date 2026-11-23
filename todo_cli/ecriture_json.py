"""Sortie JSON des commandes d'écriture : `todo done ID --format json`.

Avec `--format json` donné explicitement (ni le réglage `[general] format` ni TODO_FORMAT ne l'activent : un script qui règle
TODO_FORMAT=json ne doit pas voir les messages des commandes d'écriture disparaître), la commande s'exécute comme d'habitude
mais ses messages (« ✅ Tâche ajoutée… », avertissements, erreurs) partent sur stderr ; stdout ne reçoit qu'un objet JSON :

    {"ok": true, "action": "done", "project": "default", "count": 1, "failed": 0,
     "tasks": [{…la tâche comme `show --format json`…}], "errors": []}

  - `tasks` : les tâches touchées, relues après la commande (identifiant complet, `suivante` pour l'occurrence créée par une
    tâche récurrente terminée). Pour une tâche supprimée ou déplacée, seulement {"id", "titre"} ; `move` ajoute "to" (projet cible).
  - `ok` : le code de sortie est 0 ; `errors` : les raisons techniques des refus (celles du journal, ex. "unknown_id").
  - Une commande qui ne touche rien (tâche déjà terminée…) donne ok=true, count=0.
  - Avec --dry-run, l'aperçu garde son propre format (`--format` règle alors l'aperçu) : aucune sortie d'écriture.
Le code de sortie est celui de la commande ; les erreurs d'usage détectées par argparse (code 2) n'écrivent pas de JSON.
"""
import dbm
import json
import os
import sys

from . import config, dependances, journal
from .stockage import _normaliser_tache

COMMANDES = ("add", "edit", "done", "undone", "start", "unstart", "remove", "move", "postpone")

_etat = {"actif": False, "stdout": None, "extras": {}}


def demande(args):
    """Vrai si l'utilisateur a écrit `--format json` sur une commande d'écriture (hors --dry-run)."""
    return (getattr(args, "commande", None) in COMMANDES and getattr(args, "format", None) == "json"
            and not getattr(args, "dry_run", False))


def activer(extras=None):
    """Détourne stdout vers stderr : les messages habituels restent visibles, stdout est réservé au JSON."""
    if not _etat["actif"]:
        _etat.update(actif=True, stdout=sys.stdout, extras=dict(extras or {}))
        sys.stdout.flush()
        sys.stdout = sys.stderr


def ajouter_extras(**champs):
    _etat["extras"].update(champs)


def _taches(ids, titres, supprimees):
    """Les tâches touchées, relues dans la base du projet ; {"id", "titre"} si elles n'y sont plus (ou si l'on sait qu'elles sont parties)."""
    trouvees = {}
    if not supprimees:
        try:
            if os.path.exists(config.DB_NAME) or os.path.exists(config.DB_NAME + ".db"):
                with dbm.open(config.DB_NAME, 'r') as db:
                    for cle in ids:
                        brut = db.get(cle)
                        if brut is None:
                            continue
                        t = _normaliser_tache(brut)
                        t['id'] = cle
                        t['bloquee_par'] = [d for d, _ in dependances.en_attente(db, t)] if t['statut'] == "A FAIRE" else []
                        trouvees[cle] = t
        except Exception:
            pass
    alignes = len(titres) == len(ids)
    return [trouvees.get(cle) or {"id": cle, "titre": titres[i] if alignes else ""} for i, cle in enumerate(ids)]


def emettre(commande, code):
    """Écrit l'objet JSON sur le vrai stdout ; à appeler une fois, à la sortie (après les hooks)."""
    if not _etat["actif"]:
        return
    _etat["actif"] = False
    sys.stdout.flush()
    sys.stdout = _etat["stdout"]
    try:
        bilan = journal.bilan()
        complets = bilan["ids_complets"] if len(bilan["ids_complets"]) == len(bilan["ids"]) else bilan["ids"]
        alignes = len(bilan["titres"]) == len(complets)
        uniques = {}                                           # un même identifiant peut être noté deux fois
        for i, cle in enumerate(complets):
            uniques.setdefault(cle, bilan["titres"][i] if alignes else "")
        ids, titres = list(uniques), list(uniques.values())
        try:
            projet = config.projet()
        except Exception:
            projet = None
        taches = _taches(ids, titres, supprimees=commande in ("remove", "move"))
        objet = {"ok": code == 0, "action": commande, "project": projet, "count": len(taches),
                 "failed": bilan["champs"].get("failed", bilan["echecs"]), "tasks": taches, "errors": bilan["raisons"], **_etat["extras"]}
        print(json.dumps(objet, indent=2, ensure_ascii=False))
        sys.stdout.flush()
    except Exception as e:                                       # ne jamais perdre le code de sortie de la commande
        print(json.dumps({"ok": False, "action": commande, "errors": ["internal_error"], "detail": str(e)}), flush=True)
