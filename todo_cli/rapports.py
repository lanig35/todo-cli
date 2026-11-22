"""Rapports : tags, tâches bloquées, en retard, qui traînent, bilan des tâches terminées, tâches en cours et délais.

Chaque rapport existe dans les quatre formats habituels :
  text  affichage décoré (pager automatique), table  tableau aligné sans couleur,
  plain une ligne par enregistrement, champs séparés par des tabulations (contrat stable : voir README),
  json  un objet documenté par rapport (compatible jq).
Les rapports lisent la base sans la modifier.
"""
import json
import statistics
from datetime import datetime

from . import couleurs, dependances
from .affichage import _afficher_texte
from .agenda import _libelle_jour, _ligne_tache, _ordre
from .config import PRIORITES, STATUT_A_FAIRE, STATUT_TERMINE
from .dates import _parse_date, duree_lisible, duree_minutes, lire_instant
from .formats import imprimer_plain, tableau
from .stockage import _lire_archive, _lire_taches


def _en_json(objet):
    print(json.dumps(objet, indent=2, ensure_ascii=False))


def _jour(valeur):
    """Date d'un champ 'AAAA-MM-JJ' ou 'AAAA-MM-JJ HH:MM' (None si absent ou invalide)."""
    return _parse_date((valeur or "")[:10])


def _sortie(fmt, entetes, rangees, vide, texte, pager):
    """Écrit un rapport tabulaire : `plain` et `table` depuis `rangees`, `text` depuis `texte` (lignes déjà décorées).

    `rangees` : listes de champs (colonne "ID", si elle existe : id complet, réduit à 8 caractères pour `table`).
    `vide` : phrase affichée en `table` et `text` quand le rapport n'a rien à montrer.
    """
    if fmt == "plain":
        imprimer_plain(rangees)
    elif fmt == "table":
        if rangees:
            i = entetes.index("ID") if "ID" in entetes else None
            print(tableau(entetes, [[c[:8] if k == i else c for k, c in enumerate(r)] for r in rangees]))
        else:
            print(f" {couleurs.CLR_DIM}{vide}{couleurs.CLR_RESET}")
    else:
        _afficher_texte("\n".join(texte), pager)


def _titre(texte):
    return f"\n {couleurs.CLR_CYAN}─── {texte} ───{couleurs.CLR_RESET}"


def _pied(*morceaux):
    return [f"\n {couleurs.CLR_CYAN}──────────────────────────────────────{couleurs.CLR_RESET}",
            f" {couleurs.CLR_DIM}{' · '.join(morceaux)}{couleurs.CLR_RESET}\n"]


# ---------------------------------------------------------------------------------------------- tags
def calculer_tags(taches):
    """Compteurs par tag : ({tag: [à faire, terminées]}, [à faire, terminées] des tâches sans tag)."""
    compteurs, sans = {}, [0, 0]
    for t in taches:
        i = 0 if t['statut'] == STATUT_A_FAIRE else 1
        if not t['tags']:
            sans[i] += 1
        for tag in set(t['tags']):
            compteurs.setdefault(tag, [0, 0])[i] += 1
    return compteurs, sans


def rapport_tags(avec_archive=False, tri="count", fmt="text", pager=True):
    """Tags utilisés, avec le nombre de tâches à faire et terminées (archive comprise avec `avec_archive`)."""
    taches = _lire_taches() + (_lire_archive() if avec_archive else [])
    compteurs, sans = calculer_tags(taches)
    lignes = [(tag, a, d, a + d) for tag, (a, d) in compteurs.items()]
    lignes.sort(key=(lambda l: l[0]) if tri == "alpha" else (lambda l: (-l[3], l[0])))

    if fmt == "json":
        _en_json({"avec_archive": avec_archive,
                  "tags": [{"tag": tg, "a_faire": a, "terminees": d, "total": n} for tg, a, d, n in lignes],
                  "sans_tag": {"a_faire": sans[0], "terminees": sans[1]}})
        return
    texte = [_titre("🏷️  TAGS")]
    largeur = max((len(l[0]) for l in lignes), default=0) + 1
    for tag, a, d, n in lignes:
        texte.append(f"  {couleurs.CLR_TAG}#{tag:<{largeur}}{couleurs.CLR_RESET} {couleurs.CLR_BOLD}{n:>4}{couleurs.CLR_RESET}  "
                     f"{couleurs.CLR_DIM}{a} à faire · {d} terminée(s){couleurs.CLR_RESET}")
    if not lignes:
        texte.append(f"  {couleurs.CLR_DIM}Aucun tag.{couleurs.CLR_RESET}")
    texte += _pied(f"{len(lignes)} tag(s)", f"sans tag : {sans[0] + sans[1]}" + (" (archive comprise)" if avec_archive else ""))
    _sortie(fmt, ("TAG", "À FAIRE", "TERMINÉES", "TOTAL"), [list(map(str, l)) for l in lignes], "Aucun tag.", texte, pager)


