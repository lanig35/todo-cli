"""Accès à la base DBM : lecture/normalisation des tâches et résolution des identifiants."""
import dbm
import glob
import json
import os
import sys
from .config import PRIORITES, STATUT_A_FAIRE
from . import config
from . import couleurs, journal
from .dates import _parser_recurrence, lire_instant


# Lecture transverse (--all-projects, rappel) : `_lire_taches` / `_lire_archive` rassemblent alors tous les projets
_tous = False              # lire tous les projets au lieu du seul projet courant
_etiqueter = True          # noter le projet d'origine dans chaque tâche (clé `projet`)


def definir_tous_projets(actif, etiqueter=True):
    """Active la lecture de tous les projets (lecture seule : seules les commandes de consultation s'en servent)."""
    global _tous, _etiqueter
    _tous, _etiqueter = actif, etiqueter


def tous_projets():
    return _tous


def etiquette_projet(t):
    """Marque d'affichage du projet d'une tâche (` [travail]`), vide hors lecture transverse."""
    return f" {couleurs.CLR_DIM}[{t['projet']}]{couleurs.CLR_RESET}" if t.get('projet') else ""


def _chemins_base(nom_fichier):
    """(projet, chemin de base) de chaque projet à lire : le courant, ou tous en lecture transverse."""
    noms = config.projets() if _tous else [config.projet()]
    return [(nom, os.path.join(config.dossier_du_projet(nom), nom_fichier)) for nom in noms]


def _base_existe():
    """Vrai si au moins un fichier de la base DBM est présent sur le disque (dans l'un des projets lus)."""
    return any(glob.glob(f"{chemin}*") for _, chemin in _chemins_base(config._FICHIERS["DB_NAME"]))

def _archive_existe():
    """Vrai si au moins un fichier de la base d'archive est présent sur le disque (dans l'un des projets lus)."""
    return any(glob.glob(f"{chemin}*") for _, chemin in _chemins_base(config._FICHIERS["ARCHIVE_NAME"]))

def _normaliser_notes(brutes):
    """Liste de notes valides ({date, texte, action}) ; ce qui n'est pas une note exploitable est ignoré."""
    notes = []
    for n in brutes if isinstance(brutes, list) else []:
        if isinstance(n, dict) and n.get('texte'):
            notes.append({"date": str(n.get('date') or ""), "texte": str(n['texte']), "action": str(n.get('action') or "note")})
            if n.get('modifiee'):
                notes[-1]["modifiee"] = str(n['modifiee'])
    return notes

def _normaliser_pieces(brutes):
    """Liste de pièces jointes valides ({nom, date, taille, sha256, commentaire?}) ; le reste est ignoré (voir pieces_jointes.py)."""
    pieces, vus = [], set()
    for p in brutes if isinstance(brutes, list) else []:
        nom = p.get('nom') if isinstance(p, dict) else None
        if not isinstance(nom, str) or not nom or nom in vus or nom.startswith('.') or '/' in nom or '\\' in nom or '\x00' in nom:
            continue
        vus.add(nom)
        taille = p.get('taille')
        piece = {"nom": nom, "date": str(p.get('date') or ""),
                 "taille": taille if isinstance(taille, int) and not isinstance(taille, bool) and taille >= 0 else 0,
                 "sha256": str(p.get('sha256') or "")}
        if p.get('commentaire'):
            piece["commentaire"] = str(p['commentaire'])
        pieces.append(piece)
    return pieces

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
    demarree = t.get('demarree')   # instant de démarrage 'AAAA-MM-JJ HH:MM' (suivi du temps) ; invalide ou absent : jamais démarrée
    t['demarree'] = demarree[:16] if isinstance(demarree, str) and lire_instant(demarree) else None
    t['tags'] = t.get('tags') or []
    # Récurrence : valeur invalide ou absente => tâche non récurrente
    t['recurrence'] = _parser_recurrence(str(t['recurrence'])) if t.get('recurrence') else None
    t['suivante'] = t.get('suivante') or None  # id de l'occurrence créée à la complétion
    # Échéance d'origine de la série (AAAA-MM-JJ) : les occurrences se calculent depuis elle, pas depuis
    # la précédente, sinon un « 31 du mois » ramené au 28 en février resterait au 28 (voir _prochaine_echeance)
    t['ancre'] = t['ancre'] if isinstance(t.get('ancre'), str) and t['ancre'] else None
    apres = t.get('apres')       # ids des tâches dont celle-ci dépend (voir dependances.py)
    t['apres'] = list(dict.fromkeys(x for x in apres if isinstance(x, str) and x)) if isinstance(apres, list) else []
    t['notes'] = _normaliser_notes(t.get('notes'))  # journal daté de la tâche (absent des anciennes tâches)
    t['pieces_jointes'] = _normaliser_pieces(t.get('pieces_jointes'))  # fichiers joints (absents des anciennes tâches)
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

def _lire_bases(nom_fichier):
    """Tâches des bases `nom_fichier` du projet courant (ou de tous), en lecture seule, sans jamais rien créer."""
    taches = []
    for nom, chemin in _chemins_base(nom_fichier):
        if not glob.glob(f"{chemin}*"):
            continue
        with dbm.open(chemin, 'r') as db:
            lues = _charger_taches(db)
        if _tous and _etiqueter:
            for t in lues:
                t['projet'] = nom
        taches += lues
    return taches

def _lire_taches():
    """Charge toutes les tâches en lecture seule, sans jamais créer la base."""
    return _lire_bases(config._FICHIERS["DB_NAME"])

def _lire_archive():
    """Charge toutes les tâches archivées en lecture seule, sans jamais créer la base d'archive."""
    return _lire_bases(config._FICHIERS["ARCHIVE_NAME"])

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
