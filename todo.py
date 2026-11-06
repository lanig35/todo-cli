#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
# La ligne ci-dessus permet à l'utilitaire argcomplete de détecter le script.

# ==============================================================================
# 1. IMPORTATIONS DES MODULES STANDARD ET TIERS
# ==============================================================================
import dbm
import uuid
import argparse
import sys
import os
import re
import json
import shutil
import glob
import random
import calendar
import shlex
import subprocess
import unicodedata
from datetime import datetime, timedelta
from collections import Counter

# ==============================================================================
# 2. CONFIGURATION DE L'ESPACE DE STOCKAGE CENTRALISÉ (XDG STANDARD)
# ==============================================================================
# Base de données et dossiers de sauvegarde localisés dans le répertoire utilisateur.
# La variable d'environnement TODO_DB_DIR permet de rediriger le stockage (tests, etc.).
DB_DIR = os.environ.get("TODO_DB_DIR") or os.path.expanduser("~/.local/share/todo")
BACKUP_DIR = os.path.join(DB_DIR, "backups")

# Création récursive des répertoires s'ils n'existent pas encore
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Chemin absolu de base pour le moteur DBM
DB_NAME = os.path.join(DB_DIR, "todo_db")

# Nombre maximal de sauvegardes conservées
NB_BACKUPS_MAX = 5

# ==============================================================================
# 3. CONSTANTES MÉTIER ET CODES DE COULEUR ANSI
# ==============================================================================
STATUT_A_FAIRE = "A FAIRE"
STATUT_TERMINE = "TERMINE"
PRIORITES = ("low", "medium", "high")

CLR_RESET   = "\033[0m"
CLR_BOLD    = "\033[1m"
CLR_DIM     = "\033[2m"
CLR_TODO    = "\033[93m"  # Jaune
CLR_DONE    = "\033[92m"  # Vert
CLR_DEL     = "\033[91m"  # Rouge
CLR_CYAN    = "\033[96m"  # Cyan (Bordures et en-têtes)
CLR_TAG     = "\033[95m"  # Violet pour les tags (#tag)
CLR_P_HIGH  = "\033[91m"  # Rouge (Priorité haute)
CLR_P_MED   = "\033[94m"  # Bleu (Priorité moyenne)
CLR_P_LOW   = "\033[90m"  # Gris (Priorité basse)

# Palette d'origine, conservée à part : _configurer_couleurs() vide les constantes CLR_* pour
# désactiver les couleurs, et _PALETTE permet de les restaurer ou de les réutiliser (stderr).
_PALETTE = {nom: valeur for nom, valeur in list(globals().items()) if nom.startswith("CLR_")}

# Choix explicite de l'utilisateur ('auto', 'always', 'never' ou None), fixé par main().
_mode_couleur = None

def _couleurs_activees(mode=None, flux=None):
    """Décide si les codes couleur doivent être écrits sur `flux` (stdout par défaut).

    'always' / 'never' : choix explicite, prioritaire sur tout le reste (y compris NO_COLOR).
    'auto' ou None     : couleurs seulement si le flux est un terminal, si la variable
                         d'environnement NO_COLOR n'est pas définie (valeur non vide, voir
                         no-color.org) et si TERM n'est pas 'dumb'.
    """
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    flux = flux or sys.stdout
    try:
        return bool(flux.isatty())
    except (AttributeError, ValueError):  # flux sans isatty() ou déjà fermé
        return False

def _configurer_couleurs(mode=None):
    """Active ou désactive les couleurs (stdout) en vidant ou restaurant les constantes CLR_*."""
    actives = _couleurs_activees(mode)
    for nom, valeur in _PALETTE.items():
        globals()[nom] = valeur if actives else ""

# ==============================================================================
# 4. FONCTIONNALITÉ DE SAUVEGARDE ET ROTATION SÉCURISÉE
# ==============================================================================
# Chaque sauvegarde est un sous-dossier horodaté : backups/AAAAMMJJ_HHMMSS_µs/
_MOTIF_BACKUP = re.compile(r"^\d{8}_\d{6}_\d{6}$")

