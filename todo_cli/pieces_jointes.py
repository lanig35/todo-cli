"""Pièces jointes des tâches : des fichiers copiés dans le stockage du projet.

Chaque tâche porte une liste `pieces_jointes` (comme les notes) : `{"nom", "date", "taille", "sha256"}` et un
`commentaire` facultatif. Les fichiers eux-mêmes vivent hors de la base DBM, dans
`<dossier du projet>/attachments/<id de la tâche>/<nom>`. On **copie** : la tâche reste autonome si l'original
disparaît. Une pièce se désigne par son numéro (à partir de 1), comme une note.

Les sauvegardes et `undo` ne portent que sur la base, pas sur ces fichiers (voir le README). Pour que `undo`
reste cohérent, rien n'est jamais supprimé tout de suite : `attachment remove`, `task remove` et
`archive purge` déplacent les fichiers dans `attachments/.trash/<id>/<horodatage>/`, et un fichier absent est
d'abord cherché dans cette corbeille (c'est ce qui rend un `undo` complet). Seul `attachment gc` la vide.

Écriture sûre : copie vers un fichier temporaire du même dossier, puis renommage atomique, puis mise à jour
de la base, sous le verrou exclusif de la base. Au pire un fichier orphelin, sans conséquence.
Sécurité : noms assainis (jamais de `/` ni de `..`), droits 0600 / 0700, liens symboliques suivis à la copie
mais jamais à l'ouverture, taille limitée par `[attachments] max_size`.
"""
import dbm
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime

from . import config, couleurs, journal, reglages
from .dates import _decaler
from .formats import imprimer_plain, tableau
from .sauvegardes import sauvegarder_base
from .stockage import _base_existe, _lire_taches, _normaliser_tache, _resoudre_id

DOSSIER = "attachments"
CORBEILLE = ".trash"
_LONGUEUR_NOM = 200
_BLOC = 1024 * 1024


# ------------------------------------------------------------------------------------------ chemins
def dossier(projet=None):
    """Dossier des pièces jointes d'un projet (le courant par défaut)."""
    base = config.DB_DIR if projet is None else config.dossier_du_projet(projet)
    return os.path.join(base, DOSSIER)


def _dossier_tache(id_complet, projet=None):
    return os.path.join(dossier(projet), id_complet)


def _corbeille(id_complet=None):
    base = os.path.join(dossier(), CORBEILLE)
    return base if id_complet is None else os.path.join(base, id_complet)


def nom_sur(nom):
    """Nom de fichier assaini : sans dossier, sans caractère de contrôle, ni vide, ni caché, 200 caractères au plus."""
    nom = os.path.basename((nom or "").replace("\\", "/")).strip()
    nom = "".join("_" if (c < " " or c == "\x7f") else c for c in nom)
    if nom.startswith("."):
        nom = "_" + nom[1:]
    if nom in ("", "_"):
        nom = "fichier"
    if len(nom) > _LONGUEUR_NOM:
        racine, extension = os.path.splitext(nom)
        nom = racine[:_LONGUEUR_NOM - len(extension)] + extension
    return nom


def _nom_libre(nom, pris):
    """`nom`, ou `nom-2.ext`, `nom-3.ext`… s'il est déjà pris par une autre pièce de la tâche."""
    if nom not in pris:
        return nom
    racine, extension = os.path.splitext(nom)
    n = 2
    while f"{racine}-{n}{extension}" in pris:
        n += 1
    return f"{racine}-{n}{extension}"


def _creer_dossier(chemin):
    """Crée `chemin` ; lui et ses parents jusqu'à `attachments/` inclus sont en 0700 (makedirs n'applique `mode` qu'au dernier)."""
    os.makedirs(chemin, mode=0o700, exist_ok=True)
    courant = chemin
    while True:
        os.chmod(courant, 0o700)
        if os.path.basename(courant) == DOSSIER or os.path.dirname(courant) == courant:
            return
        courant = os.path.dirname(courant)


def _horodatage():
    return time.strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------------------- corbeille
