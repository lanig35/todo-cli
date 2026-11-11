"""Commande `next` : la ou les tâches à traiter en premier."""
import json
from datetime import datetime
from . import couleurs
from .config import PRIORITES, STATUT_A_FAIRE
from .dates import _jours_restants, _libelle_echeance, _libelle_recurrence
from .stockage import _lire_taches


def _rang(t, aujourdhui):
    """Clé de classement : retard, puis échéance du jour, puis le reste ; dans chaque groupe,
    priorité haute d'abord, échéance la plus proche (sans échéance en dernier), création, id."""
    jours = _jours_restants(t, aujourdhui)
    groupe = 0 if jours is not None and jours < 0 else 1 if jours == 0 else 2
    return (groupe, -PRIORITES.index(t['priorite']), t['date_echeance'] or "9999-12-31",
            t.get('date_creation') or "", t['id'])


def choisir_prochaines(taches, nombre, aujourdhui, tag=None, prio=None):
    """Les `nombre` premières tâches à faire (filtrables par tag / priorité) et le nombre total candidates."""
    candidates = [t for t in taches if t['statut'] == STATUT_A_FAIRE
                  and (not tag or tag.lower() in t['tags']) and (not prio or t['priorite'] == prio)]
    candidates.sort(key=lambda t: _rang(t, aujourdhui))
    return candidates[:nombre], len(candidates)


def afficher_prochaines(nombre=1, tag=None, prio=None, fmt="table"):
    """Affiche les prochaines tâches à traiter."""
    aujourdhui = datetime.now().date()
    choisies, total = choisir_prochaines(_lire_taches(), nombre, aujourdhui, tag, prio)

    if fmt == "json":
        print(json.dumps(choisies, indent=2, ensure_ascii=False))
        return
    if not choisies:
        filtre = " correspondant à ces critères" if (tag or prio) else ""
        print(f" 🎉 {couleurs.CLR_DIM}Rien à faire : aucune tâche en attente{filtre}.{couleurs.CLR_RESET}")
        return

    lignes = [f"\n {couleurs.CLR_CYAN}─── 🎯 À FAIRE ENSUITE ───{couleurs.CLR_RESET}"]
    largeur = len(str(len(choisies)))
    for rang, t in enumerate(choisies, start=1):
        prio_clr = {"high": couleurs.CLR_P_HIGH, "medium": couleurs.CLR_P_MED, "low": couleurs.CLR_P_LOW}[t['priorite']]
        tags = f" {couleurs.CLR_TAG}" + " ".join(f"#{tg}" for tg in t['tags']) + couleurs.CLR_RESET if t['tags'] else ""
        rec = f" {couleurs.CLR_DIM}↻ {_libelle_recurrence(t['recurrence'])}{couleurs.CLR_RESET}" if t['recurrence'] else ""
        numero = f"{couleurs.CLR_DIM}{rang:>{largeur}}.{couleurs.CLR_RESET} " if nombre > 1 else ""
        lignes.append(f"  {numero}{prio_clr}[{t['priorite'].upper()}]{couleurs.CLR_RESET} {couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}"
                      f"{_libelle_echeance(t, aujourdhui)}{rec}{tags} {couleurs.CLR_DIM}(id: {t['id'][:8]}){couleurs.CLR_RESET}")
        if t['description']:
            lignes.append(f"      {' ' * (largeur + 1) if nombre > 1 else ''}{couleurs.CLR_DIM}↳ {t['description']}{couleurs.CLR_RESET}")
    lignes.append(f" {couleurs.CLR_CYAN}──────────────────────────────────────{couleurs.CLR_RESET}")
    reste = total - len(choisies)
    suite = f"{reste} autre(s) tâche(s) en attente · " if reste else ""
    lignes.append(f" {couleurs.CLR_DIM}{suite}terminer : todo done {choisies[0]['id'][:8]}{couleurs.CLR_RESET}\n")
    print("\n".join(lignes))
