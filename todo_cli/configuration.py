"""Commande `config` : consulter les réglages effectifs, lire, écrire ou retirer un réglage, créer un modèle."""
import configparser
import json
import os
import sys
import tempfile
from . import couleurs, journal
from .config import REMIND_OFF
from .formats import imprimer_plain, tableau
from . import reglages
from .reglages import REGLAGES, chemin_config, modele_fichier, nom_variable, obtenir_avec_origine, origine_chemin_config


def _affichage(r, valeur):
    if r.type == "bool":
        return "true" if valeur else "false"
    if (r.section, r.cle) == ("list", "limit") and valeur == 0:
        return "0 (illimité)"
    return str(valeur)


def afficher_config(fmt="text"):
    """Affiche chaque réglage avec sa valeur effective et son origine."""
    chemin = chemin_config()
    existe = os.path.isfile(chemin)
    lignes = []
    for r in REGLAGES:
        valeur, origine = obtenir_avec_origine(r.section, r.cle)
        lignes.append((f"{r.section}.{r.cle}", valeur, origine, r))

    if fmt == "json":
        print(json.dumps({
            "fichier": chemin, "fichier_origine": origine_chemin_config(), "fichier_existe": existe,
            "reglages": [{"cle": cle, "valeur": valeur, "origine": origine, "variable": nom_variable(r.section, r.cle)}
                         for cle, valeur, origine, r in lignes],
            "rappels_coupes_par_commande": os.path.exists(REMIND_OFF),
        }, indent=2, ensure_ascii=False))
        return

    if fmt == "plain":
        imprimer_plain((cle, _affichage(r, valeur), origine) for cle, valeur, origine, r in lignes)
        return
    if fmt == "table":
        print(tableau(("RÉGLAGE", "VALEUR", "ORIGINE"), [(cle, _affichage(r, valeur), origine) for cle, valeur, origine, r in lignes]))
        return

    print(f"\n {couleurs.CLR_CYAN}─── ⚙️  CONFIGURATION ───{couleurs.CLR_RESET}")
    etat = "" if existe else f" {couleurs.CLR_DIM}(absent : valeurs par défaut){couleurs.CLR_RESET}"
    origine = origine_chemin_config()
    suite = "" if origine == "défaut" else f" {couleurs.CLR_DIM}({origine}){couleurs.CLR_RESET}"
    print(f"  Fichier : {couleurs.CLR_BOLD}{chemin}{couleurs.CLR_RESET}{suite}{etat}\n")
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


def afficher_chemin(fmt="text"):
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


def initialiser_config(forcer=False, fmt="text"):
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


# --------------------------------------------------------------------------- get, set, unset
def _erreur(raison, message, fmt, **champs):
    """Refus d'une des commandes get / set / unset : message lisible, ou document JSON {"erreur", "detail"}."""
    journal.echec(raison, **champs)
    if fmt == "json":
        print(json.dumps({"erreur": raison, "detail": message, **champs}, indent=2, ensure_ascii=False))
    else:
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {message}.")
    return False


def _valeur_texte(valeur):
    return "true" if valeur is True else "false" if valeur is False else str(valeur)


def lire_reglage(cle, fmt="text", depuis_le_fichier=False):
    """`config get` : la valeur effective du réglage (ou, avec --file, celle du fichier), seule sur une ligne."""
    try:
        r = reglages.trouver(cle)
    except ValueError as e:
        return _erreur("unknown_setting", str(e), fmt, cle=cle)
    nom = f"{r.section}.{r.cle}"
    if depuis_le_fichier:
        valeur, origine = reglages.valeur_du_fichier(r), "fichier"
        if valeur is None:
            if fmt == "json":
                print(json.dumps({"cle": nom, "valeur": None, "origine": None, "fichier": chemin_config()}, indent=2, ensure_ascii=False))
            journal.echec("not_in_file", setting=nom)
            if fmt != "json":
                print(f"{nom} n'est pas défini dans {chemin_config()}", file=sys.stderr)
            return False
    else:
        valeur, origine = obtenir_avec_origine(r.section, r.cle)
    if fmt == "json":
        print(json.dumps({"cle": nom, "valeur": valeur, "origine": origine, "variable": nom_variable(r.section, r.cle)},
                         indent=2, ensure_ascii=False))
    else:
        print(_valeur_texte(valeur))
    return True