# ---------------------------------------------------------------------------------------------- bloquées
def rapport_bloquees(fmt="text", pager=True):
    """Tâches à faire qui attendent encore une dépendance (`--after`), avec ce qu'elles attendent."""
    toutes = dependances.annoter(_lire_taches())
    par_id = {t['id']: t for t in toutes}
    bloquees = [t for t in toutes if t['bloquee_par']]
    bloquees.sort(key=lambda t: (t['date_echeance'] or "9999-12-31",) + _ordre(t))

    def attend(t):
        return [{"id": d, "titre": par_id[d]['titre']} for d in t['bloquee_par']]

    if fmt == "json":
        _en_json({"total": len(bloquees), "taches": [{**t, "attend": attend(t)} for t in bloquees]})
        return
    texte = [_titre("🔒 TÂCHES BLOQUÉES")]
    for t in bloquees:
        texte.append(_ligne_tache(t))
        texte += [f"        {couleurs.CLR_DIM}↳ attend : {a['titre']} (id: {a['id'][:8]}){couleurs.CLR_RESET}" for a in attend(t)]
    if not bloquees:
        texte.append(f"  {couleurs.CLR_DIM}Aucune tâche bloquée.{couleurs.CLR_RESET}")
    texte += _pied(f"{len(bloquees)} tâche(s) bloquée(s)")
    rangees = [[t['id'], t['priorite'], t['titre'], ",".join(t['bloquee_par']) if fmt == "plain"
                else ", ".join(a['titre'] for a in attend(t))] for t in bloquees]
    _sortie(fmt, ("ID", "PRIO", "TITRE", "ATTEND"), rangees, "Aucune tâche bloquée.", texte, pager)


# ---------------------------------------------------------------------------------------------- retards
def rapport_retards(fmt="text", pager=True):
    """Tâches à faire dont l'échéance est dépassée, les plus en retard d'abord."""
    aujourdhui = datetime.now().date()
    retards = []
    for t in _lire_taches():
        echeance = _jour(t['date_echeance'])
        if t['statut'] == STATUT_A_FAIRE and echeance is not None and echeance < aujourdhui:
            retards.append((t, (aujourdhui - echeance).days))
    retards.sort(key=lambda r: (-r[1], -PRIORITES.index(r[0]['priorite']), r[0].get('date_creation') or "", r[0]['id']))

    if fmt == "json":
        _en_json({"date": aujourdhui.isoformat(), "total": len(retards),
                  "taches": [{**t, "jours_retard": j} for t, j in retards]})
        return
    texte = [_titre("⏰ TÂCHES EN RETARD")]
    for t, j in retards:
        texte.append(_ligne_tache(t) + f" {couleurs.CLR_DEL}[{j} j.]{couleurs.CLR_RESET}")
    if not retards:
        texte.append(f"  {couleurs.CLR_DIM}Aucune tâche en retard.{couleurs.CLR_RESET}")
    texte += _pied(f"{len(retards)} tâche(s) en retard")
    rangees = [[t['id'], str(j), t['priorite'], t['date_echeance'], t['titre']] for t, j in retards]
    _sortie(fmt, ("ID", "RETARD (J)", "PRIO", "ÉCHÉANCE", "TITRE"), rangees, "Aucune tâche en retard.", texte, pager)


