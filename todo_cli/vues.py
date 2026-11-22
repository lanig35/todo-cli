"""Vues enregistrées : une ligne de commande de lecture (list, next, agenda, report…) mémorisée sous un nom.

Les vues d'un projet sont dans `views.json`, à côté de sa base (racine du stockage pour `default`, `projects/<nom>/` sinon).
Ce sont des préférences, pas des tâches : ni sauvegardées avec la base, ni concernées par `undo`, `restore` ou `reset`.

Une vue enregistre les arguments tels que tapés (`["list", "--overdue", "--prio", "high"]`), pas une structure interne : `view run`
les rejoue dans le même analyseur que la commande d'origine, si bien que tout nouveau filtre fonctionne sans migration.
"""
import json
import os
import re
import shlex
import sys
import tempfile
import time

from . import config, couleurs, journal
from .formats import imprimer_plain, tableau

_NOM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
# Commandes de lecture seule qu'on peut mémoriser (nom canonique du journal)
COMMANDES_AUTORISEES = ("list", "next", "agenda", "stats", "report_tags", "report_blocked", "report_overdue", "report_stale",
                        "report_done", "report_active", "report_cycle")
_OPTIONS_PROJET = ("-p", "--project")


class ErreurVue(Exception):
    """Erreur d'utilisation ou de fichier, avec la raison technique pour le journal."""

    def __init__(self, raison, message, **champs):
        super().__init__(message)
        self.raison, self.champs = raison, champs


def chemin():
    return config.VIEWS_FILE


def valider_nom(nom):
    if not _NOM.match(nom or ""):
        raise ErreurVue("invalid_view_name", f"nom de vue invalide : '{nom}' (lettres, chiffres, - et _ ; 40 caractères au plus ; "
                                             "doit commencer par une lettre ou un chiffre).", vue=nom)
    return nom


# ---------------------------------------------------------------------------------------------- fichier
def charger():
    """{nom: {"args": [...], "creee": "AAAA-MM-JJ HH:MM"}} ; {} si le fichier n'existe pas. Un fichier illisible n'est jamais écrasé."""
    try:
        with open(chemin(), encoding="utf-8") as f:
            donnees = json.load(f)
        vues = donnees["vues"]
        if not isinstance(vues, dict) or not all(isinstance(v, dict) and isinstance(v.get("args"), list)
                                                 and all(isinstance(a, str) for a in v["args"]) for v in vues.values()):
            raise ValueError("structure inattendue")
        return vues
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ErreurVue("views_file_invalid", f"fichier des vues illisible : {chemin()} ({e}). Corrigez-le ou supprimez-le ; "
                                               "il n'est pas modifié.", fichier=chemin())


