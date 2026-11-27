"""Rapports : tags, tâches bloquées, en retard, qui traînent, bilan des tâches terminées, tâches en cours, délais et revue hebdomadaire.

Chaque rapport existe dans les quatre formats habituels :
  text  affichage décoré (pager automatique), table  tableau aligné sans couleur,
  plain une ligne par enregistrement, champs séparés par des tabulations (contrat stable : voir README),
  json  un objet documenté par rapport (compatible jq).
Les rapports lisent la base sans la modifier.
"""
import json
import statistics
from datetime import datetime, timedelta

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


# ---------------------------------------------------------------------------------------------- revue hebdomadaire
def construire_revue(taches, archivees, aujourdhui, jours, avant, maintenant=None):
    """Données de la revue : la semaine écoulée (`jours` jours, aujourd'hui compris) et la semaine à venir.

    Fonction pure (testable) : `taches` et `archivees` sont les listes lues dans la base ; `avant` est la date au plus tard
    de création des tâches « qui traînent ». Les durées (en cours) sont calendaires.
    """
    maintenant = maintenant or datetime.now()
    depuis = aujourdhui - timedelta(days=jours - 1)
    fin = aujourdhui + timedelta(days=jours - 1)
    a_faire = [t for t in taches if t['statut'] == STATUT_A_FAIRE]

    def dans_la_periode(valeur):
        jour = _jour(valeur)
        return jour is not None and depuis <= jour <= aujourdhui

    terminees = [t for t in taches + archivees if t['statut'] == STATUT_TERMINE and dans_la_periode(t.get('date_terminee'))]
    terminees.sort(key=lambda t: (t['date_terminee'], t['id']), reverse=True)
    creees = [t for t in taches + archivees if dans_la_periode(t.get('date_creation'))]

    retards = []
    for t in a_faire:
        echeance = _jour(t['date_echeance'])
        if echeance is not None and echeance < aujourdhui:
            retards.append({**t, "jours_retard": (aujourdhui - echeance).days})
    retards.sort(key=lambda t: (-t["jours_retard"], -PRIORITES.index(t['priorite']), t.get('date_creation') or "", t['id']))

    en_cours = []
    for t in a_faire:
        debut = lire_instant(t.get('demarree'))
        if debut is not None:
            en_cours.append({**t, "ecoule_minutes": duree_minutes(debut, maintenant), "_debut": debut})
    en_cours.sort(key=lambda t: (t["_debut"], t['id']))
    for t in en_cours:
        del t["_debut"]

    par_id = {t['id']: t for t in taches}
    bloquees = []
    for t in dependances.annoter(taches):
        if t['bloquee_par']:
            bloquees.append({**t, "attend": [{"id": d, "titre": par_id[d]['titre']} for d in t['bloquee_par'] if d in par_id]})
    bloquees.sort(key=lambda t: (t['date_echeance'] or "9999-12-31",) + _ordre(t))

    trainent = []
    for t in a_faire:
        creation = _jour(t.get('date_creation'))
        if not t['date_echeance'] and creation is not None and creation <= avant:
            trainent.append({**t, "age_jours": (aujourdhui - creation).days})
    trainent.sort(key=lambda t: (-t["age_jours"], -PRIORITES.index(t['priorite']), t['id']))

    par_jour, plus_tard, sans_echeance = {}, 0, 0
    for t in a_faire:
        echeance = _jour(t['date_echeance'])
        if echeance is None:
            sans_echeance += 1
        elif echeance > fin:
            plus_tard += 1
        elif echeance >= aujourdhui:
            par_jour.setdefault(echeance, []).append(t)
    for j in par_jour:
        par_jour[j].sort(key=_ordre)
    jours_avenir = [{"date": j.isoformat(), "taches": par_jour[j]} for j in sorted(par_jour)]

    return {
        "date": aujourdhui.isoformat(), "depuis": depuis.isoformat(), "jusqu_a": aujourdhui.isoformat(), "jours": jours,
        "bilan": {"terminees": len(terminees), "creees": len(creees), "a_faire": len(a_faire), "en_retard": len(retards),
                  "en_cours": len(en_cours), "bloquees": len(bloquees), "qui_trainent": len(trainent),
                  "a_venir": sum(len(j["taches"]) for j in jours_avenir)},
        "terminees": {"total": len(terminees), "taches": terminees},
        "en_retard": {"total": len(retards), "taches": retards},
        "en_cours": {"total": len(en_cours), "taches": en_cours},
        "bloquees": {"total": len(bloquees), "taches": bloquees},
        "qui_trainent": {"avant": avant.isoformat(), "total": len(trainent), "taches": trainent},
        "a_venir": {"debut": aujourdhui.isoformat(), "fin": fin.isoformat(), "total": sum(len(j["taches"]) for j in jours_avenir),
                    "jours": jours_avenir, "plus_tard": plus_tard, "sans_echeance": sans_echeance},
    }


