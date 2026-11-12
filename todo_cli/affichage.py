"""Affichage : détail d'une tâche, liste (tri, filtres, pagination, pager) et statistiques."""
import dbm
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from .config import DB_NAME, PRIORITES, STATUT_A_FAIRE, STATUT_TERMINE
from . import couleurs, journal
from .dates import _jours_restants, _libelle_echeance, _libelle_recurrence, _parse_date
from .stockage import _base_existe, _lire_archive, _lire_taches, _normaliser_tache, _resoudre_id


def afficher_tache(id_recherche):
    """Affiche le détail complet d'une tâche (lecture seule)."""
    if not _base_existe():
        print(f" 📋 {couleurs.CLR_DIM}La liste est vide, rien à afficher.{couleurs.CLR_RESET}")
        return

    with dbm.open(DB_NAME, 'r') as db:
        key = _resoudre_id(db, id_recherche)
        if key is None:
            return
        try:
            t = _normaliser_tache(db[key])
        except ValueError:
            journal.echec("corrupted_entry")
            print(f" {couleurs.CLR_DEL}❌{couleurs.CLR_RESET} Cette entrée est corrompue et ne peut pas être affichée.")
            return
        id_complet = key.decode('utf-8', errors='replace')

    maintenant = datetime.now().date()
    a_faire = t['statut'] == STATUT_A_FAIRE
    statut = f"{couleurs.CLR_TODO}[⏳] À faire{couleurs.CLR_RESET}" if a_faire else f"{couleurs.CLR_DONE}[✅] Terminée{couleurs.CLR_RESET}"
    couleur_prio = couleurs.CLR_P_HIGH if t['priorite'] == "high" else couleurs.CLR_P_MED if t['priorite'] == "medium" else couleurs.CLR_P_LOW

    if t['date_echeance']:
        echeance = t['date_echeance'] + (_libelle_echeance(t, maintenant) if a_faire else "")
    else:
        echeance = f"{couleurs.CLR_DIM}aucune{couleurs.CLR_RESET}"
    tags = f"{couleurs.CLR_TAG}" + " ".join(f"#{tg}" for tg in t['tags']) + f"{couleurs.CLR_RESET}" if t['tags'] else f"{couleurs.CLR_DIM}aucun{couleurs.CLR_RESET}"
    description = t['description'].replace("\n", "\n                ") if t['description'] else f"{couleurs.CLR_DIM}aucune{couleurs.CLR_RESET}"

    print(f"\n {couleurs.CLR_CYAN}─── 🔎 DÉTAIL DE LA TÂCHE ───{couleurs.CLR_RESET}")
    print(f"  {couleurs.CLR_BOLD}Titre       :{couleurs.CLR_RESET} {couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}")
    print(f"  {couleurs.CLR_BOLD}ID          :{couleurs.CLR_RESET} {id_complet}")
    print(f"  {couleurs.CLR_BOLD}Statut      :{couleurs.CLR_RESET} {statut}")
    print(f"  {couleurs.CLR_BOLD}Priorité    :{couleurs.CLR_RESET} {couleur_prio}{t['priorite'].upper()}{couleurs.CLR_RESET}")
    print(f"  {couleurs.CLR_BOLD}Créée le    :{couleurs.CLR_RESET} {t.get('date_creation') or f'{couleurs.CLR_DIM}inconnue{couleurs.CLR_RESET}'}")
    print(f"  {couleurs.CLR_BOLD}Échéance    :{couleurs.CLR_RESET} {echeance}")
    if not a_faire:
        print(f"  {couleurs.CLR_BOLD}Terminée le :{couleurs.CLR_RESET} {t['date_terminee'] or f'{couleurs.CLR_DIM}inconnue{couleurs.CLR_RESET}'}")
    if t['recurrence']:
        print(f"  {couleurs.CLR_BOLD}Répétition  :{couleurs.CLR_RESET} ↻ {_libelle_recurrence(t['recurrence'])}")
    if t['suivante']:
        print(f"  {couleurs.CLR_BOLD}Suivante    :{couleurs.CLR_RESET} {t['suivante']}")
    print(f"  {couleurs.CLR_BOLD}Tags        :{couleurs.CLR_RESET} {tags}")
    print(f"  {couleurs.CLR_BOLD}Description :{couleurs.CLR_RESET} {description}")
    print(f" {couleurs.CLR_CYAN}─────────────────────────────{couleurs.CLR_RESET}\n")

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
            print(f" 📋 {couleurs.CLR_DIM}La liste est vide !{couleurs.CLR_RESET}")
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
            print(f" {couleurs.CLR_DIM}Aucune tâche ne correspond à vos critères.{couleurs.CLR_RESET}")
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
            print(f" {couleurs.CLR_DIM}Aucune tâche à partir de la position {indice_debut + 1} : la liste n'en compte que {total}.{couleurs.CLR_RESET}")
        return

    # --- MODE SORTIE FLUX JSON (COMPATIBLE JQ) : tranche seule, sans numérotation ni pied de page ---
    if fmt == "json":
        print(json.dumps(page, indent=2, ensure_ascii=False))
        return

    # --- MODE AFFICHAGE TABLEAU ANSI STYLISÉ ---
    lignes = [f"\n {couleurs.CLR_CYAN}─── 📋 MA TO-DO LIST ───{couleurs.CLR_RESET}"]
    largeur = len(str(indice_debut + len(page)))  # largeur de la numérotation (alignement)

    for position, t in enumerate(page, start=indice_debut + 1):
        a_faire = t['statut'] == STATUT_A_FAIRE
        prefixe = f"{couleurs.CLR_TODO}[⏳]{couleurs.CLR_RESET}" if a_faire else f"{couleurs.CLR_DONE}[✅]{couleurs.CLR_RESET}"
        texte_titre = f"{couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}" if a_faire else f"{couleurs.CLR_DIM}{t['titre']}{couleurs.CLR_RESET}"
        prio_color = f"{couleurs.CLR_P_HIGH}[{t['priorite'].upper()}]{couleurs.CLR_RESET}" if t['priorite'] == "high" else f"{couleurs.CLR_P_MED}[{t['priorite'].upper()}]{couleurs.CLR_RESET}" if t['priorite'] == "medium" else f"{couleurs.CLR_P_LOW}[{t['priorite'].upper()}]{couleurs.CLR_RESET}"
        # Évaluation dynamique du compte à rebours de l'échéance
        echeance_str = _libelle_echeance(t, maintenant)
        display_tags = f" {couleurs.CLR_TAG}" + " ".join([f"#{tg}" for tg in t['tags']]) + f"{couleurs.CLR_RESET}" if t['tags'] else ""
        rec_str = f" {couleurs.CLR_DIM}↻ {_libelle_recurrence(t['recurrence'])}{couleurs.CLR_RESET}" if (t['recurrence'] and a_faire) else ""
        numero = f"{couleurs.CLR_DIM}{position:>{largeur}}.{couleurs.CLR_RESET}"
        lignes.append(f"  {numero} {prefixe} {prio_color} {texte_titre}{echeance_str}{rec_str}{display_tags} {couleurs.CLR_DIM}(id: {t['id'][:8]}){couleurs.CLR_RESET}")
        if t['description']:
            lignes.append(f"      {' ' * (largeur + 2)}{couleurs.CLR_DIM if not a_faire else ''}↳ {t['description']}{couleurs.CLR_RESET}")
    lignes.append(f" {couleurs.CLR_CYAN}──────────────────────────────────────{couleurs.CLR_RESET}")

    # Pied de page : situe la tranche affichée dans la liste complète et indique la suite
    if len(page) < total:
        premiere, derniere = indice_debut + 1, indice_debut + len(page)
        resume = f"Affichage {premiere}–{derniere} sur {total}"
        if derniere < total:
            resume += f" · suite : --start {derniere + 1}" + (f" --limit {limite}" if limite else "")
    else:
        resume = f"{total} tâche(s)"
    lignes.append(f" {couleurs.CLR_DIM}{resume}{couleurs.CLR_RESET}\n")

    _afficher_texte("\n".join(lignes), pager)