def mettre_a_la_corbeille(id_complet, noms=None, projet=None):
    """Déplace les fichiers de la tâche (ou seulement `noms`) dans la corbeille ; retourne le nombre de fichiers déplacés."""
    source = _dossier_tache(id_complet, projet)
    if not os.path.isdir(source):
        return 0
    cible = os.path.join(dossier(projet), CORBEILLE, id_complet, _horodatage())
    deplaces = 0
    for nom in (os.listdir(source) if noms is None else noms):
        chemin = os.path.join(source, nom)
        if not os.path.lexists(chemin):
            continue
        _creer_dossier(cible)
        os.replace(chemin, os.path.join(cible, nom))
        deplaces += 1
    if not os.listdir(source):
        os.rmdir(source)
    return deplaces


def _depuis_la_corbeille(id_complet, nom):
    """Chemin du fichier le plus récent de la corbeille qui porte ce nom, ou None."""
    base = _corbeille(id_complet)
    if not os.path.isdir(base):
        return None
    for horodatage in sorted(os.listdir(base), reverse=True):
        chemin = os.path.join(base, horodatage, nom)
        if os.path.isfile(chemin) and not os.path.islink(chemin):
            return chemin
    return None


def retrouver(id_complet, nom):
    """Chemin du fichier d'une pièce jointe, ou None s'il est introuvable.

    Un fichier absent est d'abord cherché dans la corbeille et, s'il y est, remis en place : c'est ce qui
    rend `undo` complet après un `remove` ou une purge.
    """
    chemin = os.path.join(_dossier_tache(id_complet), nom)
    if os.path.isfile(chemin) and not os.path.islink(chemin):
        return chemin
    dans_corbeille = _depuis_la_corbeille(id_complet, nom)
    if dans_corbeille is None:
        return None
    _creer_dossier(_dossier_tache(id_complet))
    os.replace(dans_corbeille, chemin)
    _nettoyer_corbeille(os.path.dirname(dans_corbeille))
    return chemin


def _nettoyer_corbeille(dossier_horodate):
    """Supprime le dossier horodaté de la corbeille, celui de la tâche et la corbeille elle-même quand ils sont vides."""
    for d in (dossier_horodate, os.path.dirname(dossier_horodate), _corbeille()):
        try:
            os.rmdir(d)
        except FileNotFoundError:
            continue
        except OSError:
            return


def deplacer_vers_projet(id_complet, cible):
    """Suit une tâche déplacée dans un autre projet : ses fichiers quittent la source pour la cible.

    Retourne False (avec un avertissement) si le déplacement échoue : la tâche est déjà passée, ses pièces
    restent alors dans le projet d'origine, d'où `attachment list` les signalera manquantes.
    """
    source = _dossier_tache(id_complet)
    if not os.path.isdir(source):
        return True
    try:
        destination = _dossier_tache(id_complet, cible)
        _creer_dossier(os.path.dirname(destination))
        shutil.move(source, destination)
        return True
    except OSError as e:
        rouge, raz = couleurs._couleurs_erreur()
        print(f" {rouge}⚠️{raz} Pièces jointes de {id_complet[:8]} non déplacées : {e}", file=sys.stderr)
        return False


# ------------------------------------------------------------------------------------- métadonnées
def taille_lisible(octets):
    """12345 -> '12,1 Ko'."""
    valeur = float(octets)
    for unite in ("o", "Ko", "Mo", "Go"):
        if valeur < 1024 or unite == "Go":
            texte = f"{int(valeur)} {unite}" if unite == "o" else f"{valeur:.1f}".replace(".", ",") + f" {unite}"
            return texte
        valeur /= 1024


def lignes_pieces(t, indent="    "):
    """Pièces numérotées d'une tâche pour `show` ; une pièce dont le fichier manque est signalée."""
    pieces = t['pieces_jointes']
    largeur = len(str(len(pieces)))
    lignes = []
    for n, p in enumerate(pieces, 1):
        manque = ""
        if not _present(t['id'], p['nom']):
            manque = f" {couleurs.CLR_DEL}[fichier manquant]{couleurs.CLR_RESET}"
        comm = f"  {couleurs.CLR_DIM}{p['commentaire']}{couleurs.CLR_RESET}" if p.get('commentaire') else ""
        lignes.append(f"{indent}{couleurs.CLR_DIM}{n:>{largeur}}.{couleurs.CLR_RESET} {p['nom']} "
                      f"{couleurs.CLR_DIM}({taille_lisible(p['taille'])}, {p['date'] or '?'}){couleurs.CLR_RESET}{comm}{manque}")
    return lignes


