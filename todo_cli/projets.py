"""Projets : listes de tâches indépendantes (perso, travail…), chacune avec sa base, son archive et ses sauvegardes.

Le projet `default` vit à la racine du stockage (disposition historique, aucune migration) ; les autres dans
`<stockage>/projects/<nom>/`. Le projet courant se choisit par `--project/-p`, `TODO_PROJECT`, `[general] project`
(écrit par `project use`), sinon `default` ; la résolution est dans `config.py`. Ce module porte le groupe de
commandes `project` : current, list, create, use, rename, delete (déplace dans une corbeille récupérable).
"""
import dbm
import json
import os
import sys

from . import config, couleurs, journal, pieces_jointes, reglages
from .configuration import ecrire_reglage
from .formats import imprimer_plain, tableau
from .stockage import _charger_taches
from .config import PROJET_DEFAUT, STATUT_A_FAIRE


def _refus(raison, message, fmt="text", **champs):
    """Refus d'une commande `project` : message sur stderr (ou document JSON sur stdout) ; retourne False."""
    journal.echec(raison, **champs)
    if fmt == "json":
        print(json.dumps({"erreur": raison, "detail": message, **champs}, indent=2, ensure_ascii=False))
    else:
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {message}.", file=sys.stderr)
    return False


def _lire(base):
    """Tâches d'une base DBM (liste vide si elle n'existe pas), sans jamais la créer."""
    try:
        with dbm.open(base, 'r') as db:
            return _charger_taches(db)
    except dbm.error:
        return []


def compter(nom):
    """{'a_faire', 'terminees', 'archivees'} d'un projet existant."""
    dossier = config.dossier_du_projet(nom)
    taches = _lire(os.path.join(dossier, config._FICHIERS["DB_NAME"]))
    a_faire = sum(t['statut'] == STATUT_A_FAIRE for t in taches)
    archivees = len(_lire(os.path.join(dossier, config._FICHIERS["ARCHIVE_NAME"])))
    return {"a_faire": a_faire, "terminees": len(taches) - a_faire, "archivees": archivees}


def _origine_lisible(origine):
    return "option --project" if origine == "option" else origine


# ---------------------------------------------------------------------------------------------- current
def afficher_courant(courant, origine, fmt="text"):
    """Nom du projet courant et d'où il vient (option, variable, fichier ou défaut)."""
    existe = config.existe(courant)
    if fmt == "json":
        print(json.dumps({"projet": courant, "origine": origine, "existe": existe,
                          "dossier": config.dossier_du_projet(courant)}, indent=2, ensure_ascii=False))
    elif fmt == "plain":
        print(courant)
    elif fmt == "table":
        print(tableau(("PROJET", "ORIGINE", "DOSSIER"), [(courant, _origine_lisible(origine), config.dossier_du_projet(courant))]))
    else:
        print(f" 📁 Projet courant : {couleurs.CLR_BOLD}{courant}{couleurs.CLR_RESET} "
              f"{couleurs.CLR_DIM}({_origine_lisible(origine)}){couleurs.CLR_RESET}")
    if not existe:
        return _refus("unknown_project", f"le projet '{courant}' n'existe pas (`todo project create {courant}`, "
                      f"ou `todo project use default`)", "text", projet=courant)
    return True