# ---------------------------------------------------------------------------------------------- qui traînent
def rapport_stagnantes(avant, libelle, fmt="text", pager=True):
    """Tâches à faire sans échéance, créées au plus tard le `avant` (date) : celles qu'on oublie."""
    aujourdhui = datetime.now().date()
    anciennes = []
    for t in _lire_taches():
        creation = _jour(t.get('date_creation'))
        if t['statut'] == STATUT_A_FAIRE and not t['date_echeance'] and creation is not None and creation <= avant:
            anciennes.append((t, (aujourdhui - creation).days))
    anciennes.sort(key=lambda r: (-r[1], -PRIORITES.index(r[0]['priorite']), r[0]['id']))

    if fmt == "json":
        _en_json({"avant": avant.isoformat(), "total": len(anciennes),
                  "taches": [{**t, "age_jours": j} for t, j in anciennes]})
        return
    texte = [_titre("🕸️  TÂCHES QUI TRAÎNENT")]
    for t, j in anciennes:
        texte.append(_ligne_tache(t) + f" {couleurs.CLR_DIM}[créée il y a {j} j.]{couleurs.CLR_RESET}")
    if not anciennes:
        texte.append(f"  {couleurs.CLR_DIM}Aucune tâche sans échéance créée depuis plus de {libelle}.{couleurs.CLR_RESET}")
    texte += _pied(f"{len(anciennes)} tâche(s) sans échéance, créée(s) il y a {libelle} ou plus")
    rangees = [[t['id'], str(j), t['priorite'], t['titre']] for t, j in anciennes]
    _sortie(fmt, ("ID", "ÂGE (J)", "PRIO", "TITRE"), rangees, f"Aucune tâche sans échéance créée depuis plus de {libelle}.", texte, pager)


# ---------------------------------------------------------------------------------------------- terminées
def rapport_terminees(depuis, jusqu_a, avec_archive=False, fmt="text", pager=True):
    """Bilan des tâches terminées entre `depuis` et `jusqu_a` (dates incluses), jour par jour, le plus récent d'abord."""
    taches = _lire_taches() + (_lire_archive() if avec_archive else [])
    par_jour = {}
    for t in taches:
        jour = _jour(t.get('date_terminee'))
        if t['statut'] == STATUT_TERMINE and jour is not None and depuis <= jour <= jusqu_a:
            par_jour.setdefault(jour, []).append(t)
    jours = sorted(par_jour, reverse=True)
    for j in jours:
        par_jour[j].sort(key=lambda t: (t['date_terminee'], t['id']))
    total = sum(len(v) for v in par_jour.values())

    if fmt == "json":
        _en_json({"depuis": depuis.isoformat(), "jusqu_a": jusqu_a.isoformat(), "avec_archive": avec_archive, "total": total,
                  "jours": [{"date": j.isoformat(), "taches": par_jour[j]} for j in jours]})
        return
    aujourdhui = datetime.now().date()
    texte = [_titre(f"✅ TÂCHES TERMINÉES : {_libelle_jour(depuis, aujourdhui)} → {_libelle_jour(jusqu_a, aujourdhui)}")]
    for j in jours:
        texte.append(f"\n  {couleurs.CLR_BOLD}{_libelle_jour(j, aujourdhui).capitalize()}{couleurs.CLR_RESET} {couleurs.CLR_DIM}({len(par_jour[j])}){couleurs.CLR_RESET}")
        texte += [_ligne_tache(t) for t in par_jour[j]]
    if not jours:
        texte.append(f"\n  {couleurs.CLR_DIM}Aucune tâche terminée sur cette période.{couleurs.CLR_RESET}")
    texte += _pied(f"{total} tâche(s) terminée(s)", f"{len(jours)} jour(s) actif(s)")
    rangees = [[t['date_terminee'], t['id'], t['priorite'], t['titre']] for j in jours for t in par_jour[j]]
    _sortie(fmt, ("TERMINÉE", "ID", "PRIO", "TITRE"), rangees, "Aucune tâche terminée sur cette période.", texte, pager)


# ---------------------------------------------------------------------------------------------- en cours
def rapport_en_cours(fmt="text", pager=True):
    """Tâches démarrées et pas terminées, la plus ancienne en premier, avec le temps écoulé (calendaire)."""
    maintenant = datetime.now()
    actives = []
    for t in _lire_taches():
        debut = lire_instant(t.get('demarree'))
        if t['statut'] == STATUT_A_FAIRE and debut is not None:
            actives.append((t, debut, duree_minutes(debut, maintenant)))
    actives.sort(key=lambda r: (r[1], r[0]['id']))

    if fmt == "json":
        _en_json({"date": maintenant.strftime("%Y-%m-%d %H:%M"), "total": len(actives),
                  "taches": [{**t, "ecoule_minutes": m} for t, _, m in actives]})
        return
    texte = [_titre("▶️  TÂCHES EN COURS")]
    for t, _, m in actives:
        texte.append(_ligne_tache(t) + f" {couleurs.CLR_TODO}[▶ {duree_lisible(m)}]{couleurs.CLR_RESET}")
    if not actives:
        texte.append(f"  {couleurs.CLR_DIM}Aucune tâche en cours (`todo task start ID`).{couleurs.CLR_RESET}")
    texte += _pied(f"{len(actives)} tâche(s) en cours", "durées calendaires")
    rangees = [[t['id'], str(m), t['demarree'], t['priorite'], t['titre']] for t, _, m in actives]
    _sortie(fmt, ("ID", "ÉCOULÉ (MIN)", "DÉMARRÉE", "PRIO", "TITRE"), rangees, "Aucune tâche en cours.", texte, pager)


