"""Dépendances entre tâches (`--after`) : une tâche attend que d'autres soient terminées.

Une tâche à faire est **bloquée** tant qu'au moins une des tâches de son champ `apres` est encore à faire.
Une dépendance terminée, archivée ou supprimée ne bloque plus. `next` ne propose pas les tâches bloquées ;
`done` reste possible sur une tâche bloquée (avec un avertissement).
"""
import sys

from . import couleurs, journal
from .config import STATUT_A_FAIRE
from .stockage import _normaliser_tache, _resoudre_id


def annoter(taches):
    """Ajoute à chaque tâche `bloquee_par` : ids des dépendances encore à faire (liste vide si aucune)."""
    actives = {t['id']: t for t in taches}
    for t in taches:
        t['bloquee_par'] = [d for d in t.get('apres', []) if t['statut'] == STATUT_A_FAIRE
                            and d in actives and actives[d]['statut'] == STATUT_A_FAIRE]
    return taches


def _lire(db, identifiant):
    try:
        return _normaliser_tache(db[identifiant])
    except (KeyError, ValueError):
        return None


def en_attente(db, t):
    """[(id, tâche)] des dépendances de `t` encore à faire."""
    res = []
    for d in t.get('apres', []):
        dep = _lire(db, d)
        if dep is not None and dep['statut'] == STATUT_A_FAIRE:
            res.append((d, dep))
    return res


def _cycle(db, cle, deps):
    """Vrai si `cle` est atteignable depuis `deps` en suivant les dépendances (la tâche s'attendrait elle-même)."""
    pile, vus = list(deps), set()
    while pile:
        d = pile.pop()
        if d == cle:
            return True
        if d in vus:
            continue
        vus.add(d)
        dep = _lire(db, d)
        if dep is not None:
            pile.extend(dep.get('apres', []))
    return False


def resoudre(db, prefixes, cle=None):
    """Identifiants complets des dépendances désignées par `prefixes`, ou None (message affiché) si l'une est
    introuvable, ambiguë, désigne la tâche elle-même (`cle`) ou crée un cycle."""
    ids = []
    for prefixe in prefixes:
        k = _resoudre_id(db, prefixe)
        if k is None:
            return None
        k = k.decode('utf-8', errors='replace')
        if k not in ids:
            ids.append(k)
    if cle is not None and _cycle(db, cle, ids):
        journal.echec("dependency_cycle")
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Dépendance circulaire : la tâche s'attendrait elle-même "
              f"(directement ou par une autre tâche).", file=sys.stdout)
        return None
    return ids


def liste_prefixes(texte):
    """'abc, def' -> ['abc', 'def'] ; chaîne vide ou 'none' -> [] (suppression)."""
    t = (texte or "").strip()
    if t.lower() == "none":
        return []
    return [x.strip() for x in t.split(",") if x.strip()]