def _present(id_complet, nom):
    """Le fichier est-il en place, ou récupérable dans la corbeille ? (lecture seule : ne déplace rien)"""
    return (os.path.isfile(os.path.join(_dossier_tache(id_complet), nom))
            or _depuis_la_corbeille(id_complet, nom) is not None)


def _erreur(raison, message, **champs):
    journal.echec(raison, **champs)
    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {message}")
    return False


def _taille_max():
    return reglages.obtenir('attachments', 'max_size') * 1024 * 1024


# ------------------------------------------------------------------------------------------ copie
def _copier(source, destination):
    """Copie `source` vers `destination` (fichier temporaire puis renommage) ; retourne (taille, sha256)."""
    temporaire = os.path.join(os.path.dirname(destination), f".tmp-{os.getpid()}-{os.path.basename(destination)}")
    empreinte, taille = hashlib.sha256(), 0
    try:
        with open(source, 'rb') as entree, os.fdopen(os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'wb') as sortie:
            while True:
                bloc = entree.read(_BLOC)
                if not bloc:
                    break
                empreinte.update(bloc)
                taille += len(bloc)
                sortie.write(bloc)
        os.replace(temporaire, destination)
    except BaseException:
        if os.path.lexists(temporaire):
            os.unlink(temporaire)
        raise
    return taille, empreinte.hexdigest()


def _verifier_source(chemin, maximum):
    """Message d'erreur si `chemin` ne peut pas être joint, sinon None."""
    if not os.path.exists(chemin):
        return f"fichier introuvable : {chemin}"
    if not os.path.isfile(chemin):
        return f"{chemin} n'est pas un fichier ordinaire"
    if not os.access(chemin, os.R_OK):
        return f"{chemin} n'est pas lisible"
    taille = os.path.getsize(chemin)
    if maximum and taille > maximum:
        return (f"{chemin} est trop gros ({taille_lisible(taille)} ; maximum {taille_lisible(maximum)}, "
                f"réglage [attachments] max_size)")
    return None


# ----------------------------------------------------------------------------------------- commandes
def _ouvrir_tache(id_recherche, ecriture):
    """(db, clé, tâche) ; fermer db soi-même. None si la tâche est introuvable (message déjà affiché)."""
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, aucune tâche à qui joindre un fichier.{couleurs.CLR_RESET}")
        return None
    db = dbm.open(config.DB_NAME, 'w' if ecriture else 'r')
    cle = _resoudre_id(db, id_recherche)
    if cle is None:
        db.close()
        return None
    try:
        t = _normaliser_tache(db[cle])
    except ValueError:
        db.close()
        _erreur("corrupted_entry", "Cette entrée est corrompue et ne peut pas être modifiée.")
        return None
    t['id'] = cle.decode('utf-8', errors='replace')
    return db, cle, t


def _numero_valide(t, numero):
    """Message d'erreur si `numero` ne désigne pas une pièce de `t`, sinon None."""
    pieces = t['pieces_jointes']
    if 1 <= numero <= len(pieces):
        return None
    quoi = "n'a aucune pièce jointe" if not pieces else f"n'a que {len(pieces)} pièce(s) jointe(s)"
    return f"Pièce n°{numero} introuvable : '{t['titre']}' {quoi}."


