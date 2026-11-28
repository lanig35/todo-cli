"""Pièces jointes des tâches : des fichiers copiés dans le stockage du projet.

Chaque tâche porte une liste `pieces_jointes` (comme les notes) : `{"nom", "date", "taille", "sha256"}` et un
`commentaire` facultatif. Les fichiers eux-mêmes vivent hors de la base DBM, dans
`<dossier du projet>/attachments/<id de la tâche>/<nom>` (ou `<dir>/<projet>/<id de la tâche>/<nom>` avec le réglage
`[attachments] dir`). On **copie** : la tâche reste autonome si l'original
disparaît. Avec `--link`, on ne copie rien : la pièce porte `lien` (chemin absolu) et le fichier reste où il est ;
`attachment check` signale alors un fichier déplacé, supprimé ou modifié. Une pièce se désigne par son numéro
(à partir de 1), comme une note.

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
from .stockage import _base_existe, _lire_archive, _lire_taches, _normaliser_tache, _resoudre_id

DOSSIER = "attachments"
CORBEILLE = ".trash"
_LONGUEUR_NOM = 200
_BLOC = 1024 * 1024


# ------------------------------------------------------------------------------------------ chemins
def racine_configuree():
    """Dossier `[attachments] dir` (`~` développé ; un chemin relatif part du dossier de stockage, jamais du dossier courant), ou None."""
    valeur = reglages.obtenir("attachments", "dir").strip()
    if not valeur:
        return None
    chemin = os.path.expanduser(valeur)
    return os.path.normpath(chemin if os.path.isabs(chemin) else os.path.join(config.dossier(), chemin))


def dossier(projet=None):
    """Dossier des pièces jointes d'un projet (le courant par défaut).

    Par défaut `<dossier du projet>/attachments` ; avec `[attachments] dir`, `<dir>/<projet>` (`default` pour le projet par défaut).
    """
    racine = racine_configuree()
    if racine:
        return os.path.join(racine, projet or config.projet())
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


def _creer_dossier(chemin, projet=None):
    """Crée `chemin` ; lui et ses parents jusqu'au dossier des pièces du projet inclus sont en 0700 (makedirs n'applique `mode` qu'au dernier).

    Avec `[attachments] dir`, le dossier choisi par l'utilisateur n'est jamais modifié : seul `<dir>/<projet>` et dessous le sont.
    """
    racine = dossier(projet)
    os.makedirs(chemin, mode=0o700, exist_ok=True)
    courant = chemin
    while True:
        os.chmod(courant, 0o700)
        if courant == racine or os.path.dirname(courant) == courant:
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
        _creer_dossier(cible, projet)
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
        _creer_dossier(os.path.dirname(destination), cible)
        shutil.move(source, destination)
        return True
    except OSError as e:
        rouge, raz = couleurs._couleurs_erreur()
        print(f" {rouge}⚠️{raz} Pièces jointes de {id_complet[:8]} non déplacées : {e}", file=sys.stderr)
        return False


def renommer_projet(ancien, nouveau):
    """Avec `[attachments] dir`, les pièces d'un projet vivent hors de son dossier : elles suivent son renommage (OSError si impossible)."""
    racine = racine_configuree()
    source = os.path.join(racine, ancien) if racine else None
    if source and os.path.isdir(source):
        cible = os.path.join(racine, nouveau)
        if os.path.lexists(cible):
            raise OSError(f"{cible} existe déjà")
        os.rename(source, cible)


