"""Vue agenda : les tâches à faire regroupées par jour d'échéance."""
import json
from datetime import datetime, timedelta
from . import couleurs
from .affichage import _afficher_texte
from .config import PRIORITES, STATUT_A_FAIRE
from .dates import _libelle_recurrence, _parse_date
from .stockage import _lire_taches

_NOMS_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_NOMS_MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
              "septembre", "octobre", "novembre", "décembre")


def _libelle_jour(jour, aujourdhui):
    """'mardi 10 novembre', avec l'année si elle diffère de l'année courante."""
    texte = f"{_NOMS_JOURS[jour.weekday()]} {jour.day} {_NOMS_MOIS[jour.month - 1]}"
    return texte if jour.year == aujourdhui.year else f"{texte} {jour.year}"


def _ordre(t):
    """Ordre au sein d'un jour : priorité haute d'abord, puis création, puis id (déterministe)."""
    return (-PRIORITES.index(t['priorite']), t.get('date_creation') or "", t['id'])


def construire_agenda(taches, debut, nb_jours, aujourdhui):
    """Répartit les tâches à faire entre retards, jours de la fenêtre, plus tard et sans échéance.

    La fenêtre couvre `nb_jours` jours à partir de `debut` (inclus). Les retards sont mesurés par
    rapport à `aujourdhui` et ne sont affichés que si la fenêtre commence au plus tard aujourd'hui.
    """
    fin = debut + timedelta(days=nb_jours - 1)
    retards, jours, plus_tard, sans = [], {debut + timedelta(days=i): [] for i in range(nb_jours)}, [], []
    for t in taches:
        if t['statut'] != STATUT_A_FAIRE:
            continue
        echeance = _parse_date(t['date_echeance'])
        if echeance is None:
            sans.append(t)
        elif echeance < aujourdhui and debut <= aujourdhui:
            retards.append(t)
        elif echeance in jours:
            jours[echeance].append(t)
        elif echeance > fin:
            plus_tard.append(t)
        # Échéance antérieure à la fenêtre : hors sujet (fenêtre commençant dans le futur, ou passé voulu)
    retards.sort(key=lambda t: (t['date_echeance'],) + _ordre(t))
    for liste in jours.values():
        liste.sort(key=_ordre)
    return retards, jours, plus_tard, sans


def _ligne_tache(t):
    prio = {"high": couleurs.CLR_P_HIGH, "medium": couleurs.CLR_P_MED, "low": couleurs.CLR_P_LOW}[t['priorite']]
    tags = f" {couleurs.CLR_TAG}" + " ".join(f"#{tg}" for tg in t['tags']) + couleurs.CLR_RESET if t['tags'] else ""
    rec = f" {couleurs.CLR_DIM}↻ {_libelle_recurrence(t['recurrence'])}{couleurs.CLR_RESET}" if t['recurrence'] else ""
    return (f"    {prio}[{t['priorite'].upper()}]{couleurs.CLR_RESET} {couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}"
            f"{rec}{tags} {couleurs.CLR_DIM}(id: {t['id'][:8]}){couleurs.CLR_RESET}")


def afficher_agenda(debut=None, nb_jours=7, fmt="table", pager=True):
    """Affiche l'agenda des `nb_jours` jours à partir de `debut` (aujourd'hui par défaut)."""
    aujourdhui = datetime.now().date()
    debut = debut or aujourdhui
    fin = debut + timedelta(days=nb_jours - 1)
    retards, jours, plus_tard, sans = construire_agenda(_lire_taches(), debut, nb_jours, aujourdhui)

    if fmt == "json":
        print(json.dumps({
            "debut": debut.isoformat(), "fin": fin.isoformat(),
            "en_retard": retards,
            "jours": [{"date": j.isoformat(), "taches": ts} for j, ts in jours.items()],
            "plus_tard": len(plus_tard), "sans_echeance": len(sans),
        }, indent=2, ensure_ascii=False))
        return

    lignes = [f"\n {couleurs.CLR_CYAN}─── 🗓️  AGENDA : {_libelle_jour(debut, aujourdhui)} → {_libelle_jour(fin, aujourdhui)} ───{couleurs.CLR_RESET}"]
    if retards:
        lignes.append(f"\n  {couleurs.CLR_DEL}{couleurs.CLR_BOLD}En retard ({len(retards)}){couleurs.CLR_RESET}")
        for t in retards:
            jours_retard = (aujourdhui - _parse_date(t['date_echeance'])).days
            lignes.append(_ligne_tache(t) + f" {couleurs.CLR_DEL}[{jours_retard} j.]{couleurs.CLR_RESET}")
    for jour, taches in jours.items():
        marque = " — aujourd'hui" if jour == aujourdhui else " — demain" if jour == aujourdhui + timedelta(days=1) else ""
        couleur = couleurs.CLR_BOLD if taches else couleurs.CLR_DIM
        lignes.append(f"\n  {couleur}{_libelle_jour(jour, aujourdhui).capitalize()}{marque}{couleurs.CLR_RESET}")
        if taches:
            lignes.extend(_ligne_tache(t) for t in taches)
        else:
            lignes.append(f"    {couleurs.CLR_DIM}rien de prévu{couleurs.CLR_RESET}")
    resume = []
    if plus_tard:
        resume.append(f"Plus tard : {len(plus_tard)}")
    if sans:
        resume.append(f"Sans échéance : {len(sans)}")
    lignes.append(f"\n {couleurs.CLR_CYAN}──────────────────────────────────────{couleurs.CLR_RESET}")
    if resume:
        lignes.append(f" {couleurs.CLR_DIM}{' · '.join(resume)}{couleurs.CLR_RESET}")
    lignes.append("")
    _afficher_texte("\n".join(lignes), pager)