# ---------------------------------------------------------------------------------------------- list
def lister(courant, fmt="text"):
    lignes = []
    for nom in config.projets():
        n = compter(nom)
        lignes.append((nom, n["a_faire"], n["terminees"], n["archivees"], nom == courant))
    if fmt == "json":
        print(json.dumps({"courant": courant, "projets": [
            {"projet": nom, "a_faire": a, "terminees": d, "archivees": r, "courant": c, "dossier": config.dossier_du_projet(nom)}
            for nom, a, d, r, c in lignes]}, indent=2, ensure_ascii=False))
    elif fmt == "plain":
        imprimer_plain([nom, str(a), str(d), str(r), "1" if c else "0"] for nom, a, d, r, c in lignes)
    elif fmt == "table":
        print(tableau(("PROJET", "À FAIRE", "TERMINÉES", "ARCHIVÉES", "COURANT"),
                      [(nom, a, d, r, "*" if c else "") for nom, a, d, r, c in lignes]))
    else:
        print(f"\n {couleurs.CLR_CYAN}─── 📁 PROJETS ───{couleurs.CLR_RESET}")
        largeur = max(len(nom) for nom, *_ in lignes)
        for nom, a, d, r, c in lignes:
            marque = f"{couleurs.CLR_BOLD}●{couleurs.CLR_RESET}" if c else " "
            print(f"  {marque} {couleurs.CLR_BOLD}{nom:<{largeur}}{couleurs.CLR_RESET}  "
                  f"{couleurs.CLR_DIM}{a} à faire · {d} terminée(s) · {r} archivée(s){couleurs.CLR_RESET}")
        print(f"\n {couleurs.CLR_DIM}● projet courant ({_origine_lisible(config.origine_projet())}){couleurs.CLR_RESET}\n")
    return True


# ---------------------------------------------------------------------------------------------- create
def _nom_valide(nom, fmt):
    try:
        return config.valider_nom(nom)
    except ValueError as e:
        _refus("invalid_project_name", str(e), fmt, projet=nom)
        return None


def creer(nom, fmt="text"):
    if _nom_valide(nom, fmt) is None:
        return False
    try:
        config.creer_projet(nom)
    except ValueError as e:
        return _refus("project_exists", str(e), fmt, projet=nom)
    except OSError as e:
        return _refus("project_error", f"impossible de créer le projet '{nom}' : {e.strerror or e}", fmt, projet=nom)
    journal.noter(modifie=True, project_action="create", target=nom)
    if fmt == "json":
        print(json.dumps({"projet": nom, "cree": True, "dossier": config.dossier_du_projet(nom)}, indent=2, ensure_ascii=False))
    elif fmt != "plain":
        print(f" ✅ Projet {couleurs.CLR_BOLD}{nom}{couleurs.CLR_RESET} créé. "
              f"{couleurs.CLR_DIM}Utilisez-le avec -p {nom}, ou `todo project use {nom}`.{couleurs.CLR_RESET}")
    return True


# ---------------------------------------------------------------------------------------------- use
def utiliser(nom, fmt="text"):
    """Fait de `nom` le projet courant (écrit `[general] project` dans le fichier de configuration)."""
    if _nom_valide(nom, fmt) is None:
        return False
    if not config.existe(nom):
        return _refus("unknown_project", f"le projet '{nom}' n'existe pas (`todo project create {nom}`)", fmt, projet=nom)
    return ecrire_reglage("general.project", nom, fmt)


# ---------------------------------------------------------------------------------------------- rename
def renommer(ancien, nouveau, fmt="text"):
    if _nom_valide(ancien, fmt) is None or _nom_valide(nouveau, fmt) is None:
        return False
    if PROJET_DEFAUT in (ancien, nouveau):
        return _refus("reserved_project", f"le projet '{PROJET_DEFAUT}' ne peut être ni renommé ni remplacé", fmt, projet=ancien)
    if not config.existe(ancien):
        return _refus("unknown_project", f"le projet '{ancien}' n'existe pas", fmt, projet=ancien)
    if config.existe(nouveau):
        return _refus("project_exists", f"le projet '{nouveau}' existe déjà", fmt, projet=nouveau)
    try:
        pieces_jointes.renommer_projet(ancien, nouveau)           # [attachments] dir : les pièces suivent le projet
        try:
            config.renommer_projet(ancien, nouveau)
        except OSError:
            pieces_jointes.renommer_projet(nouveau, ancien)       # retour en arrière : le renommage est tout ou rien
            raise
    except OSError as e:
        return _refus("project_error", f"impossible de renommer '{ancien}' : {e.strerror or e}", fmt, projet=ancien)
    journal.noter(modifie=True, project_action="rename", target=ancien, new=nouveau)
    if reglages.valeur_du_fichier(reglages.trouver("general.project")) == ancien:
        ecrire_reglage("general.project", nouveau, "plain")      # le projet courant suit son nouveau nom
    if fmt == "json":
        print(json.dumps({"ancien": ancien, "nouveau": nouveau, "renomme": True}, indent=2, ensure_ascii=False))
    elif fmt != "plain":
        print(f" ✅ Projet {couleurs.CLR_BOLD}{ancien}{couleurs.CLR_RESET} renommé en {couleurs.CLR_BOLD}{nouveau}{couleurs.CLR_RESET}.")
    return True


