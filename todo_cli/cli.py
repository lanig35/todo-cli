"""Définition de la ligne de commande (argparse) et aiguillage vers les commandes."""
import argparse
import difflib
import os
import sys
from datetime import datetime
from .agenda import afficher_agenda
from .archive import MSG_FORMAT_ANCIENNETE, _parser_anciennete, archivage_automatique, archiver_taches, desarchiver_taches, lister_archive, purger_archive
from .affichage import CHAMPS_RECHERCHE, afficher_stats, afficher_tache, champs_recherche, lister_taches, selectionner
from .config import PRIORITES, STATUT_A_FAIRE
from . import config
from . import __version__, couleurs, dependances, journal, lot, reglages, verrou
from .stockage import _lire_taches
from . import deplacement, projets, stockage
from .deplacement import deplacer_taches
from .configuration import afficher_chemin, afficher_config, ecrire_reglage, initialiser_config, lire_reglage, retirer_reglage
from .dates import MSG_FORMATS_DATE, _resoudre_date
from .dates import _decaler
from .filtres import MSG_FORMATS_DATE_PASSEE, parser_instant, resoudre_date_passee
from .saisie import analyser_titre
from .prochaine import afficher_prochaines
from .rapports import rapport_bloquees, rapport_delais, rapport_en_cours, rapport_retards, rapport_stagnantes, rapport_tags, rapport_terminees
from .rappel import activer_rappels, afficher_etat_rappels, desactiver_rappels, rappeler
from .sauvegardes import annuler_derniere_action, reinitialiser_base, restaurer_base
from .seed import peupler_fausses_taches
from .echange import exporter, importer
from .formats import FORMATS, colonnes_tache, resoudre as resoudre_format
from .notes import commande_note
from . import pieces_jointes
from .taches import ajouter_tache, annuler_demarrage, demarrer_taches, marquer_terminee, modifier_tache, reporter_taches, rouvrir_tache, supprimer_tache


def _date_filtre(valeur, option):
    """Résout la valeur d'une option de filtre de date (absolue ou relative), ou quitte avec une erreur."""
    if valeur is None:
        return None
    date_obj = _resoudre_date(valeur)
    if date_obj is None:
        journal.echec("invalid_date")
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Date non reconnue pour {couleurs.CLR_BOLD}{option}{couleurs.CLR_RESET} : '{valeur}'. "
              f"Formats acceptés : {couleurs.CLR_BOLD}{MSG_FORMATS_DATE}{couleurs.CLR_RESET}.")
        sys.exit(1)
    return date_obj

def _champs_recherche(valeur):
    """Type argparse de --search-in : un ou plusieurs champs séparés par des virgules."""
    try:
        return champs_recherche(valeur)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


_AIDE_SEARCH_IN = ("Limite --search à ces champs, séparés par des virgules : title, description, tags, notes "
                   "(défaut : all). Ex. : --search-in notes")


def _prios(valeur):
    """Type argparse : une ou plusieurs priorités séparées par des virgules."""
    noms = tuple(n.strip().lower() for n in str(valeur).split(",") if n.strip())
    mauvais = [n for n in noms if n not in PRIORITES]
    if not noms or mauvais:
        raise argparse.ArgumentTypeError(f"priorité inconnue : {', '.join(mauvais) or valeur} (attendues : {', '.join(PRIORITES)})")
    return noms


def _liste(valeurs):
    """Valeurs d'une option répétable ou séparée par des virgules, en minuscules sans doublon (None si absente)."""
    if not valeurs:
        return None
    res = []
    for v in valeurs:
        for x in str(v).split(","):
            x = x.strip().lower()
            if x and x not in res:
                res.append(x)
    return res or None


def _args_filtres_selection(p, prio=True):
    """Filtres par tag, priorité, récurrence, création et identifiant (list, archive list, actions en lot).

    `prio=False` omet --prio : `edit` l'utilise déjà pour la NOUVELLE priorité (--not-prio reste disponible).
    """
    p.add_argument('--tag', action='append', default=None, metavar='TAGS',
                   help="Seulement les tâches portant ce tag ; répétable ou séparé par des virgules : TOUS les tags indiqués")
    p.add_argument('--any-tag', action='append', default=None, metavar='TAGS',
                   help="Seulement les tâches portant AU MOINS UN de ces tags (répétable ou séparés par des virgules)")
    p.add_argument('--no-tag', action='store_true', help="Seulement les tâches sans aucun tag")
    p.add_argument('--not-tag', action='append', default=None, metavar='TAGS',
                   help="Écarter les tâches portant l'un de ces tags (répétable ou séparés par des virgules)")
    if prio:
        p.add_argument('--prio', type=_prios, default=None, metavar='PRIO',
                       help="Seulement cette priorité (ou plusieurs, séparées par des virgules : high,medium)")
    p.add_argument('--not-prio', type=_prios, default=None, metavar='PRIO', help="Écarter cette priorité (ou plusieurs, séparées par des virgules)")
    g = p.add_mutually_exclusive_group()
    g.add_argument('--recurring', action='store_true', help="Seulement les tâches récurrentes")
    g.add_argument('--no-recurring', action='store_true', help="Seulement les tâches non récurrentes")
    p.add_argument('--created-after', type=str, default=None, metavar='DATE',
                   help="Créées à partir de cette date, incluse (AAAA-MM-JJ, hier, ou durée écoulée : 7d, 2w, 1m, 1y)")
    p.add_argument('--created-before', type=str, default=None, metavar='DATE',
                   help="Créées au plus tard à cette date, incluse (mêmes formats que --created-after)")
    p.add_argument('--id', dest='filtre_id', action='append', default=None, metavar='ID',
                   help="Seulement la tâche dont l'identifiant commence par ID (répétable ou séparés par des virgules)")


_ATTRS_SELECTION = ('tag', 'any_tag', 'no_tag', 'not_tag', 'prio', 'not_prio', 'recurring', 'no_recurring',
                    'created_after', 'created_before', 'filtre_id')


def _args_filtres_notes(p):
    g = p.add_mutually_exclusive_group()
    g.add_argument('--has-notes', action='store_true', help="Seulement les tâches qui ont au moins une note")
    g.add_argument('--no-notes', action='store_true', help="Seulement les tâches sans note")
    g = p.add_mutually_exclusive_group()
    g.add_argument('--has-files', action='store_true', help="Seulement les tâches qui ont au moins une pièce jointe")
    g.add_argument('--no-files', action='store_true', help="Seulement les tâches sans pièce jointe")
    g = p.add_mutually_exclusive_group()
    g.add_argument('--started', action='store_true', help="Seulement les tâches démarrées (`task start` ; avec --status todo : les tâches en cours)")
    g.add_argument('--not-started', action='store_true', help="Seulement les tâches jamais démarrées")


def _args_filtres_fin(p, archive=False):
    aide = "Terminées à partir de cette date, incluse (AAAA-MM-JJ, hier, ou durée écoulée : 7d, 2w, 1m, 1y)"
    p.add_argument('--done-after', type=str, default=None, metavar='DATE', help=aide)
    p.add_argument('--done-before', type=str, default=None, metavar='DATE',
                   help="Terminées au plus tard à cette date, incluse (mêmes formats que --done-after)")
    if archive:
        p.add_argument('--archived-after', type=str, default=None, metavar='DATE',
                       help="Archivées à partir de cette date, incluse (mêmes formats que --done-after)")
        p.add_argument('--archived-before', type=str, default=None, metavar='DATE',
                       help="Archivées au plus tard à cette date, incluse (mêmes formats que --done-after)")


def _date_passee(valeur, option):
    """Date d'une option sur le passé (--done-after…), ou erreur et sortie."""
    if valeur is None:
        return None
    date_obj = resoudre_date_passee(valeur)
    if date_obj is None:
        journal.echec("invalid_date")
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Date non reconnue pour {couleurs.CLR_BOLD}{option}{couleurs.CLR_RESET} : '{valeur}'. "
              f"Formats acceptés : {couleurs.CLR_BOLD}{MSG_FORMATS_DATE_PASSEE}{couleurs.CLR_RESET}.")
        sys.exit(1)
    return date_obj


def _plage_vide(apres, avant, option_apres, option_avant):
    if apres is not None and avant is not None and apres > avant:
        journal.echec("empty_range")
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Plage vide : {option_apres} ({apres}) est postérieure à {option_avant} ({avant}).")
        sys.exit(1)


def _filtres_communs(args, archive=False, sans_prio=False):
    """Dict d'options pour `filtres.garder`, d'après les options de la ligne de commande (erreur si incohérentes).

    `sans_prio` : ignore args.prio (pour `edit`, où --prio est la nouvelle priorité et non un filtre)."""
    f = {}
    tags, un_tag, pas_tags = _liste(args.tag), _liste(args.any_tag), _liste(args.not_tag)
    if args.no_tag and (tags or un_tag):
        journal.echec("invalid_combination")
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --no-tag ne se combine pas avec --tag ni --any-tag.")
        sys.exit(1)
    f.update(tags=tags, un_tag=un_tag, pas_tags=pas_tags, prios=None if sans_prio else args.prio, pas_prios=args.not_prio,
             ids=_liste(args.filtre_id))
    if args.no_tag:
        f['sans_tag'] = True
    if args.recurring or args.no_recurring:
        f['recurrente'] = bool(args.recurring)
    f['cree_apres'] = _date_passee(args.created_after, '--created-after')
    f['cree_avant'] = _date_passee(args.created_before, '--created-before')
    _plage_vide(f['cree_apres'], f['cree_avant'], '--created-after', '--created-before')
    if getattr(args, 'no_due', False):
        f['sans_echeance'] = True
    if getattr(args, 'blocked', False) or getattr(args, 'ready', False):
        f['bloquee'] = bool(args.blocked)
    if args.has_notes or args.no_notes:
        f['notes'] = bool(args.has_notes)
    if args.has_files or args.no_files:
        f['fichiers'] = bool(args.has_files)
    if args.started or args.not_started:
        f['demarree'] = bool(args.started)
    f['fini_apres'] = _date_passee(args.done_after, '--done-after')
    f['fini_avant'] = _date_passee(args.done_before, '--done-before')
    _plage_vide(f['fini_apres'], f['fini_avant'], '--done-after', '--done-before')
    if archive:
        f['archive_apres'] = _date_passee(args.archived_after, '--archived-after')
        f['archive_avant'] = _date_passee(args.archived_before, '--archived-before')
        _plage_vide(f['archive_apres'], f['archive_avant'], '--archived-after', '--archived-before')
        if args.anciennete is not None:
            anciennete = _parser_anciennete(args.anciennete)
            if anciennete is None:
                journal.echec("invalid_duration")
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Durée non reconnue pour --older-than : '{args.anciennete}'. "
                      f"Format : {MSG_FORMAT_ANCIENNETE}.")
                sys.exit(1)
            f['anciennete'] = _decaler(datetime.now().date(), -anciennete[0], anciennete[1])
    return {k: v for k, v in f.items() if v is not None}