def mettre_projet_a_la_corbeille(nom, nom_corbeille):
    """Avec `[attachments] dir`, met les pièces d'un projet supprimé dans `<dir>/.trash/<nom_corbeille>/` ; retourne ce chemin, ou None."""
    racine = racine_configuree()
    source = os.path.join(racine, nom) if racine else None
    if not (source and os.path.isdir(source)):
        return None
    cible = os.path.join(racine, CORBEILLE, nom_corbeille)
    os.makedirs(os.path.dirname(cible), mode=0o700, exist_ok=True)
    shutil.move(source, cible)
    return cible


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
        if not _present_piece(t, p):
            manque = f" {couleurs.CLR_DEL}[fichier manquant]{couleurs.CLR_RESET}"
        comm = f"  {couleurs.CLR_DIM}{p['commentaire']}{couleurs.CLR_RESET}" if p.get('commentaire') else ""
        lien = f" {couleurs.CLR_DIM}🔗 {p['lien']}{couleurs.CLR_RESET}" if p.get('lien') else ""
        lignes.append(f"{indent}{couleurs.CLR_DIM}{n:>{largeur}}.{couleurs.CLR_RESET} {p['nom']} "
                      f"{couleurs.CLR_DIM}({taille_lisible(p['taille'])}, {p['date'] or '?'}){couleurs.CLR_RESET}{lien}{comm}{manque}")
    return lignes


def _present(id_complet, nom):
    """Le fichier est-il en place, ou récupérable dans la corbeille ? (lecture seule : ne déplace rien)"""
    return (os.path.isfile(os.path.join(_dossier_tache(id_complet), nom))
            or _depuis_la_corbeille(id_complet, nom) is not None)


def _present_piece(t, p):
    """Le fichier de la pièce est-il disponible ? (lien : au chemin indiqué ; copie : en place ou en corbeille)"""
    if p.get('lien'):
        return os.path.isfile(p['lien'])
    return _present(t['id'], p['nom'])


def _fichier(t, p):
    """Chemin du fichier d'une pièce (un fichier copié absent est remis en place depuis la corbeille), ou None."""
    if p.get('lien'):
        return p['lien'] if os.path.isfile(p['lien']) else None
    return retrouver(t['id'], p['nom'])


def _empreinte(chemin):
    """(taille, sha256) d'un fichier, lu par blocs."""
    empreinte, taille = hashlib.sha256(), 0
    with open(chemin, 'rb') as f:
        for bloc in iter(lambda: f.read(_BLOC), b""):
            empreinte.update(bloc)
            taille += len(bloc)
    return taille, empreinte.hexdigest()


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


def ajouter(id_recherche, fichiers, commentaire=None, fmt="text", lien=False):
    """Copie `fichiers` dans la tâche (ou, avec `lien`, les référence sans les copier) ; tout est vérifié avant la première
    copie. Retourne False en cas d'échec."""
    commentaire = " ".join((commentaire or "").split()) or None
    if commentaire and len(commentaire) > 200:
        return _erreur("comment_too_long", f"Commentaire trop long ({len(commentaire)} caractères, maximum 200).")
    maximum = 0 if lien else _taille_max()       # un lien ne prend pas de place : pas de limite de taille
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
        if not lien:
            _creer_dossier(_dossier_tache(t['id']))
        pris = {p['nom'] for p in t['pieces_jointes']}
        for f in fichiers:
            nom = _nom_libre(nom_sur(f), pris)
            pris.add(nom)
            if lien:
                taille, empreinte = _empreinte(f)
            else:
                destination = os.path.join(_dossier_tache(t['id']), nom)
                taille, empreinte = _copier(f, destination)
                copies.append(destination)
            piece = {"nom": nom, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "taille": taille, "sha256": empreinte}
            if lien:
                piece["lien"] = os.path.abspath(f)
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
        return _erreur("attachment_copy_failed", f"{'Lecture' if lien else 'Copie'} impossible : {e.strerror or e}.")
    finally:
        try:
            db.close()
        except Exception:
            pass
    journal.noter(ids=[cle], titres=[t['titre']], modifie=True, attached=len(ajoutees), linked=len(ajoutees) if lien else 0)
    sauvegarder_base()
    total = len(t['pieces_jointes'])
    if fmt == "json":
        print(json.dumps({"id": t['id'], "titre": t['titre'], "ajoutees": ajoutees, "total": total}, indent=2, ensure_ascii=False))
    else:
        for p in ajoutees:
            print(f" {couleurs.CLR_DONE}📎{couleurs.CLR_RESET} '{couleurs.CLR_BOLD}{p['nom']}{couleurs.CLR_RESET}' "
                  f"({taille_lisible(p['taille'])}) {'liée' if lien else 'jointe'} à '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' ({total} au total).")
    return True