def ajouter(id_recherche, fichiers, commentaire=None, fmt="text"):
    """Copie `fichiers` dans la tâche ; tout est vérifié avant la première copie. Retourne False en cas d'échec."""
    commentaire = " ".join((commentaire or "").split()) or None
    if commentaire and len(commentaire) > 200:
        return _erreur("comment_too_long", f"Commentaire trop long ({len(commentaire)} caractères, maximum 200).")
    maximum = _taille_max()
    for f in fichiers:
        probleme = _verifier_source(f, maximum)
        if probleme:
            return _erreur("invalid_attachment", probleme.capitalize() + ".", file=os.path.basename(f))
    ouverte = _ouvrir_tache(id_recherche, True)
    if ouverte is None:
        return False
    db, cle, t = ouverte
    ajoutees, copies = [], []
    try:
        _creer_dossier(_dossier_tache(t['id']))
        pris = {p['nom'] for p in t['pieces_jointes']}
        for f in fichiers:
            nom = _nom_libre(nom_sur(f), pris)
            pris.add(nom)
            destination = os.path.join(_dossier_tache(t['id']), nom)
            taille, empreinte = _copier(f, destination)
            copies.append(destination)
            piece = {"nom": nom, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "taille": taille, "sha256": empreinte}
            if commentaire:
                piece["commentaire"] = commentaire
            t['pieces_jointes'].append(piece)
            ajoutees.append(piece)
        db[cle] = json.dumps(t)
    except OSError as e:
        for c in copies:
            if os.path.lexists(c):
                os.unlink(c)
        db.close()
        return _erreur("attachment_copy_failed", f"Copie impossible : {e.strerror or e}.")
    finally:
        try:
            db.close()
        except Exception:
            pass
    journal.noter(ids=[cle], titres=[t['titre']], modifie=True, attached=len(ajoutees))
    sauvegarder_base()
    total = len(t['pieces_jointes'])
    if fmt == "json":
        print(json.dumps({"id": t['id'], "titre": t['titre'], "ajoutees": ajoutees, "total": total}, indent=2, ensure_ascii=False))
    else:
        for p in ajoutees:
            print(f" {couleurs.CLR_DONE}📎{couleurs.CLR_RESET} '{couleurs.CLR_BOLD}{p['nom']}{couleurs.CLR_RESET}' "
                  f"({taille_lisible(p['taille'])}) jointe à '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' ({total} au total).")
    return True


def _enregistrement(t, p, numero):
    """Description JSON d'une pièce : métadonnées, chemin et présence du fichier."""
    chemin = os.path.join(_dossier_tache(t['id']), p['nom'])
    return {"numero": numero, **p, "chemin": chemin, "present": _present(t['id'], p['nom'])}


def lister(id_recherche=None, fmt="text"):
    """Liste les pièces d'une tâche, ou de toutes les tâches qui en ont. Retourne False si la tâche est introuvable."""
    if id_recherche is not None:
        ouverte = _ouvrir_tache(id_recherche, False)
        if ouverte is None:
            return False
        db, _, t = ouverte
        db.close()
        taches = [t]
    else:
        taches = sorted((t for t in _lire_taches() if t['pieces_jointes']), key=lambda t: (t['titre'].lower(), t['id']))

    if fmt == "json":
        donnees = [{"id": t['id'], "titre": t['titre'],
                    "pieces_jointes": [_enregistrement(t, p, n) for n, p in enumerate(t['pieces_jointes'], 1)]} for t in taches]
        print(json.dumps(donnees[0] if id_recherche is not None else donnees, indent=2, ensure_ascii=False))
        return True
    lignes = [(t, n, p) for t in taches for n, p in enumerate(t['pieces_jointes'], 1)]
    if fmt == "plain":
        imprimer_plain((t['id'], n, p['nom'], p['taille'], p['date'], p['sha256'], p.get('commentaire', "")) for t, n, p in lignes)
    elif fmt == "table":
        if lignes:
            print(tableau(("ID", "N°", "NOM", "TAILLE", "DATE", "COMMENTAIRE"),
                          [(t['id'][:8], n, p['nom'], taille_lisible(p['taille']), p['date'], p.get('commentaire', "")) for t, n, p in lignes]))
    elif not lignes:
        suite = f" pour '{taches[0]['titre']}'. Ajout : todo attachment add {taches[0]['id'][:8]} FICHIER" if id_recherche is not None else ""
        print(f" {couleurs.CLR_DIM}Aucune pièce jointe{suite}.{couleurs.CLR_RESET}")
    else:
        for t in taches:
            if not t['pieces_jointes']:
                continue
            print(f"\n {couleurs.CLR_CYAN}─── 📎 PIÈCES JOINTES : {t['titre']} {couleurs.CLR_DIM}(id: {t['id'][:8]}){couleurs.CLR_RESET}"
                  f"{couleurs.CLR_CYAN} ───{couleurs.CLR_RESET}")
            print("\n".join(lignes_pieces(t, "  ")))
        print()
    return True