def _args_archive_filtres(p):
    """Filtres, tri et tranche de `archive list`."""
    _args_filtres_selection(p)
    _args_filtres_notes(p)
    _args_filtres_fin(p, archive=True)
    p.add_argument('--older-than', dest='anciennete', type=str, default=None, metavar='DUREE',
                   help="Seulement les tâches terminées depuis au moins cette durée (30d, 2w, 6m, 1y)")
    p.add_argument('--sort', choices=['done', 'archived', 'alpha', 'priority'], default=None,
                   help="Critère de tri : done (défaut, la plus récemment terminée d'abord), archived, alpha, priority")
    p.add_argument('--limit', type=_entier_positif, default=None, metavar='N', help="N'afficher que N tâches (après filtres et tri)")
    p.add_argument('--start', type=_entier_positif, default=None, metavar='N', help="Commencer à la tâche n°N de la liste")
    _args_colonnes(p)


def _filtres_archive_actifs(args):
    return any([*(getattr(args, a) for a in _ATTRS_SELECTION), args.has_notes, args.no_notes, args.has_files, args.no_files, args.started, args.not_started, args.done_after, args.done_before,
                args.archived_after, args.archived_before, args.sort, args.limit, args.start, args.columns])


_ATTRS_LOT = ('status', 'search', 'search_in', 'overdue', 'today', 'due_before', 'due_after', 'no_due', 'blocked', 'ready',
              'has_notes', 'no_notes', 'has_files', 'no_files', 'started', 'not_started', 'done_after', 'done_before', *_ATTRS_SELECTION)


def _args_lot(p, statut=False, prio=True):
    """Options communes des actions en lot (done, undone, postpone, remove, edit) : sélection par filtre.

    Les filtres sont ceux de `list` ; sans identifiant, ils désignent les tâches visées. `statut` ajoute
    --status (done et postpone, undone s'appliquent d'office aux tâches à faire / terminées).
    `prio=False` : voir `_args_filtres_selection`.
    """
    g = p.add_argument_group("sélection par filtre (à la place des identifiants)",
                             "Les filtres de `list`, combinés par ET : la sélection est calculée d'abord, puis l'action s'applique à "
                             "chaque tâche retenue (une seule sauvegarde, un seul `undo`). Une confirmation est demandée à partir de "
                             "[general] batch_confirm tâches (5 par défaut) ; -y la passe.")
    g.add_argument('--all', dest='tout', action='store_true', help="Toutes les tâches concernées (sans filtre ni identifiant)")
    if statut:
        g.add_argument('--status', choices=['todo', 'done'], default=None, help="Seulement les tâches à faire (todo) ou terminées (done)")
    g.add_argument('--search', type=str, default=None, help='Recherche plein texte (titre, description, tags, notes), sans accents ni casse')
    g.add_argument('--search-in', type=_champs_recherche, default=None, metavar='CHAMPS', help=_AIDE_SEARCH_IN)
    _args_filtres_selection(g, prio=prio)
    gb = g.add_mutually_exclusive_group()
    gb.add_argument('--blocked', action='store_true', help="Seulement les tâches à faire qui attendent une dépendance (--after)")
    gb.add_argument('--ready', action='store_true', help="Seulement les tâches à faire qui ne sont pas bloquées")
    g.add_argument('--no-due', action='store_true', help="Seulement les tâches sans échéance")
    _args_filtres_notes(g)
    _args_filtres_fin(g)
    g.add_argument('--overdue', action='store_true', help="Tâches à faire dont l'échéance est dépassée")
    g.add_argument('--today', action='store_true', help="Tâches à faire dont l'échéance est aujourd'hui (avec --overdue : l'un ou l'autre)")
    g.add_argument('--due-before', type=str, default=None, metavar='DATE', help="Échéance au plus tard à cette date, incluse")
    g.add_argument('--due-after', type=str, default=None, metavar='DATE', help="Échéance à partir de cette date, incluse")
    g.add_argument('--dry-run', action='store_true', help="Montre les tâches visées sans rien modifier")
    g.add_argument('-y', '--yes', action='store_true', help="Ne pas demander de confirmation pour un lot")
    g.add_argument('--format', choices=FORMATS, default=None, help="Format de l'aperçu de --dry-run (json : compatible jq)")
    _args_colonnes(g)


def _erreur_lot(cause, message, code=1):
    """Quitte avec une erreur de sélection (code 2 = erreur d'usage, sur stderr, comme argparse)."""
    if code == 2:
        journal.echec("usage", detail=message)
    else:
        journal.echec(cause)
    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {message}", file=sys.stderr if code == 2 else sys.stdout)
    sys.exit(code)


def _ids_ou_lot(args, statut_implicite, infinitif, participe, sans_prio=False):
    """Identifiants visés par une action : ceux donnés, ou la sélection par filtre (`None` : rien à faire).

    Sans filtre ni `--all`, les identifiants de la ligne de commande sont rendus tels quels. Avec un filtre, la
    sélection est calculée et figée (identifiants complets) ; elle est annoncée vide, simulée (`--dry-run`) ou
    confirmée avant que l'action ne soit lancée. `statut_implicite` : "todo" / "done" pour les actions qui ne
    concernent que ces tâches, None pour celles où `--status` choisit.
    """
    attrs = [a for a in _ATTRS_LOT if not (sans_prio and a == 'prio')]
    filtre = any(getattr(args, a, None) for a in attrs)
    if not filtre and not args.tout:
        if args.dry_run:
            _erreur_lot("invalid_combination", "--dry-run s'utilise avec un filtre ou --all.")
        if not args.ids:
            _erreur_lot("missing_target", "Indiquez au moins un identifiant, ou un filtre (--all pour toutes les tâches concernées).", code=2)
        return args.ids
    if args.ids:
        _erreur_lot("invalid_combination", "Indiquez des identifiants OU des filtres (ou --all), pas les deux.")
    if filtre and args.tout:
        _erreur_lot("invalid_combination", "--all ne se combine pas avec des filtres : ils désignent déjà les tâches visées.")
    _exiger_search(args)
    if args.no_due and (args.due_before or args.due_after):
        _erreur_lot("invalid_combination", "--no-due ne se combine pas avec --due-before ni --due-after.")
    avant = _date_filtre(args.due_before, '--due-before')
    apres = _date_filtre(args.due_after, '--due-after')
    if avant is not None and apres is not None and apres > avant:
        _erreur_lot("empty_range", f"Plage vide : --due-after ({apres}) est postérieure à --due-before ({avant}).")
    cibles = selectionner(dependances.annoter(_lire_taches()), statut_implicite or getattr(args, 'status', None), args.search,
                          args.search_in or CHAMPS_RECHERCHE, args.overdue, args.today, avant, apres,
                          _filtres_communs(args, sans_prio=sans_prio))
    cibles.sort(key=lambda t: (t['statut'] != STATUT_A_FAIRE, t['date_echeance'] or "9999-12-31",
                               -PRIORITES.index(t['priorite']), t.get('date_creation') or "", t['id']))
    if not cibles:
        journal.noter(total=0)
        print(f" ℹ️  {couleurs.CLR_DIM}Aucune tâche ne correspond à ces critères : rien à {infinitif}.{couleurs.CLR_RESET}")
        return None
    if args.dry_run:
        lot.apercu(cibles, resoudre_format(args.format or 'auto'), _colonnes_effectives(args), participe)
        return None
    if not lot.confirmer(cibles, infinitif.capitalize(), reglages.obtenir('general', 'batch_confirm'), args.yes):
        return None
    journal.noter(selection="filter", count=len(cibles))
    return [t['id'] for t in cibles]


def _colonnes(valeur):
    """Type argparse de --columns."""
    try:
        return colonnes_tache(valeur)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def _args_colonnes(p):
    p.add_argument('--columns', type=_colonnes, default=None, metavar='COLONNES',
                   help="Colonnes des formats table et plain, séparées par des virgules, dans cet ordre : id, status, prio, due, "
                        "tags, title, notes, files, started, created, done, archived, recurrence, description, after, blocked. L'id est toujours présent "
                        "(placé en tête s'il manque). Défaut : id,status,prio,due,tags,title,notes (ou [general] columns)")


def _colonnes_effectives(args):
    """Colonnes des formats table et plain : --columns, sinon [general] columns (TODO_COLUMNS, fichier, défaut)."""
    colonnes = args.columns or colonnes_tache(reglages.obtenir('general', 'columns'))
    if stockage.tous_projets() and 'project' not in colonnes:      # lecture transverse : la colonne du projet suit l'id
        colonnes = (colonnes[0], 'project', *colonnes[1:])
    return colonnes


