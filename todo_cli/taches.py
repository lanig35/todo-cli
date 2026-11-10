"""Opérations sur les tâches : ajout, fin, réouverture, modification, suppression, report."""
import dbm
import json
import re
import sys
import uuid
from datetime import datetime
from .config import DB_NAME, PRIORITES, STATUT_A_FAIRE, STATUT_TERMINE
from . import couleurs
from .dates import MSG_FORMATS_DATE, MSG_FORMATS_REPETITION, _decaler, _libelle_recurrence, _parse_date, _parser_recurrence, _prochaine_echeance, _resoudre_date, _sans_accents
from .sauvegardes import sauvegarder_base
from .stockage import _afficher_bilan_lot, _base_existe, _normaliser_tache, _resoudre_id, _resoudre_ids


def _parser_tags(tags_str):
    """Transforme 'Pro, dev' en ['pro', 'dev'] (minuscules, sans vides)."""
    return [t.strip().lower() for t in tags_str.split(",") if t.strip()] if tags_str else []

def ajouter_tache(titre, description, priorite, date_echeance, tags_str, silencieux=False, sauvegarder=True, repeter=None):
    """Insère une tâche sérialisée en JSON dans la base clé-valeur intégrée."""
    if not titre or not titre.strip():
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Le titre ne peut pas être vide.")
        sys.exit(1)

    priorite = (priorite or "medium").lower()
    if priorite not in PRIORITES:
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Priorité invalide. Valeurs possibles : {couleurs.CLR_BOLD}{', '.join(PRIORITES)}{couleurs.CLR_RESET}.")
        sys.exit(1)

    date_echeance = date_echeance or None
    if date_echeance:
        date_obj = _resoudre_date(date_echeance)
        if date_obj is None:
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Date non reconnue. Formats acceptés : {couleurs.CLR_BOLD}{MSG_FORMATS_DATE}{couleurs.CLR_RESET}.")
            sys.exit(1)
        date_echeance = date_obj.strftime("%Y-%m-%d")

    # Récurrence : une tâche récurrente a toujours une échéance (aujourd'hui par défaut)
    recurrence = None
    echeance_par_defaut = False
    if repeter:
        recurrence = _parser_recurrence(repeter)
        if recurrence is None:
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Répétition non reconnue. Valeurs acceptées : {couleurs.CLR_BOLD}{MSG_FORMATS_REPETITION}{couleurs.CLR_RESET}.")
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
        print(f" {couleurs.CLR_DONE}✅{couleurs.CLR_RESET} Tâche ajoutée : '{couleurs.CLR_BOLD}{titre.strip()}{couleurs.CLR_RESET}'")
        if recurrence:
            suite = f" — première échéance : aujourd'hui" if echeance_par_defaut else f" — échéance : {date_echeance}"
            print(f"    {couleurs.CLR_DIM}↻ Répétition {_libelle_recurrence(recurrence)}{suite}{couleurs.CLR_RESET}")
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