def _piece(id_recherche, numero):
    """(tâche, pièce, chemin du fichier) ou None après un message d'erreur."""
    ouverte = _ouvrir_tache(id_recherche, False)
    if ouverte is None:
        return None
    db, _, t = ouverte
    db.close()
    probleme = _numero_valide(t, numero)
    if probleme:
        _erreur("invalid_attachment_number", probleme, index=numero)
        return None
    p = t['pieces_jointes'][numero - 1]
    chemin = retrouver(t['id'], p['nom'])
    if chemin is None:
        _erreur("attachment_missing", f"Le fichier de la pièce n°{numero} ('{p['nom']}') est introuvable dans "
                                      f"{_dossier_tache(t['id'])}.", index=numero)
        return None
    return t, p, chemin


def _commande_ouverture():
    """Commande d'ouverture : le réglage `[attachments] opener`, sinon xdg-open quand une session graphique existe, sinon None."""
    choisie = reglages.obtenir('attachments', 'opener')
    if choisie:
        return shlex.split(choisie), True
    if (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and shutil.which("xdg-open"):
        return ["xdg-open"], False
    return None, False


def ouvrir(id_recherche, numero, fmt="text"):
    """Ouvre une pièce avec l'outil système ; sans session graphique (ou sans outil), affiche seulement son chemin.

    Avec `[attachments] opener` (less, bat, evince…), la commande reprend le terminal : elle attend la fermeture.
    """
    trouve = _piece(id_recherche, numero)
    if trouve is None:
        return False
    t, p, chemin = trouve
    commande, au_premier_plan = _commande_ouverture()
    ouvert = False
    if commande:
        try:
            if au_premier_plan:
                ouvert = subprocess.run([*commande, chemin]).returncode == 0
            else:
                subprocess.Popen([*commande, chemin], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                ouvert = True
        except OSError as e:
            return _erreur("opener_failed", f"Impossible de lancer « {commande[0]} » : {e.strerror or e}.")
        if not ouvert:
            return _erreur("opener_failed", f"« {commande[0]} » a échoué sur {chemin}.")
    journal.noter(opened=p['nom'])
    if fmt == "json":
        print(json.dumps({"id": t['id'], "numero": numero, "nom": p['nom'], "chemin": chemin, "ouvert": ouvert}, indent=2, ensure_ascii=False))
    elif not commande:
        print(chemin if fmt == "plain" else f" 📎 {chemin}  {couleurs.CLR_DIM}(pas d'outil d'ouverture : voir [attachments] opener){couleurs.CLR_RESET}")
    return True


def extraire(id_recherche, numero, vers=None, ecraser=False, fmt="text"):
    """Copie une pièce dans un dossier (le dossier courant par défaut), sous son nom d'origine."""
    trouve = _piece(id_recherche, numero)
    if trouve is None:
        return False
    t, p, chemin = trouve
    dossier_cible = os.path.abspath(os.path.expanduser(vers)) if vers else os.getcwd()
    if not os.path.isdir(dossier_cible):
        return _erreur("invalid_destination", f"Dossier de destination introuvable : {dossier_cible}.")
    destination = os.path.join(dossier_cible, p['nom'])
    if os.path.lexists(destination) and not ecraser:
        return _erreur("destination_exists", f"{destination} existe déjà (--force pour l'écraser).")
    try:
        shutil.copyfile(chemin, destination)
    except OSError as e:
        return _erreur("attachment_copy_failed", f"Copie impossible : {e.strerror or e}.")
    journal.noter(saved=p['nom'])
    if fmt == "json":
        print(json.dumps({"id": t['id'], "numero": numero, "nom": p['nom'], "destination": destination}, indent=2, ensure_ascii=False))
    else:
        print(f" {couleurs.CLR_DONE}💾{couleurs.CLR_RESET} '{p['nom']}' copiée vers {destination}.")
    return True


def detacher(id_recherche, numero, fmt="text"):
    """Détache la pièce n° `numero` : le fichier va à la corbeille (`attachment gc` la vide)."""
    ouverte = _ouvrir_tache(id_recherche, True)
    if ouverte is None:
        return False
    db, cle, t = ouverte
    try:
        probleme = _numero_valide(t, numero)
        if probleme:
            return _erreur("invalid_attachment_number", probleme, index=numero)
        p = t['pieces_jointes'].pop(numero - 1)
        db[cle] = json.dumps(t)
    finally:
        db.close()
    mettre_a_la_corbeille(t['id'], [p['nom']])
    journal.noter(ids=[cle], titres=[t['titre']], modifie=True, detached=p['nom'])
    sauvegarder_base()
    if fmt == "json":
        print(json.dumps({"id": t['id'], "titre": t['titre'], "detachee": p, "total": len(t['pieces_jointes'])}, indent=2, ensure_ascii=False))
    else:
        print(f" {couleurs.CLR_DEL}🗑️{couleurs.CLR_RESET} Pièce n°{numero} '{p['nom']}' détachée de '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' "
              f"{couleurs.CLR_DIM}(fichier en corbeille : `todo attachment gc` la vide).{couleurs.CLR_RESET}")
    return True


# ------------------------------------------------------------------------------------------- gc
def _horodatage_dossier(nom):
    try:
        return datetime.strptime(nom, "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def _contenu_corbeille(avant=None):
    """[(dossier horodaté, nb fichiers, octets)] de la corbeille ; `avant` : seulement les entrées plus anciennes (date)."""
    base = _corbeille()
    trouves = []
    if not os.path.isdir(base):
        return trouves
    for id_tache in sorted(os.listdir(base)):
        for h in sorted(os.listdir(os.path.join(base, id_tache))):
            chemin = os.path.join(base, id_tache, h)
            quand = _horodatage_dossier(h)
            if avant is not None and (quand is None or quand.date() > avant):
                continue
            tailles = [os.path.getsize(os.path.join(chemin, f)) for f in os.listdir(chemin)] if os.path.isdir(chemin) else []
            trouves.append((chemin, len(tailles), sum(tailles)))
    return trouves


def vider_corbeille(anciennete=None, confirmer=True, fmt="text"):
    """Supprime DÉFINITIVEMENT les fichiers de la corbeille (ceux d'avant `anciennete` = (n, unité) si indiqué).

    Après cela, `undo` ne peut plus rendre les fichiers correspondants (la tâche, elle, revient).
    """
    limite = _decaler(datetime.now().date(), -anciennete[0], anciennete[1]) if anciennete else None
    entrees = _contenu_corbeille(limite)
    nb, octets = sum(e[1] for e in entrees), sum(e[2] for e in entrees)
    if not entrees:
        if fmt == "json":
            print(json.dumps({"supprimes": 0, "octets": 0}))
        else:
            print(f" 🗑️  {couleurs.CLR_DIM}La corbeille des pièces jointes est vide.{couleurs.CLR_RESET}")
        return True
    if confirmer:
        try:
            reponse = input(f" {couleurs.CLR_DEL}⚠️ DANGER :{couleurs.CLR_RESET} Supprimer définitivement {nb} fichier(s) "
                            f"({taille_lisible(octets)}) de la corbeille ? (y/N) : ").strip().lower()
        except EOFError:
            reponse = ""
        if reponse != 'y':
            print(" ❌ Opération annulée.")
            return True
    for chemin, _, _ in entrees:
        shutil.rmtree(chemin, ignore_errors=True)
        _nettoyer_corbeille(chemin)
    journal.noter(modifie=True, purged=nb)
    if fmt == "json":
        print(json.dumps({"supprimes": nb, "octets": octets}))
    else:
        print(f" {couleurs.CLR_DEL}🗑️{couleurs.CLR_RESET} {nb} fichier(s) supprimé(s) ({taille_lisible(octets)}).")
    return True