def _exiger_search(args):
    """--search-in n'a de sens qu'avec --search."""
    if args.search_in is not None and args.search is None:
        journal.echec("invalid_combination")
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --search-in s'utilise avec --search.")
        sys.exit(1)


def _entier_positif(valeur):
    """Type argparse : entier >= 1."""
    try:
        n = int(valeur)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{valeur}' n'est pas un entier")
    if n < 1:
        raise argparse.ArgumentTypeError("doit être supérieur ou égal à 1")
    return n

class _Parseur(argparse.ArgumentParser):
    """ArgumentParser dont les erreurs d'usage (code 2) sont aussi écrites dans le journal."""

    def error(self, message):
        journal.echec("usage", detail=message)
        super().error(message)


def _completer_projets(prefix, parsed_args, **kwargs):
    """Complétion d'un nom de projet : ceux qui existent (rien n'est créé en complétant)."""
    return config.projets()


def _ajouter_options_couleur(p):
    """Ajoute --color, --no-color et --log-level à un parseur (principal ou de sous-commande).

    default=SUPPRESS : une option absente ne doit pas écraser celle donnée à l'autre niveau,
    ce qui permet `todo --no-color list` comme `todo list --no-color`.
    """
    p.add_argument('--color', choices=['auto', 'always', 'never'], dest='couleur', default=argparse.SUPPRESS,
                   help="Couleurs : auto (défaut : seulement dans un terminal, sauf si NO_COLOR est défini), always, never")
    p.add_argument('--no-color', action='store_const', const='never', dest='couleur', default=argparse.SUPPRESS,
                   help="Désactive les couleurs (équivaut à --color never)")
    p.add_argument('--log-level', choices=['off', 'error', 'warning', 'info', 'debug'], dest='niveau_log',
                   default=argparse.SUPPRESS, help="Niveau du journal pour cette commande (défaut : info, ou [log] level)")
    p.add_argument('-p', '--project', dest='projet', metavar='PROJET', default=argparse.SUPPRESS,
                   help="Projet (liste de tâches) à utiliser pour cette commande (prioritaire sur TODO_PROJECT et [general] project ; "
                        "`todo project list` les liste)").completer = _completer_projets
    p.add_argument('--config', dest='fichier_config', metavar='FICHIER', default=argparse.SUPPRESS,
                   help="Fichier de configuration à utiliser à la place de celui par défaut (prioritaire sur TODO_CONFIG) ; "
                        "à écrire en toutes lettres")


def _args_add(p):
    p.add_argument('titre', type=str,
                            help="Titre ; saisie rapide : 'Appeler Paul demain !high #pro ~weekly' (voir --literal)")
    p.add_argument('--desc', type=str, default="", help='Notes explicatives complémentaires')
    p.add_argument('--prio', choices=list(PRIORITES), default=None, help='Gravité / Priorité (défaut : medium, ou [add] priority)')
    p.add_argument('--due', type=str, default=None,
                            help="Échéance : AAAA-MM-JJ, aujourd'hui, demain, apres-demain, +3d/+2w/+1m/+1y ou un jour (lundi...)")
    p.add_argument('--tags', type=str, default=None, help='Tags catégoriels indexés (ex: pro,dev)')
    p.add_argument('--after', type=str, default=None, metavar='IDS',
                   help="Tâche(s) à terminer d'abord (identifiants ou préfixes, séparés par des virgules) : elle n'apparaît pas dans `next` tant qu'elles sont à faire")
    p.add_argument('--repeat', type=str, default=None,
                            help="Tâche récurrente : daily, weekly, monthly, yearly ou 3d/2w/1m/1y (échéance = aujourd'hui si --due absent)")

    p.add_argument('--literal', action='store_true',
                            help="Garde le titre tel quel : désactive la saisie rapide (dates, !priorité, #tags, ~récurrence)")


def _ajouter_tous_projets(p):
    p.add_argument('--all-projects', dest='tous_projets', action='store_true',
                   help="Porte sur tous les projets (lecture seule) ; chaque tâche indique son projet. "
                        "Les identifiants affichés s'utilisent ensuite avec -p PROJET")


def _args_list(p):
    _ajouter_tous_projets(p)
    p.add_argument('--status', choices=['todo', 'done'], help="Filtrer selon l'avancement")
    p.add_argument('--search', type=str, help='Recherche plein texte (titre, description, tags, notes), sans tenir compte des accents ni de la casse')
    p.add_argument('--search-in', type=_champs_recherche, default=None, metavar='CHAMPS', help=_AIDE_SEARCH_IN)
    _args_filtres_selection(p)
    g = p.add_mutually_exclusive_group()
    g.add_argument('--blocked', action='store_true', help="Seulement les tâches à faire qui attendent une dépendance (--after)")
    g.add_argument('--ready', action='store_true', help="Seulement les tâches à faire qui ne sont pas bloquées")
    p.add_argument('--no-due', action='store_true', help="Seulement les tâches sans échéance")
    _args_filtres_notes(p)
    _args_filtres_fin(p)
    p.add_argument('--overdue', action='store_true', help="Tâches à faire dont l'échéance est dépassée")
    p.add_argument('--today', action='store_true', help="Tâches à faire dont l'échéance est aujourd'hui (avec --overdue : l'un ou l'autre)")
    p.add_argument('--overdue-first', action=argparse.BooleanOptionalAction, default=None,
                             help="Place (--overdue-first, défaut) ou non (--no-overdue-first) les tâches en retard en premier ; "
                                  "sans, l'ordre de --sort s'applique à toute la liste. Réglage : [list] overdue_first")
    p.add_argument('--due-before', type=str, default=None, metavar='DATE',
                             help="Échéance au plus tard à cette date, incluse (AAAA-MM-JJ, demain, +7d, vendredi...). "
                                  "Exclut les tâches sans échéance et les terminées (sauf avec --status done)")
    p.add_argument('--due-after', type=str, default=None, metavar='DATE',
                             help="Échéance à partir de cette date, incluse (mêmes formats que --due-before)")
    p.add_argument('--limit', type=_entier_positif, default=None, metavar='N',
                             help="N'afficher que N tâches (après filtres et tris). Réglage : [list] limit")
    p.add_argument('--start', type=_entier_positif, default=None, metavar='N',
                             help="Commencer à la tâche n°N de la liste (la numérotation affichée commence à 1)")
    p.add_argument('--pager', action=argparse.BooleanOptionalAction, default=None,
                             help="Utilise (--pager) ou non (--no-pager) un pager (less) quand l'affichage dépasse l'écran. Réglage : [general] pager")
    p.add_argument('--sort', choices=['alpha', 'status', 'priority', 'due'], help='Critère de tri')
    _args_colonnes(p)
    p.add_argument('--format', choices=FORMATS, default=None, help='Structure de la sortie textuelle')



def _args_edit(p):
    p.add_argument('ids', nargs='*', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté) ; ou un filtre (voir plus bas)")
    p.add_argument('--title', type=str, default=None, help='Nouveau titre')
    p.add_argument('--desc', type=str, default=None, help='Nouvelle description (chaîne vide pour effacer)')
    p.add_argument('--prio', choices=list(PRIORITES), default=None, help='Nouvelle priorité')
    p.add_argument('--due', type=str, default=None,
                             help="Nouvelle échéance : AAAA-MM-JJ, demain, +3d, lundi... ('none' pour la supprimer)")
    p.add_argument('--tags', type=str, default=None, help="Nouveaux tags, remplace les anciens (chaîne vide pour tout effacer)")
    p.add_argument('--add-tag', type=str, default=None, metavar='TAGS', help="Ajoute ces tags (séparés par des virgules) aux tags existants")
    p.add_argument('--remove-tag', type=str, default=None, metavar='TAGS', help="Retire ces tags (séparés par des virgules) des tags existants")
    p.add_argument('-m', '--note', type=str, default=None, help="Ajoute une note à chaque tâche modifiée")
    p.add_argument('--after', type=str, default=None, metavar='IDS',
                   help="Remplace les dépendances : tâche(s) à terminer d'abord (identifiants ou préfixes, séparés par des virgules ; 'none' pour les supprimer)")
    p.add_argument('--repeat', type=str, default=None,
                             help="Nouvelle répétition : daily, weekly, monthly, yearly, 3d/2w/1m/1y ('none' pour la supprimer)")
    _args_lot(p, statut=True, prio=False)



def _args_show(p):
    p.add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    p.add_argument('--format', choices=FORMATS, default=None,
                             help="Format de sortie (json : un objet, comme un élément de `list --format json`, compatible jq)")


def _instant(valeur):
    """Type argparse de --at : instant passé (voir filtres.parser_instant)."""
    try:
        return parser_instant(valeur)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def _args_start(p):
    p.add_argument('ids', nargs='*', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté) ; ou un filtre (voir plus bas)")
    p.add_argument('--at', type=_instant, default=None, metavar='HEURE',
                   help="Instant du démarrage, pour rattraper un oubli : 14:30, hier 9:15, 2026-11-20 16:00 (défaut : maintenant ; jamais dans le futur)")
    p.add_argument('-m', '--note', type=str, default=None, help="Ajoute une note à chaque tâche démarrée")
    _args_lot(p)


def _args_unstart(p):
    p.add_argument('ids', nargs='*', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté) ; ou un filtre (voir plus bas)")
    p.add_argument('-m', '--note', type=str, default=None, help="Ajoute une note à chaque tâche dont le démarrage est annulé")
    _args_lot(p, statut=True)


def _args_undone(p):
    p.add_argument('ids', nargs='*', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté) ; ou un filtre (voir plus bas)")
    p.add_argument('-m', '--note', type=str, default=None, help="Ajoute une note à chaque tâche rouverte")
    _args_lot(p)


def _args_export(p):
    p.add_argument('fichier', nargs='?', default=None,
                               help="Fichier à écrire ; sans argument ou `-` : sortie standard (pour jq ou une redirection)")
    p.add_argument('--no-archive', action='store_true', help="Ne pas exporter l'archive")
    p.add_argument('--force', action='store_true', help="Remplacer le fichier s'il existe déjà")


