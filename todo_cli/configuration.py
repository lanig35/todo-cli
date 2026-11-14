"""Commande `config` : consulter les réglages effectifs et créer un fichier de configuration modèle."""
import json
import os
from . import couleurs, journal
from .config import REMIND_OFF
from .reglages import REGLAGES, chemin_config, modele_fichier, nom_variable, obtenir_avec_origine


def _affichage(r, valeur):
    if r.type == "bool":
        return "true" if valeur else "false"
    if (r.section, r.cle) == ("list", "limit") and valeur == 0:
        return "0 (illimité)"
    return str(valeur)


def afficher_config(fmt="table"):
    """Affiche chaque réglage avec sa valeur effective et son origine."""
    chemin = chemin_config()
    existe = os.path.isfile(chemin)
    lignes = []
    for r in REGLAGES:
        valeur, origine = obtenir_avec_origine(r.section, r.cle)
        lignes.append((f"{r.section}.{r.cle}", valeur, origine, r))

    if fmt == "json":
        print(json.dumps({
            "fichier": chemin, "fichier_existe": existe,
            "reglages": [{"cle": cle, "valeur": valeur, "origine": origine, "variable": nom_variable(r.section, r.cle)}
                         for cle, valeur, origine, r in lignes],
            "rappels_coupes_par_commande": os.path.exists(REMIND_OFF),
        }, indent=2, ensure_ascii=False))
        return

    print(f"\n {couleurs.CLR_CYAN}─── ⚙️  CONFIGURATION ───{couleurs.CLR_RESET}")
    etat = "" if existe else f" {couleurs.CLR_DIM}(absent : valeurs par défaut){couleurs.CLR_RESET}"
    print(f"  Fichier : {couleurs.CLR_BOLD}{chemin}{couleurs.CLR_RESET}{etat}\n")
    largeur_cle = max(len(cle) for cle, *_ in lignes)
    largeur_val = max(len(_affichage(r, valeur)) for _, valeur, _, r in lignes)
    section = None
    for cle, valeur, origine, r in lignes:
        if r.section != section:
            section = r.section
        texte = _affichage(r, valeur)
        modifie = origine != "défaut"
        style = couleurs.CLR_BOLD if modifie else ""
        print(f"  {cle:<{largeur_cle}}  {style}{texte:<{largeur_val}}{couleurs.CLR_RESET}  "
              f"{couleurs.CLR_DIM}{origine}{couleurs.CLR_RESET}")
    if os.path.exists(REMIND_OFF):
        print(f"\n  {couleurs.CLR_DIM}Rappels coupés par « todo remind --disable » (todo remind --enable pour les réactiver).{couleurs.CLR_RESET}")
    print(f"\n  {couleurs.CLR_DIM}Priorité : option > variable d'environnement > fichier > défaut.{couleurs.CLR_RESET}\n")


def afficher_chemin(fmt="table"):
    """Écrit le chemin du fichier de configuration (seul, pour pouvoir s'en servir dans un script)."""
    chemin = chemin_config()
    if fmt == "json":
        print(json.dumps({"fichier": chemin, "existe": os.path.isfile(chemin)}, indent=2, ensure_ascii=False))
    else:
        print(chemin)


def _json_init(chemin, cree, erreur=None, detail=None, ecrase=False):
    document = {"fichier": chemin, "cree": cree, "ecrase": ecrase}
    if erreur:
        document["erreur"], document["detail"] = erreur, detail
    print(json.dumps(document, indent=2, ensure_ascii=False))


def initialiser_config(forcer=False, fmt="table"):
    """Crée un fichier de configuration modèle (toutes les valeurs en commentaire). Retourne True si créé.

    En JSON, le résultat (créé ou non, et la raison d'un échec) est un document, pour qu'un script
    n'ait jamais à analyser un message destiné à un humain.
    """
    chemin = chemin_config()
    existait = os.path.exists(chemin)
    if existait and not forcer:
        journal.echec("config_exists")
        if fmt == "json":
            _json_init(chemin, False, "existe_deja", "utilisez --force pour le remplacer")
            return False
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {chemin} existe déjà. "
              f"Utilisez {couleurs.CLR_BOLD}--force{couleurs.CLR_RESET} pour le remplacer.")
        return False
    try:
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(modele_fichier())
    except OSError as e:
        journal.echec("config_write_error", detail=e.strerror or str(e))
        if fmt == "json":
            _json_init(chemin, False, "ecriture_impossible", e.strerror or str(e))
            return False
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} impossible d'écrire {chemin} : {e.strerror or e}.")
        return False
    journal.noter(modifie=True, file=chemin)
    if fmt == "json":
        _json_init(chemin, True, ecrase=existait)
        return True
    print(f" 📝 Fichier de configuration créé : {couleurs.CLR_BOLD}{chemin}{couleurs.CLR_RESET}")
    print(f"    {couleurs.CLR_DIM}Toutes les valeurs y sont en commentaire : décommentez celles à changer.{couleurs.CLR_RESET}")
    return True