def marquer_terminee(ids):
    """Bascule le statut d'une ou plusieurs tâches vers 'TERMINE' via préfixes d'ID (uniques).

    Si une tâche est récurrente, l'occurrence suivante est créée dans la foulée.
    Retourne True si aucun identifiant n'a posé problème (introuvable, ambigu, entrée corrompue).
    """
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, rien à valider.{couleurs.CLR_RESET}")
        return False

    nb_ok = 0
    with dbm.open(DB_NAME, 'w') as db:
        cles, echecs = _resoudre_ids(db, ids)
        for key in cles:
            try:
                t = _normaliser_tache(db[key])
            except ValueError:
                print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Cette entrée est corrompue et ne peut pas être modifiée.")
                echecs += 1
                continue
            if t['statut'] == STATUT_TERMINE:
                print(f" {couleurs.CLR_DIM}ℹ️  La tâche '{t['titre']}' est déjà terminée.{couleurs.CLR_RESET}")
                continue
            t['statut'] = STATUT_TERMINE
            t['date_terminee'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            occurrence = _creer_occurrence_suivante(db, t) if t['recurrence'] else None
            db[key] = json.dumps(t)
            print(f" {couleurs.CLR_DONE}🎉{couleurs.CLR_RESET} Tâche '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' validée !")
            if occurrence:
                print(f"    {couleurs.CLR_CYAN}↻ Prochaine occurrence : {occurrence[1]}{couleurs.CLR_RESET} {couleurs.CLR_DIM}(id: {occurrence[0][:8]}){couleurs.CLR_RESET}")
            elif t['recurrence']:
                print(f"    {couleurs.CLR_DEL}⚠️ Prochaine occurrence non créée : date hors limites.{couleurs.CLR_RESET}")
            nb_ok += 1

    # Une seule sauvegarde pour tout le lot, APRÈS fermeture de la base pour capturer les écritures
    if nb_ok:
        sauvegarder_base()
    _afficher_bilan_lot(len(ids), nb_ok, "validée(s)", echecs)
    return echecs == 0

def rouvrir_tache(id_recherche):
    """Repasse une tâche terminée au statut 'A FAIRE' via préfixe d'ID (unique)."""
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, rien à rouvrir.{couleurs.CLR_RESET}")
        return

    modifie = False
    with dbm.open(DB_NAME, 'w') as db:
        key = _resoudre_id(db, id_recherche)
        if key is None:
            return
        try:
            t = _normaliser_tache(db[key])
        except ValueError:
            print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Cette entrée est corrompue et ne peut pas être modifiée.")
            return
        if t['statut'] == STATUT_A_FAIRE:
            print(f" {couleurs.CLR_DIM}ℹ️  La tâche '{t['titre']}' est déjà à faire.{couleurs.CLR_RESET}")
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
                    print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Impossible : l'occurrence suivante de '{t['titre']}' est déjà terminée.")
                    return
                if suivante is not None:
                    del db[cle_suivante]
                    echeance_supprimee = suivante['date_echeance']
            t['suivante'] = None

        t['statut'] = STATUT_A_FAIRE
        t['date_terminee'] = None  # une tâche rouverte n'est plus terminée
        db[key] = json.dumps(t)
        print(f" {couleurs.CLR_TODO}↩️{couleurs.CLR_RESET}  Tâche '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' rouverte.")
        if echeance_supprimee:
            print(f"    {couleurs.CLR_DIM}↻ L'occurrence suivante (échéance {echeance_supprimee}) a été supprimée.{couleurs.CLR_RESET}")
        modifie = True

    # Sauvegarde APRÈS fermeture de la base, pour capturer la modification
    if modifie:
        sauvegarder_base()

def modifier_tache(id_recherche, titre=None, description=None, priorite=None, date_echeance=None, tags_str=None, repeter=None):
    """Modifie les champs fournis d'une tâche (None = champ inchangé).

    - date_echeance : date absolue ou relative ; 'none' (ou chaîne vide) supprime l'échéance.
    - tags_str      : chaîne vide supprime tous les tags ; sinon remplace la liste.
    - repeter       : 'weekly', '2w'... ; 'none' (ou chaîne vide) supprime la répétition.
    """
    if all(v is None for v in (titre, description, priorite, date_echeance, tags_str, repeter)):
        print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Rien à modifier. Options : --title, --desc, --prio, --due, --tags, --repeat.")
        return

    # --- Validation des valeurs AVANT toute ouverture de la base ---
    if titre is not None:
        titre = titre.strip()
        if not titre:
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Le titre ne peut pas être vide.")
            sys.exit(1)

    if priorite is not None:
        priorite = priorite.lower()
        if priorite not in PRIORITES:
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Priorité invalide. Valeurs possibles : {couleurs.CLR_BOLD}{', '.join(PRIORITES)}{couleurs.CLR_RESET}.")
            sys.exit(1)

    if date_echeance is not None:
        date_echeance = date_echeance.strip()
        if date_echeance.lower() in ("", "none"):
            date_echeance = ""  # suppression de l'échéance
        else:
            date_obj = _resoudre_date(date_echeance)
            if date_obj is None:
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Date non reconnue. Formats acceptés : {couleurs.CLR_BOLD}{MSG_FORMATS_DATE}{couleurs.CLR_RESET} (ou 'none' pour supprimer).")
                sys.exit(1)
            date_echeance = date_obj.strftime("%Y-%m-%d")  # forme absolue normalisée

    if repeter is not None:
        repeter = repeter.strip()
        if repeter.lower() in ("", "none"):
            repeter = ""  # suppression de la répétition
        else:
            recurrence_norm = _parser_recurrence(repeter)
            if recurrence_norm is None:
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Répétition non reconnue. Valeurs acceptées : {couleurs.CLR_BOLD}{MSG_FORMATS_REPETITION}{couleurs.CLR_RESET}.")
                sys.exit(1)
            repeter = recurrence_norm

    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, rien à modifier.{couleurs.CLR_RESET}")
        return

    modifications = []
    with dbm.open(DB_NAME, 'w') as db:
        key = _resoudre_id(db, id_recherche)
        if key is None:
            return
        try:
            t = _normaliser_tache(db[key])
        except ValueError:
            print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Cette entrée est corrompue et ne peut pas être modifiée.")
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
                print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Une tâche récurrente doit avoir une échéance : supprimez d'abord la répétition (--repeat none).")
                return
            t['date_echeance'] = datetime.now().date().strftime("%Y-%m-%d")
            modifications.append("échéance (aujourd'hui par défaut)")

        if not modifications:
            print(f" {couleurs.CLR_DIM}ℹ️  Aucun changement : les valeurs fournies sont déjà celles de la tâche '{t['titre']}'.{couleurs.CLR_RESET}")
            return

        db[key] = json.dumps(t)
        print(f" {couleurs.CLR_DONE}✏️{couleurs.CLR_RESET} Tâche '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' modifiée ({', '.join(modifications)}).")

    # Sauvegarde APRÈS fermeture de la base, pour capturer la modification
    sauvegarder_base()

def supprimer_tache(ids):
    """Retire définitivement une ou plusieurs entrées de la base de données.

    Retourne True si aucun identifiant n'a posé problème (introuvable, ambigu).
    """
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, rien à supprimer.{couleurs.CLR_RESET}")
        return False

    nb_ok = 0
    with dbm.open(DB_NAME, 'w') as db:
        cles, echecs = _resoudre_ids(db, ids)
        for key in cles:
            try:
                titre = _normaliser_tache(db[key])['titre']
            except ValueError:
                titre = None  # entrée corrompue : on peut quand même la supprimer
            del db[key]
            detail = f" : '{couleurs.CLR_BOLD}{titre}{couleurs.CLR_RESET}'" if titre else ""
            print(f" {couleurs.CLR_DEL}🗑️{couleurs.CLR_RESET} Tâche supprimée{detail}.")
            nb_ok += 1

    # Une seule sauvegarde pour tout le lot, APRÈS fermeture de la base
    if nb_ok:
        sauvegarder_base()
    _afficher_bilan_lot(len(ids), nb_ok, "supprimée(s)", echecs)
    return echecs == 0

def reporter_taches(ids, cible="+1d"):
    """Reporte l'échéance d'une ou plusieurs tâches à faire.

    cible : - décalage '+Nd', '+Nw', '+Nm', '+Ny' : appliqué à partir de max(échéance actuelle,
              aujourd'hui). Reporter de 2 jours une tâche en retard (ou sans échéance) donne donc
              « aujourd'hui + 2 jours », pas une date déjà passée.
            - date fixe : AAAA-MM-JJ, demain, lundi... (mêmes formats que --due).
    Retourne True si aucun identifiant n'a posé problème.
    """
    aujourdhui = datetime.now().date()
    cible = (cible or "").strip()
    if _resoudre_date(cible, aujourdhui) is None:
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Date non reconnue : '{cible}'. Formats acceptés : {couleurs.CLR_BOLD}{MSG_FORMATS_DATE}{couleurs.CLR_RESET}.")
        sys.exit(1)
    relatif = re.fullmatch(r"\+(\d{1,4})([dwmy])", _sans_accents(cible).lower())

    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, rien à reporter.{couleurs.CLR_RESET}")
        return False

    nb_ok = 0
    with dbm.open(DB_NAME, 'w') as db:
        cles, echecs = _resoudre_ids(db, ids)
        for key in cles:
            try:
                t = _normaliser_tache(db[key])
            except ValueError:
                print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Cette entrée est corrompue et ne peut pas être modifiée.")
                echecs += 1
                continue
            if t['statut'] == STATUT_TERMINE:
                print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} La tâche '{t['titre']}' est terminée : rien à reporter ('undone' pour la rouvrir).")
                echecs += 1
                continue

            try:
                if relatif:
                    base = max(_parse_date(t['date_echeance']) or aujourdhui, aujourdhui)
                    nouvelle = _decaler(base, int(relatif.group(1)), relatif.group(2))
                else:
                    nouvelle = _resoudre_date(cible, aujourdhui)
                nouvelle_txt = nouvelle.strftime("%Y-%m-%d")
            except (ValueError, OverflowError):
                print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Date hors limites pour la tâche '{t['titre']}'.")
                echecs += 1
                continue

            ancienne = t['date_echeance']
            if nouvelle_txt == ancienne:
                print(f" {couleurs.CLR_DIM}ℹ️  La tâche '{t['titre']}' a déjà pour échéance le {ancienne}.{couleurs.CLR_RESET}")
                continue
            t['date_echeance'] = nouvelle_txt
            db[key] = json.dumps(t)
            print(f" {couleurs.CLR_TODO}📅{couleurs.CLR_RESET} Tâche '{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}' reportée : "
                  f"{ancienne or 'aucune échéance'} → {couleurs.CLR_BOLD}{nouvelle_txt}{couleurs.CLR_RESET}")
            if t['recurrence']:
                print(f"    {couleurs.CLR_DIM}↻ Tâche récurrente : les prochaines occurrences partiront de cette échéance.{couleurs.CLR_RESET}")
            nb_ok += 1

    # Une seule sauvegarde pour tout le lot, APRÈS fermeture de la base
    if nb_ok:
        sauvegarder_base()
    _afficher_bilan_lot(len(ids), nb_ok, "reportée(s)", echecs)
    return echecs == 0

def nettoyer_terminees():
    """Purge de masse ciblant exclusivement les tâches archivées (TERMINE)."""
    if not _base_existe():
        print(f" 🧹 {couleurs.CLR_DIM}Aucune tâche terminée à nettoyer.{couleurs.CLR_RESET}")
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
            print(f" 🧹 {couleurs.CLR_DIM}Aucune tâche terminée à nettoyer.{couleurs.CLR_RESET}")
            return
        for k in cles:
            del db[k]
        print(f" {couleurs.CLR_DEL}🗑️{couleurs.CLR_RESET} Nettoyage réussi ({len(cles)} supprimée(s)).")
    sauvegarder_base()