def _args_import(p):
    p.add_argument('fichier', help="Fichier JSON à lire ; `-` : entrée standard")
    mode_import = p.add_mutually_exclusive_group()
    mode_import.add_argument('--update', action='store_true',
                             help="Si l'identifiant existe déjà, le contenu du fichier remplace la tâche (défaut : elle est ignorée)")
    mode_import.add_argument('--replace', action='store_true', help="Vide la liste et l'archive avant d'importer (confirmation demandée)")
    p.add_argument('--dry-run', action='store_true', help="Indique ce qui serait importé, sans rien modifier")
    p.add_argument('-y', '--yes', action='store_true', help="Ne pas demander de confirmation (avec --replace)")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format du bilan (json : compatible jq)")



def _args_restore(p):
    p.add_argument('backup', type=str, nargs='?', default=None,
                                help="Numéro (1 = la plus récente) ou préfixe d'horodatage ; sans argument : liste les sauvegardes")
    p.add_argument('-y', '--yes', action='store_true', help='Ne pas demander de confirmation')



def _args_done(p):
    p.add_argument('ids', nargs='*', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté) ; ou un filtre (voir plus bas)")
    p.add_argument('-m', '--note', type=str, default=None, help="Ajoute une note à chaque tâche clôturée")
    _args_lot(p)


def _args_move(p):
    p.add_argument('ids', nargs='*', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté) ; ou un filtre (voir plus bas)")
    p.add_argument('--to', dest='vers', required=True, metavar='PROJET', type=str,
                   help="Projet de destination (il doit exister : `todo project create`)").completer = _completer_projets
    _args_lot(p, statut=True)


def _args_remove(p):
    p.add_argument('ids', nargs='*', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté) ; ou un filtre (voir plus bas)")
    p.add_argument('-m', '--note', type=str, default=None,
                               help="Motif de la suppression : la tâche disparaît, il est écrit au journal (avec le titre)")
    _args_lot(p, statut=True)


def _args_postpone(p):
    p.add_argument('ids', nargs='*', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté) ; ou un filtre (voir plus bas)")
    p.add_argument('-m', '--note', type=str, default=None, help="Ajoute une note à chaque tâche reportée")
    p.add_argument('--to', type=str, default='+1d', metavar='DATE',
                                 help="Nouvelle échéance (défaut : +1d). +2d / +1w / +1m / +1y : décalage depuis l'échéance actuelle, "
                                      "ou depuis aujourd'hui si elle est dépassée ou absente ; ou date fixe : AAAA-MM-JJ, demain, lundi...")
    _args_lot(p)


def _args_seed(p):
    p.add_argument('count', type=int, nargs='?', default=5, help='Quantité')


def _args_agenda(p):
    _ajouter_tous_projets(p)
    p.add_argument('--days', type=_entier_positif, default=None, metavar='N',
                               help='Nombre de jours affichés (défaut : 7, ou [agenda] days)')
    p.add_argument('--from', dest='depuis', type=str, default=None, metavar='DATE',
                               help="Premier jour affiché (défaut : aujourd'hui ; mêmes formats que --due)")
    p.add_argument('--pager', action=argparse.BooleanOptionalAction, default=None,
                               help="Utilise (--pager) ou non (--no-pager) un pager (less) quand l'affichage dépasse l'écran. Réglage : [general] pager")
    p.add_argument('--format', choices=FORMATS, default=None, help='Format de sortie')


def _args_next(p):
    _ajouter_tous_projets(p)
    p.add_argument('-n', '--count', type=_entier_positif, default=None, metavar='N',
                             help='Nombre de tâches affichées (défaut : 1, ou [next] count)')
    p.add_argument('--tag', type=str, default=None, help='Ne considérer que les tâches portant ce tag')
    p.add_argument('--prio', choices=list(PRIORITES), default=None, help='Ne considérer que cette priorité')
    _args_colonnes(p)
    p.add_argument('--format', choices=FORMATS, default=None, help='Format de sortie')


def _args_remind(p):
    p.add_argument('--limit', type=_entier_positif, default=None, metavar='N',
                               help='Nombre maximal de tâches listées (défaut : 5, ou [remind] limit)')
    p.add_argument('--soon', type=_entier_positif, default=None, metavar='N',
                               help="Signale aussi les échéances des N prochains jours (défaut : retards et aujourd'hui seulement, ou [remind] soon)")
    p.add_argument('--once-a-day', action='store_true',
                               help="N'affiche le rappel qu'une fois par jour (le premier terminal de la journée)")
    action = p.add_mutually_exclusive_group()
    action.add_argument('--write-status', action='store_true',
                        help="N'affiche rien : met à jour le résumé d'une ligne lu par l'invite du shell (pour cron)")
    action.add_argument('--disable', action='store_true', help='Désactive les rappels (remind et --write-status deviennent muets)')
    action.add_argument('--enable', action='store_true', help='Réactive les rappels')
    action.add_argument('--status', action='store_true', help='Indique si les rappels sont activés')
    p.add_argument('--format', choices=FORMATS, default=None,
                               help="Format de sortie : json émet toujours un document (même sans rien à signaler), "
                                    "sans limite de tâches ; avec --enable, --disable ou --status, il décrit l'état des rappels")


def _args_unarchive(p):
    p.add_argument('ids', nargs='+', help="Identifiants (ou préfixes) des tâches archivées à récupérer")


def _args_sortie_rapport(p):
    _ajouter_tous_projets(p)
    p.add_argument('--pager', action=argparse.BooleanOptionalAction, default=None,
                   help="Utilise (--pager) ou non (--no-pager) un pager (less) quand l'affichage dépasse l'écran. Réglage : [general] pager")
    p.add_argument('--format', choices=FORMATS, default=None, help='Format de sortie (voir `todo --help`)')


def _args_rapport_tags(p):
    p.add_argument('--with-archive', action='store_true', help='Compter aussi les tâches archivées')
    p.add_argument('--sort', choices=['count', 'alpha'], default='count',
                   help="Ordre : nombre de tâches décroissant (count, défaut) ou alphabétique (alpha)")
    _args_sortie_rapport(p)


def _args_rapport_stale(p):
    p.add_argument('--older-than', type=str, default='30d', metavar='DURÉE',
                   help="Créées il y a au moins cette durée : 30d (défaut), 2w, 6m, 1y, hier ou AAAA-MM-JJ")
    _args_sortie_rapport(p)


def _args_rapport_done(p):
    p.add_argument('--since', type=str, default='7d', metavar='DATE',
                   help="Terminées à partir de cette date, incluse (défaut : 7d) : 7d, 2w, 1m, 1y, hier, aujourd'hui ou AAAA-MM-JJ")
    p.add_argument('--until', type=str, default=None, metavar='DATE',
                   help="Terminées au plus tard à cette date, incluse (défaut : aujourd'hui ; mêmes formats que --since)")
    p.add_argument('--with-archive', action='store_true', help='Inclure les tâches archivées')
    _args_sortie_rapport(p)


def _args_rapport_active(p):
    _args_sortie_rapport(p)


def _args_rapport_cycle(p):
    p.add_argument('--since', type=str, default='30d', metavar='DATE',
                   help="Terminées à partir de cette date, incluse (défaut : 30d) : 7d, 2w, 1m, 1y, hier, aujourd'hui ou AAAA-MM-JJ")
    p.add_argument('--until', type=str, default=None, metavar='DATE',
                   help="Terminées au plus tard à cette date, incluse (défaut : aujourd'hui ; mêmes formats que --since)")
    p.add_argument('--by', choices=['tag', 'prio'], default=None, help="Regroupe par tag (une tâche compte pour chacun de ses tags) ou par priorité")
    p.add_argument('--with-archive', action='store_true', help='Inclure les tâches archivées')
    _args_sortie_rapport(p)


def _args_stats(p):
    _ajouter_tous_projets(p)
    p.add_argument('--with-archive', action='store_true', help='Compter aussi les tâches archivées')
    p.add_argument('--format', choices=FORMATS, default=None, help='Format de sortie (voir `todo --help`)')


def _args_reset(p):
    p.add_argument('--include-archive', action='store_true',
                              help="Vide aussi l'archive (par défaut, reset ne touche qu'à la liste)")


def _args_undo(p):
    pass


def _completer_cles(prefix, parsed_args, **kwargs):
    """Complétion de `config get|set|unset CLE` : toutes les clés ; pour unset, celles écrites dans le fichier."""
    action = getattr(parsed_args, 'action', None)
    if action in ('get', 'set'):
        return reglages.cles()
    if action == 'unset':
        ecrits = reglages._charger_fichier()
        return [f"{s}.{c}" for (s, c) in ecrits]
    return []


def _completer_valeurs(prefix, parsed_args, **kwargs):
    """Complétion de `config set CLE VALEUR` : les choix du réglage, true/false, ou des fichiers pour un chemin."""
    if getattr(parsed_args, 'action', None) != 'set' or not getattr(parsed_args, 'cle', None):
        return []
    try:
        r = reglages.trouver(parsed_args.cle)
    except ValueError:
        return []
    if r.type == 'choix':
        return list(r.choix)
    if r.type == 'bool':
        return ['true', 'false']
    if r.type == 'chemin':
        from argcomplete.completers import FilesCompleter
        return FilesCompleter()(prefix=prefix, **kwargs)
    return []


