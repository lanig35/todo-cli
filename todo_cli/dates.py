"""Dates relatives, récurrences et libellés d'échéance."""
import calendar
import re
import unicodedata
from datetime import datetime
from datetime import timedelta
from .config import STATUT_A_FAIRE
from . import couleurs


def _parse_date(valeur):
    """Convertit 'AAAA-MM-JJ' en date, ou None si la valeur est absente ou invalide."""
    if not valeur:
        return None
    try:
        return datetime.strptime(valeur, "%Y-%m-%d").date()
    except ValueError:
        return None

# --- Dates relatives -----------------------------------------------------------
_JOURS_SEMAINE = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
}

MSG_FORMATS_DATE = "AAAA-MM-JJ, aujourd'hui, demain, apres-demain, +3d / +2w / +1m / +1y, ou un jour de la semaine (lundi...)"

def _sans_accents(texte):
    """'Après-demain' -> 'Apres-demain' (comparaisons insensibles aux accents)."""
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")

def _ajouter_mois(d, n):
    """Ajoute n mois à une date en ramenant le jour au dernier jour du mois si besoin (31 janv. + 1 mois = 28/29 févr.)."""
    mois = d.month - 1 + n
    annee = d.year + mois // 12
    mois = mois % 12 + 1
    return d.replace(year=annee, month=mois, day=min(d.day, calendar.monthrange(annee, mois)[1]))

def _decaler(d, n, unite):
    """Décale une date de n jours ('d'), semaines ('w'), mois ('m') ou années ('y')."""
    if unite == "d":
        return d + timedelta(days=n)
    if unite == "w":
        return d + timedelta(weeks=n)
    if unite == "m":
        return _ajouter_mois(d, n)
    return _ajouter_mois(d, 12 * n)

def _resoudre_date(texte, reference=None):
    """Convertit une date saisie en objet date, ou None si elle n'est pas reconnue.

    Formats : AAAA-MM-JJ ; aujourd'hui / today ; demain / tomorrow ; apres-demain ;
    +Nd, +Nw, +Nm, +Ny (jours, semaines, mois, années) ; nom d'un jour de la semaine
    (la prochaine occurrence, jamais aujourd'hui).
    """
    if texte is None:
        return None
    ref = reference or datetime.now().date()
    t = _sans_accents(texte).strip().lower()
    if not t:
        return None

    absolue = _parse_date(t)
    if absolue is not None:
        return absolue
    if t in ("today", "aujourdhui", "aujourd'hui"):
        return ref
    if t in ("tomorrow", "demain"):
        return ref + timedelta(days=1)
    if t in ("apres-demain", "apresdemain", "day-after-tomorrow"):
        return ref + timedelta(days=2)

    m = re.fullmatch(r"\+(\d{1,4})([dwmy])", t)
    if m:
        try:
            return _decaler(ref, int(m.group(1)), m.group(2))
        except (ValueError, OverflowError):
            return None  # hors plage de dates supportée

    if t in _JOURS_SEMAINE:
        ecart = (_JOURS_SEMAINE[t] - ref.weekday()) % 7 or 7
        return ref + timedelta(days=ecart)
    return None

# --- Récurrence ------------------------------------------------------------------
_ALIAS_RECURRENCE = {
    "daily": "1d", "quotidien": "1d",
    "weekly": "1w", "hebdo": "1w", "hebdomadaire": "1w",
    "monthly": "1m", "mensuel": "1m",
    "yearly": "1y", "annuel": "1y",
}

MSG_FORMATS_REPETITION = "daily, weekly, monthly, yearly, ou 3d / 2w / 1m / 1y ('none' pour supprimer)"

def _parser_recurrence(texte):
    """Normalise une récurrence ('weekly' -> '1w', '2W' -> '2w'), ou None si invalide."""
    t = _sans_accents(texte).strip().lower()
    t = _ALIAS_RECURRENCE.get(t, t)
    m = re.fullmatch(r"(\d{1,3})([dwmy])", t)
    if not m or int(m.group(1)) == 0:
        return None
    return f"{int(m.group(1))}{m.group(2)}"

def _libelle_recurrence(rec):
    """'1w' -> 'chaque semaine', '3m' -> 'tous les 3 mois'."""
    n, unite = int(rec[:-1]), rec[-1]
    if n == 1:
        return {"d": "chaque jour", "w": "chaque semaine", "m": "chaque mois", "y": "chaque année"}[unite]
    return {"d": f"tous les {n} jours", "w": f"toutes les {n} semaines",
            "m": f"tous les {n} mois", "y": f"tous les {n} ans"}[unite]

def _prochaine_echeance(t, aujourdhui):
    """Prochaine échéance d'une tâche récurrente, calculée depuis son échéance d'origine
    (sans dérive) et strictement postérieure à aujourd'hui : les occurrences manquées
    ne s'accumulent pas en retard.
    """
    n, unite = int(t['recurrence'][:-1]), t['recurrence'][-1]
    base = _parse_date(t['date_echeance']) or aujourdhui
    k = 1
    prochaine = _decaler(base, n * k, unite)
    while prochaine <= aujourdhui:
        k += 1
        prochaine = _decaler(base, n * k, unite)
    return prochaine

def _jours_restants(t, maintenant):
    """Nombre de jours avant l'échéance (négatif = en retard), ou None sans échéance valide."""
    date_obj = _parse_date(t['date_echeance'])
    return None if date_obj is None else (date_obj - maintenant).days

def _libelle_echeance(t, maintenant):
    """Étiquette colorée d'échéance (avec espace initial), ou chaîne vide sans échéance."""
    if not t['date_echeance']:
        return ""
    jours = _jours_restants(t, maintenant)
    if jours is None:
        return f" {couleurs.CLR_DIM}[Éch: {t['date_echeance']} ?]{couleurs.CLR_RESET}"
    if t['statut'] != STATUT_A_FAIRE:
        return f" {couleurs.CLR_DIM}[Éch: {t['date_echeance']}]{couleurs.CLR_RESET}"
    if jours < 0:
        return f" {couleurs.CLR_DEL}[RETARD : {-jours} j.]{couleurs.CLR_RESET}"
    if jours == 0:
        return f" {couleurs.CLR_P_HIGH}[AUJOURD'HUI]{couleurs.CLR_RESET}"
    if jours == 1:
        return f" {couleurs.CLR_TODO}[DEMAIN]{couleurs.CLR_RESET}"
    return f" {couleurs.CLR_CYAN}[J-{jours}]{couleurs.CLR_RESET}"