def _ecrire(vues):
    """Écriture atomique (fichier temporaire puis renommage), droits 0600."""
    dossier = os.path.dirname(chemin())
    os.makedirs(dossier, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dossier, prefix=".views-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "vues": vues}, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, chemin())
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ErreurVue("views_write_error", f"impossible d'écrire {chemin()} : {e.strerror or e}", fichier=chemin())


def noms_pour_completion(projet=None):
    """Noms des vues du projet courant (ou de `projet`) ; vide au moindre problème (la complétion ne doit jamais échouer)."""
    try:
        if projet:
            config.definir_projet(config.valider_nom(projet), "option")
        return sorted(charger())
    except Exception:
        return []


# ---------------------------------------------------------------------------------------------- arguments
def extraire_projet(mots):
    """Retire `-p NOM` / `--project NOM` / `--project=NOM` d'une liste d'arguments : (nom ou None, reste)."""
    reste, projet, i = [], None, 0
    while i < len(mots):
        m = mots[i]
        if m in _OPTIONS_PROJET and i + 1 < len(mots):
            projet, i = mots[i + 1], i + 2
        elif m.startswith("--project="):
            projet, i = m.split("=", 1)[1], i + 1
        else:
            reste.append(m)
            i += 1
    return projet, reste


def normaliser(mots):
    """Ajoute `list` devant des options seules : `view save x --overdue` équivaut à `view save x list --overdue`."""
    return ["list"] + mots if not mots or mots[0].startswith("-") else list(mots)


def commande_equivalente(mots):
    return "todo " + shlex.join(mots)


# ---------------------------------------------------------------------------------------------- actions
def enregistrer(nom, mots, remplacer, verifier):
    """Mémorise la vue `nom`. `verifier(mots)` analyse la ligne et retourne le nom canonique de la commande (ou sort en erreur d'usage)."""
    valider_nom(nom)
    mots = normaliser(mots)
    if any(m == "--config" or m.startswith("--config=") for m in mots):
        raise ErreurVue("invalid_view", "--config ne peut pas faire partie d'une vue (elle dépend de la machine).", vue=nom)
    canon = verifier(mots)
    if canon not in COMMANDES_AUTORISEES:
        raise ErreurVue("invalid_view", f"une vue ne peut mémoriser qu'une commande de lecture "
                                        f"(list, next, agenda, report …), pas `{' '.join(mots[:2])}`.", vue=nom)
    vues = charger()
    existe = nom in vues
    if existe and not remplacer:
        raise ErreurVue("view_exists", f"la vue '{nom}' existe déjà (--replace pour la remplacer).", vue=nom)
    vues[nom] = {"args": mots, "creee": time.strftime("%Y-%m-%d %H:%M")}
    _ecrire(vues)
    return existe


def lire(nom):
    vues = charger()
    if nom not in vues:
        proches = [n for n in vues if n.lower().startswith(nom.lower())]
        indice = f" Vues du projet '{config.projet()}' : {', '.join(sorted(vues))}." if vues else \
            f" Le projet '{config.projet()}' n'a aucune vue (`todo view save` en crée)."
        raise ErreurVue("unknown_view", f"vue '{nom}' introuvable." + (f" Vouliez-vous dire '{proches[0]}' ?" if proches else indice), vue=nom)
    return vues[nom]


def renommer(ancien, nouveau):
    valider_nom(nouveau)
    vues = charger()
    lire(ancien)
    if nouveau in vues and nouveau != ancien:
        raise ErreurVue("view_exists", f"la vue '{nouveau}' existe déjà.", vue=nouveau)
    vues[nouveau] = vues.pop(ancien)
    _ecrire(vues)


def supprimer(nom):
    vues = charger()
    lire(nom)
    del vues[nom]
    _ecrire(vues)


# ---------------------------------------------------------------------------------------------- affichage
def _erreur(e):
    journal.echec(e.raison, **e.champs)
    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {e}", file=sys.stderr)
    return False


def commande_enregistrer(nom, mots, remplacer, verifier, fmt="text"):
    try:
        remplacee = enregistrer(nom, mots, remplacer, verifier)
    except ErreurVue as e:
        return _erreur(e)
    mots = normaliser(mots)
    journal.noter([], [], True, view=nom, view_action="replace" if remplacee else "save")
    if fmt == "json":
        print(json.dumps({"vue": nom, "args": mots, "commande": commande_equivalente(mots), "remplacee": remplacee},
                         indent=2, ensure_ascii=False))
    elif fmt != "plain":
        print(f" ✅ Vue {couleurs.CLR_BOLD}{nom}{couleurs.CLR_RESET} {'remplacée' if remplacee else 'enregistrée'} : "
              f"{couleurs.CLR_DIM}{commande_equivalente(mots)}{couleurs.CLR_RESET}")
        print(f" {couleurs.CLR_DIM}Rejouez-la avec `todo view run {nom}` (des options s'ajoutent : `todo view run {nom} --format json`).{couleurs.CLR_RESET}")
    return True


def commande_lister(fmt="text"):
    try:
        vues = charger()
    except ErreurVue as e:
        return _erreur(e)
    lignes = [(n, commande_equivalente(v["args"]), v.get("creee", "")) for n, v in sorted(vues.items())]
    if fmt == "json":
        print(json.dumps({"projet": config.projet(), "vues": [{"vue": n, "args": vues[n]["args"], "commande": c, "creee": d}
                                                              for n, c, d in lignes]}, indent=2, ensure_ascii=False))
    elif fmt == "plain":
        imprimer_plain([n, c, d] for n, c, d in lignes)
    elif fmt == "table":
        print(tableau(("VUE", "COMMANDE", "CRÉÉE"), lignes))
    elif not lignes:
        print(f" 🔎 {couleurs.CLR_DIM}Aucune vue dans le projet '{config.projet()}'. `todo view save NOM [list] OPTIONS…` en crée.{couleurs.CLR_RESET}")
    else:
        print(f"\n {couleurs.CLR_CYAN}─── 🔎 VUES · {config.projet()} ───{couleurs.CLR_RESET}")
        largeur = max(len(n) for n, *_ in lignes)
        for n, c, d in lignes:
            print(f"  {couleurs.CLR_BOLD}{n:<{largeur}}{couleurs.CLR_RESET}  {c}  {couleurs.CLR_DIM}({d}){couleurs.CLR_RESET}")
        print()
    return True


def commande_afficher(nom, fmt="text"):
    try:
        vue = lire(nom)
    except ErreurVue as e:
        return _erreur(e)
    if fmt == "json":
        print(json.dumps({"vue": nom, "args": vue["args"], "commande": commande_equivalente(vue["args"]), "creee": vue.get("creee")},
                         indent=2, ensure_ascii=False))
    elif fmt == "plain":
        imprimer_plain([[nom, commande_equivalente(vue["args"]), vue.get("creee", "")]])
    else:
        print(commande_equivalente(vue["args"]))
    return True


def commande_renommer(ancien, nouveau, fmt="text"):
    try:
        renommer(ancien, nouveau)
    except ErreurVue as e:
        return _erreur(e)
    journal.noter([], [], True, view=nouveau, view_action="rename", previous=ancien)
    if fmt == "json":
        print(json.dumps({"vue": nouveau, "ancien": ancien}, indent=2, ensure_ascii=False))
    elif fmt != "plain":
        print(f" ✅ Vue {couleurs.CLR_BOLD}{ancien}{couleurs.CLR_RESET} renommée en {couleurs.CLR_BOLD}{nouveau}{couleurs.CLR_RESET}.")
    return True


def commande_supprimer(nom, fmt="text"):
    try:
        supprimer(nom)
    except ErreurVue as e:
        return _erreur(e)
    journal.noter([], [], True, view=nom, view_action="remove")
    if fmt == "json":
        print(json.dumps({"vue": nom, "supprimee": True}, indent=2, ensure_ascii=False))
    elif fmt != "plain":
        print(f" 🗑️  Vue {couleurs.CLR_BOLD}{nom}{couleurs.CLR_RESET} supprimée.")
    return True