def _args_config(p):
    p.add_argument('action', nargs='?', choices=['show', 'list', 'path', 'init', 'get', 'set', 'unset'], default='show',
                   help="show (ou list) : valeurs effectives et leur origine (défaut) ; path : chemin du fichier ; "
                        "init : crée un fichier modèle commenté ; get CLE : valeur effective d'un réglage ; "
                        "set CLE VALEUR : l'écrit dans le fichier ; unset CLE : le retire du fichier")
    p.add_argument('cle', nargs='?', default=None, metavar='CLE',
                   help="get, set, unset : réglage, sous la forme section.clé (list.limit)").completer = _completer_cles
    p.add_argument('valeur', nargs='?', default=None, metavar='VALEUR', help="set : nouvelle valeur").completer = _completer_valeurs
    p.add_argument('--file', action='store_true', help="get : valeur écrite dans le fichier de configuration, sans tenir compte de l'environnement ni des défauts")
    p.add_argument('--force', action='store_true', help="init : remplace un fichier existant")
    p.add_argument('--format', choices=FORMATS, default=None, help='Format de sortie (json : compatible jq, pour show, path et init)')


# --- Groupe ``project`` -------------------------------------------------------------------------------------------
def _args_projet_nom(p):
    p.add_argument('nom', type=str, metavar='NOM', help="Nom du projet (minuscules, chiffres, - et _)").completer = _completer_projets
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")

def _args_projet_renommer(p):
    p.add_argument('ancien', type=str, metavar='ANCIEN', help="Projet à renommer").completer = _completer_projets
    p.add_argument('nouveau', type=str, metavar='NOUVEAU', help="Nouveau nom")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")

def _args_projet_supprimer(p):
    _args_projet_nom(p)
    p.add_argument('--force', action='store_true', help="Supprime aussi un projet qui contient des tâches (déplacé dans la corbeille)")
    p.add_argument('-y', '--yes', action='store_true', help="Ne pas demander de confirmation")


# --- Groupes ``note``, ``archive`` et ``reminder`` : une feuille par action -------------------------------------
def _args_note_ajouter(p):
    p.add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    p.add_argument('texte', nargs='+', help="Texte de la note (500 caractères au plus)")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")

def _args_note_lister(p):
    p.add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")

def _args_note_modifier(p):
    p.add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    p.add_argument('edit', type=int, metavar='N', help="Numéro de la note (voir `todo note list ID`)")
    p.add_argument('texte', nargs='+', help="Nouveau texte (la date de la note est conservée)")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")

def _args_note_supprimer(p):
    p.add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    p.add_argument('delete', type=int, metavar='N', help="Numéro de la note à supprimer (numérotées de 1, la plus ancienne)")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")

# --- Groupe ``attachment`` : fichiers joints aux tâches ------------------------------------------------------------
def _args_pj_ajouter(p):
    p.add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    p.add_argument('fichiers', nargs='+', metavar='FICHIER', help="Fichier(s) à copier dans le stockage de la tâche")
    p.add_argument('--comment', type=str, default=None, help="Commentaire de la pièce (200 caractères au plus)")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")

def _args_pj_lister(p):
    p.add_argument('id', type=str, nargs='?', default=None, help="UUID de la tâche (préfixe unique accepté) ; sans identifiant : toutes les tâches qui ont des pièces")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")

def _args_pj_numero(p):
    p.add_argument('id', type=str, help="UUID cible (préfixe unique accepté)")
    p.add_argument('numero', type=int, metavar='N', help="Numéro de la pièce (voir `todo attachment list ID`)")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")

def _args_pj_extraire(p):
    _args_pj_numero(p)
    p.add_argument('--to', dest='vers', type=str, default=None, metavar='DOSSIER', help="Dossier de destination (défaut : le dossier courant)")
    p.add_argument('--force', action='store_true', help="Écrase un fichier existant")

def _args_pj_gc(p):
    p.add_argument('--older-than', dest='anciennete', type=str, default=None, metavar='DUREE',
                   help="Ne supprime que ce qui est en corbeille depuis au moins cette durée (30d, 2w, 6m, 1y)")
    p.add_argument('-y', '--yes', action='store_true', help="Ne pas demander de confirmation")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")


def _args_archive_ajouter(p):
    p.add_argument('ids', nargs='*', help='Identifiants (ou préfixes) de tâches terminées à archiver ; sans identifiant : toutes les tâches terminées')
    p.add_argument('--older-than', dest='anciennete', type=str, default=None, metavar='DUREE',
                   help='Ne retient que les tâches terminées depuis au moins cette durée (30d, 2w, 6m, 1y)')
    p.add_argument('--tag', dest='tags_archive', action='append', default=None, metavar='TAGS',
                   help="Archive les tâches terminées portant ce tag (répétable ou séparé par des virgules : tous les tags) ; "
                        "les tâches à faire portant ce tag restent en place")

def _args_archive_lister(p):
    p.add_argument('--search', type=str, default=None, help="Recherche dans l'archive (titre, description, tags, notes), sans accents ni casse")
    p.add_argument('--search-in', type=_champs_recherche, default=None, metavar='CHAMPS', help=_AIDE_SEARCH_IN)
    _args_archive_filtres(p)
    p.add_argument('--pager', action=argparse.BooleanOptionalAction, default=None,
                   help="Utilise (--pager) ou non (--no-pager) un pager (less) quand l'affichage dépasse l'écran. Réglage : [general] pager")
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie")

def _args_archive_purger(p):
    p.add_argument('ids', nargs='*', help="Identifiants (ou préfixes) à supprimer de l'archive ; sans identifiant : toute l'archive (ou --older-than)")
    p.add_argument('--older-than', dest='anciennete', type=str, default=None, metavar='DUREE',
                   help='Ne retient que les tâches terminées depuis au moins cette durée (30d, 2w, 6m, 1y)')
    p.add_argument('-y', '--yes', action='store_true', help="Ne pas demander de confirmation")

def _args_format(p):
    p.add_argument('--format', choices=FORMATS, default=None, help="Format de sortie (json : compatible jq)")


_RAPPEL_DEFAUTS = dict(limit=None, soon=None, once_a_day=False, write_status=False, disable=False, enable=False, status=False)
_ARCHIVE_DEFAUTS = dict(ids=[], anciennete=None, tags_archive=None, purge=False, lister=False, search=None, search_in=None, yes=False, pager=None, format=None,
                     tag=None, any_tag=None, no_tag=False, not_tag=None, prio=None, not_prio=None, recurring=False,
                     no_recurring=False, created_after=None, created_before=None, filtre_id=None, has_notes=False, no_notes=False, has_files=False, no_files=False, started=False, not_started=False, done_after=None, done_before=None,
                     archived_after=None, archived_before=None, sort=None, limit=None, start=None, columns=None)

# (groupe, aide, [(verbe, canon, constructeur, aide, valeurs par défaut)])
_GROUPES = [
    ('task', "Créer, consulter et faire avancer les tâches", [
        ('add', 'add', _args_add, 'Créer une nouvelle tâche', {}),
        ('list', 'list', _args_list, 'Afficher et filtrer les tâches', {}),
        ('show', 'show', _args_show, "Afficher le détail complet d'une tâche", {}),
        ('edit', 'edit', _args_edit, 'Modifier une tâche', {}),
        ('done', 'done', _args_done, 'Clôturer une ou plusieurs tâches', {}),
        ('start', 'start', _args_start, "Noter le démarrage d'une ou plusieurs tâches (plusieurs peuvent être en cours)", {}),
        ('unstart', 'unstart', _args_unstart, "Annuler le démarrage d'une ou plusieurs tâches", {}),
        ('undone', 'undone', _args_undone, 'Rouvrir une tâche terminée', {}),
        ('remove', 'remove', _args_remove, 'Supprimer une ou plusieurs tâches', {}),
        ('move', 'move', _args_move, 'Déplacer une ou plusieurs tâches vers un autre projet', {}),
        ('postpone', 'postpone', _args_postpone, "Reporter l'échéance d'une ou plusieurs tâches", {}),
        ('next', 'next', _args_next, 'Afficher la ou les prochaines tâches à traiter', {}),
    ]),
    ('note', "Notes attachées aux tâches", [
        ('add', 'note', _args_note_ajouter, 'Ajouter une note à une tâche', dict(edit=None, delete=None, format=None)),
        ('list', 'note', _args_note_lister, "Lister les notes d'une tâche", dict(texte=[], edit=None, delete=None)),
        ('edit', 'note', _args_note_modifier, "Remplacer le texte d'une note", dict(delete=None, format=None)),
        ('delete', 'note', _args_note_supprimer, 'Supprimer une note', dict(texte=[], edit=None, format=None)),
    ]),
    ('attachment', "Pièces jointes des tâches (fichiers copiés dans le stockage)", [
        ('add', 'attachment_add', _args_pj_ajouter, 'Joindre un ou plusieurs fichiers à une tâche', {}),
        ('list', 'attachment_list', _args_pj_lister, "Lister les pièces jointes d'une tâche (ou de toutes)", {}),
        ('open', 'attachment_open', _args_pj_numero, 'Ouvrir une pièce jointe (ou afficher son chemin sans session graphique)', {}),
        ('save', 'attachment_save', _args_pj_extraire, 'Copier une pièce jointe dans un dossier', {}),
        ('remove', 'attachment_remove', _args_pj_numero, 'Détacher une pièce jointe (fichier mis en corbeille)', {}),
        ('gc', 'attachment_gc', _args_pj_gc, 'Vider la corbeille des pièces jointes (définitif)', {}),
    ]),
    ('archive', "Archive des tâches terminées", [
        ('add', 'archive', _args_archive_ajouter, 'Archiver les tâches terminées', _ARCHIVE_DEFAUTS),
        ('list', 'archive', _args_archive_lister, "Consulter l'archive", {**_ARCHIVE_DEFAUTS, 'lister': True}),
        ('purge', 'archive', _args_archive_purger, "Supprimer DÉFINITIVEMENT des tâches de l'archive", {**_ARCHIVE_DEFAUTS, 'purge': True}),
        ('restore', 'unarchive', _args_unarchive, "Remettre des tâches archivées dans la liste", {}),
    ]),
    ('reminder', "Rappels des tâches en retard (invite du shell, cron)", [
        ('check', 'remind', _args_remind, "Rappeler les tâches en retard (silencieux s'il n'y en a pas)", {}),
        ('enable', 'remind', _args_format, 'Réactiver les rappels', {**_RAPPEL_DEFAUTS, 'enable': True}),
        ('disable', 'remind', _args_format, 'Désactiver les rappels', {**_RAPPEL_DEFAUTS, 'disable': True}),
        ('status', 'remind', _args_format, 'Indiquer si les rappels sont activés', {**_RAPPEL_DEFAUTS, 'status': True}),
    ]),
    ('project', "Projets : listes de tâches indépendantes (perso, travail…)", [
        ('current', 'project_current', _args_format, 'Indiquer le projet courant et son origine', {}),
        ('list', 'project_list', _args_format, 'Lister les projets et leurs compteurs', {}),
        ('create', 'project_create', _args_projet_nom, 'Créer un projet', {}),
        ('use', 'project_use', _args_projet_nom, 'Choisir le projet courant (écrit [general] project)', {}),
        ('rename', 'project_rename', _args_projet_renommer, 'Renommer un projet', {}),
        ('delete', 'project_delete', _args_projet_supprimer, 'Supprimer un projet (déplacé dans la corbeille)', {}),
    ]),
    ('report', "Vues d'ensemble", [
        ('stats', 'stats', _args_stats, 'Tableau de bord des indicateurs', {}),
        ('agenda', 'agenda', _args_agenda, 'Tâches à faire jour par jour', {}),
        ('tags', 'report_tags', _args_rapport_tags, 'Tags utilisés, avec le nombre de tâches', {}),
        ('blocked', 'report_blocked', _args_sortie_rapport, 'Tâches bloquées par une dépendance, et ce qu\'elles attendent', {}),
        ('overdue', 'report_overdue', _args_sortie_rapport, 'Tâches en retard, les plus en retard d\'abord', {}),
        ('stale', 'report_stale', _args_rapport_stale, 'Tâches sans échéance qui traînent depuis longtemps', {}),
        ('done', 'report_done', _args_rapport_done, 'Bilan des tâches terminées sur une période', {}),
        ('active', 'report_active', _args_rapport_active, 'Tâches en cours (démarrées, pas terminées) et temps écoulé', {}),
        ('cycle', 'report_cycle', _args_rapport_cycle, 'Délai démarrage → fin des tâches terminées', {}),
    ]),
    ('admin', "Maintenance de la base", [
        ('undo', 'undo', _args_undo, "Annuler la dernière modification (un second 'undo' la rétablit)", {}),
        ('restore', 'restore', _args_restore, "Lister les sauvegardes ou restaurer l'une d'elles", {}),
        ('reset', 'reset', _args_reset, 'Détruire le contenu de la base', {}),
        ('seed', 'seed', _args_seed, 'Remplir la base avec de faux enregistrements', {}),
    ]),
    ('data', "Échange de données JSON", [
        ('export', 'export', _args_export, 'Exporter les tâches (et l\'archive) en JSON', {}),
        ('import', 'import', _args_import, 'Importer des tâches depuis un fichier JSON', {}),
    ]),
]
# Raccourcis de premier niveau (même syntaxe que dans le groupe) : nom -> (groupe, verbe)
_RACCOURCIS = {'add': 'task', 'list': 'task', 'show': 'task', 'done': 'task', 'next': 'task',
               'agenda': 'report', 'undo': 'admin'}
