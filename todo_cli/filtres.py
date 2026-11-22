"""Filtres communs à `list` et `archive list` : échéance absente, notes, dates de fin et d'archivage."""
import re
from datetime import datetime, timedelta
from .config import STATUT_A_FAIRE
from .dates import _decaler, _parse_date, _resoudre_date, _sans_accents

MSG_FORMATS_DATE_PASSEE = ("AAAA-MM-JJ, aujourd'hui, hier, ou une durée écoulée : 3d / 2w / 1m / 1y "
                           "(il y a 3 jours, 2 semaines, 1 mois, 1 an)")


def resoudre_date_passee(texte, reference=None):
    """Date désignée par une option sur le passé (--done-after…), ou None si elle n'est pas reconnue.

    `7d` / `2w` / `1m` / `1y` = il y a 7 jours, 2 semaines… ; `hier`, `aujourd'hui`, AAAA-MM-JJ.
    Les dates futures (`demain`, `+3d`, un jour de la semaine) ne sont pas admises : elles ne
    désignent jamais une tâche déjà terminée.
    """
    ref = reference or datetime.now().date()
    t = _sans_accents(texte or "").strip().lower()
    if t in ("hier", "yesterday"):
        return _decaler(ref, -1, "d")
    m = re.fullmatch(r"(\d{1,4})([dwmy])", t)
    if m:
        try:
            return _decaler(ref, -int(m.group(1)), m.group(2))
        except (ValueError, OverflowError):
            return None
    if t.startswith("+") or t in ("demain", "tomorrow", "apres-demain", "apresdemain"):
        return None
    date = _resoudre_date(t, ref)
    return date if date is not None and date <= ref else None


_HEURE = re.compile(r"(\d{1,2}):(\d{2})")
MSG_FORMAT_INSTANT = ("HH:MM (aujourd'hui), ou une date passée suivie de HH:MM : hier 9:15, 2026-11-20 16:00, 2d 10:00 "
                      "(il y a 2 jours)")


def parser_instant(texte, maintenant=None):
    """Instant saisi par `--at` : `HH:MM` (aujourd'hui), ou une date du passé (formats de --done-after) suivie de `HH:MM`.

    Retourne un datetime (secondes à zéro) ; lève ValueError (message lisible) si le texte est incompris ou si
    l'instant est dans le futur : on ne peut pas avoir démarré plus tard que maintenant.
    """
    maintenant = maintenant or datetime.now()
    brut = (texte or "").strip()
    mots = brut.rsplit(None, 1)
    m = _HEURE.fullmatch(mots[-1]) if mots else None
    if m is None:
        raise ValueError(f"instant non reconnu : '{brut}' (formats : {MSG_FORMAT_INSTANT})")
    heure, minute = int(m.group(1)), int(m.group(2))
    if heure > 23 or minute > 59:
        raise ValueError(f"heure invalide : '{mots[-1]}'")
    jour = maintenant.date()
    if len(mots) == 2:
        jour = resoudre_date_passee(mots[0], maintenant.date())
        if jour is None and _resoudre_date(mots[0], maintenant.date()) is not None:
            raise ValueError(f"'{mots[0]}' est dans le futur : on ne peut pas avoir démarré plus tard que maintenant")
        if jour is None:
            raise ValueError(f"date non reconnue : '{mots[0]}' (formats : {MSG_FORMATS_DATE_PASSEE})")
    instant = datetime(jour.year, jour.month, jour.day, heure, minute)
    if instant > maintenant:
        raise ValueError(f"{instant:%Y-%m-%d %H:%M} est dans le futur : on ne peut pas avoir démarré plus tard que maintenant")
    return instant


def _jour(valeur):
    """Date (sans l'heure) d'un champ 'AAAA-MM-JJ' ou 'AAAA-MM-JJ HH:MM', ou None."""
    return _parse_date((valeur or "")[:10])


def garder(t, sans_echeance=False, notes=None, fini_apres=None, fini_avant=None, archive_apres=None, archive_avant=None,
           anciennete=None, tags=None, un_tag=None, sans_tag=False, pas_tags=None, prios=None, pas_prios=None,
           recurrente=None, cree_apres=None, cree_avant=None, ids=None, bloquee=None, fichiers=None, demarree=None):
    """Vrai si la tâche satisfait tous les filtres donnés (les filtres absents ne retiennent rien).

    sans_echeance : seulement les tâches sans échéance ; notes : True = au moins une note,
    False = aucune ; fini_* / archive_* : bornes INCLUSES (dates) sur la date de fin / d'archivage —
    une tâche sans cette date est exclue ; anciennete : date limite, la tâche doit être terminée
    au plus tard ce jour-là (comme `archive add --older-than`).
    tags : TOUS ces tags ; un_tag : AU MOINS UN de ces tags ; sans_tag : aucun tag ; pas_tags : aucun de ces
    tags ; prios / pas_prios : priorité dans / hors de ces valeurs ; recurrente : True/False ; cree_* : bornes
    incluses sur la date de création ; ids : début de l'identifiant (l'un d'eux suffit) ; bloquee : True =
    à faire et en attente d'une dépendance, False = à faire et prête (voir dependances.annoter) ; fichiers : True = au moins
    une pièce jointe, False = aucune ; demarree : True = démarrée (champ `demarree` renseigné), False = jamais démarrée.
    """
    if tags and not all(x in t['tags'] for x in tags):
        return False
    if un_tag and not any(x in t['tags'] for x in un_tag):
        return False
    if sans_tag and t['tags']:
        return False
    if pas_tags and any(x in t['tags'] for x in pas_tags):
        return False
    if prios and t['priorite'] not in prios:
        return False
    if pas_prios and t['priorite'] in pas_prios:
        return False
    if recurrente is not None and bool(t.get('recurrence')) != recurrente:
        return False
    if cree_apres is not None or cree_avant is not None:
        jour = _jour(t.get('date_creation'))
        if jour is None or (cree_apres is not None and jour < cree_apres) or (cree_avant is not None and jour > cree_avant):
            return False
    if bloquee is not None and (t['statut'] != STATUT_A_FAIRE or bool(t.get('bloquee_par')) != bloquee):
        return False
    if ids and not any(t['id'].lower().startswith(i) for i in ids):
        return False
    if sans_echeance and _parse_date(t.get('date_echeance')) is not None:
        return False
    if notes is not None and bool(t.get('notes')) != notes:
        return False
    if fichiers is not None and bool(t.get('pieces_jointes')) != fichiers:
        return False
    if demarree is not None and bool(t.get('demarree')) != demarree:
        return False
    for champ, apres, avant in (("date_terminee", fini_apres, fini_avant), ("date_archivage", archive_apres, archive_avant)):
        if apres is None and avant is None:
            continue
        jour = _jour(t.get(champ))
        if jour is None or (apres is not None and jour < apres) or (avant is not None and jour > avant):
            return False
    if anciennete is not None:
        jour = _jour(t.get("date_terminee"))
        if jour is None or jour > anciennete:
            return False
    return True