def _enregistrement(t, p, numero):
    """Description JSON d'une pièce : métadonnées, chemin et présence du fichier."""
    chemin = p.get('lien') or os.path.join(_dossier_tache(t['id']), p['nom'])
    return {"numero": numero, **p, "chemin": chemin, "present": _present_piece(t, p)}


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
        imprimer_plain((t['id'], n, p['nom'], p['taille'], p['date'], p['sha256'], p.get('commentaire', ""), p.get('lien', "")) for t, n, p in lignes)
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
    chemin = _fichier(t, p)
    if chemin is None:
        _erreur("attachment_missing", f"Le fichier de la pièce n°{numero} ('{p['nom']}') est introuvable dans "
                                      f"{p.get('lien') and os.path.dirname(p['lien']) or _dossier_tache(t['id'])}.", index=numero)
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
    if not p.get('lien'):
        mettre_a_la_corbeille(t['id'], [p['nom']])
    journal.noter(ids=[cle], titres=[t['titre']], modifie=True, detached=p['nom'])
    sauvegarder_base()
    if fmt == "json":
        print(json.dumps({"id": t['id'], "titre": t['titre'], "detachee": p, "total": len(t['pieces_jointes'])}, indent=2, ensure_ascii=False))
    else:
        suite = ("lien retiré, le fichier d'origine n'est pas touché" if p.get('lien')
                 else "fichier en corbeille : `todo attachment gc` la vide")
        print(f" {couleurs.CLR_DEL}🗑️{couleurs.CLR_RESET} Pièce n°{numero} '{p['nom']}' détachée de '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' "
              f"{couleurs.CLR_DIM}({suite}).{couleurs.CLR_RESET}")
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


# ----------------------------------------------------------------------------------------- check
ETATS = ("ok", "en_corbeille", "manquant", "modifie")


def _etat(t, p):
    """État d'une pièce : ok, en_corbeille (copie retirée mais récupérable), manquant, modifie ; avec un détail lisible."""
    lien = p.get('lien')
    chemin = lien or os.path.join(_dossier_tache(t['id']), p['nom'])
    if not os.path.isfile(chemin):
        if not lien and _depuis_la_corbeille(t['id'], p['nom']) is not None:
            return "en_corbeille", "dans la corbeille (remise en place à l'accès)"
        return "manquant", ("fichier lié introuvable" if lien else "fichier introuvable dans le stockage")
    try:
        taille, empreinte = _empreinte(chemin)
    except OSError as e:
        return "manquant", f"illisible : {e.strerror or e}"
    if taille != p['taille']:
        return "modifie", f"taille {taille_lisible(taille)} au lieu de {taille_lisible(p['taille'])}"
    if p['sha256'] and empreinte != p['sha256']:
        return "modifie", "contenu différent (empreinte SHA-256)"
    return "ok", ""


def _orphelins(taches, restreint_a=None):
    """Fichiers de `attachments/` qu'aucune pièce ne référence (ni tâche connue) ; `restreint_a` : id d'une seule tâche."""
    base = dossier()
    if not os.path.isdir(base):
        return []
    connues = {t['id']: {p['nom'] for p in t['pieces_jointes'] if not p.get('lien')} for t in taches}
    trouves = []
    for id_tache in sorted(os.listdir(base)):
        chemin_tache = os.path.join(base, id_tache)
        if id_tache == CORBEILLE or not os.path.isdir(chemin_tache) or (restreint_a and id_tache != restreint_a):
            continue
        for nom in sorted(os.listdir(chemin_tache)):
            if nom not in connues.get(id_tache, ()):
                trouves.append((id_tache, nom, os.path.join(chemin_tache, nom)))
    return trouves