_VERBES = {g: {v[0] for v in verbes} for g, _, verbes in _GROUPES}
_OPTIONS_A_VALEUR = {'--color', '--log-level', '--config', '--project', '-p'}


def _mots(argv):
    """Mots de la commande (options globales ignorées) : ['archive', 'list', ...]."""
    mots, saute = [], False
    for a in argv:
        if saute:
            saute = False
        elif a in _OPTIONS_A_VALEUR:
            saute = True
        elif not a.startswith('-'):
            mots.append(a)
    return mots


# Commandes de la syntaxe 1.x, supprimées en 3.0 : nom -> ce qui les remplace (pour le message d'erreur)
_SUPPRIMEES = {
    'edit': 'task edit', 'undone': 'task undone', 'remove': 'task remove', 'postpone': 'task postpone',
    'note': 'note add|list|edit|delete',
    'archive': 'archive add|list|purge', 'unarchive': 'archive restore',
    'remind': 'reminder check|enable|disable|status',
    'stats': 'report stats', 'reset': 'admin reset', 'restore': 'admin restore', 'seed': 'admin seed',
    'export': 'data export', 'import': 'data import',
}


def _syntaxe_supprimee(mots):
    """Vrai si la ligne de commande utilise la syntaxe 1.x (plate), supprimée en 3.0, plutôt que les groupes."""
    if not mots:
        return False
    if mots[0] == 'archive':
        return len(mots) == 1 or mots[1] not in _VERBES['archive']
    if mots[0] == 'note':
        return len(mots) > 1 and mots[1] not in _VERBES['note']
    return mots[0] in _SUPPRIMEES


def _refuser_syntaxe_supprimee(nom):
    """Erreur d'usage (code 2) qui indique la commande actuelle équivalente ; rien n'est exécuté."""
    journal.echec("removed_command", command=nom)
    print(f"todo : la commande `todo {nom}` a été supprimée en 3.0 : utilisez `todo {_SUPPRIMEES[nom]}` "
          f"(table de correspondance : « Migration depuis la 2.x » dans le CHANGELOG).", file=sys.stderr)
    sys.exit(2)


def _commande_visee(mots):
    """Nom de commande (vocabulaire du journal) deviné avant l'analyse, pour tracer aussi les erreurs d'usage."""
    if not mots:
        return None
    if mots[0] in _RACCOURCIS:
        return mots[0]
    for groupe, _, verbes in _GROUPES:
        if mots[0] == groupe and len(mots) > 1:
            return next((v[1] for v in verbes if v[0] == mots[1]), None)
    return mots[0] if mots[0] == 'config' else None


def _construire():
    """Construit le parseur : arbre de groupes (task, note, archive, reminder, project, report, admin, data) et raccourcis."""
    parser = _Parseur(description="Gestionnaire de tâches (To-Do List) CLI avancé et persistant.",
                      epilog="Formats de sortie (--format, réglage [general] format, variable TODO_FORMAT) : "
                             "text (affichage décoré), table (tableau aligné), plain (une ligne par enregistrement, "
                             "champs séparés par des tabulations, pour grep/cut/awk), json (compatible jq). "
                             "Par défaut (auto) : text dans un terminal, plain dans un pipe.")
    parser.add_argument('--version', action='version', version=f"todo {__version__}")
    tous = [parser]
    sub = parser.add_subparsers(dest="groupe", metavar="COMMANDE", help="Groupes de commandes et raccourcis")

    def feuille(parent, nom, constructeur, canon, aide, defauts=None):
        p = parent.add_parser(nom, help=aide, description=aide if aide != argparse.SUPPRESS else None)
        constructeur(p)
        p.set_defaults(canon=canon, **(defauts or {}))
        tous.append(p)
        return p

    for groupe, aide, verbes in _GROUPES:
        g = sub.add_parser(groupe, help=aide, description=aide)
        tous.append(g)
        sg = g.add_subparsers(dest="verbe", metavar="ACTION", required=True)
        for verbe, canon, constructeur, aide_v, defauts in verbes:
            feuille(sg, verbe, constructeur, canon, aide_v, defauts)
    for nom, groupe in _RACCOURCIS.items():
        ligne = next(v for g, _, vs in _GROUPES if g == groupe for v in vs if v[0] == nom)
        feuille(sub, nom, ligne[2], ligne[1], f"Raccourci de `{groupe} {nom}` : {ligne[3]}", ligne[4])
    feuille(sub, 'config', _args_config, 'config', 'Voir les réglages effectifs ou créer un fichier de configuration')
    for p in tous:
        _ajouter_options_couleur(p)
    return parser


def _completer_ligne():
    """Réponse à une demande de complétion du shell (variable `_ARGCOMPLETE`, posée par argcomplete).

    Appuyer sur Tab ne doit jamais produire d'erreur ni de trace, ni écrire dans le journal ou les logs :
    le journal est coupé, les avertissements de configuration sont tus (voir `reglages`), et toute exception
    est avalée (la complétion est alors simplement vide). `_ARC_DEBUG=1` affiche la trace pour comprendre.
    """
    journal.desactiver()
    try:
        import argcomplete
        argcomplete.autocomplete(_construire())
    except BaseException:
        if os.environ.get('_ARC_DEBUG'):
            import traceback
            traceback.print_exc()
    sys.exit(0)


# Commandes qui ne déclenchent pas l'archivage automatique (elles gèrent déjà l'archive ou l'historique)
_SANS_ARCHIVAGE_AUTO = ('archive', 'unarchive', 'undo', 'restore', 'reset', 'import', 'seed', 'project_rename', 'project_delete', 'attachment_gc')


def _mode_verrou(args):
    """Verrou à prendre sur la base : None (rien), PARTAGE (lecture) ou EXCLUSIF (écriture)."""
    c = args.commande
    if c == 'config' or c in ('project_current', 'project_list', 'project_create', 'project_use'):
        return None
    if c in ('project_rename', 'project_delete'):
        return verrou.EXCLUSIF         # sur le projet visé (voir main)
    if c in ('list', 'show', 'next', 'agenda', 'stats', 'export', 'remind', 'report_tags', 'report_blocked', 'report_overdue',
             'report_stale', 'report_done', 'report_active', 'report_cycle', 'attachment_list', 'attachment_open', 'attachment_save'):
        return verrou.PARTAGE
    if c == 'archive' and (args.lister or args.search is not None):
        return verrou.PARTAGE
    if c == 'note' and not args.texte and args.edit is None and args.delete is None:
        return verrou.PARTAGE
    if c == 'import' and args.dry_run:
        return verrou.PARTAGE
    if c in ('done', 'undone', 'postpone', 'remove', 'edit', 'start', 'unstart') and args.dry_run:
        return verrou.PARTAGE          # simulation : ne modifie rien (ni archivage automatique)
    return verrou.EXCLUSIF