# ---------------------------------------------------------------------------------------------- delete
def supprimer(nom, courant, oui=False, forcer=False, fmt="text"):
    """Déplace un projet dans la corbeille (`<stockage>/.trash/`), d'où il se récupère à la main."""
    if _nom_valide(nom, fmt) is None:
        return False
    if nom == PROJET_DEFAUT:
        return _refus("reserved_project", f"le projet '{PROJET_DEFAUT}' ne peut pas être supprimé", fmt, projet=nom)
    if not config.existe(nom):
        return _refus("unknown_project", f"le projet '{nom}' n'existe pas", fmt, projet=nom)
    if nom == courant:
        return _refus("current_project", f"'{nom}' est le projet courant : choisissez-en un autre d'abord "
                      f"(`todo project use default`)", fmt, projet=nom)
    n = compter(nom)
    total = n["a_faire"] + n["terminees"] + n["archivees"]
    if total and not forcer:
        return _refus("project_not_empty", f"le projet '{nom}' contient {total} tâche(s) ({n['a_faire']} à faire, "
                      f"{n['terminees']} terminée(s), {n['archivees']} archivée(s)) : ajoutez --force pour le supprimer", fmt, projet=nom)
    if not oui:
        if not sys.stdin.isatty():
            return _refus("confirmation_required", f"suppression du projet '{nom}' : ajoutez -y pour confirmer "
                          f"(aucun terminal pour poser la question)", fmt, projet=nom)
        try:
            reponse = input(f" {couleurs.CLR_DEL}⚠️ Supprimer{couleurs.CLR_RESET} le projet '{nom}' ({total} tâche(s)) ? "
                            f"Il est déplacé dans la corbeille. (y/N) : ").strip().lower()
        except EOFError:
            reponse = ""
        if reponse != "y":
            print(" ❌ Opération annulée.")
            return True
    try:
        cible = config.mettre_a_la_corbeille(nom)
    except OSError as e:
        return _refus("project_error", f"impossible de supprimer '{nom}' : {e.strerror or e}", fmt, projet=nom)
    journal.noter(modifie=True, project_action="delete", target=nom)
    pieces = None
    try:
        pieces = pieces_jointes.mettre_projet_a_la_corbeille(nom, os.path.basename(cible))
    except OSError as e:
        rouge, raz = couleurs._couleurs_erreur()
        print(f" {rouge}⚠️{raz} Pièces jointes de '{nom}' non déplacées : {e.strerror or e}", file=sys.stderr)
    if fmt == "json":
        print(json.dumps({"projet": nom, "supprime": True, "corbeille": cible, **({"corbeille_pieces_jointes": pieces} if pieces else {})},
                         indent=2, ensure_ascii=False))
    elif fmt != "plain":
        print(f" 🗑️  Projet {couleurs.CLR_BOLD}{nom}{couleurs.CLR_RESET} déplacé dans la corbeille : {cible}\n"
              f"    {couleurs.CLR_DIM}Pour le récupérer : déplacez ce dossier vers "
              f"{config.dossier_du_projet(nom)}{couleurs.CLR_RESET}")
        if pieces:
            print(f"    {couleurs.CLR_DIM}Pièces jointes déplacées dans {pieces} (à remettre dans {os.path.join(pieces_jointes.racine_configuree(), nom)}){couleurs.CLR_RESET}")
    return True