def _noms_sauvegardes():
    """Noms des dossiers de sauvegarde, du plus ancien au plus récent."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    return sorted(
        d for d in os.listdir(BACKUP_DIR)
        if _MOTIF_BACKUP.match(d) and os.path.isdir(os.path.join(BACKUP_DIR, d))
    )

def sauvegarder_base(rotation=True):
    """Crée un instantané daté de la base DBM dans son propre dossier
    et, si rotation=True, ne conserve que les NB_BACKUPS_MAX plus récents.

    Doit être appelée une fois la base fermée, sinon les dernières écritures
    pourraient ne pas encore être sur le disque.
    Retourne le chemin du dossier créé (ou None s'il n'y a rien à sauvegarder).
    """
    fichiers_base = [f for f in glob.glob(f"{DB_NAME}*") if os.path.isfile(f)]
    if not fichiers_base:
        return None

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dossier = os.path.join(BACKUP_DIR, horodatage)
    os.makedirs(dossier, exist_ok=True)

    # Duplication de l'ensemble des sous-fichiers DBM (.db, .pag, .dir selon OS)
    for fichier in fichiers_base:
        shutil.copy2(fichier, os.path.join(dossier, os.path.basename(fichier)))

    # --- Rotation : on supprime les dossiers les plus anciens ---
    if rotation:
        for ancien in _noms_sauvegardes()[:-NB_BACKUPS_MAX]:
            shutil.rmtree(os.path.join(BACKUP_DIR, ancien), ignore_errors=True)
    return dossier

# ==============================================================================
# 5. OUTILS D'ACCÈS À LA BASE (FACTORISATION)
# ==============================================================================
def _base_existe():
    """Vrai si au moins un fichier de la base DBM est présent sur le disque."""
    return bool(glob.glob(f"{DB_NAME}*"))

def _normaliser_tache(brut):
    """Décode une entrée DBM et complète les champs manquants (compatibilité ascendante).

    Lève ValueError si l'entrée n'est pas un objet JSON exploitable.
    """
    t = json.loads(brut.decode('utf-8'))
    if not isinstance(t, dict):
        raise ValueError("entrée non conforme")
    t['titre'] = t.get('titre') or "(sans titre)"
    t['description'] = t.get('description') or ""
    priorite = str(t.get('priorite') or "medium").lower()
    t['priorite'] = priorite if priorite in PRIORITES else "medium"
    t['statut'] = t.get('statut') or STATUT_A_FAIRE
    t['date_echeance'] = t.get('date_echeance') or None
    t['date_terminee'] = t.get('date_terminee') or None  # absente des anciennes tâches terminées
    t['tags'] = t.get('tags') or []
    # Récurrence : valeur invalide ou absente => tâche non récurrente
    t['recurrence'] = _parser_recurrence(str(t['recurrence'])) if t.get('recurrence') else None
    t['suivante'] = t.get('suivante') or None  # id de l'occurrence créée à la complétion
    return t

def _charger_taches(db):
    """Retourne la liste des tâches normalisées (avec leur 'id'), en ignorant les entrées illisibles."""
    taches = []
    for key in list(db.keys()):
        id_str = key.decode('utf-8', errors='replace')
        try:
            t = _normaliser_tache(db[key])
        except ValueError:
            # Les avertissements vont sur stderr : leur couleur dépend de stderr, pas de stdout
            rouge, raz = (_PALETTE["CLR_DEL"], _PALETTE["CLR_RESET"]) if _couleurs_activees(_mode_couleur, sys.stderr) else ("", "")
            print(f" {rouge}⚠️{raz} Entrée illisible ignorée (id: {id_str[:8]}).", file=sys.stderr)
            continue
        t['id'] = id_str
        taches.append(t)
    return taches

def _lire_taches():
    """Charge toutes les tâches en lecture seule, sans jamais créer la base."""
    if not _base_existe():
        return []
    with dbm.open(DB_NAME, 'r') as db:
        return _charger_taches(db)

def _resoudre_id(db, prefixe):
    """Retrouve la clé unique correspondant à un préfixe d'ID.

    Retourne None (avec un message) si le préfixe est vide, inconnu ou ambigu.
    """
    prefixe = prefixe.strip().lower()
    if not prefixe:
        print(f" {CLR_DEL}❌{CLR_RESET} Identifiant vide.")
        return None

    correspondances = [k for k in db.keys() if k.decode('utf-8', errors='replace').lower().startswith(prefixe)]
    if not correspondances:
        print(f" {CLR_DEL}❌{CLR_RESET} Aucun identifiant ne correspond à '{prefixe}'.")
        return None
    if len(correspondances) > 1:
        largeur = max(8, len(prefixe) + 2)
        candidats = ", ".join(k.decode('utf-8', errors='replace')[:largeur] for k in correspondances)
        print(f" {CLR_DEL}❌{CLR_RESET} Identifiant ambigu '{prefixe}' ({len(correspondances)} correspondances : {candidats}).")
        print(f"    {CLR_DIM}Précisez davantage le préfixe.{CLR_RESET}")
        return None
    return correspondances[0]

def _parse_date(valeur):
    """Convertit 'AAAA-MM-JJ' en date, ou None si la valeur est absente ou invalide."""
    if not valeur:
        return None
    try:
        return datetime.strptime(valeur, "%Y-%m-%d").date()
    except ValueError:
        return None

def _parser_tags(tags_str):
    """Transforme 'Pro, dev' en ['pro', 'dev'] (minuscules, sans vides)."""
    return [t.strip().lower() for t in tags_str.split(",") if t.strip()] if tags_str else []

# --- Dates relatives -----------------------------------------------------------
_JOURS_SEMAINE = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
}
MSG_FORMATS_DATE = "AAAA-MM-JJ, aujourd'hui, demain, apres-demain, +3d / +2w / +1m / +1y, ou un jour de la semaine (lundi...)"

def _sans_accents(texte):
    """'Après-demain' -> 'Apres-demain' (comparaisons insensibles aux accents)."""
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")

def _ajouter_mois(d, n):
    """Ajoute n mois à une date en ramenant le jour au dernier jour du mois si besoin (31 janv. + 1 mois = 28/29 févr.)."""
    mois = d.month - 1 + n
    annee = d.year + mois // 12
    mois = mois % 12 + 1
    return d.replace(year=annee, month=mois, day=min(d.day, calendar.monthrange(annee, mois)[1]))

def _decaler(d, n, unite):
    """Décale une date de n jours ('d'), semaines ('w'), mois ('m') ou années ('y')."""
    if unite == "d":
        return d + timedelta(days=n)
    if unite == "w":
        return d + timedelta(weeks=n)
    if unite == "m":
        return _ajouter_mois(d, n)
    return _ajouter_mois(d, 12 * n)

def _resoudre_date(texte, reference=None):
    """Convertit une date saisie en objet date, ou None si elle n'est pas reconnue.

    Formats : AAAA-MM-JJ ; aujourd'hui / today ; demain / tomorrow ; apres-demain ;
    +Nd, +Nw, +Nm, +Ny (jours, semaines, mois, années) ; nom d'un jour de la semaine
    (la prochaine occurrence, jamais aujourd'hui).
    """
    if texte is None:
        return None
    ref = reference or datetime.now().date()
    t = _sans_accents(texte).strip().lower()
    if not t:
        return None

    absolue = _parse_date(t)
    if absolue is not None:
        return absolue
    if t in ("today", "aujourdhui", "aujourd'hui"):
        return ref
    if t in ("tomorrow", "demain"):
        return ref + timedelta(days=1)
    if t in ("apres-demain", "apresdemain", "day-after-tomorrow"):
        return ref + timedelta(days=2)

    m = re.fullmatch(r"\+(\d{1,4})([dwmy])", t)
    if m:
        try:
            return _decaler(ref, int(m.group(1)), m.group(2))
        except (ValueError, OverflowError):
            return None  # hors plage de dates supportée

    if t in _JOURS_SEMAINE:
        ecart = (_JOURS_SEMAINE[t] - ref.weekday()) % 7 or 7
        return ref + timedelta(days=ecart)
    return None

# --- Récurrence ------------------------------------------------------------------
_ALIAS_RECURRENCE = {
    "daily": "1d", "quotidien": "1d",
    "weekly": "1w", "hebdo": "1w", "hebdomadaire": "1w",
    "monthly": "1m", "mensuel": "1m",
    "yearly": "1y", "annuel": "1y",
}
MSG_FORMATS_REPETITION = "daily, weekly, monthly, yearly, ou 3d / 2w / 1m / 1y ('none' pour supprimer)"

def _parser_recurrence(texte):
    """Normalise une récurrence ('weekly' -> '1w', '2W' -> '2w'), ou None si invalide."""
    t = _sans_accents(texte).strip().lower()
    t = _ALIAS_RECURRENCE.get(t, t)
    m = re.fullmatch(r"(\d{1,3})([dwmy])", t)
    if not m or int(m.group(1)) == 0:
        return None
    return f"{int(m.group(1))}{m.group(2)}"

def _libelle_recurrence(rec):
    """'1w' -> 'chaque semaine', '3m' -> 'tous les 3 mois'."""
    n, unite = int(rec[:-1]), rec[-1]
    if n == 1:
        return {"d": "chaque jour", "w": "chaque semaine", "m": "chaque mois", "y": "chaque année"}[unite]
    return {"d": f"tous les {n} jours", "w": f"toutes les {n} semaines",
            "m": f"tous les {n} mois", "y": f"tous les {n} ans"}[unite]

def _prochaine_echeance(t, aujourdhui):
    """Prochaine échéance d'une tâche récurrente, calculée depuis son échéance d'origine
    (sans dérive) et strictement postérieure à aujourd'hui : les occurrences manquées
    ne s'accumulent pas en retard.
    """
    n, unite = int(t['recurrence'][:-1]), t['recurrence'][-1]
    base = _parse_date(t['date_echeance']) or aujourdhui
    k = 1
    prochaine = _decaler(base, n * k, unite)
    while prochaine <= aujourdhui:
        k += 1
        prochaine = _decaler(base, n * k, unite)
    return prochaine

def _jours_restants(t, maintenant):
    """Nombre de jours avant l'échéance (négatif = en retard), ou None sans échéance valide."""
    date_obj = _parse_date(t['date_echeance'])
    return None if date_obj is None else (date_obj - maintenant).days

def _libelle_echeance(t, maintenant):
    """Étiquette colorée d'échéance (avec espace initial), ou chaîne vide sans échéance."""
    if not t['date_echeance']:
        return ""
    jours = _jours_restants(t, maintenant)
    if jours is None:
        return f" {CLR_DIM}[Éch: {t['date_echeance']} ?]{CLR_RESET}"
    if t['statut'] != STATUT_A_FAIRE:
        return f" {CLR_DIM}[Éch: {t['date_echeance']}]{CLR_RESET}"
    if jours < 0:
        return f" {CLR_DEL}[RETARD : {-jours} j.]{CLR_RESET}"
    if jours == 0:
        return f" {CLR_P_HIGH}[AUJOURD'HUI]{CLR_RESET}"
    if jours == 1:
        return f" {CLR_TODO}[DEMAIN]{CLR_RESET}"
    return f" {CLR_CYAN}[J-{jours}]{CLR_RESET}"

# ==============================================================================
# 6. FONCTIONS DE GESTION DU CYCLE DE VIE DES TÂCHES (C.R.U.D.)
# ==============================================================================
def ajouter_tache(titre, description, priorite, date_echeance, tags_str, silencieux=False, sauvegarder=True, repeter=None):
    """Insère une tâche sérialisée en JSON dans la base clé-valeur intégrée."""
    if not titre or not titre.strip():
        print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Le titre ne peut pas être vide.")
        sys.exit(1)

    priorite = (priorite or "medium").lower()
    if priorite not in PRIORITES:
        print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Priorité invalide. Valeurs possibles : {CLR_BOLD}{', '.join(PRIORITES)}{CLR_RESET}.")
        sys.exit(1)

    date_echeance = date_echeance or None
    if date_echeance:
        date_obj = _resoudre_date(date_echeance)
        if date_obj is None:
            print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Date non reconnue. Formats acceptés : {CLR_BOLD}{MSG_FORMATS_DATE}{CLR_RESET}.")
            sys.exit(1)
        date_echeance = date_obj.strftime("%Y-%m-%d")

    # Récurrence : une tâche récurrente a toujours une échéance (aujourd'hui par défaut)
    recurrence = None
    echeance_par_defaut = False
    if repeter:
        recurrence = _parser_recurrence(repeter)
        if recurrence is None:
            print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Répétition non reconnue. Valeurs acceptées : {CLR_BOLD}{MSG_FORMATS_REPETITION}{CLR_RESET}.")
            sys.exit(1)
        if not date_echeance:
            date_echeance = datetime.now().date().strftime("%Y-%m-%d")
            echeance_par_defaut = True

    # Parsing et normalisation des tags optionnels
    tags = _parser_tags(tags_str)

    with dbm.open(DB_NAME, 'c') as db:
        id_tache = str(uuid.uuid4())
        donnees_tache = {
            "titre": titre.strip(),
            "description": description if description else "",
            "priorite": priorite,
            "statut": STATUT_A_FAIRE,
            "date_creation": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "date_echeance": date_echeance,
            "tags": tags,
            "recurrence": recurrence
        }
        # Conversion du dictionnaire en chaîne JSON exploitable par DBM
        db[id_tache] = json.dumps(donnees_tache)

    if not silencieux:
        print(f" {CLR_DONE}✅{CLR_RESET} Tâche ajoutée : '{CLR_BOLD}{titre.strip()}{CLR_RESET}'")
        if recurrence:
            suite = f" — première échéance : aujourd'hui" if echeance_par_defaut else f" — échéance : {date_echeance}"
            print(f"    {CLR_DIM}↻ Répétition {_libelle_recurrence(recurrence)}{suite}{CLR_RESET}")
    if sauvegarder:
        sauvegarder_base()

def _creer_occurrence_suivante(db, t):
    """Crée l'occurrence suivante d'une tâche récurrente qui vient d'être terminée.

    Copie titre, description, priorité, tags et récurrence ; la nouvelle échéance est
    calculée par _prochaine_echeance. Renseigne t['suivante'] et retourne
    (id, échéance), ou None si la date sort de la plage supportée.
    """
    try:
        prochaine = _prochaine_echeance(t, datetime.now().date())
    except (ValueError, OverflowError):
        return None
    nouvelle = {
        "titre": t['titre'],
        "description": t['description'],
        "priorite": t['priorite'],
        "statut": STATUT_A_FAIRE,
        "date_creation": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date_echeance": prochaine.strftime("%Y-%m-%d"),
        "tags": list(t['tags']),
        "recurrence": t['recurrence'],
    }
    id_nouvelle = str(uuid.uuid4())
    db[id_nouvelle] = json.dumps(nouvelle)
    t['suivante'] = id_nouvelle
    return id_nouvelle, nouvelle['date_echeance']

def marquer_terminee(id_recherche):
    """Bascule le statut d'une tâche ciblée vers 'TERMINE' via préfixe d'ID (unique).

    Si la tâche est récurrente, l'occurrence suivante est créée dans la foulée.
    """
    if not _base_existe():
        print(f" 📋 {CLR_DIM}La liste est vide, rien à valider.{CLR_RESET}")
        return

    modifie = False
    with dbm.open(DB_NAME, 'w') as db:
        key = _resoudre_id(db, id_recherche)
        if key is None:
            return
        try:
            t = _normaliser_tache(db[key])
        except ValueError:
            print(f" {CLR_DEL}❌{CLR_RESET} Cette entrée est corrompue et ne peut pas être modifiée.")
            return
        if t['statut'] == STATUT_TERMINE:
            print(f" {CLR_DIM}ℹ️  La tâche '{t['titre']}' est déjà terminée.{CLR_RESET}")
            return
        t['statut'] = STATUT_TERMINE
        t['date_terminee'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        occurrence = _creer_occurrence_suivante(db, t) if t['recurrence'] else None
        db[key] = json.dumps(t)
        print(f" {CLR_DONE}🎉{CLR_RESET} Tâche '{CLR_BOLD}{t['titre']}{CLR_RESET}' validée !")
        if occurrence:
            print(f"    {CLR_CYAN}↻ Prochaine occurrence : {occurrence[1]}{CLR_RESET} {CLR_DIM}(id: {occurrence[0][:8]}){CLR_RESET}")
        elif t['recurrence']:
            print(f"    {CLR_DEL}⚠️ Prochaine occurrence non créée : date hors limites.{CLR_RESET}")
        modifie = True

    # Sauvegarde APRÈS fermeture de la base, pour capturer l'écriture
    if modifie:
        sauvegarder_base()

def rouvrir_tache(id_recherche):
    """Repasse une tâche terminée au statut 'A FAIRE' via préfixe d'ID (unique)."""
    if not _base_existe():
        print(f" 📋 {CLR_DIM}La liste est vide, rien à rouvrir.{CLR_RESET}")
        return

    modifie = False
    with dbm.open(DB_NAME, 'w') as db:
        key = _resoudre_id(db, id_recherche)
        if key is None:
            return
        try:
            t = _normaliser_tache(db[key])
        except ValueError:
            print(f" {CLR_DEL}❌{CLR_RESET} Cette entrée est corrompue et ne peut pas être modifiée.")
            return
        if t['statut'] == STATUT_A_FAIRE:
            print(f" {CLR_DIM}ℹ️  La tâche '{t['titre']}' est déjà à faire.{CLR_RESET}")
            return
        # Annuler la complétion d'une tâche récurrente annule aussi l'occurrence qu'elle a créée,
        # sinon on aurait deux occurrences actives (tant que celle-ci n'a pas été terminée).
        echeance_supprimee = None
        if t['suivante']:
            cle_suivante = t['suivante'].encode('utf-8')
            if cle_suivante in db:
                try:
                    suivante = _normaliser_tache(db[cle_suivante])
                except ValueError:
                    suivante = None
                if suivante is not None and suivante['statut'] != STATUT_A_FAIRE:
                    print(f" {CLR_DEL}❌{CLR_RESET} Impossible : l'occurrence suivante de '{t['titre']}' est déjà terminée.")
                    return
                if suivante is not None:
                    del db[cle_suivante]
                    echeance_supprimee = suivante['date_echeance']
            t['suivante'] = None

        t['statut'] = STATUT_A_FAIRE
        t['date_terminee'] = None  # une tâche rouverte n'est plus terminée
        db[key] = json.dumps(t)
        print(f" {CLR_TODO}↩️{CLR_RESET}  Tâche '{CLR_BOLD}{t['titre']}{CLR_RESET}' rouverte.")
        if echeance_supprimee:
            print(f"    {CLR_DIM}↻ L'occurrence suivante (échéance {echeance_supprimee}) a été supprimée.{CLR_RESET}")
        modifie = True

    # Sauvegarde APRÈS fermeture de la base, pour capturer la modification
    if modifie:
        sauvegarder_base()

def afficher_tache(id_recherche):
    """Affiche le détail complet d'une tâche (lecture seule)."""
    if not _base_existe():
        print(f" 📋 {CLR_DIM}La liste est vide, rien à afficher.{CLR_RESET}")
        return

    with dbm.open(DB_NAME, 'r') as db:
        key = _resoudre_id(db, id_recherche)
        if key is None:
            return
        try:
            t = _normaliser_tache(db[key])
        except ValueError:
            print(f" {CLR_DEL}❌{CLR_RESET} Cette entrée est corrompue et ne peut pas être affichée.")
            return
        id_complet = key.decode('utf-8', errors='replace')

    maintenant = datetime.now().date()
    a_faire = t['statut'] == STATUT_A_FAIRE
    statut = f"{CLR_TODO}[⏳] À faire{CLR_RESET}" if a_faire else f"{CLR_DONE}[✅] Terminée{CLR_RESET}"
    couleur_prio = CLR_P_HIGH if t['priorite'] == "high" else CLR_P_MED if t['priorite'] == "medium" else CLR_P_LOW

    if t['date_echeance']:
        echeance = t['date_echeance'] + (_libelle_echeance(t, maintenant) if a_faire else "")
    else:
        echeance = f"{CLR_DIM}aucune{CLR_RESET}"
    tags = f"{CLR_TAG}" + " ".join(f"#{tg}" for tg in t['tags']) + f"{CLR_RESET}" if t['tags'] else f"{CLR_DIM}aucun{CLR_RESET}"
    description = t['description'].replace("\n", "\n                ") if t['description'] else f"{CLR_DIM}aucune{CLR_RESET}"

    print(f"\n {CLR_CYAN}─── 🔎 DÉTAIL DE LA TÂCHE ───{CLR_RESET}")
    print(f"  {CLR_BOLD}Titre       :{CLR_RESET} {CLR_BOLD}{t['titre']}{CLR_RESET}")
    print(f"  {CLR_BOLD}ID          :{CLR_RESET} {id_complet}")
    print(f"  {CLR_BOLD}Statut      :{CLR_RESET} {statut}")
    print(f"  {CLR_BOLD}Priorité    :{CLR_RESET} {couleur_prio}{t['priorite'].upper()}{CLR_RESET}")
    print(f"  {CLR_BOLD}Créée le    :{CLR_RESET} {t.get('date_creation') or f'{CLR_DIM}inconnue{CLR_RESET}'}")
    print(f"  {CLR_BOLD}Échéance    :{CLR_RESET} {echeance}")
    if not a_faire:
        print(f"  {CLR_BOLD}Terminée le :{CLR_RESET} {t['date_terminee'] or f'{CLR_DIM}inconnue{CLR_RESET}'}")
    if t['recurrence']:
        print(f"  {CLR_BOLD}Répétition  :{CLR_RESET} ↻ {_libelle_recurrence(t['recurrence'])}")
    if t['suivante']:
        print(f"  {CLR_BOLD}Suivante    :{CLR_RESET} {t['suivante']}")
    print(f"  {CLR_BOLD}Tags        :{CLR_RESET} {tags}")
    print(f"  {CLR_BOLD}Description :{CLR_RESET} {description}")
    print(f" {CLR_CYAN}─────────────────────────────{CLR_RESET}\n")

def modifier_tache(id_recherche, titre=None, description=None, priorite=None, date_echeance=None, tags_str=None, repeter=None):
    """Modifie les champs fournis d'une tâche (None = champ inchangé).

    - date_echeance : date absolue ou relative ; 'none' (ou chaîne vide) supprime l'échéance.
    - tags_str      : chaîne vide supprime tous les tags ; sinon remplace la liste.
    - repeter       : 'weekly', '2w'... ; 'none' (ou chaîne vide) supprime la répétition.
    """
    if all(v is None for v in (titre, description, priorite, date_echeance, tags_str, repeter)):
        print(f" {CLR_DEL}❌{CLR_RESET} Rien à modifier. Options : --title, --desc, --prio, --due, --tags, --repeat.")
        return

    # --- Validation des valeurs AVANT toute ouverture de la base ---
    if titre is not None:
        titre = titre.strip()
        if not titre:
            print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Le titre ne peut pas être vide.")
            sys.exit(1)

    if priorite is not None:
        priorite = priorite.lower()
        if priorite not in PRIORITES:
            print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Priorité invalide. Valeurs possibles : {CLR_BOLD}{', '.join(PRIORITES)}{CLR_RESET}.")
            sys.exit(1)

    if date_echeance is not None:
        date_echeance = date_echeance.strip()
        if date_echeance.lower() in ("", "none"):
            date_echeance = ""  # suppression de l'échéance
        else:
            date_obj = _resoudre_date(date_echeance)
            if date_obj is None:
                print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Date non reconnue. Formats acceptés : {CLR_BOLD}{MSG_FORMATS_DATE}{CLR_RESET} (ou 'none' pour supprimer).")
                sys.exit(1)
            date_echeance = date_obj.strftime("%Y-%m-%d")  # forme absolue normalisée

    if repeter is not None:
        repeter = repeter.strip()
        if repeter.lower() in ("", "none"):
            repeter = ""  # suppression de la répétition
        else:
            recurrence_norm = _parser_recurrence(repeter)
            if recurrence_norm is None:
                print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Répétition non reconnue. Valeurs acceptées : {CLR_BOLD}{MSG_FORMATS_REPETITION}{CLR_RESET}.")
                sys.exit(1)
            repeter = recurrence_norm

    if not _base_existe():
        print(f" 📋 {CLR_DIM}La liste est vide, rien à modifier.{CLR_RESET}")
        return

    modifications = []
    with dbm.open(DB_NAME, 'w') as db:
        key = _resoudre_id(db, id_recherche)
        if key is None:
            return
        try:
            t = _normaliser_tache(db[key])
        except ValueError:
            print(f" {CLR_DEL}❌{CLR_RESET} Cette entrée est corrompue et ne peut pas être modifiée.")
            return

        if titre is not None and titre != t['titre']:
            t['titre'] = titre
            modifications.append("titre")
        if description is not None and description != t['description']:
            t['description'] = description
            modifications.append("description")
        if priorite is not None and priorite != t['priorite']:
            t['priorite'] = priorite
            modifications.append("priorité")
        if date_echeance is not None and (date_echeance or None) != t['date_echeance']:
            t['date_echeance'] = date_echeance or None
            modifications.append("échéance")
        if tags_str is not None:
            nouveaux_tags = _parser_tags(tags_str)
            if nouveaux_tags != t['tags']:
                t['tags'] = nouveaux_tags
                modifications.append("tags")
        if repeter is not None and (repeter or None) != t['recurrence']:
            t['recurrence'] = repeter or None
            modifications.append("répétition")

        # Une tâche récurrente doit toujours avoir une échéance
        if t['recurrence'] and not t['date_echeance']:
            if date_echeance == "":
                print(f" {CLR_DEL}❌{CLR_RESET} Une tâche récurrente doit avoir une échéance : supprimez d'abord la répétition (--repeat none).")
                return
            t['date_echeance'] = datetime.now().date().strftime("%Y-%m-%d")
            modifications.append("échéance (aujourd'hui par défaut)")

        if not modifications:
            print(f" {CLR_DIM}ℹ️  Aucun changement : les valeurs fournies sont déjà celles de la tâche '{t['titre']}'.{CLR_RESET}")
            return

        db[key] = json.dumps(t)
        print(f" {CLR_DONE}✏️{CLR_RESET} Tâche '{CLR_BOLD}{t['titre']}{CLR_RESET}' modifiée ({', '.join(modifications)}).")

    # Sauvegarde APRÈS fermeture de la base, pour capturer la modification
    sauvegarder_base()

def supprimer_tache(id_recherche):
    """Retire définitivement une entrée unique de la base de données."""
    if not _base_existe():
        print(f" 📋 {CLR_DIM}La liste est vide, rien à supprimer.{CLR_RESET}")
        return

    modifie = False
    with dbm.open(DB_NAME, 'w') as db:
        key = _resoudre_id(db, id_recherche)
        if key is None:
            return
        del db[key]
        print(f" {CLR_DEL}🗑️{CLR_RESET} Tâche supprimée.")
        modifie = True

    # Sauvegarde APRÈS fermeture de la base, pour capturer la suppression
    if modifie:
        sauvegarder_base()

def nettoyer_terminees():
    """Purge de masse ciblant exclusivement les tâches archivées (TERMINE)."""
    if not _base_existe():
        print(f" 🧹 {CLR_DIM}Aucune tâche terminée à nettoyer.{CLR_RESET}")
        return

    with dbm.open(DB_NAME, 'w') as db:
        cles = []
        for k in list(db.keys()):
            try:
                if _normaliser_tache(db[k])['statut'] == STATUT_TERMINE:
                    cles.append(k)
            except ValueError:
                continue  # entrée illisible : on la laisse intacte
        if not cles:
            print(f" 🧹 {CLR_DIM}Aucune tâche terminée à nettoyer.{CLR_RESET}")
            return
        for k in cles:
            del db[k]
        print(f" {CLR_DEL}🗑️{CLR_RESET} Nettoyage réussi ({len(cles)} supprimée(s)).")
    sauvegarder_base()

def reinitialiser_base():
    """Remise à zéro complète après confirmation et sauvegarde ultime."""
    if not _base_existe():
        print(f" 📋 {CLR_DIM}La base de données est déjà vide.{CLR_RESET}")
        return

    with dbm.open(DB_NAME, 'r') as db:
        if len(db) == 0:
            print(f" 📋 {CLR_DIM}La base de données est déjà vide.{CLR_RESET}")
            return

    try:
        reponse = input(f" {CLR_DEL}⚠️ DANGER :{CLR_RESET} Purger intégralement la base ? (y/N) : ").strip().lower()
    except EOFError:
        reponse = ""
    if reponse != 'y':
        print(" ❌ Opération annulée.")
        return

    sauvegarder_base()  # Sauvegarde de l'état AVANT purge (base fermée)
    with dbm.open(DB_NAME, 'w') as db:
        for key in list(db.keys()):
            del db[key]
    print(f" {CLR_DONE}🗑️ Base réinitialisée.{CLR_RESET}")

# ==============================================================================
# 6 bis. RESTAURATION À PARTIR DES SAUVEGARDES
# ==============================================================================
def _infos_sauvegarde(nom):
    """Retourne (date lisible, nombre de tâches ou None) pour un dossier de sauvegarde."""
    try:
        date_txt = datetime.strptime(nom[:15], "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        date_txt = nom
    try:
        with dbm.open(os.path.join(BACKUP_DIR, nom, "todo_db"), 'r') as db:
            nb = len(db)
    except (dbm.error, OSError):
        nb = None
    return date_txt, nb

def _resoudre_sauvegarde(reference, noms_recents_d_abord):
    """Retrouve un dossier de sauvegarde par numéro (1 = la plus récente) ou par préfixe d'horodatage."""
    reference = reference.strip()
    if reference.isdigit() and len(reference) <= 3:
        n = int(reference)
        if 1 <= n <= len(noms_recents_d_abord):
            return noms_recents_d_abord[n - 1]
        print(f" {CLR_DEL}❌{CLR_RESET} Numéro de sauvegarde invalide : {reference} (1 à {len(noms_recents_d_abord)}).")
        return None

    correspondances = [d for d in noms_recents_d_abord if d.startswith(reference)] if reference else []
    if not correspondances:
        print(f" {CLR_DEL}❌{CLR_RESET} Aucune sauvegarde ne correspond à '{reference}'.")
        return None
    if len(correspondances) > 1:
        print(f" {CLR_DEL}❌{CLR_RESET} Référence ambiguë '{reference}' ({len(correspondances)} sauvegardes). Utilisez le numéro affiché par 'restore'.")
        return None
    return correspondances[0]

def lister_sauvegardes():
    """Affiche les sauvegardes disponibles (la plus récente en premier)."""
    noms = _noms_sauvegardes()[::-1]
    if not noms:
        print(f" 📦 {CLR_DIM}Aucune sauvegarde disponible.{CLR_RESET}")
        return

    print(f"\n {CLR_CYAN}─── 📦 SAUVEGARDES DISPONIBLES ───{CLR_RESET}")
    for i, nom in enumerate(noms, start=1):
        date_txt, nb = _infos_sauvegarde(nom)
        detail = f"{nb} tâche(s)" if nb is not None else f"{CLR_DEL}illisible{CLR_RESET}"
        print(f"  {CLR_BOLD}{i}{CLR_RESET}. {date_txt}  {CLR_DIM}({detail}){CLR_RESET}")
    print(f" {CLR_CYAN}──────────────────────────────────{CLR_RESET}")
    print(f" {CLR_DIM}Restaurer : todo restore <numéro>   (1 = la plus récente){CLR_RESET}\n")

def restaurer_base(reference=None, confirmer=True):
    """Liste les sauvegardes (sans argument) ou restaure celle désignée.

    L'état actuel est sauvegardé juste avant la restauration, ce qui la rend réversible.
    """
    if reference is None:
        lister_sauvegardes()
        return

    noms = _noms_sauvegardes()[::-1]
    if not noms:
        print(f" 📦 {CLR_DIM}Aucune sauvegarde disponible.{CLR_RESET}")
        return

    nom = _resoudre_sauvegarde(reference, noms)
    if nom is None:
        return

    date_txt, nb = _infos_sauvegarde(nom)
    if nb is None:
        print(f" {CLR_DEL}❌{CLR_RESET} La sauvegarde du {date_txt} est illisible : restauration annulée.")
        return

    if confirmer:
        try:
            reponse = input(f" {CLR_DEL}⚠️ Restaurer{CLR_RESET} la sauvegarde du {CLR_BOLD}{date_txt}{CLR_RESET} ({nb} tâche(s)) ? "
                            f"L'état actuel sera sauvegardé avant. (y/N) : ").strip().lower()
        except EOFError:
            reponse = ""
        if reponse != 'y':
            print(" ❌ Opération annulée.")
            return

    dossier_source = os.path.join(BACKUP_DIR, nom)
    fichiers_source = [f for f in glob.glob(os.path.join(dossier_source, "*")) if os.path.isfile(f)]

    # 1. Filet de sécurité : sauvegarde de l'état actuel SANS rotation, pour que
    #    la sauvegarde choisie ne puisse pas être supprimée avant d'être copiée.
    filet = sauvegarder_base(rotation=False)

    # 2. Remplacement des fichiers de la base par ceux de la sauvegarde
    try:
        for f in glob.glob(f"{DB_NAME}*"):
            if os.path.isfile(f):
                os.remove(f)
        for f in fichiers_source:
            shutil.copy2(f, os.path.join(DB_DIR, os.path.basename(f)))
    except OSError as e:
        print(f" {CLR_DEL}❌ Erreur pendant la restauration :{CLR_RESET} {e}")
        if filet:
            print(f"    L'état précédent est conservé dans : {filet}")
        sys.exit(1)

    # 3. Nouvelle sauvegarde de l'état restauré (avec rotation)
    sauvegarder_base()
    print(f" {CLR_DONE}♻️  Base restaurée{CLR_RESET} depuis la sauvegarde du {CLR_BOLD}{date_txt}{CLR_RESET} ({nb} tâche(s)).")
    if filet:
        print(f"    {CLR_DIM}L'état précédent a été sauvegardé : 'restore' permet de le retrouver (le plus récent juste après celui-ci).{CLR_RESET}")

# ==============================================================================
# 7. MOTEURS DE RESTITUTION VISUELLE (AFFICHAGE, FILTRAGE, TRIS)
# ==============================================================================
def _afficher_texte(texte, pager=True):
    """Affiche un texte, via un pager quand il dépasse la hauteur du terminal.

    Le pager (less par défaut, ou la commande de $PAGER) n'est utilisé que si la sortie est un
    terminal interactif : dans un pipe ou une redirection, le texte est écrit tel quel.
    Si le pager est introuvable ou inutilisable, l'affichage se fait directement.
    """
    if pager and sys.stdout.isatty() and texte.count("\n") + 1 >= shutil.get_terminal_size().lines:
        try:
            cmd = shlex.split(os.environ.get("PAGER") or "less")
        except ValueError:
            cmd = []
        if cmd and shutil.which(cmd[0]):
            env = os.environ.copy()
            env.setdefault("LESS", "FRX")  # F : quitte si tout tient à l'écran, R : garde les couleurs, X : ne vide pas l'écran
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=env)
                try:
                    proc.stdin.write((texte + "\n").encode("utf-8"))
                    proc.stdin.close()
                except BrokenPipeError:
                    pass  # l'utilisateur a quitté le pager avant la fin : normal
                while True:
                    try:
                        proc.wait()
                        break
                    except KeyboardInterrupt:
                        continue  # Ctrl+C est géré par le pager, pas par nous
                return
            except OSError:
                pass  # pager inutilisable : repli sur l'affichage direct
    print(texte)

def lister_taches(statut_filtre=None, recherche_filtre=None, tri=None, fmt="table", tag_filtre=None,
                  prio_filtre=None, retard=False, aujourdhui=False, retards_en_premier=True,
                  limite=None, debut=None, pager=True, avant=None, apres=None):
    """Extrait, filtre, trie et met en forme l'ensemble des enregistrements actifs.

    retard / aujourdhui ne retiennent que les tâches À FAIRE dont l'échéance est
    dépassée / du jour ; s'ils sont combinés, une tâche qui satisfait l'un OU l'autre est gardée.

    avant / apres (objets date) bornent l'échéance, bornes INCLUSES. Une tâche sans échéance
    valide est exclue, et les tâches terminées aussi, sauf si statut_filtre vaut "done".

    limite / debut : n'affichent qu'une tranche de la liste triée (debut commence à 1,
    comme la numérotation affichée). pager : autorise l'usage d'un pager en mode table.
    """
    maintenant = datetime.now().date()
    toutes = _lire_taches()

    if not toutes:
        if fmt == "json":
            print("[]")
        else:
            print(f" 📋 {CLR_DIM}La liste est vide !{CLR_RESET}")
        return

    # Application sélective des filtres
    liste_taches = []
    for t in toutes:
        if statut_filtre == "todo" and t['statut'] != STATUT_A_FAIRE: continue
        if statut_filtre == "done" and t['statut'] != STATUT_TERMINE: continue
        if tag_filtre and tag_filtre.lower() not in t['tags']: continue
        if prio_filtre and t['priorite'] != prio_filtre: continue
        if avant is not None or apres is not None:
            echeance = _parse_date(t['date_echeance'])
            if echeance is None: continue
            if t['statut'] != STATUT_A_FAIRE and statut_filtre != "done": continue
            if avant is not None and echeance > avant: continue
            if apres is not None and echeance < apres: continue
        if retard or aujourdhui:
            jours = _jours_restants(t, maintenant)
            if t['statut'] != STATUT_A_FAIRE or jours is None: continue
            if not ((retard and jours < 0) or (aujourdhui and jours == 0)): continue
        if recherche_filtre and recherche_filtre.lower() not in (t['titre'] + " " + t['description'] + " " + " ".join(t['tags'])).lower(): continue
        liste_taches.append(t)

    if not liste_taches:
        if fmt == "json":
            print("[]")
        else:
            print(f" {CLR_DIM}Aucune tâche ne correspond à vos critères.{CLR_RESET}")
        return

    # Ordre de base DÉTERMINISTE (indispensable pour que --limit/--start ne répètent ni ne sautent
    # de tâches d'un appel à l'autre) : à faire avant terminées, puis échéance, puis
    # priorité (haute d'abord), date de création, puis id. Les tris ci-dessous sont stables et
    # s'appuient donc sur cet ordre.
    liste_taches.sort(key=lambda x: (x['statut'] != STATUT_A_FAIRE,
                                     x['date_echeance'] or "9999-12-31",
                                     -PRIORITES.index(x['priorite']),  # high (index 2) en premier
                                     x.get('date_creation') or "",
                                     x['id']))

    # Application des règles d'ordonnancement (Tris)
    if tri == "alpha":
        liste_taches.sort(key=lambda x: x['titre'].lower())
    elif tri == "status":
        liste_taches.sort(key=lambda x: x['statut'])
    elif tri == "priority":
        ordre_prio = {"high": 1, "medium": 2, "low": 3}
        liste_taches.sort(key=lambda x: ordre_prio.get(x['priorite'], 4))
    elif tri == "due":
        liste_taches.sort(key=lambda x: x['date_echeance'] if x['date_echeance'] else "9999-12-31")

    # Les tâches à faire en retard passent toujours en premier. Le regroupement est stable :
    # à l'intérieur de chaque groupe, l'ordre du tri choisi (--sort) est conservé.
    # Sans --sort, l'ordre de base classe déjà les retards du plus ancien au plus récent.
    def _en_retard(t):
        jours = _jours_restants(t, maintenant)
        return t['statut'] == STATUT_A_FAIRE and jours is not None and jours < 0

    # retards_en_premier=False (option --no-overdue-first) laisse l'ordre du tri tel quel.
    if retards_en_premier:
        en_retard = [t for t in liste_taches if _en_retard(t)]
        liste_taches = en_retard + [t for t in liste_taches if not _en_retard(t)]

    # --- Tranche demandée (--start / --limit), appliquée APRÈS filtres et tris ---
    total = len(liste_taches)
    indice_debut = (debut or 1) - 1
    indice_fin = indice_debut + limite if limite else total
    page = liste_taches[indice_debut:indice_fin]

    if not page:
        if fmt == "json":
            print("[]")
        else:
            print(f" {CLR_DIM}Aucune tâche à partir de la position {indice_debut + 1} : la liste n'en compte que {total}.{CLR_RESET}")
        return

    # --- MODE SORTIE FLUX JSON (COMPATIBLE JQ) : tranche seule, sans numérotation ni pied de page ---
    if fmt == "json":
        print(json.dumps(page, indent=2, ensure_ascii=False))
        return

    # --- MODE AFFICHAGE TABLEAU ANSI STYLISÉ ---
    lignes = [f"\n {CLR_CYAN}─── 📋 MA TO-DO LIST ───{CLR_RESET}"]
    largeur = len(str(indice_debut + len(page)))  # largeur de la numérotation (alignement)

    for position, t in enumerate(page, start=indice_debut + 1):
        a_faire = t['statut'] == STATUT_A_FAIRE
        prefixe = f"{CLR_TODO}[⏳]{CLR_RESET}" if a_faire else f"{CLR_DONE}[✅]{CLR_RESET}"
        texte_titre = f"{CLR_BOLD}{t['titre']}{CLR_RESET}" if a_faire else f"{CLR_DIM}{t['titre']}{CLR_RESET}"
        prio_color = f"{CLR_P_HIGH}[{t['priorite'].upper()}]{CLR_RESET}" if t['priorite'] == "high" else f"{CLR_P_MED}[{t['priorite'].upper()}]{CLR_RESET}" if t['priorite'] == "medium" else f"{CLR_P_LOW}[{t['priorite'].upper()}]{CLR_RESET}"
        # Évaluation dynamique du compte à rebours de l'échéance
        echeance_str = _libelle_echeance(t, maintenant)
        display_tags = f" {CLR_TAG}" + " ".join([f"#{tg}" for tg in t['tags']]) + f"{CLR_RESET}" if t['tags'] else ""
        rec_str = f" {CLR_DIM}↻ {_libelle_recurrence(t['recurrence'])}{CLR_RESET}" if (t['recurrence'] and a_faire) else ""
        numero = f"{CLR_DIM}{position:>{largeur}}.{CLR_RESET}"
        lignes.append(f"  {numero} {prefixe} {prio_color} {texte_titre}{echeance_str}{rec_str}{display_tags} {CLR_DIM}(id: {t['id'][:8]}){CLR_RESET}")
        if t['description']:
            lignes.append(f"      {' ' * (largeur + 2)}{CLR_DIM if not a_faire else ''}↳ {t['description']}{CLR_RESET}")
    lignes.append(f" {CLR_CYAN}──────────────────────────────────────{CLR_RESET}")

    # Pied de page : situe la tranche affichée dans la liste complète et indique la suite
    if len(page) < total:
        premiere, derniere = indice_debut + 1, indice_debut + len(page)
        resume = f"Affichage {premiere}–{derniere} sur {total}"
        if derniere < total:
            resume += f" · suite : --start {derniere + 1}" + (f" --limit {limite}" if limite else "")
    else:
        resume = f"{total} tâche(s)"
    lignes.append(f" {CLR_DIM}{resume}{CLR_RESET}\n")

    _afficher_texte("\n".join(lignes), pager)

# ==============================================================================
# 8. ANALYSE ET TABLEAU DE BORD STATISTIQUE
# ==============================================================================
def afficher_stats():
    """Agrège les métadonnées pour générer des indicateurs de performance et des graphiques texte."""
    taches = _lire_taches()
    total = len(taches)
    if total == 0:
        print(f" 📊 {CLR_DIM}Aucune statistique disponible. La base est vide.{CLR_RESET}")
        return

    faits = 0
    faits_aujourdhui = 0
    faits_7_jours = 0
    prio_counts = {"high": 0, "medium": 0, "low": 0}
    retards = 0
    aujourdhui = 0
    maintenant = datetime.now().date()
    tous_les_tags = []

    for t in taches:
        if t['statut'] == STATUT_TERMINE:
            faits += 1
            # Rythme de complétion (les anciennes tâches sans date ne sont pas comptées)
            date_fin = _parse_date((t['date_terminee'] or "")[:10])
            if date_fin is not None:
                ecart = (maintenant - date_fin).days
                if ecart == 0: faits_aujourdhui += 1
                if 0 <= ecart < 7: faits_7_jours += 1
            continue  # Les tâches terminées n'entrent ni dans la charge ni dans les alertes

        # 'priorite' est déjà normalisée : pas de KeyError possible
        prio_counts[t['priorite']] += 1
        tous_les_tags.extend(t['tags'])

        date_obj = _parse_date(t['date_echeance'])
        if date_obj is not None:
            jours = (date_obj - maintenant).days
            if jours < 0: retards += 1
            elif jours == 0: aujourdhui += 1

    # Rendu de la barre de complétion horizontale
    pct_accompli = int((faits / total) * 100)
    barre_longueur = 20
    blocs_faits = int((faits / total) * barre_longueur)
    barre_str = f"{CLR_DONE}{'█' * blocs_faits}{CLR_RESET}{CLR_DIM}{'░' * (barre_longueur - blocs_faits)}{CLR_RESET}"

    print(f"\n {CLR_CYAN}─── 📊 TABLEAU DE BORD DE VOS TÂCHES ───{CLR_RESET}")
    print(f"  {CLR_BOLD}Volume global :{CLR_RESET} {total} tâche(s) au total")
    print(f"  {CLR_BOLD}Progression   :{CLR_RESET} [{barre_str}] {CLR_BOLD}{pct_accompli}%{CLR_RESET} terminées ({faits}/{total})")
    print(f"  {CLR_BOLD}Rythme        :{CLR_RESET} {CLR_DONE}{faits_aujourdhui}{CLR_RESET} terminée(s) aujourd'hui · {CLR_DONE}{faits_7_jours}{CLR_RESET} sur les 7 derniers jours")

    print(f"\n  {CLR_BOLD}{CLR_TODO}📋 Charge active par Priorité :{CLR_RESET}")
    for p in PRIORITES[::-1]:  # high, medium, low
        c = prio_counts[p]
        lbl = f"{CLR_P_HIGH}HAUTE {CLR_RESET}" if p == 'high' else f"{CLR_P_MED}MOYENNE{CLR_RESET}" if p == 'medium' else f"{CLR_P_LOW}BASSE  {CLR_RESET}"
        barre_p = '█' * c
        print(f"    - {lbl} : {CLR_BOLD}{c}{CLR_RESET} \t{CLR_DIM}{barre_p}{CLR_RESET}")

    print(f"\n  {CLR_BOLD}{CLR_TAG}🏷️  Top Tags actifs :{CLR_RESET}")
    if tous_les_tags:
        top_tags = Counter(tous_les_tags).most_common(3)
        for tag, count in top_tags:
            print(f"    - {CLR_TAG}#{tag}{CLR_RESET} : {count} tâche(s)")
    else:
        print(f"    {CLR_DIM}Aucun tag utilisé sur vos tâches actives.{CLR_RESET}")

    print(f"\n  {CLR_BOLD}{CLR_DEL}🚨 Alertes & Échéances (Actives) :{CLR_RESET}")
    print(f"    - En retard        : {CLR_DEL}{CLR_BOLD}{retards}{CLR_RESET} tâche(s)")
    print(f"    - Pour aujourd'hui : {CLR_P_HIGH}{CLR_BOLD}{aujourdhui}{CLR_RESET} tâche(s)")
    print(f" {CLR_CYAN}────────────────────────────────────────{CLR_RESET}\n")

# ==============================================================================
# 9. OUTILS DE DÉVELOPPEMENT ET SIMULATION (SEEDING)
# ==============================================================================
def peupler_fausses_taches(nombre):
    """Injecte un jeu de données factices complexes pour le test de charge."""
    try:
        from faker import Faker
    except ImportError:
        print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Le module 'faker' est requis. Lancez : pip install faker")
        sys.exit(1)

    fake = Faker('fr_FR')
    liste_tags_test = ['pro', 'perso', 'dev', 'achat', 'urgent', 'sante', 'admin']

    print(f" ⏳ Génération de {CLR_BOLD}{nombre}{CLR_RESET} tâches factices...")

    for _ in range(nombre):
        titre = fake.sentence(nb_words=3)
        description = fake.sentence(nb_words=10)
        priorite = random.choice(PRIORITES)
        jours_ecart = random.randint(-3, 10)
        date_echeance = (datetime.now() + timedelta(days=jours_ecart)).strftime("%Y-%m-%d")

        if random.random() < 0.15:
            date_echeance = None

        tags_choisis = random.sample(liste_tags_test, k=random.randint(0, 2))
        # Pas de sauvegarde à chaque tâche : une seule à la fin
        ajouter_tache(titre, description, priorite, date_echeance, ",".join(tags_choisis),
                      silencieux=True, sauvegarder=False)

    sauvegarder_base()
    print(f" {CLR_DONE}🎉 Injection de données de test validée.{CLR_RESET}")

# ==============================================================================
# 10. POINT D'ENTRÉE DU SCRIPT ET ROUTAGE DES COMMANDES D'ARGPARSE
# ==============================================================================
def _date_filtre(valeur, option):
    """Résout la valeur d'une option de filtre de date (absolue ou relative), ou quitte avec une erreur."""
    if valeur is None:
        return None
    date_obj = _resoudre_date(valeur)
    if date_obj is None:
        print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Date non reconnue pour {CLR_BOLD}{option}{CLR_RESET} : '{valeur}'. "
              f"Formats acceptés : {CLR_BOLD}{MSG_FORMATS_DATE}{CLR_RESET}.")
        sys.exit(1)
    return date_obj

def _entier_positif(valeur):
    """Type argparse : entier >= 1."""
    try:
        n = int(valeur)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valeur}' n'est pas un entier")
    if n < 1:
        raise argparse.ArgumentTypeError("doit être supérieur ou égal à 1")
    return n

