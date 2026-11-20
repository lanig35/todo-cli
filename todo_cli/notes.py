"""Notes des tâches : un journal daté, en ajout seul, distinct de la description.

Chaque note est `{"date", "texte", "action"}` ; `action` dit ce qui l'a produite (`note`, `done`,
`undone`, `postpone`, `edit`). Une note corrigée par `note edit` garde sa date et reçoit `modifiee`. Les notes vivent dans la tâche : elles suivent l'archivage, les
sauvegardes et `undo`. `remove` supprime la tâche : sa note (le motif) va au journal système.
"""
import dbm
import json
import sys
from datetime import datetime
from . import config
from .formats import imprimer_plain, tableau
from . import couleurs, journal
from .sauvegardes import sauvegarder_base
from .stockage import _base_existe, _normaliser_tache, _resoudre_id

LONGUEUR_MAX = 500


def valider_note(texte):
    """Texte de note nettoyé (espaces et retours à la ligne réduits à un espace) ; sort en erreur si vide ou trop long."""
    nettoye = " ".join((texte or "").split())
    if not nettoye:
        journal.echec("empty_note")
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} La note ne peut pas être vide.")
        sys.exit(1)
    if len(nettoye) > LONGUEUR_MAX:
        journal.echec("note_too_long", length=len(nettoye))
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Note trop longue ({len(nettoye)} caractères, maximum {LONGUEUR_MAX}).")
        sys.exit(1)
    return nettoye


def ajouter_a(t, texte, action):
    """Ajoute une note (déjà validée) à la tâche `t` en mémoire ; retourne la note."""
    note = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "texte": texte, "action": action}
    t['notes'].append(note)
    # Le texte n'est écrit au journal que si [log] titles est actif (ou pour remove, voir taches.py)
    journal.noter(note_len=len(texte), note=texte if journal.titres_actifs() else None)
    return note


def confirmer_ajout():
    """Ligne affichée après une action accompagnée de --note."""
    print(f"    {couleurs.CLR_DIM}📝 Note ajoutée.{couleurs.CLR_RESET}")


def lignes_notes(notes, indent="    "):
    """Notes numérotées (1 = la plus ancienne), de la plus ancienne à la plus récente."""
    largeur = len(str(len(notes)))
    lignes = []
    for position, n in enumerate(notes, 1):
        origine = f" {couleurs.CLR_DIM}({n['action']}){couleurs.CLR_RESET}" if n['action'] != "note" else ""
        modifiee = f" {couleurs.CLR_DIM}[modifiée {n['modifiee']}]{couleurs.CLR_RESET}" if n.get('modifiee') else ""
        lignes.append(f"{indent}{couleurs.CLR_DIM}{position:>{largeur}}. {n['date'] or '?':<16}{couleurs.CLR_RESET}  {n['texte']}{origine}{modifiee}")
    return lignes


def _erreur(raison, message, **champs):
    journal.echec(raison, **champs)
    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {message}")
    return False


def commande_note(id_recherche, mots, fmt="text", modifier=None, supprimer=None):
    """Ajoute, liste, modifie (`modifier` = numéro) ou supprime (`supprimer` = numéro) les notes d'une tâche.

    `todo note add ID texte…` ajoute ; `todo note list ID` liste ; `note edit ID N texte…` remplace le texte de la note N
    (sa date est conservée) ; `note delete ID N` la supprime. Retourne False en cas d'échec.
    """
    if modifier is not None and supprimer is not None:
        return _erreur("invalid_combination", "--edit et --delete ne se combinent pas.")
    if supprimer is not None and mots:
        return _erreur("invalid_combination", "--delete ne prend pas de texte.")
    if modifier is not None and not mots:
        return _erreur("empty_note", "--edit demande le nouveau texte de la note.")
    texte = valider_note(" ".join(mots)) if mots else None
    ecriture = bool(texte) or supprimer is not None
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, aucune tâche à annoter.{couleurs.CLR_RESET}")
        return False

    with dbm.open(config.DB_NAME, 'w' if ecriture else 'r') as db:
        cle = _resoudre_id(db, id_recherche)
        if cle is None:
            return False
        try:
            t = _normaliser_tache(db[cle])
        except ValueError:
            return _erreur("corrupted_entry", "Cette entrée est corrompue et ne peut pas être modifiée.")
        id_complet = cle.decode('utf-8', errors='replace')
        numero = modifier if modifier is not None else supprimer
        if numero is not None and not 1 <= numero <= len(t['notes']):
            quoi = "n'a aucune note" if not t['notes'] else f"n'a que {len(t['notes'])} note(s)"
            return _erreur("invalid_note_number", f"Note n°{numero} introuvable : '{t['titre']}' {quoi}.", index=numero)

        resultat = None
        if supprimer is not None:
            resultat = t['notes'].pop(supprimer - 1)
            journal.noter(note_deleted=supprimer, note=resultat['texte'] if journal.titres_actifs() else None)
        elif modifier is not None:
            resultat = t['notes'][modifier - 1]
            resultat['texte'] = texte
            resultat['modifiee'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            journal.noter(note_edited=modifier, note_len=len(texte), note=texte if journal.titres_actifs() else None)
        elif texte:
            resultat = ajouter_a(t, texte, "note")
        if ecriture:
            db[cle] = json.dumps(t)
            journal.noter(ids=[cle], titres=[t['titre']], modifie=True)

    if ecriture:
        sauvegarder_base()          # APRÈS fermeture de la base, pour capturer la modification
        total = len(t['notes'])
        if fmt == "json":
            cle_json = "supprimee" if supprimer is not None else "note"
            print(json.dumps({"id": id_complet, "titre": t['titre'], cle_json: resultat, "total": total},
                             indent=2, ensure_ascii=False))
        else:
            verbe = "supprimée de" if supprimer is not None else ("modifiée sur" if modifier is not None else "ajoutée à")
            nom = f"Note n°{numero} " if numero is not None else "Note "
            print(f" {couleurs.CLR_DONE}📝{couleurs.CLR_RESET} {nom}{verbe} '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' "
                  f"({total} au total).")
    elif fmt == "json":
        print(json.dumps({"id": id_complet, "titre": t['titre'], "notes": t['notes']}, indent=2, ensure_ascii=False))
    elif fmt == "plain":
        imprimer_plain((i, n['date'], n['texte']) for i, n in enumerate(t['notes'], start=1))
    elif fmt == "table" and t['notes']:
        print(tableau(("N°", "DATE", "NOTE"), [(i, n['date'], n['texte']) for i, n in enumerate(t['notes'], start=1)]))
    elif not t['notes']:
        print(f" {couleurs.CLR_DIM}Aucune note pour '{t['titre']}'. Ajout : todo note add {id_complet[:8]} \"texte\"{couleurs.CLR_RESET}")
    else:
        print(f"\n {couleurs.CLR_CYAN}─── 📝 NOTES : {t['titre']} ───{couleurs.CLR_RESET}")
        print("\n".join(lignes_notes(t['notes'], "  ")))
        print()
    return True
