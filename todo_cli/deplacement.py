"""Déplacer des tâches d'un projet à un autre (`task move ID… --to projet`).

Le déplacement écrit d'abord dans le projet cible, puis supprime de la source : un plantage au milieu laisse au pire
une tâche en double, jamais perdue. Les deux projets sont verrouillés (voir `verrou.prendre_projets`).

Les dépendances (`--after`) ne traversent pas les projets : la tâche déplacée n'attend plus ce qui reste dans la
source, et ce qui l'attendait dans la source ne l'attend plus (avertissement dans les deux cas). Des tâches
déplacées ensemble gardent leurs liens. Une occurrence suivante restée dans la source n'est plus reliée.

Les pièces jointes (fichiers) suivent la tâche dans le projet cible.

Limite assumée : `undo` ne défait un déplacement que dans un projet à la fois (chaque projet a ses sauvegardes).
Annuler dans la source remet la tâche dans la source, sans la retirer de la cible, et inversement.
"""
import dbm
import json
import os

from . import config, couleurs, journal, pieces_jointes
from .stockage import _afficher_bilan_lot, _base_existe, _normaliser_tache, _resoudre_ids
from .sauvegardes import sauvegarder_base


def cible_valide(cible):
    """Message d'erreur si `cible` ne peut pas recevoir de tâches depuis le projet courant, sinon None."""
    try:
        config.valider_nom(cible)
    except ValueError as e:
        return str(e)
    if cible == config.projet():
        return f"la tâche est déjà dans le projet '{cible}'"
    if not config.existe(cible):
        return f"le projet '{cible}' n'existe pas (`todo project create {cible}`)"
    return None


def _erreur(raison, message):
    journal.echec(raison)
    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {message}.")
    return False


def _sauvegarder_cible(cible):
    """Sauvegarde du projet cible (après la modification, comme toute commande), sans changer de projet courant."""
    courant, origine = config.projet(), config.origine_projet()
    config.definir_projet(cible, "option")
    try:
        sauvegarder_base()
    finally:
        config.definir_projet(courant, origine)


def deplacer_taches(ids, cible):
    """Déplace les tâches désignées (préfixes d'id ou identifiants complets) vers le projet `cible`.

    Retourne True si aucun identifiant n'a posé problème (introuvable, ambigu, entrée corrompue, déjà dans la cible).
    """
    probleme = cible_valide(cible)
    if probleme:
        return _erreur("invalid_target_project", probleme)
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, rien à déplacer.{couleurs.CLR_RESET}")
        return False
    source = config.projet()
    base_cible = os.path.join(config.dossier_du_projet(cible), config._FICHIERS["DB_NAME"])

    deplacees, echecs, titres_cles = 0, 0, []
    avertissements = []
    with dbm.open(config.DB_NAME, 'w') as db_source, dbm.open(base_cible, 'c') as db_cible:
        cles, echecs = _resoudre_ids(db_source, ids)
        a_deplacer = {}
        for cle in cles:
            try:
                a_deplacer[cle.decode('utf-8', errors='replace')] = _normaliser_tache(db_source[cle])
            except ValueError:
                journal.echec("corrupted_entry")
                print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Cette entrée est corrompue et ne peut pas être déplacée.")
                echecs += 1
        for identifiant in [i for i in a_deplacer if i.encode('utf-8') in db_cible]:
            print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Le projet '{cible}' contient déjà une tâche d'identifiant {identifiant[:8]} : "
                  f"'{a_deplacer.pop(identifiant)['titre']}' reste dans '{source}'.")
            echecs += 1
        if a_deplacer:
            restantes = {}
            for cle in db_source.keys():
                identifiant = cle.decode('utf-8', errors='replace')
                if identifiant in a_deplacer:
                    continue
                try:
                    restantes[identifiant] = _normaliser_tache(db_source[cle])
                except ValueError:
                    continue

            # 1. Liens des tâches déplacées : seuls ceux qui visent d'autres tâches déplacées survivent
            for identifiant, t in a_deplacer.items():
                perdus = [f"{restantes[d]['titre']} (restée dans '{source}')" for d in t['apres'] if d in restantes]
                t['apres'] = [d for d in t['apres'] if d in a_deplacer]
                if perdus:
                    avertissements.append(f"'{t['titre']}' n'attend plus : {', '.join(perdus)}")
                if t['suivante'] and t['suivante'] not in a_deplacer:
                    t['suivante'] = None
            # 2. Tâches restées dans la source : elles n'attendent plus ce qui est parti, ni ne pointent vers lui
            modifiees = {}
            for identifiant, r in restantes.items():
                attendues = [d for d in r['apres'] if d in a_deplacer]
                if attendues:
                    r['apres'] = [d for d in r['apres'] if d not in a_deplacer]
                    modifiees[identifiant] = r
                    avertissements.append(f"'{r['titre']}' n'attend plus : "
                                          + ", ".join(f"{a_deplacer[d]['titre']} (déplacée vers '{cible}')" for d in attendues))
                if r['suivante'] in a_deplacer:
                    r['suivante'] = None
                    modifiees[identifiant] = r

            # 3. Écriture : la cible d'abord, puis la source
            for identifiant, t in a_deplacer.items():
                db_cible[identifiant] = json.dumps(t)
            for identifiant, r in modifiees.items():
                db_source[identifiant] = json.dumps(r)
            for identifiant, t in a_deplacer.items():
                del db_source[identifiant]
                pieces_jointes.deplacer_vers_projet(identifiant, cible)
                print(f" {couleurs.CLR_DONE}➡️ {couleurs.CLR_RESET} Tâche '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' déplacée "
                      f"vers le projet {couleurs.CLR_BOLD}{cible}{couleurs.CLR_RESET} {couleurs.CLR_DIM}(id: {identifiant[:8]}){couleurs.CLR_RESET}")
            deplacees = len(a_deplacer)
            titres_cles = [(i, t['titre']) for i, t in a_deplacer.items()]

    if deplacees:
        sauvegarder_base()                 # source
        _sauvegarder_cible(cible)
        for a in avertissements:
            print(f"    {couleurs.CLR_DEL}⚠️ {a}.{couleurs.CLR_RESET}")
        print(f"    {couleurs.CLR_DIM}↩️  `undo` agit sur un projet à la fois : annuler ici remet la tâche dans '{source}' "
              f"sans la retirer de '{cible}' (et inversement).{couleurs.CLR_RESET}")
        journal.noter(ids=[i for i, _ in titres_cles], titres=[t for _, t in titres_cles], modifie=True, to=cible)
    _afficher_bilan_lot(len(ids), deplacees, "déplacée(s)", echecs)
    return echecs == 0
