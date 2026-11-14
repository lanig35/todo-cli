"""Accès à la base DBM : lecture/normalisation des tâches et résolution des identifiants."""
import dbm
import glob
import json
import sys
from .config import ARCHIVE_NAME, DB_NAME, PRIORITES, STATUT_A_FAIRE
from . import couleurs, journal
from .dates import _parser_recurrence


def _base_existe():
    """Vrai si au moins un fichier de la base DBM est présent sur le disque."""
    return bool(glob.glob(f"{DB_NAME}*"))

def _archive_existe():
    """Vrai si au moins un fichier de la base d'archive est présent sur le disque."""
    return bool(glob.glob(f"{ARCHIVE_NAME}*"))

def _normaliser_notes(brutes):
    """Liste de notes valides ({date, texte, action}) ; ce qui n'est pas une note exploitable est ignoré."""
    notes = []
    for n in brutes if isinstance(brutes, list) else []:
        if isinstance(n, dict) and n.get('texte'):
            notes.append({"date": str(n.get('date') or ""), "texte": str(n['texte']), "action": str(n.get('action') or "note")})
    return notes

def _normaliser_tache(brut):
    """Décode une entrée DBM et complète les champs manquants (compatibilité ascendante).

    Lève ValueError si l'entrée n'est pas un objet JSON exploitable.
    """
    t = json.loads(brut.decode('utf-8'))
    if not isinstance(t, dict):
        raise ValueError("entrée non conforme")
    t['titre'] = t.get('titre') or "(sans titre)"
    t['description'] = t.get('description') or ""
    priorite = str(t.get('priorite') or "medium").lower()
    t['priorite'] = priorite if priorite in PRIORITES else "medium"
    t['statut'] = t.get('statut') or STATUT_A_FAIRE
    t['date_echeance'] = t.get('date_echeance') or None
    t['date_terminee'] = t.get('date_terminee') or None  # absente des anciennes tâches terminées
    t['tags'] = t.get('tags') or []
    # Récurrence : valeur invalide ou absente => tâche non récurrente
    t['recurrence'] = _parser_recurrence(str(t['recurrence'])) if t.get('recurrence') else None
    t['suivante'] = t.get('suivante') or None  # id de l'occurrence créée à la complétion
    t['notes'] = _normaliser_notes(t.get('notes'))  # journal daté de la tâche (absent des anciennes tâches)
    return t

def _charger_taches(db):
    """Retourne la liste des tâches normalisées (avec leur 'id'), en ignorant les entrées illisibles."""
    taches = []
    for key in list(db.keys()):
        id_str = key.decode('utf-8', errors='replace')
        try:
            t = _normaliser_tache(db[key])
        except ValueError:
            # Les avertissements vont sur stderr : leur couleur dépend de stderr, pas de stdout
            rouge, raz = couleurs._couleurs_erreur()
            journal.echec("unreadable_entry", id=id_str[:8])
            print(f" {rouge}⚠️{raz} Entrée illisible ignorée (id: {id_str[:8]}).", file=sys.stderr)
            continue
        t['id'] = id_str
        taches.append(t)
    return taches

def _lire_taches():
    """Charge toutes les tâches en lecture seule, sans jamais créer la base."""
    if not _base_existe():
        return []
    with dbm.open(DB_NAME, 'r') as db:
        return _charger_taches(db)

def _lire_archive():
    """Charge toutes les tâches archivées en lecture seule, sans jamais créer la base d'archive."""
    if not _archive_existe():
        return []
    with dbm.open(ARCHIVE_NAME, 'r') as db:
        return _charger_taches(db)

def _resoudre_id(db, prefixe):
    """Retrouve la clé unique correspondant à un préfixe d'ID.

    Retourne None (avec un message) si le préfixe est vide, inconnu ou ambigu.
    """
    prefixe = prefixe.strip().lower()
    if not prefixe:
        journal.echec("empty_id")
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Identifiant vide.")
        return None

    correspondances = [k for k in db.keys() if k.decode('utf-8', errors='replace').lower().startswith(prefixe)]
    if not correspondances:
        journal.echec("unknown_id", prefix=prefixe)
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Aucun identifiant ne correspond à '{prefixe}'.")
        return None
    if len(correspondances) > 1:
        largeur = max(8, len(prefixe) + 2)
        candidats = ", ".join(k.decode('utf-8', errors='replace')[:largeur] for k in correspondances)
        journal.echec("ambiguous_id", prefix=prefixe)
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Identifiant ambigu '{prefixe}' ({len(correspondances)} correspondances : {candidats}).")
        print(f"    {couleurs.CLR_DIM}Précisez davantage le préfixe.{couleurs.CLR_RESET}")
        return None
    return correspondances[0]

def _resoudre_ids(db, prefixes):
    """Résout plusieurs préfixes d'ID AVANT toute modification de la base.

    Résoudre d'abord, modifier ensuite, rend le résultat indépendant de l'ordre et évite qu'une
    entrée créée en cours de route (occurrence d'une tâche récurrente) rende un préfixe ambigu.
    Retourne (clés uniques dans l'ordre donné, nombre d'identifiants en échec). Un préfixe qui
    désigne une tâche déjà indiquée est ignoré (sinon `done` créerait deux occurrences).
    """
    cles, vues, echecs = [], set(), 0
    for prefixe in prefixes:
        cle = _resoudre_id(db, prefixe)
        if cle is None:
            echecs += 1
        elif cle in vues:
            print(f" {couleurs.CLR_DIM}ℹ️  '{prefixe}' désigne une tâche déjà indiquée : ignoré.{couleurs.CLR_RESET}")
        else:
            vues.add(cle)
            cles.append(cle)
    return cles, echecs

def _afficher_bilan_lot(nb_demandes, nb_ok, libelle, nb_echecs):
    """Ligne de bilan d'une commande portant sur plusieurs ids (rien n'est affiché pour un seul)."""
    journal.noter(total=nb_demandes, failed=nb_echecs)
    if nb_demandes < 2:
        return
    texte = f"{nb_ok} tâche(s) {libelle}"
    if nb_echecs:
        texte += f", {couleurs.CLR_DEL}{nb_echecs} échec(s){couleurs.CLR_RESET}"
    print(f" {couleurs.CLR_BOLD}Bilan :{couleurs.CLR_RESET} {texte}.")
