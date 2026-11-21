"""Actions en lot : aperçu et confirmation d'une sélection de tâches par filtre.

postpone --overdue --to demain, done --tag courses… visent des tâches choisies par les filtres de
`list` plutôt que par leurs identifiants. La sélection est calculée d'abord (et figée : les identifiants
complets sont ensuite passés à l'action habituelle, qui garde donc son bilan, sa sauvegarde unique et son code de
sortie), puis éventuellement confirmée. Ce module ne sait rien des filtres : il reçoit les tâches retenues.
"""
import json
import sys

from . import couleurs, journal
from .formats import sortie_taches

APERCU_MAX = 5      # titres cités dans la question de confirmation


def apercu(cibles, fmt, colonnes, action):
    """Affiche les tâches visées sans rien modifier (`--dry-run`), dans le format demandé."""
    if fmt == "json":
        print(json.dumps(cibles, indent=2, ensure_ascii=False))
        return
    if sortie_taches(fmt, cibles, colonnes):
        return
    print(f" {couleurs.CLR_CYAN}🔎 Simulation :{couleurs.CLR_RESET} {len(cibles)} tâche(s) seraient {action}. Rien n'est modifié.")
    for t in cibles:
        print(f"   {couleurs.CLR_DIM}{t['id'][:8]}{couleurs.CLR_RESET}  {t['titre']}")


def confirmer(cibles, verbe, seuil, oui):
    """Demande confirmation quand la sélection atteint `seuil` tâches (0 = jamais), sauf avec `--yes`.

    Retourne True pour continuer, False si l'utilisateur renonce. Sans terminal pour poser la question, la
    commande s'arrête (code 1) : un script doit ajouter `-y` pour un lot de cette taille.
    """
    if oui or not seuil or len(cibles) < seuil:
        return True
    resume = ", ".join(f"'{t['titre']}'" for t in cibles[:APERCU_MAX]) + (" …" if len(cibles) > APERCU_MAX else "")
    if not sys.stdin.isatty():
        journal.echec("confirmation_required", count=len(cibles))
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {len(cibles)} tâches sont visées ({resume}) : "
              f"ajoutez -y pour confirmer (aucun terminal pour poser la question).", file=sys.stderr)
        sys.exit(1)
    try:
        reponse = input(f" {couleurs.CLR_DEL}⚠️ {verbe}{couleurs.CLR_RESET} {len(cibles)} tâche(s) ({resume}) ? "
                        f"Annulable avec `undo`. (y/N) : ").strip().lower()
    except EOFError:
        reponse = ""
    if reponse != "y":
        print(" ❌ Opération annulée.")
        return False
    return True