def _ecrire_atomiquement(chemin, contenu):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(chemin), prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenu)
        if os.path.exists(chemin):
            os.chmod(tmp, os.stat(chemin).st_mode & 0o777)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _modifier_fichier(cle, texte, fmt, commande):
    """Cœur de `set` (texte = valeur) et de `unset` (texte = None). Retourne True en cas de succès."""
    try:
        r = reglages.trouver(cle)
        valeur = None if texte is None else reglages.texte_a_ecrire(r, texte)
    except ValueError as e:
        return _erreur("invalid_value" if texte is not None and not str(e).startswith("réglage inconnu") else "unknown_setting",
                       str(e), fmt, cle=cle)
    nom = f"{r.section}.{r.cle}"
    chemin = chemin_config()
    existait = os.path.isfile(chemin)
    if existait:
        try:
            with open(chemin, encoding="utf-8") as f:
                contenu = f.read()
            configparser.ConfigParser(interpolation=None, strict=False).read_string(contenu)
        except (configparser.Error, OSError, UnicodeDecodeError) as e:
            return _erreur("config_unreadable", f"{chemin} n'est pas un fichier de configuration lisible, il n'est pas modifié "
                           f"({' '.join(str(e).split())})", fmt, fichier=chemin)
    elif texte is None:
        contenu = ""
    else:
        contenu = modele_fichier()
    nouveau, ancien = reglages.modifier_texte(contenu, r.section, r.cle, valeur)
    ecrit = False
    if (texte is not None and nouveau != contenu) or (texte is None and ancien is not None) or (texte is not None and not existait):
        try:
            _ecrire_atomiquement(chemin, nouveau)
        except OSError as e:
            return _erreur("config_write_error", f"impossible d'écrire {chemin} : {e.strerror or e}", fmt, fichier=chemin)
        ecrit = True
        journal.noter(modifie=True, setting=nom, action=commande, file=chemin)
    _, origine = obtenir_avec_origine(r.section, r.cle)
    surcharge = origine.split(" ", 1)[1] if origine.startswith("variable") else None
    if fmt == "json":
        document = {"cle": nom, "fichier": chemin, "surcharge_par": surcharge}
        if texte is None:
            document["supprime"] = ancien is not None
        else:
            document.update(valeur=reglages.convertir(r, valeur), fichier_cree=not existait, ancienne_valeur=ancien)
        print(json.dumps(document, indent=2, ensure_ascii=False))
    elif texte is None:
        if ancien is None:
            print(f" {couleurs.CLR_DIM}{nom} n'est pas défini dans {chemin} : rien à retirer.{couleurs.CLR_RESET}")
        else:
            print(f" 🧹 {couleurs.CLR_BOLD}{nom}{couleurs.CLR_RESET} retiré de {chemin} (retour à la valeur par défaut).")
    else:
        print(f" ✅ {couleurs.CLR_BOLD}{nom} = {valeur}{couleurs.CLR_RESET}  {couleurs.CLR_DIM}({chemin}){couleurs.CLR_RESET}")
    if surcharge and (ecrit or texte is None):
        print(f" ⚠️  {surcharge.replace('variable ', '')} est définie : elle l'emporte sur le fichier.", file=sys.stderr)
    return True


def ecrire_reglage(cle, texte, fmt="text"):
    """`config set` : valide la valeur et l'écrit dans le fichier de configuration (créé au besoin)."""
    return _modifier_fichier(cle, texte, fmt, "set")


def retirer_reglage(cle, fmt="text"):
    """`config unset` : retire le réglage du fichier, qui revient ainsi à sa valeur par défaut."""
    return _modifier_fichier(cle, None, fmt, "unset")