# ---------------------------------------------------------------------------------------------- délais
def _resume_delais(nom, minutes):
    """Statistiques d'une série de délais (minutes) : nombre, moyenne, médiane, plus court, plus long (entiers)."""
    return {"nom": nom, "nombre": len(minutes), "moyenne": round(statistics.mean(minutes)),
            "mediane": round(statistics.median(minutes)), "min": min(minutes), "max": max(minutes)}


def rapport_delais(depuis, jusqu_a, avec_archive=False, par=None, fmt="text", pager=True):
    """Délai démarrage → fin des tâches terminées entre `depuis` et `jusqu_a` (dates incluses).

    `par` : None (tout ensemble), "tag" (une tâche compte pour chacun de ses tags) ou "prio". Les tâches terminées
    sans instant de démarrage ne peuvent pas être mesurées : elles sont comptées à part. Délais calendaires.
    """
    mesurees, sans_demarrage = [], 0
    for t in _lire_taches() + (_lire_archive() if avec_archive else []):
        jour = _jour(t.get('date_terminee'))
        if t['statut'] != STATUT_TERMINE or jour is None or not (depuis <= jour <= jusqu_a):
            continue
        debut, fin = lire_instant(t.get('demarree')), lire_instant(t.get('date_terminee'))
        if debut is None or fin is None:
            sans_demarrage += 1
        else:
            mesurees.append((t, duree_minutes(debut, fin)))
    mesurees.sort(key=lambda r: (r[0]['date_terminee'], r[0]['id']))

    series = {}
    for t, m in mesurees:
        if par == "tag":
            noms = t['tags'] or ["(sans tag)"]
        elif par == "prio":
            noms = [t['priorite']]
        else:
            noms = ["tout"]
        for nom in noms:
            series.setdefault(nom, []).append(m)
    if par == "prio":
        ordre = [p for p in reversed(PRIORITES) if p in series]
    else:
        ordre = sorted(series, key=lambda n: (-len(series[n]), n))
    groupes = [_resume_delais(n, series[n]) for n in ordre]

    if fmt == "json":
        _en_json({"depuis": depuis.isoformat(), "jusqu_a": jusqu_a.isoformat(), "avec_archive": avec_archive, "par": par,
                  "mesurees": len(mesurees), "sans_demarrage": sans_demarrage, "unite": "minutes", "groupes": groupes,
                  "taches": [{**t, "delai_minutes": m} for t, m in mesurees]})
        return
    aujourdhui = datetime.now().date()
    texte = [_titre(f"⏱️  DÉLAIS DE TRAITEMENT : {_libelle_jour(depuis, aujourdhui)} → {_libelle_jour(jusqu_a, aujourdhui)}")]
    if par:
        texte.append(f"  {couleurs.CLR_DIM}par {'tag' if par == 'tag' else 'priorité'}{couleurs.CLR_RESET}")
    for g in groupes:
        entete = "" if g["nom"] == "tout" else f"{couleurs.CLR_BOLD}{g['nom']}{couleurs.CLR_RESET}  "
        texte.append(f"\n  {entete}{couleurs.CLR_DIM}({g['nombre']} tâche(s)){couleurs.CLR_RESET}\n"
                     f"    moyenne {duree_lisible(g['moyenne'])} · médiane {duree_lisible(g['mediane'])} · "
                     f"plus court {duree_lisible(g['min'])} · plus long {duree_lisible(g['max'])}")
    if not groupes:
        texte.append(f"\n  {couleurs.CLR_DIM}Aucune tâche terminée et démarrée sur cette période.{couleurs.CLR_RESET}")
    morceaux = [f"{len(mesurees)} tâche(s) mesurée(s)"]
    if sans_demarrage:
        morceaux.append(f"{sans_demarrage} terminée(s) sans démarrage (non mesurées)")
    texte += _pied(*morceaux, "durées calendaires")
    rangees = [[g["nom"], str(g["nombre"]), str(g["moyenne"]), str(g["mediane"]), str(g["min"]), str(g["max"])] for g in groupes]
    _sortie(fmt, ("GROUPE", "NOMBRE", "MOYENNE (MIN)", "MÉDIANE (MIN)", "MIN", "MAX"), rangees,
            "Aucune tâche terminée et démarrée sur cette période.", texte, pager)
