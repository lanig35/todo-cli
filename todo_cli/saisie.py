"""Saisie rapide : extrait date, priorité, tags et récurrence d'un titre libre.

    todo add 'Appeler Paul demain !high #pro #urgent ~weekly'

Marqueurs reconnus (un mot isolé, séparé par des espaces) :
  - date         : aujourd'hui, demain, après-demain, +3d / +2w / +1m / +1y, un jour de la semaine
                   ou AAAA-MM-JJ, avec ou sans « @ » (`@lundi`) ;
  - priorité     : `!high` `!medium` `!low` (ou `!haute` `!moyenne` `!basse`, `!h` `!m` `!l`) ;
  - tag          : `#pro` (commence par une lettre : `#42` reste dans le titre) ;
  - récurrence   : `~weekly`, `~2w`, `~mensuel`…
Un mot qui ressemble à un marqueur sans en être un (`!bravo`, `@truc`) reste dans le titre.
Si plusieurs marqueurs de même nature sont présents, le dernier l'emporte (les tags s'additionnent).
"""
import re
from .dates import _parser_recurrence, _resoudre_date, _sans_accents

_PRIORITES = {"high": "high", "haute": "high", "h": "high",
              "medium": "medium", "moyenne": "medium", "m": "medium",
              "low": "low", "basse": "low", "l": "low"}
_TAG = re.compile(r"#([^\W\d_][\w-]*)")


def analyser_titre(texte, due=True, prio=True, tags=True, repeat=True):
    """Analyse un titre de saisie rapide.

    Les paramètres due / prio / tags / repeat désactivent l'extraction du marqueur correspondant
    (utile quand l'option explicite équivalente est fournie : elle est prioritaire et le mot reste
    alors dans le titre).

    Retourne un dict : titre (nettoyé), due (texte de date), prio, tags (liste), repeat — None ou
    liste vide pour ce qui n'a pas été trouvé — et `trouve` (vrai si quelque chose a été extrait).
    Si le titre se réduirait à rien, il est conservé tel quel et rien n'est extrait.
    """
    mots, restants = texte.split(), []
    res = {"titre": texte, "due": None, "prio": None, "tags": [], "repeat": None, "trouve": False}
    for mot in mots:
        if prio and mot.startswith("!") and _sans_accents(mot[1:]).lower() in _PRIORITES:
            res["prio"] = _PRIORITES[_sans_accents(mot[1:]).lower()]
        elif tags and _TAG.fullmatch(mot):
            tag = mot[1:].lower()
            if tag not in res["tags"]:
                res["tags"].append(tag)
        elif repeat and mot.startswith("~") and _parser_recurrence(mot[1:]) is not None:
            res["repeat"] = mot[1:]
        elif due and _resoudre_date(mot.lstrip("@") if mot.startswith("@") else mot) is not None:
            res["due"] = mot.lstrip("@") if mot.startswith("@") else mot
        else:
            restants.append(mot)

    if len(restants) == len(mots) or not restants:
        return {**res, "titre": texte, "due": None, "prio": None, "tags": [], "repeat": None, "trouve": False}
    return {**res, "titre": " ".join(restants), "trouve": True}