def _lecture_transverse(args, option):
    """Active la lecture de tous les projets : `--all-projects`, ou le rappel quand aucun projet n'est désigné par --project.

    Le rappel couvre tous les projets par défaut (même si un projet courant est choisi) : il sert à ne rien oublier.
    """
    if getattr(args, 'tous_projets', False):
        if option is not None:
            journal.echec("invalid_combination")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --all-projects ne se combine pas avec --project.", file=sys.stderr)
            sys.exit(1)
        stockage.definir_tous_projets(True)
        return True
    if args.commande == 'remind' and option is None:
        stockage.definir_tous_projets(True, etiqueter=len(config.projets()) > 1)
        return True
    return False


def _choisir_projet(args):
    """Fixe le projet de la commande (option > TODO_PROJECT > fichier > default) et refuse un projet inexistant.

    Seul le groupe `project` s'accommode d'un projet courant inexistant (il sert justement à le créer ou à en changer).
    """
    option = getattr(args, 'projet', None)
    if option is not None:
        try:
            config.definir_projet(config.valider_nom(option), "option")
        except ValueError as e:
            journal.echec("invalid_project_name", projet=option)
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} {e} (option --project).", file=sys.stderr)
            sys.exit(1)
    nom = config.projet()
    journal.definir_projet(nom)
    transverse = _lecture_transverse(args, option)
    if not str(args.commande).startswith('project_') and not transverse and not config.existe(nom):
        proche = difflib.get_close_matches(nom, config.projets(), n=1)
        journal.echec("unknown_project", projet=nom)
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} le projet '{nom}' n'existe pas ({projets._origine_lisible(config.origine_projet())})"
              + (f" ; vouliez-vous dire '{proche[0]}' ?" if proche else "")
              + f" `todo project create {nom}` le crée, `todo project list` les liste.", file=sys.stderr)
        sys.exit(1)