def rapport_revue(jours=7, avant=None, libelle_avant="30d", limite=10, fmt="text", pager=True):
    """Revue hebdomadaire en lecture seule : bilan de la semaine écoulée, ce qui demande une décision, semaine à venir."""
    aujourdhui = datetime.now().date()
    avant = avant or aujourdhui - timedelta(days=30)
    revue = construire_revue(_lire_taches(), _lire_archive(), aujourdhui, jours, avant)
    if fmt == "json":
        _en_json(revue)
        return

    b = revue["bilan"]
    rangees = []
    for t in revue["terminees"]["taches"]:
        rangees.append(["terminee", t['id'], t['priorite'], t['date_terminee'], t['titre']])
    for t in revue["en_retard"]["taches"]:
        rangees.append(["retard", t['id'], t['priorite'], t['date_echeance'], t['titre']])
    for t in revue["en_cours"]["taches"]:
        rangees.append(["en_cours", t['id'], t['priorite'], t['demarree'], t['titre']])
    for t in revue["bloquees"]["taches"]:
        rangees.append(["bloquee", t['id'], t['priorite'], t['date_echeance'] or "", t['titre']])
    for t in revue["qui_trainent"]["taches"]:
        rangees.append(["traine", t['id'], t['priorite'], t['date_creation'][:10], t['titre']])
    for j in revue["a_venir"]["jours"]:
        for t in j["taches"]:
            rangees.append(["a_venir", t['id'], t['priorite'], j["date"], t['titre']])
    if fmt in ("plain", "table"):
        _sortie(fmt, ("SECTION", "ID", "PRIO", "DATE", "TITRE"), rangees, "Rien à signaler.", [], pager)
        return

    def bloc(titre, taches, annexe=None, conseil=""):
        lignes = [_titre(titre)]
        if not taches:
            lignes.append(f"  {couleurs.CLR_DIM}Rien à signaler.{couleurs.CLR_RESET}")
            return lignes
        for t in taches[:limite]:
            lignes.append(_ligne_tache(t) + (annexe(t) if annexe else ""))
        if len(taches) > limite:
            lignes.append(f"  {couleurs.CLR_DIM}… et {len(taches) - limite} autre(s){' (' + conseil + ')' if conseil else ''}{couleurs.CLR_RESET}")
        return lignes

    depuis, fin = _parse_date(revue["depuis"]), _parse_date(revue["a_venir"]["fin"])
    texte = [_titre(f"📋 REVUE : {_libelle_jour(depuis, aujourdhui)} → {_libelle_jour(aujourdhui, aujourdhui)}"),
             f"  {couleurs.CLR_BOLD}{b['terminees']}{couleurs.CLR_RESET} terminée(s) · {couleurs.CLR_BOLD}{b['creees']}{couleurs.CLR_RESET} créée(s) · "
             f"{couleurs.CLR_BOLD}{b['a_faire']}{couleurs.CLR_RESET} à faire"
             + (f" · {couleurs.CLR_DEL}{b['en_retard']} en retard{couleurs.CLR_RESET}" if b['en_retard'] else "")]
    texte += bloc("✅ TERMINÉES CETTE SEMAINE", revue["terminees"]["taches"], lambda t: f" {couleurs.CLR_DIM}[{t['date_terminee'][:10]}]{couleurs.CLR_RESET}",
                  f"todo report done --since {jours}d")
    texte += bloc("⏰ EN RETARD", revue["en_retard"]["taches"], lambda t: f" {couleurs.CLR_DEL}[{t['jours_retard']} j.]{couleurs.CLR_RESET}",
                  "todo report overdue")
    texte += bloc("▶️  EN COURS", revue["en_cours"]["taches"], lambda t: f" {couleurs.CLR_TODO}[▶ {duree_lisible(t['ecoule_minutes'])}]{couleurs.CLR_RESET}",
                  "todo report active")
    texte += bloc("🔒 BLOQUÉES", revue["bloquees"]["taches"], lambda t: f" {couleurs.CLR_DIM}↳ attend : "
                  + ", ".join(a['titre'] for a in t['attend']) + couleurs.CLR_RESET, "todo report blocked")
    texte += bloc(f"🕸️  QUI TRAÎNENT (sans échéance, créées il y a {libelle_avant} ou plus)", revue["qui_trainent"]["taches"],
                  lambda t: f" {couleurs.CLR_DIM}[créée il y a {t['age_jours']} j.]{couleurs.CLR_RESET}", f"todo report stale --older-than {libelle_avant}")
    texte.append(_titre(f"📅 SEMAINE À VENIR : {_libelle_jour(aujourdhui, aujourdhui)} → {_libelle_jour(fin, aujourdhui)}"))
    av, restant = revue["a_venir"], limite
    if not av["jours"]:
        texte.append(f"  {couleurs.CLR_DIM}Rien d'échu sur cette période.{couleurs.CLR_RESET}")
    for j in av["jours"]:
        if restant <= 0:
            texte.append(f"  {couleurs.CLR_DIM}… et {av['total'] - (limite - restant)} autre(s) (todo agenda --days {jours}){couleurs.CLR_RESET}")
            break
        texte.append(f"\n  {couleurs.CLR_BOLD}{_libelle_jour(_parse_date(j['date']), aujourdhui).capitalize()}{couleurs.CLR_RESET} "
                     f"{couleurs.CLR_DIM}({len(j['taches'])}){couleurs.CLR_RESET}")
        for t in j["taches"][:restant]:
            texte.append(_ligne_tache(t))
        restant -= len(j["taches"])
    texte += _pied(f"{av['total']} échéance(s) cette semaine", f"{av['plus_tard']} plus tard", f"{av['sans_echeance']} sans échéance")
    _afficher_texte("\n".join(texte), pager)