def verifier(id_recherche=None, fmt="text"):
    """Vérifie les pièces jointes : fichiers manquants ou modifiés (copies et liens), fichiers orphelins.

    Sans identifiant : toutes les tâches, archivées comprises. Retourne False s'il y a une pièce manquante ou modifiée
    (les orphelins et les fichiers en corbeille sont signalés mais ne sont pas des erreurs).
    """
    if id_recherche is not None:
        ouverte = _ouvrir_tache(id_recherche, False)
        if ouverte is None:
            return False
        db, _, t = ouverte
        db.close()
        taches, restreint = [t], t['id']
    else:
        taches, restreint = _lire_taches() + _lire_archive(), None
    taches = sorted((t for t in taches), key=lambda t: (t['titre'].lower(), t['id']))
    resultats = []
    for t in taches:
        for n, p in enumerate(t['pieces_jointes'], 1):
            etat, detail = _etat(t, p)
            resultats.append({"id": t['id'], "titre": t['titre'], "numero": n, "nom": p['nom'], "lien": p.get('lien'),
                              "chemin": p.get('lien') or os.path.join(_dossier_tache(t['id']), p['nom']), "etat": etat, "detail": detail})
    orphelins = _orphelins(taches, restreint)
    comptes = {e: sum(1 for r in resultats if r["etat"] == e) for e in ETATS}
    succes = comptes["manquant"] == 0 and comptes["modifie"] == 0
    journal.noter(checked=len(resultats), problems=comptes["manquant"] + comptes["modifie"])
    if not succes:
        journal.echec("attachment_check_failed", manquantes=comptes["manquant"], modifiees=comptes["modifie"])

    if fmt == "json":
        print(json.dumps({"verifiees": len(resultats), "ok": comptes["ok"], "en_corbeille": comptes["en_corbeille"],
                          "manquantes": comptes["manquant"], "modifiees": comptes["modifie"],
                          "orphelins": [{"id": i, "nom": n, "chemin": c} for i, n, c in orphelins], "pieces": resultats},
                         indent=2, ensure_ascii=False))
        return succes
    if fmt == "plain":
        imprimer_plain([(r["id"], r["numero"], r["nom"], r["etat"], r["chemin"]) for r in resultats]
                       + [(i, "", n, "orphelin", c) for i, n, c in orphelins])
        return succes
    if fmt == "table":
        lignes = [(r["id"][:8], r["numero"], r["nom"], r["etat"], r["detail"]) for r in resultats if r["etat"] != "ok"]
        lignes += [(i[:8], "", n, "orphelin", c) for i, n, c in orphelins]
        if lignes:
            print(tableau(("ID", "N°", "NOM", "ÉTAT", "DÉTAIL"), lignes))
        return succes
    icones = {"manquant": f"{couleurs.CLR_DEL}❌ manquant{couleurs.CLR_RESET}", "modifie": f"{couleurs.CLR_DEL}⚠️  modifié{couleurs.CLR_RESET}",
              "en_corbeille": f"{couleurs.CLR_DIM}🗑️  en corbeille{couleurs.CLR_RESET}"}
    for r in resultats:
        if r["etat"] != "ok":
            print(f" {icones[r['etat']]}  {r['nom']}  {couleurs.CLR_DIM}(pièce {r['numero']} de '{r['titre']}', id: {r['id'][:8]}) : {r['detail']}{couleurs.CLR_RESET}")
            if r["lien"]:
                print(f"     {couleurs.CLR_DIM}lien : {r['lien']}{couleurs.CLR_RESET}")
    for i, n, c in orphelins:
        print(f" {couleurs.CLR_DIM}❔ orphelin  {c}  (aucune pièce ne le référence){couleurs.CLR_RESET}")
    if not resultats and not orphelins:
        print(f" 📎 {couleurs.CLR_DIM}Aucune pièce jointe à vérifier.{couleurs.CLR_RESET}")
        return True
    bilan = f"{comptes['ok']} ok sur {len(resultats)} pièce(s)"
    for e, libelle in (("manquant", "manquante(s)"), ("modifie", "modifiée(s)"), ("en_corbeille", "en corbeille")):
        if comptes[e]:
            bilan += f", {comptes[e]} {libelle}"
    if orphelins:
        bilan += f", {len(orphelins)} orphelin(s)"
    marque = f"{couleurs.CLR_DONE}✔{couleurs.CLR_RESET}" if succes else f"{couleurs.CLR_DEL}✘{couleurs.CLR_RESET}"
    print(f" {marque} {bilan}.")
    return succes
