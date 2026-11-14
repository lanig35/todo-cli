"""Notes des tâches : un journal daté, en ajout seul, distinct de la description.

Chaque note est `{"date", "texte", "action"}` ; `action` dit ce qui l'a produite (`note`, `done`,
`undone`, `postpone`, `edit`). Les notes vivent dans la tâche : elles suivent l'archivage, les
sauvegardes et `undo`. `remove` supprime la tâche : sa note (le motif) va au journal système.
"""
import dbm
import json
import sys
from datetime import datetime
from .config import DB_NAME
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
    """Notes mises en forme, de la plus ancienne à la plus récente."""
    lignes = []
    for n in notes:
        origine = f" {couleurs.CLR_DIM}({n['action']}){couleurs.CLR_RESET}" if n['action'] != "note" else ""
        lignes.append(f"{indent}{couleurs.CLR_DIM}{n['date'] or '?':<16}{couleurs.CLR_RESET}  {n['texte']}{origine}")
    return lignes


def commande_note(id_recherche, mots, fmt="table"):
    """`todo note ID texte…` ajoute une note ; `todo note ID` liste celles de la tâche. Retourne False en cas d'échec."""
    texte = valider_note(" ".join(mots)) if mots else None
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, aucune tâche à annoter.{couleurs.CLR_RESET}")
        return False

    with dbm.open(DB_NAME, 'w' if texte else 'r') as db:
        cle = _resoudre_id(db, id_recherche)
        if cle is None:
            return False
        try:
            t = _normaliser_tache(db[cle])
        except ValueError:
            journal.echec("corrupted_entry")
            print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Cette entrée est corrompue et ne peut pas être modifiée.")
            return False
        id_complet = cle.decode('utf-8', errors='replace')
        if texte:
            note = ajouter_a(t, texte, "note")
            db[cle] = json.dumps(t)
            journal.noter(ids=[cle], titres=[t['titre']], modifie=True)

    if texte:
        sauvegarder_base()          # APRÈS fermeture de la base, pour capturer la modification
        if fmt == "json":
            print(json.dumps({"id": id_complet, "titre": t['titre'], "note": note, "total": len(t['notes'])},
                             indent=2, ensure_ascii=False))
        else:
            print(f" {couleurs.CLR_DONE}📝{couleurs.CLR_RESET} Note ajoutée à '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' "
                  f"({len(t['notes'])} au total).")
    elif fmt == "json":
        print(json.dumps({"id": id_complet, "titre": t['titre'], "notes": t['notes']}, indent=2, ensure_ascii=False))
    elif not t['notes']:
        print(f" {couleurs.CLR_DIM}Aucune note pour '{t['titre']}'. Ajout : todo note {id_complet[:8]} \"texte\"{couleurs.CLR_RESET}")
    else:
        print(f"\n {couleurs.CLR_CYAN}─── 📝 NOTES : {t['titre']} ───{couleurs.CLR_RESET}")
        print("\n".join(lignes_notes(t['notes'], "  ")))
        print()
    return True
