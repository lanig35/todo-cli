"""Export et import JSON : sauvegarde lisible, transfert d'une machine à l'autre, indépendant du backend DBM.

Le fichier d'export est un document JSON :

    {"format": "todo-cli", "version": 1, "exporte_le": "...", "compteurs": {...},
     "taches": [{"id": ..., "titre": ..., ...}], "archive": [{..., "date_archivage": ...}]}

L'import accepte ce document, ou une simple liste de tâches (la sortie de `list --format json`).
"""
import dbm
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime
from . import __version__
from .config import PRIORITES, STATUT_A_FAIRE, STATUT_TERMINE
from . import config
from . import couleurs, journal
from .dates import _parser_recurrence, lire_instant
from .sauvegardes import sauvegarder_base
from .stockage import _lire_archive, _lire_taches, _normaliser_notes

FORMAT = "todo-cli"
VERSION = 1
CHAMPS = ("titre", "description", "priorite", "statut", "date_creation", "date_echeance", "date_terminee",
          "tags", "recurrence", "suivante", "ancre", "apres", "notes", "demarree")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_HEURE = re.compile(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?")


def _erreur(raison, message, **champs):
    journal.echec(raison, **champs)
    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {message}", file=sys.stderr)
    return False


def _maintenant():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------- export
def _exportable(t, archive=False):
    """Tâche normalisée réduite aux champs du format (l'identifiant en premier), triable et stable."""
    sortie = {"id": t['id']}
    sortie.update({c: t.get(c) for c in CHAMPS})
    if archive:
        sortie["date_archivage"] = t.get("date_archivage")
    return sortie


def construire_export(avec_archive=True):
    taches = sorted(_lire_taches(), key=lambda t: (t.get('date_creation') or "", t['id']))
    archivees = sorted(_lire_archive(), key=lambda t: (t.get('date_creation') or "", t['id'])) if avec_archive else []
    return {
        "format": FORMAT, "version": VERSION, "genere_par": f"todo {__version__}", "exporte_le": _maintenant(),
        "compteurs": {"taches": len(taches), "archive": len(archivees)},
        "taches": [_exportable(t) for t in taches],
        "archive": [_exportable(t, archive=True) for t in archivees],
    }


def exporter(fichier=None, avec_archive=True, forcer=False):
    """Écrit l'export sur la sortie standard (pas de fichier, ou `-`) ou dans `fichier`. Retourne False en cas d'échec."""
    document = construire_export(avec_archive)
    texte = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    n, m = document["compteurs"]["taches"], document["compteurs"]["archive"]
    if fichier in (None, "-"):
        sys.stdout.write(texte)
        return True

    if os.path.exists(fichier) and not forcer:
        return _erreur("file_exists", f"'{fichier}' existe déjà. Utilisez --force pour le remplacer.")
    dossier = os.path.dirname(os.path.abspath(fichier))
    try:
        # Écriture atomique : un export interrompu ne laisse jamais un fichier tronqué
        descripteur, temporaire = tempfile.mkstemp(dir=dossier, prefix=".todo-export-")
        with os.fdopen(descripteur, "w", encoding="utf-8") as f:
            f.write(texte)
        os.chmod(temporaire, 0o644 & ~_umask())
        os.replace(temporaire, fichier)
    except OSError as e:
        return _erreur("export_write_error", f"Impossible d'écrire '{fichier}' : {e.strerror or e}.", detail=e.strerror or str(e))
    reste = f" et {m} archivée(s)" if m else ""
    print(f" 📤 {couleurs.CLR_DONE}{n} tâche(s){reste} exportée(s){couleurs.CLR_RESET} vers {couleurs.CLR_BOLD}{fichier}{couleurs.CLR_RESET}.")
    return True


def _umask():
    masque = os.umask(0)
    os.umask(masque)
    return masque


# --------------------------------------------------------------------------- import : lecture et validation
def _lire_document(source):
    """Retourne (tâches, archive) à partir du fichier JSON (`-` = entrée standard), ou None après un message d'erreur."""
    try:
        if source == "-":
            brut = sys.stdin.read()
        else:
            with open(source, encoding="utf-8") as f:
                brut = f.read()
    except OSError as e:
        _erreur("import_read_error", f"Impossible de lire '{source}' : {e.strerror or e}.", detail=e.strerror or str(e))
        return None
    except UnicodeDecodeError:
        _erreur("import_invalid_file", f"'{source}' n'est pas un fichier texte UTF-8.")
        return None
    try:
        document = json.loads(brut)
    except ValueError as e:
        _erreur("import_invalid_file", f"'{source}' n'est pas du JSON valide ({e}).")
        return None

    if isinstance(document, list):
        return document, []
    if not isinstance(document, dict):
        _erreur("import_invalid_file", "Le JSON doit être un export todo-cli (objet) ou une liste de tâches.")
        return None
    if document.get("format") not in (None, FORMAT):
        _erreur("import_invalid_file", f"Format inconnu : {document.get('format')!r} (attendu : {FORMAT!r}).")
        return None
    version = document.get("version", VERSION)
    if not isinstance(version, int) or version > VERSION:
        _erreur("import_invalid_file", f"Version {version!r} non prise en charge (cette version de todo lit jusqu'à la {VERSION}).")
        return None
    if "taches" not in document and "archive" not in document:
        _erreur("import_invalid_file", "Aucune tâche trouvée : les clés 'taches' et 'archive' sont absentes.")
        return None
    taches, archive = document.get("taches", []), document.get("archive", [])
    if not isinstance(taches, list) or not isinstance(archive, list):
        _erreur("import_invalid_file", "'taches' et 'archive' doivent être des listes.")
        return None
    return taches, archive


def _valider(entree, archive):
    """Retourne (id, enregistrement) pour une entrée valide, ou (None, raison). L'enregistrement est prêt pour la base."""
    if not isinstance(entree, dict):
        return None, "ce n'est pas un objet"
    titre = entree.get("titre")
    if not isinstance(titre, str) or not titre.strip():
        return None, "titre absent ou vide"
    priorite = str(entree.get("priorite") or "medium").lower()
    if priorite not in PRIORITES:
        return None, f"priorité invalide : {entree.get('priorite')!r}"
    statut = entree.get("statut") or STATUT_A_FAIRE
    if statut not in (STATUT_A_FAIRE, STATUT_TERMINE):
        return None, f"statut invalide : {statut!r}"
    echeance = entree.get("date_echeance") or None
    if echeance is not None and not (isinstance(echeance, str) and _DATE.fullmatch(echeance)):
        return None, f"échéance invalide : {echeance!r} (AAAA-MM-JJ attendu)"
    for champ in ("date_creation", "date_terminee", "date_archivage"):
        valeur = entree.get(champ) or None
        if valeur is not None and not (isinstance(valeur, str) and _DATE_HEURE.fullmatch(valeur)):
            return None, f"{champ} invalide : {valeur!r}"
    tags = entree.get("tags") or []
    if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
        return None, "tags : liste de chaînes attendue"
    description = entree.get("description") or ""
    if not isinstance(description, str):
        return None, "description : chaîne attendue"
    recurrence = entree.get("recurrence") or None
    if recurrence is not None:
        recurrence = _parser_recurrence(str(recurrence))
        if recurrence is None:
            return None, f"récurrence invalide : {entree.get('recurrence')!r}"
    ancre = entree.get("ancre") or None
    if ancre is not None and not (isinstance(ancre, str) and _DATE.fullmatch(ancre)):
        return None, f"ancre invalide : {ancre!r} (AAAA-MM-JJ attendu)"
    apres = entree.get("apres") or []
    if not isinstance(apres, list) or not all(isinstance(x, str) and x for x in apres):
        return None, "apres : liste d'identifiants attendue"
    demarree = entree.get("demarree") or None
    if demarree is not None and not (isinstance(demarree, str) and lire_instant(demarree)):
        return None, f"demarree invalide : {demarree!r} (AAAA-MM-JJ HH:MM attendu)"
    identifiant = entree.get("id")
    if identifiant is None or identifiant == "":
        identifiant = str(uuid.uuid4())
    elif not isinstance(identifiant, str) or not identifiant.isprintable() or len(identifiant) > 100:
        return None, "identifiant invalide"

    enregistrement = {
        "titre": titre.strip(), "description": description, "priorite": priorite, "statut": statut,
        "date_creation": entree.get("date_creation") or _maintenant(), "date_echeance": echeance,
        "date_terminee": entree.get("date_terminee") or None,
        "tags": [x.strip().lower() for x in tags if x.strip()], "recurrence": recurrence,
        "suivante": entree.get("suivante") or None, "ancre": ancre, "apres": list(dict.fromkeys(apres)), "notes": _normaliser_notes(entree.get("notes")),
        "demarree": demarree[:16] if demarree else None,
    }
    if archive:
        enregistrement["date_archivage"] = entree.get("date_archivage") or _maintenant()
    return identifiant, enregistrement


# --------------------------------------------------------------------------- import : application
def importer(source, mode="ajouter", simuler=False, confirmer=True, fmt="text"):
    """Importe un fichier JSON.

    mode : "ajouter" (défaut : les identifiants déjà présents sont ignorés), "mettre_a_jour" (le contenu
    du fichier remplace la tâche portant le même identifiant, où qu'elle soit) ou "remplacer" (la liste et
    l'archive sont vidées d'abord). `simuler` ne modifie rien. Retourne False si le fichier est inutilisable
    ou si des entrées sont invalides.
    """
    if mode == "remplacer" and confirmer and source == "-" and not simuler:
        return _erreur("invalid_combination", "--replace lit la confirmation au clavier : avec `-` (entrée standard), ajoutez -y.")
    lu = _lire_document(source)
    if lu is None:
        return False

    # Validation de toutes les entrées AVANT la moindre modification
    valides, invalides, vus = [], [], set()
    for magasin, entrees in (("taches", lu[0]), ("archive", lu[1])):
        for position, entree in enumerate(entrees):
            identifiant, resultat = _valider(entree, magasin == "archive")
            lieu = f"{magasin}[{position}]"
            if identifiant is None:
                invalides.append({"position": lieu, "raison": resultat})
            elif identifiant in vus:
                invalides.append({"position": lieu, "raison": f"identifiant en double dans le fichier : {identifiant[:8]}"})
            else:
                vus.add(identifiant)
                valides.append((magasin, identifiant, resultat))

    lues_taches, lues_archive = _lire_taches(), _lire_archive()
    existantes_taches = {t['id'] for t in lues_taches}
    existantes_archive = {t['id'] for t in lues_archive}
    pieces = {t['id']: t['pieces_jointes'] for t in lues_taches + lues_archive}
    ajoutees = mises_a_jour = ignorees = 0
    plan = []
    for magasin, identifiant, enregistrement in valides:
        present = identifiant in existantes_taches or identifiant in existantes_archive
        if mode == "remplacer" or not present:
            plan.append(("ajouter", magasin, identifiant, enregistrement))
            ajoutees += 1
        elif mode == "mettre_a_jour":
            enregistrement["pieces_jointes"] = pieces.get(identifiant, [])     # les fichiers ne s'échangent pas : on garde ceux d'ici
            plan.append(("mettre_a_jour", magasin, identifiant, enregistrement))
            mises_a_jour += 1
        else:
            ignorees += 1
    supprimees = len(existantes_taches) + len(existantes_archive) if mode == "remplacer" else 0

    if not simuler and mode == "remplacer" and confirmer and supprimees:
        try:
            reponse = input(f" {couleurs.CLR_DEL}⚠️ Remplacer{couleurs.CLR_RESET} les {len(existantes_taches)} tâche(s) et "
                            f"{len(existantes_archive)} archivée(s) actuelles par le contenu de {source} ? "
                            f"L'état actuel est sauvegardé avant. (y/N) : ").strip().lower()
        except EOFError:
            reponse = ""
        if reponse != 'y':
            print(" ❌ Opération annulée.")
            return False

    if not simuler and (plan or supprimees):
        with dbm.open(config.DB_NAME, 'c') as db, dbm.open(config.ARCHIVE_NAME, 'c') as archive:
            if mode == "remplacer":
                for base in (db, archive):
                    for cle in list(base.keys()):
                        del base[cle]
            for action, magasin, identifiant, enregistrement in plan:
                cle = identifiant.encode("utf-8")
                for base in (db, archive):   # l'identifiant ne doit vivre que dans un seul des deux
                    if cle in base:
                        del base[cle]
                (archive if magasin == "archive" else db)[cle] = json.dumps(enregistrement)
                journal.noter(ids=[cle], titres=[enregistrement['titre']], modifie=True)
        journal.noter(modifie=True)
        sauvegarder_base()          # APRÈS fermeture des bases ; `undo` rétablit l'état précédent
    journal.noter(imported=ajoutees, updated=mises_a_jour, skipped=ignorees, invalid=len(invalides),
                  removed=supprimees or None, dry_run=simuler or None, file=None if source == "-" else source)

    resume = {"source": source, "mode": mode, "simulation": simuler, "ajoutees": ajoutees,
              "mises_a_jour": mises_a_jour, "ignorees": ignorees, "supprimees": supprimees, "invalides": invalides}
    if fmt == "json":
        print(json.dumps(resume, indent=2, ensure_ascii=False))
    else:
        _afficher_bilan(resume)
    return not invalides


def _afficher_bilan(r):
    for i in r["invalides"]:
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} {i['position']} ignorée : {i['raison']}.", file=sys.stderr)
    morceaux = [f"{r['ajoutees']} ajoutée(s)"]
    if r["mises_a_jour"]:
        morceaux.append(f"{r['mises_a_jour']} mise(s) à jour")
    if r["supprimees"]:
        morceaux.append(f"{r['supprimees']} supprimée(s) avant import")
    if r["ignorees"]:
        morceaux.append(f"{r['ignorees']} ignorée(s) (identifiant déjà présent ; --update pour les remplacer)")
    if r["invalides"]:
        morceaux.append(f"{couleurs.CLR_DEL}{len(r['invalides'])} invalide(s){couleurs.CLR_RESET}")
    prefixe = f"{couleurs.CLR_DIM}Simulation, rien n'est modifié :{couleurs.CLR_RESET} " if r["simulation"] else ""
    print(f" 📥 {prefixe}{', '.join(morceaux)}.")