def main():
    if os.environ.get('_ARGCOMPLETE'):
        _completer_ligne()
    journal.initialiser()
    mots = _mots(sys.argv[1:])
    if _syntaxe_supprimee(mots) and not (mots == ['archive'] and {'-h', '--help'} & set(sys.argv[1:])):
        _refuser_syntaxe_supprimee(mots[0])             # `todo archive --help` décrit le groupe
    parser = _construire()

    # La commande est connue du journal avant l'analyse, pour tracer aussi les erreurs d'usage
    journal.definir_commande(_commande_visee(mots))
    args = parser.parse_args()
    args.commande = getattr(args, 'canon', None)
    if args.commande == 'config' and args.action == 'list':
        args.action = 'show'
    if args.commande == 'config':
        attendus = {'get': 1, 'unset': 1, 'set': 2}.get(args.action, 0)
        donnes = sum(v is not None for v in (args.cle, args.valeur))
        if donnes != attendus:
            parser.error({'get': "config get attend un réglage : todo config get section.clé",
                          'unset': "config unset attend un réglage : todo config unset section.clé",
                          'set': "config set attend un réglage et une valeur : todo config set section.clé valeur"}
                         .get(args.action, f"config {args.action} n'accepte pas d'argument supplémentaire"))
    explicite = getattr(args, 'fichier_config', None)
    if explicite is not None:
        reglages.definir_fichier(explicite)
        if (not os.path.isfile(reglages.chemin_config())
                and not (args.commande == 'config' and args.action in ('set', 'init', 'path'))):
            journal.echec("config_not_found", file=reglages.chemin_config())
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} fichier de configuration introuvable : "
                  f"{reglages.chemin_config()} (option --config). `todo --config FICHIER config init` le crée.", file=sys.stderr)
            sys.exit(1)
    _choisir_projet(args)
    config.preparer()               # dossier de stockage (après --config, qui peut en changer)
    journal.regler_niveau(getattr(args, 'niveau_log', None))
    couleurs._configurer_couleurs(reglages.obtenir('general', 'color', getattr(args, 'couleur', None)))
    if hasattr(args, 'format'):     # option > TODO_FORMAT > fichier > auto ; auto : text dans un terminal, plain sinon
        demande = args.format                 # valeur de --format (None si absent)
        choisi = reglages.obtenir('general', 'format', demande)
        # Les rappels (cron, e-mails, invite du shell) restent en text sauf demande explicite de plain ou table
        args.format = 'text' if (args.commande == 'remind' and choisi == 'auto') else resoudre_format(choisi)
        if getattr(args, 'columns', None):
            if demande in ('text', 'json'):
                journal.echec("invalid_combination")
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --columns s'applique aux formats table et plain, pas à {demande}.")
                sys.exit(1)
            if args.format in ('text', 'json'):     # format venu du réglage ou d'un terminal : --columns suppose un tableau
                args.format = 'table'

    mode_verrou = _mode_verrou(args)
    if args.commande in ('project_rename', 'project_delete'):
        args.courant = config.projet()            # le verrou se prend sur le projet visé, pas sur le courant
        cible = args.ancien if args.commande == 'project_rename' else args.nom
        if config._MOTIF_PROJET.match(cible) and config.existe(cible):
            config.definir_projet(cible, "option")
    if args.commande == 'move' and deplacement.cible_valide(args.vers) is None:
        noms = [n for n in config.projets() if n in (config.projet(), args.vers)]      # ordre commun : pas d'attente croisée
        verrou.prendre_projets(noms, verrou.EXCLUSIF, reglages.obtenir('general', 'lock_timeout'))
    elif mode_verrou and stockage.tous_projets():
        verrou.prendre_tous(reglages.obtenir('general', 'lock_timeout'))
    elif mode_verrou:
        verrou.prendre(mode_verrou, reglages.obtenir('general', 'lock_timeout'))
    if mode_verrou == verrou.EXCLUSIF and args.commande not in _SANS_ARCHIVAGE_AUTO:
        archivage_automatique(reglages.obtenir('archive', 'auto_days'))

    # Moteur d'aiguillage vers l'action requise.
    # `succes` passe à False si un identifiant de done / remove / postpone n'a pas pu être traité :
    # le code de sortie vaut alors 1, ce qui permet de s'en servir dans un script.
    succes = True
    if args.commande == 'add':
        titre, due, prio, tags, repeter = args.titre, args.due, args.prio, args.tags, args.repeat
        analyse = None
        if not args.literal:
            # Une option explicite est prioritaire : le marqueur équivalent reste alors dans le titre
            analyse = analyser_titre(args.titre, due=args.due is None, prio=args.prio is None,
                                     tags=args.tags is None, repeat=args.repeat is None,
                                     prefixe_obligatoire=reglages.obtenir('add', 'date_prefix') == 'required')
            if analyse["trouve"]:
                titre = analyse["titre"]
                due = analyse["due"] or due
                prio = analyse["prio"] or prio
                tags = ",".join(analyse["tags"]) or tags
                repeter = analyse["repeat"] or repeter
            else:
                analyse = None
        prio = prio or reglages.obtenir('add', 'priority')   # option > titre > variable > fichier > défaut
        ajouter_tache(titre, args.desc, prio, due, tags, repeter=repeter, apres=args.after)
        if analyse:
            compris = []
            if analyse["due"]:
                compris.append(f"échéance {_resoudre_date(analyse['due']).strftime('%Y-%m-%d')}")
            if analyse["prio"]:
                compris.append(f"priorité {analyse['prio'].upper()}")
            if analyse["tags"]:
                compris.append("tags " + " ".join(f"#{tg}" for tg in analyse["tags"]))
            if analyse["repeat"]:
                compris.append(f"répétition {analyse['repeat']}")
            print(f"    {couleurs.CLR_DIM}⚡ Compris dans le titre : {' · '.join(compris)}{couleurs.CLR_RESET}")
    elif args.commande == 'list':
        _exiger_search(args)
        if args.no_due and (args.due_before or args.due_after):
            journal.echec("invalid_combination")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --no-due ne se combine pas avec --due-before ni --due-after.")
            sys.exit(1)
        filtres = _filtres_communs(args)
        avant = _date_filtre(args.due_before, '--due-before')
        apres = _date_filtre(args.due_after, '--due-after')
        if avant is not None and apres is not None and apres > avant:
            journal.echec("empty_range")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Plage vide : --due-after ({apres}) est postérieure à --due-before ({avant}).")
            sys.exit(1)
        lister_taches(args.status, args.search, args.sort, args.format,
                      retard=args.overdue, aujourdhui=args.today,
                      retards_en_premier=reglages.obtenir('list', 'overdue_first', args.overdue_first),
                      limite=reglages.obtenir('list', 'limit', args.limit) or None, debut=args.start,
                      pager=reglages.obtenir('general', 'pager', args.pager), champs=args.search_in or CHAMPS_RECHERCHE,
                      avant=avant, apres=apres, filtres=filtres, colonnes=_colonnes_effectives(args))
    elif args.commande == 'show':
        succes = afficher_tache(args.id, args.format)
    elif args.commande == 'start':
        ids = _ids_ou_lot(args, 'todo', "démarrer", "démarrées")
        succes = demarrer_taches(ids, args.at, args.note) if ids else True
    elif args.commande == 'unstart':
        ids = _ids_ou_lot(args, None, "annuler le démarrage de", "annulées")
        succes = annuler_demarrage(ids, args.note) if ids else True
    elif args.commande == 'undone':
        ids = _ids_ou_lot(args, 'done', "rouvrir", "rouvertes")
        succes = rouvrir_tache(ids, args.note) if ids else True
    elif args.commande == 'edit':
        champs = (args.title, args.desc, args.prio, args.due, args.tags, args.repeat, args.note, args.after, args.add_tag, args.remove_tag)
        ids = args.ids if all(v is None for v in champs) else _ids_ou_lot(args, None, "modifier", "modifiées", sans_prio=True)
        if ids is not None and args.title is not None and (len(ids) > 1 or args.tout):
            _erreur_lot("invalid_combination", "--title ne s'applique qu'à une seule tâche.")
        succes = modifier_tache(ids, args.title, args.desc, args.prio, args.due, args.tags, args.repeat, args.note,
                                apres=args.after, tags_ajout=args.add_tag, tags_retrait=args.remove_tag) if ids is not None else True
    elif args.commande == 'note':
        succes = commande_note(args.id, args.texte, args.format, args.edit, args.delete)
    elif args.commande == 'attachment_add':
        succes = pieces_jointes.ajouter(args.id, args.fichiers, args.comment, args.format)
    elif args.commande == 'attachment_list':
        succes = pieces_jointes.lister(args.id, args.format)
    elif args.commande == 'attachment_open':
        succes = pieces_jointes.ouvrir(args.id, args.numero, args.format)
    elif args.commande == 'attachment_save':
        succes = pieces_jointes.extraire(args.id, args.numero, args.vers, args.force, args.format)
    elif args.commande == 'attachment_remove':
        succes = pieces_jointes.detacher(args.id, args.numero, args.format)
    elif args.commande == 'attachment_gc':
        anciennete = None
        if args.anciennete is not None:
            anciennete = _parser_anciennete(args.anciennete)
            if anciennete is None:
                journal.echec("invalid_duration")
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Durée non reconnue pour --older-than : '{args.anciennete}'. "
                      f"Format : {MSG_FORMAT_ANCIENNETE}.")
                sys.exit(1)
        succes = pieces_jointes.vider_corbeille(anciennete, not args.yes, args.format)
    elif args.commande == 'export':
        succes = exporter(args.fichier, not args.no_archive, args.force)
    elif args.commande == 'import':
        mode = 'mettre_a_jour' if args.update else ('remplacer' if args.replace else 'ajouter')
        succes = importer(args.fichier, mode, args.dry_run, not args.yes, args.format)
    elif args.commande == 'restore':
        restaurer_base(args.backup, confirmer=not args.yes)
    elif args.commande == 'done':
        ids = _ids_ou_lot(args, 'todo', "valider", "validées")
        succes = marquer_terminee(ids, args.note) if ids else True
    elif args.commande == 'remove':
        ids = _ids_ou_lot(args, None, "supprimer", "supprimées")
        succes = supprimer_tache(ids, args.note) if ids else True
    elif args.commande == 'move':
        ids = _ids_ou_lot(args, None, "déplacer", "déplacées")
        succes = deplacer_taches(ids, args.vers) if ids else True
    elif args.commande == 'postpone':
        ids = _ids_ou_lot(args, 'todo', "reporter", "reportées")
        succes = reporter_taches(ids, args.to, args.note) if ids else True
    elif args.commande == 'seed':
        peupler_fausses_taches(args.count)
    elif args.commande == 'agenda':
        if args.days is not None and args.days > 366:
            journal.echec("days_limit")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --days est limité à 366 jours.")
            sys.exit(1)
        afficher_agenda(_date_filtre(args.depuis, '--from'), reglages.obtenir('agenda', 'days', args.days), args.format,
                        pager=reglages.obtenir('general', 'pager', args.pager))
    elif args.commande == 'undo':
        succes = annuler_derniere_action()
    elif args.commande == 'next':
        afficher_prochaines(reglages.obtenir('next', 'count', args.count), args.tag, args.prio, args.format, _colonnes_effectives(args))
    elif args.commande == 'remind':
        if args.disable:
            desactiver_rappels(args.format)
        elif args.enable:
            activer_rappels(args.format)
        elif args.status:
            afficher_etat_rappels(args.format)
        elif args.once_a_day and args.write_status:
            journal.echec("invalid_combination")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --once-a-day ne s'utilise pas avec --write-status.")
            sys.exit(1)
        elif args.format == 'json' and (args.once_a_day or args.write_status):
            journal.echec("invalid_combination")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --format json ne se combine pas avec --once-a-day ni --write-status "
                  f"(le JSON est émis à chaque appel).")
            sys.exit(1)
        else:
            rappeler(reglages.obtenir('remind', 'limit', args.limit), reglages.obtenir('remind', 'soon', args.soon),
                     args.once_a_day, args.write_status, args.format)
    elif args.commande == 'archive':
        liste = args.lister or args.search is not None or _filtres_archive_actifs(args)
        if args.purge and liste:
            journal.echec("invalid_combination")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --purge ne se combine pas avec --list, --search ni les filtres de liste.")
            sys.exit(1)
        if liste:
            _exiger_search(args)
            if args.ids:
                journal.echec("invalid_combination")
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --list / --search ne se combinent pas avec des identifiants.")
                sys.exit(1)
            lister_archive(args.search, args.format, pager=reglages.obtenir('general', 'pager', args.pager),
                           champs=args.search_in or CHAMPS_RECHERCHE, filtres=_filtres_communs(args, archive=True),
                           tri=args.sort, limite=args.limit, debut=args.start, colonnes=_colonnes_effectives(args))
        else:
            tags_archive = _liste(getattr(args, 'tags_archive', None))
            if args.ids and (args.anciennete or tags_archive):
                journal.echec("invalid_combination")
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Indiquez des identifiants OU --older-than / --tag, pas les deux.")
                sys.exit(1)
            anciennete = None
            if args.anciennete is not None:
                anciennete = _parser_anciennete(args.anciennete)
                if anciennete is None:
                    journal.echec("invalid_duration")
                    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Durée non reconnue pour --older-than : '{args.anciennete}'. "
                          f"Format : {MSG_FORMAT_ANCIENNETE}.")
                    sys.exit(1)
            if args.purge:
                succes = purger_archive(args.ids or None, anciennete, not args.yes)
            else:
                succes = archiver_taches(args.ids or None, anciennete, tags=tags_archive)
    elif args.commande == 'unarchive':
        succes = desarchiver_taches(args.ids)
    elif args.commande == 'config':
        if args.action == 'path':
            afficher_chemin(args.format)
        elif args.action == 'init':
            succes = initialiser_config(args.force, args.format)
        elif args.action == 'get':
            succes = lire_reglage(args.cle, args.format, args.file)
        elif args.action == 'set':
            succes = ecrire_reglage(args.cle, args.valeur, args.format)
        elif args.action == 'unset':
            succes = retirer_reglage(args.cle, args.format)
        else:
            afficher_config(args.format)
    elif args.commande == 'stats':
        afficher_stats(args.with_archive, args.format)
    elif args.commande == 'report_tags':
        rapport_tags(args.with_archive, args.sort, args.format, pager=reglages.obtenir('general', 'pager', args.pager))
    elif args.commande == 'report_blocked':
        rapport_bloquees(args.format, pager=reglages.obtenir('general', 'pager', args.pager))
    elif args.commande == 'report_overdue':
        rapport_retards(args.format, pager=reglages.obtenir('general', 'pager', args.pager))
    elif args.commande == 'report_stale':
        avant = _date_passee(args.older_than, '--older-than')
        rapport_stagnantes(avant, args.older_than, args.format, pager=reglages.obtenir('general', 'pager', args.pager))
    elif args.commande == 'report_done':
        depuis = _date_passee(args.since, '--since')
        jusqu_a = _date_passee(args.until, '--until') or datetime.now().date()
        _plage_vide(depuis, jusqu_a, '--since', '--until')
        rapport_terminees(depuis, jusqu_a, args.with_archive, args.format, pager=reglages.obtenir('general', 'pager', args.pager))
    elif args.commande == 'report_active':
        rapport_en_cours(args.format, pager=reglages.obtenir('general', 'pager', args.pager))
    elif args.commande == 'report_cycle':
        depuis = _date_passee(args.since, '--since')
        jusqu_a = _date_passee(args.until, '--until') or datetime.now().date()
        _plage_vide(depuis, jusqu_a, '--since', '--until')
        rapport_delais(depuis, jusqu_a, args.with_archive, args.by, args.format, pager=reglages.obtenir('general', 'pager', args.pager))
    elif args.commande == 'project_current':
        succes = projets.afficher_courant(config.projet(), config.origine_projet(), args.format)
    elif args.commande == 'project_list':
        succes = projets.lister(config.projet(), args.format)
    elif args.commande == 'project_create':
        succes = projets.creer(args.nom, args.format)
    elif args.commande == 'project_use':
        succes = projets.utiliser(args.nom, args.format)
    elif args.commande == 'project_rename':
        succes = projets.renommer(args.ancien, args.nouveau, args.format)
    elif args.commande == 'project_delete':
        succes = projets.supprimer(args.nom, args.courant, args.yes, args.force, args.format)
    elif args.commande == 'reset':
        reinitialiser_base(args.include_archive)
    else:
        parser.print_help()
        sys.exit(1)

    if not succes:
        sys.exit(1)


def executer():
    """Lance `main()`, traduit Ctrl+C en code de sortie 130 et écrit le message de synthèse du journal."""
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n {couleurs.CLR_DIM}Interrompu.{couleurs.CLR_RESET}")
        journal.terminer(130)
        sys.exit(130)
    except BrokenPipeError:
        # `todo list | head` : le lecteur a fermé le tube, ce n'est pas une erreur ; stdout est redirigé vers
        # /dev/null pour que l'interpréteur ne signale pas un second échec en vidant sa sortie à l'arrêt.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        journal.terminer(0)
        sys.exit(0)
    except SystemExit as e:
        journal.terminer(e.code if isinstance(e.code, int) else (0 if e.code is None else 1))
        raise
    except Exception:
        journal.critique()
        journal.terminer(1)
        raise
    journal.terminer(0)