def _ajouter_options_couleur(p):
    """Ajoute --color et --no-color à un parseur (principal ou de sous-commande).

    default=SUPPRESS : une option absente ne doit pas écraser celle donnée à l'autre niveau,
    ce qui permet `todo --no-color list` comme `todo list --no-color`.
    """
    p.add_argument('--color', choices=['auto', 'always', 'never'], dest='couleur', default=argparse.SUPPRESS,
                   help="Couleurs : auto (défaut : seulement dans un terminal, sauf si NO_COLOR est défini), always, never")
    p.add_argument('--no-color', action='store_const', const='never', dest='couleur', default=argparse.SUPPRESS,
                   help="Désactive les couleurs (équivaut à --color never)")

def main():
    global _mode_couleur
    parser = argparse.ArgumentParser(description="Gestionnaire de tâches (To-Do List) CLI avancé et persistant.")
    subparsers = parser.add_subparsers(dest="commande", help="Commandes système disponibles")

    # Commande 'add'
    parser_add = subparsers.add_parser('add', help='Créer et insérer une nouvelle tâche')
    parser_add.add_argument('titre', type=str, help='Titre ou intitulé synthétique')
    parser_add.add_argument('--desc', type=str, default="", help='Notes explicatives complémentaires')
    parser_add.add_argument('--prio', choices=list(PRIORITES), default='medium', help='Gravité / Priorité')
    parser_add.add_argument('--due', type=str, default=None,
                            help="Échéance : AAAA-MM-JJ, aujourd'hui, demain, apres-demain, +3d/+2w/+1m/+1y ou un jour (lundi...)")
    parser_add.add_argument('--tags', type=str, default=None, help='Tags catégoriels indexés (ex: pro,dev)')
    parser_add.add_argument('--repeat', type=str, default=None,
                            help="Tâche récurrente : daily, weekly, monthly, yearly ou 3d/2w/1m/1y (échéance = aujourd'hui si --due absent)")

    # Commande 'list'
    parser_list = subparsers.add_parser('list', help='Afficher et filtrer les entrées de la base')
    parser_list.add_argument('--status', choices=['todo', 'done'], help="Filtrer selon l'avancement")
    parser_list.add_argument('--search', type=str, help='Recherche plein texte (Titre & Description)')
    parser_list.add_argument('--tag', type=str, default=None, help='Extraction par étiquette exclusive')
    parser_list.add_argument('--prio', choices=list(PRIORITES), default=None, help='Ne montrer que cette priorité')
    parser_list.add_argument('--overdue', action='store_true', help="Tâches à faire dont l'échéance est dépassée")
    parser_list.add_argument('--today', action='store_true', help="Tâches à faire dont l'échéance est aujourd'hui (avec --overdue : l'un ou l'autre)")
    parser_list.add_argument('--no-overdue-first', action='store_true',
                             help="Ne pas placer les tâches en retard en premier (l'ordre de --sort s'applique à toute la liste)")
    parser_list.add_argument('--due-before', type=str, default=None, metavar='DATE',
                             help="Échéance au plus tard à cette date, incluse (AAAA-MM-JJ, demain, +7d, vendredi...). "
                                  "Exclut les tâches sans échéance et les terminées (sauf avec --status done)")
    parser_list.add_argument('--due-after', type=str, default=None, metavar='DATE',
                             help="Échéance à partir de cette date, incluse (mêmes formats que --due-before)")
    parser_list.add_argument('--limit', type=_entier_positif, default=None, metavar='N',
                             help="N'afficher que N tâches (après filtres et tris)")
    parser_list.add_argument('--start', type=_entier_positif, default=None, metavar='N',
                             help="Commencer à la tâche n°N de la liste (la numérotation affichée commence à 1)")
    parser_list.add_argument('--no-pager', action='store_true',
                             help="Ne pas utiliser de pager (less) même si la liste dépasse l'écran")
    parser_list.add_argument('--sort', choices=['alpha', 'status', 'priority', 'due'], help='Critère de tri')
    parser_list.add_argument('--format', choices=['table', 'json'], default='table', help='Structure de la sortie textuelle')

    # Commande 'edit'
    parser_edit = subparsers.add_parser('edit', help="Modifier une tâche existante")
    parser_edit.add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    parser_edit.add_argument('--title', type=str, default=None, help='Nouveau titre')
    parser_edit.add_argument('--desc', type=str, default=None, help='Nouvelle description (chaîne vide pour effacer)')
    parser_edit.add_argument('--prio', choices=list(PRIORITES), default=None, help='Nouvelle priorité')
    parser_edit.add_argument('--due', type=str, default=None,
                             help="Nouvelle échéance : AAAA-MM-JJ, demain, +3d, lundi... ('none' pour la supprimer)")
    parser_edit.add_argument('--tags', type=str, default=None, help="Nouveaux tags, remplace les anciens (chaîne vide pour tout effacer)")
    parser_edit.add_argument('--repeat', type=str, default=None,
                             help="Nouvelle répétition : daily, weekly, monthly, yearly, 3d/2w/1m/1y ('none' pour la supprimer)")

    # Commandes 'show' et 'undone'
    subparsers.add_parser('show', help="Afficher le détail complet d'une tâche").add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    subparsers.add_parser('undone', help='Rouvrir une tâche terminée').add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")

    # Commande 'restore'
    parser_restore = subparsers.add_parser('restore', help='Lister les sauvegardes ou restaurer l\'une d\'elles')
    parser_restore.add_argument('backup', type=str, nargs='?', default=None,
                                help="Numéro (1 = la plus récente) ou préfixe d'horodatage ; sans argument : liste les sauvegardes")
    parser_restore.add_argument('-y', '--yes', action='store_true', help='Ne pas demander de confirmation')

    # Commandes utilitaires
    subparsers.add_parser('done', help='Clôturer définitivement une tâche').add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    subparsers.add_parser('remove', help='Supprimer une tâche de la base').add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    subparsers.add_parser('clear-done', help='Purger toutes les tâches terminées')
    parser_seed = subparsers.add_parser('seed', help='Remplir la base avec des faux enregistrements')
    parser_seed.add_argument('count', type=int, nargs='?', default=5, help='Quantité')
    subparsers.add_parser('stats', help='Calculer et afficher le tableau de bord des indicateurs')
    subparsers.add_parser('reset', help='Détruire intégralement le contenu de la base')

    # Options de couleur : au niveau principal et sur chaque sous-commande
    _ajouter_options_couleur(parser)
    for sous_parseur in subparsers.choices.values():
        _ajouter_options_couleur(sous_parseur)

    # Enregistrement dynamique du parseur auprès du démon d'auto-complétion argcomplete
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()
    _mode_couleur = getattr(args, 'couleur', None)
    _configurer_couleurs(_mode_couleur)

    # Moteur d'aiguillage vers l'action requise
    if args.commande == 'add':
        ajouter_tache(args.titre, args.desc, args.prio, args.due, args.tags, repeter=args.repeat)
    elif args.commande == 'list':
        avant = _date_filtre(args.due_before, '--due-before')
        apres = _date_filtre(args.due_after, '--due-after')
        if avant is not None and apres is not None and apres > avant:
            print(f" {CLR_DEL}❌ Erreur :{CLR_RESET} Plage vide : --due-after ({apres}) est postérieure à --due-before ({avant}).")
            sys.exit(1)
        lister_taches(args.status, args.search, args.sort, args.format, args.tag,
                      prio_filtre=args.prio, retard=args.overdue, aujourdhui=args.today,
                      retards_en_premier=not args.no_overdue_first,
                      limite=args.limit, debut=args.start, pager=not args.no_pager,
                      avant=avant, apres=apres)
    elif args.commande == 'show':
        afficher_tache(args.id)
    elif args.commande == 'undone':
        rouvrir_tache(args.id)
    elif args.commande == 'edit':
        modifier_tache(args.id, args.title, args.desc, args.prio, args.due, args.tags, args.repeat)
    elif args.commande == 'restore':
        restaurer_base(args.backup, confirmer=not args.yes)
    elif args.commande == 'done':
        marquer_terminee(args.id)
    elif args.commande == 'remove':
        supprimer_tache(args.id)
    elif args.commande == 'clear-done':
        nettoyer_terminees()
    elif args.commande == 'seed':
        peupler_fausses_taches(args.count)
    elif args.commande == 'stats':
        afficher_stats()
    elif args.commande == 'reset':
        reinitialiser_base()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n {CLR_DIM}Interrompu.{CLR_RESET}")
        sys.exit(130)