def afficher_stats(avec_archive=False):
    """Agrège les métadonnées pour générer des indicateurs de performance et des graphiques texte.

    avec_archive : compte aussi les tâches archivées (toutes terminées) dans le volume, la
    progression et le rythme de complétion.
    """
    taches = _lire_taches()
    archivees = _lire_archive() if avec_archive else []
    taches = taches + archivees
    total = len(taches)
    if total == 0:
        print(f" 📊 {couleurs.CLR_DIM}Aucune statistique disponible. La base est vide.{couleurs.CLR_RESET}")
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
    barre_str = f"{couleurs.CLR_DONE}{'█' * blocs_faits}{couleurs.CLR_RESET}{couleurs.CLR_DIM}{'░' * (barre_longueur - blocs_faits)}{couleurs.CLR_RESET}"

    print(f"\n {couleurs.CLR_CYAN}─── 📊 TABLEAU DE BORD DE VOS TÂCHES ───{couleurs.CLR_RESET}")
    print(f"  {couleurs.CLR_BOLD}Volume global :{couleurs.CLR_RESET} {total} tâche(s) au total"
          + (f" {couleurs.CLR_DIM}(dont {len(archivees)} archivée(s)){couleurs.CLR_RESET}" if avec_archive else ""))
    print(f"  {couleurs.CLR_BOLD}Progression   :{couleurs.CLR_RESET} [{barre_str}] {couleurs.CLR_BOLD}{pct_accompli}%{couleurs.CLR_RESET} terminées ({faits}/{total})")
    print(f"  {couleurs.CLR_BOLD}Rythme        :{couleurs.CLR_RESET} {couleurs.CLR_DONE}{faits_aujourdhui}{couleurs.CLR_RESET} terminée(s) aujourd'hui · {couleurs.CLR_DONE}{faits_7_jours}{couleurs.CLR_RESET} sur les 7 derniers jours")

    print(f"\n  {couleurs.CLR_BOLD}{couleurs.CLR_TODO}📋 Charge active par Priorité :{couleurs.CLR_RESET}")
    for p in PRIORITES[::-1]:  # high, medium, low
        c = prio_counts[p]
        lbl = f"{couleurs.CLR_P_HIGH}HAUTE {couleurs.CLR_RESET}" if p == 'high' else f"{couleurs.CLR_P_MED}MOYENNE{couleurs.CLR_RESET}" if p == 'medium' else f"{couleurs.CLR_P_LOW}BASSE  {couleurs.CLR_RESET}"
        barre_p = '█' * c
        print(f"    - {lbl} : {couleurs.CLR_BOLD}{c}{couleurs.CLR_RESET} \t{couleurs.CLR_DIM}{barre_p}{couleurs.CLR_RESET}")

    print(f"\n  {couleurs.CLR_BOLD}{couleurs.CLR_TAG}🏷️  Top Tags actifs :{couleurs.CLR_RESET}")
    if tous_les_tags:
        top_tags = Counter(tous_les_tags).most_common(3)
        for tag, count in top_tags:
            print(f"    - {couleurs.CLR_TAG}#{tag}{couleurs.CLR_RESET} : {count} tâche(s)")
    else:
        print(f"    {couleurs.CLR_DIM}Aucun tag utilisé sur vos tâches actives.{couleurs.CLR_RESET}")

    print(f"\n  {couleurs.CLR_BOLD}{couleurs.CLR_DEL}🚨 Alertes & Échéances (Actives) :{couleurs.CLR_RESET}")
    print(f"    - En retard        : {couleurs.CLR_DEL}{couleurs.CLR_BOLD}{retards}{couleurs.CLR_RESET} tâche(s)")
    print(f"    - Pour aujourd'hui : {couleurs.CLR_P_HIGH}{couleurs.CLR_BOLD}{aujourdhui}{couleurs.CLR_RESET} tâche(s)")
    print(f" {couleurs.CLR_CYAN}────────────────────────────────────────{couleurs.CLR_RESET}\n")
