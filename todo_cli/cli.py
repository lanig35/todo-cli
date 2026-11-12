"""Définition de la ligne de commande (argparse) et aiguillage vers les commandes."""
import argparse
import sys
from .agenda import afficher_agenda
from .archive import MSG_FORMAT_ANCIENNETE, _parser_anciennete, archiver_taches, desarchiver_taches, lister_archive
from .affichage import afficher_stats, afficher_tache, lister_taches
from .config import PRIORITES
from . import couleurs, reglages, journal
from .configuration import afficher_chemin, afficher_config, initialiser_config
from .dates import MSG_FORMATS_DATE, _resoudre_date
from .saisie import analyser_titre
from .prochaine import afficher_prochaines
from .rappel import activer_rappels, afficher_etat_rappels, desactiver_rappels, rappeler
from .sauvegardes import annuler_derniere_action, reinitialiser_base, restaurer_base
from .seed import peupler_fausses_taches
from .taches import ajouter_tache, marquer_terminee, modifier_tache, nettoyer_terminees, reporter_taches, rouvrir_tache, supprimer_tache


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

def main():
    journal.initialiser()
    parser = _Parseur(description="Gestionnaire de tâches (To-Do List) CLI avancé et persistant.")
    subparsers = parser.add_subparsers(dest="commande", help="Commandes système disponibles")

    # Commande 'add'
    parser_add = subparsers.add_parser('add', help='Créer et insérer une nouvelle tâche')
    parser_add.add_argument('titre', type=str,
                            help="Titre ; saisie rapide : 'Appeler Paul demain !high #pro ~weekly' (voir --literal)")
    parser_add.add_argument('--desc', type=str, default="", help='Notes explicatives complémentaires')
    parser_add.add_argument('--prio', choices=list(PRIORITES), default=None, help='Gravité / Priorité (défaut : medium, ou [add] priority)')
    parser_add.add_argument('--due', type=str, default=None,
                            help="Échéance : AAAA-MM-JJ, aujourd'hui, demain, apres-demain, +3d/+2w/+1m/+1y ou un jour (lundi...)")
    parser_add.add_argument('--tags', type=str, default=None, help='Tags catégoriels indexés (ex: pro,dev)')
    parser_add.add_argument('--repeat', type=str, default=None,
                            help="Tâche récurrente : daily, weekly, monthly, yearly ou 3d/2w/1m/1y (échéance = aujourd'hui si --due absent)")

    parser_add.add_argument('--literal', action='store_true',
                            help="Garde le titre tel quel : désactive la saisie rapide (dates, !priorité, #tags, ~récurrence)")

    # Commande 'list'
    parser_list = subparsers.add_parser('list', help='Afficher et filtrer les entrées de la base')
    parser_list.add_argument('--status', choices=['todo', 'done'], help="Filtrer selon l'avancement")
    parser_list.add_argument('--search', type=str, help='Recherche plein texte (Titre & Description)')
    parser_list.add_argument('--tag', type=str, default=None, help='Extraction par étiquette exclusive')
    parser_list.add_argument('--prio', choices=list(PRIORITES), default=None, help='Ne montrer que cette priorité')
    parser_list.add_argument('--overdue', action='store_true', help="Tâches à faire dont l'échéance est dépassée")
    parser_list.add_argument('--today', action='store_true', help="Tâches à faire dont l'échéance est aujourd'hui (avec --overdue : l'un ou l'autre)")
    parser_list.add_argument('--overdue-first', action=argparse.BooleanOptionalAction, default=None,
                             help="Place (--overdue-first, défaut) ou non (--no-overdue-first) les tâches en retard en premier ; "
                                  "sans, l'ordre de --sort s'applique à toute la liste. Réglage : [list] overdue_first")
    parser_list.add_argument('--due-before', type=str, default=None, metavar='DATE',
                             help="Échéance au plus tard à cette date, incluse (AAAA-MM-JJ, demain, +7d, vendredi...). "
                                  "Exclut les tâches sans échéance et les terminées (sauf avec --status done)")
    parser_list.add_argument('--due-after', type=str, default=None, metavar='DATE',
                             help="Échéance à partir de cette date, incluse (mêmes formats que --due-before)")
    parser_list.add_argument('--limit', type=_entier_positif, default=None, metavar='N',
                             help="N'afficher que N tâches (après filtres et tris). Réglage : [list] limit")
    parser_list.add_argument('--start', type=_entier_positif, default=None, metavar='N',
                             help="Commencer à la tâche n°N de la liste (la numérotation affichée commence à 1)")
    parser_list.add_argument('--pager', action=argparse.BooleanOptionalAction, default=None,
                             help="Utilise (--pager) ou non (--no-pager) un pager (less) quand l'affichage dépasse l'écran. Réglage : [general] pager")
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
    subparsers.add_parser('done', help='Clôturer une ou plusieurs tâches').add_argument(
        'ids', nargs='+', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté)")
    subparsers.add_parser('remove', help='Supprimer une ou plusieurs tâches de la base').add_argument(
        'ids', nargs='+', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté)")
    parser_postpone = subparsers.add_parser('postpone', help="Reporter l'échéance d'une ou plusieurs tâches")
    parser_postpone.add_argument('ids', nargs='+', metavar='id', type=str, help="UUID cible, un ou plusieurs (préfixe unique accepté)")
    parser_postpone.add_argument('--to', type=str, default='+1d', metavar='DATE',
                                 help="Nouvelle échéance (défaut : +1d). +2d / +1w / +1m / +1y : décalage depuis l'échéance actuelle, "
                                      "ou depuis aujourd'hui si elle est dépassée ou absente ; ou date fixe : AAAA-MM-JJ, demain, lundi...")
    subparsers.add_parser('clear-done', help='Purger toutes les tâches terminées')
    parser_seed = subparsers.add_parser('seed', help='Remplir la base avec des faux enregistrements')
    parser_seed.add_argument('count', type=int, nargs='?', default=5, help='Quantité')
    parser_agenda = subparsers.add_parser('agenda', help='Voir les tâches à faire jour par jour')
    parser_agenda.add_argument('--days', type=_entier_positif, default=None, metavar='N',
                               help='Nombre de jours affichés (défaut : 7, ou [agenda] days)')
    parser_agenda.add_argument('--from', dest='depuis', type=str, default=None, metavar='DATE',
                               help="Premier jour affiché (défaut : aujourd'hui ; mêmes formats que --due)")
    parser_agenda.add_argument('--pager', action=argparse.BooleanOptionalAction, default=None,
                               help="Utilise (--pager) ou non (--no-pager) un pager (less) quand l'affichage dépasse l'écran. Réglage : [general] pager")
    parser_agenda.add_argument('--format', choices=['table', 'json'], default='table', help='Format de sortie')
    subparsers.add_parser('undo', help="Annuler la dernière modification (un second 'undo' la rétablit)")
    parser_next = subparsers.add_parser('next', help='Afficher la ou les prochaines tâches à traiter')
    parser_next.add_argument('-n', '--count', type=_entier_positif, default=None, metavar='N',
                             help='Nombre de tâches affichées (défaut : 1, ou [next] count)')
    parser_next.add_argument('--tag', type=str, default=None, help='Ne considérer que les tâches portant ce tag')
    parser_next.add_argument('--prio', choices=list(PRIORITES), default=None, help='Ne considérer que cette priorité')
    parser_next.add_argument('--format', choices=['table', 'json'], default='table', help='Format de sortie')
    parser_remind = subparsers.add_parser('remind', help="Rappeler les tâches en retard (silencieux s'il n'y en a pas)")
    parser_remind.add_argument('--limit', type=_entier_positif, default=None, metavar='N',
                               help='Nombre maximal de tâches listées (défaut : 5, ou [remind] limit)')
    parser_remind.add_argument('--soon', type=_entier_positif, default=None, metavar='N',
                               help="Signale aussi les échéances des N prochains jours (défaut : retards et aujourd'hui seulement, ou [remind] soon)")
    parser_remind.add_argument('--once-a-day', action='store_true',
                               help="N'affiche le rappel qu'une fois par jour (le premier terminal de la journée)")
    action = parser_remind.add_mutually_exclusive_group()
    action.add_argument('--write-status', action='store_true',
                        help="N'affiche rien : met à jour le résumé d'une ligne lu par l'invite du shell (pour cron)")
    action.add_argument('--disable', action='store_true', help='Désactive les rappels (remind et --write-status deviennent muets)')
    action.add_argument('--enable', action='store_true', help='Réactive les rappels')
    action.add_argument('--status', action='store_true', help='Indique si les rappels sont activés')
    parser_archive = subparsers.add_parser('archive', help='Archiver les tâches terminées (ou consulter l\'archive)')
    parser_archive.add_argument('ids', nargs='*', help='Identifiants (ou préfixes) de tâches terminées à archiver ; sans identifiant : toutes les tâches terminées')
    parser_archive.add_argument('--older-than', dest='anciennete', type=str, default=None, metavar='DUREE',
                                help='Ne retient que les tâches terminées depuis au moins cette durée (30d, 2w, 6m, 1y)')
    parser_archive.add_argument('--list', dest='lister', action='store_true', help="Affiche l'archive au lieu d'archiver")
    parser_archive.add_argument('--search', type=str, default=None, help="Recherche dans l'archive (titre, description, tags) ; implique --list")
    parser_archive.add_argument('--pager', action=argparse.BooleanOptionalAction, default=None,
                                help="Utilise (--pager) ou non (--no-pager) un pager (less) quand l'affichage dépasse l'écran. Réglage : [general] pager")
    parser_archive.add_argument('--format', choices=['table', 'json'], default='table', help="Format de sortie de --list")
    parser_unarchive = subparsers.add_parser('unarchive', help="Remettre des tâches archivées dans la liste")
    parser_unarchive.add_argument('ids', nargs='+', help="Identifiants (ou préfixes) des tâches archivées à récupérer")
    parser_config = subparsers.add_parser('config', help='Voir les réglages effectifs ou créer un fichier de configuration')
    parser_config.add_argument('action', nargs='?', choices=['show', 'path', 'init'], default='show',
                               help="show : valeurs effectives et leur origine (défaut) ; path : chemin du fichier ; "
                                    "init : crée un fichier modèle commenté")
    parser_config.add_argument('--force', action='store_true', help="init : remplace un fichier existant")
    parser_config.add_argument('--format', choices=['table', 'json'], default='table', help='Format de sortie de show')
    parser_stats = subparsers.add_parser('stats', help='Calculer et afficher le tableau de bord des indicateurs')
    parser_stats.add_argument('--with-archive', action='store_true', help='Compter aussi les tâches archivées')
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

    # La commande est connue du journal avant l'analyse, pour tracer aussi les erreurs d'usage
    journal.definir_commande(next((a for a in sys.argv[1:] if a in subparsers.choices), None))
    args = parser.parse_args()
    journal.regler_niveau(getattr(args, 'niveau_log', None))
    couleurs._configurer_couleurs(reglages.obtenir('general', 'color', getattr(args, 'couleur', None)))

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
                                     tags=args.tags is None, repeat=args.repeat is None)
            if analyse["trouve"]:
                titre = analyse["titre"]
                due = analyse["due"] or due
                prio = analyse["prio"] or prio
                tags = ",".join(analyse["tags"]) or tags
                repeter = analyse["repeat"] or repeter
            else:
                analyse = None
        prio = prio or reglages.obtenir('add', 'priority')   # option > titre > variable > fichier > défaut
        ajouter_tache(titre, args.desc, prio, due, tags, repeter=repeter)
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
        avant = _date_filtre(args.due_before, '--due-before')
        apres = _date_filtre(args.due_after, '--due-after')
        if avant is not None and apres is not None and apres > avant:
            journal.echec("empty_range")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Plage vide : --due-after ({apres}) est postérieure à --due-before ({avant}).")
            sys.exit(1)
        lister_taches(args.status, args.search, args.sort, args.format, args.tag,
                      prio_filtre=args.prio, retard=args.overdue, aujourdhui=args.today,
                      retards_en_premier=reglages.obtenir('list', 'overdue_first', args.overdue_first),
                      limite=reglages.obtenir('list', 'limit', args.limit) or None, debut=args.start,
                      pager=reglages.obtenir('general', 'pager', args.pager),
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
        succes = marquer_terminee(args.ids)
    elif args.commande == 'remove':
        succes = supprimer_tache(args.ids)
    elif args.commande == 'postpone':
        succes = reporter_taches(args.ids, args.to)
    elif args.commande == 'clear-done':
        nettoyer_terminees()
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
        afficher_prochaines(reglages.obtenir('next', 'count', args.count), args.tag, args.prio, args.format)
    elif args.commande == 'remind':
        if args.disable:
            desactiver_rappels()
        elif args.enable:
            activer_rappels()
        elif args.status:
            afficher_etat_rappels()
        elif args.once_a_day and args.write_status:
            journal.echec("invalid_combination")
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --once-a-day ne s'utilise pas avec --write-status.")
            sys.exit(1)
        else:
            rappeler(reglages.obtenir('remind', 'limit', args.limit), reglages.obtenir('remind', 'soon', args.soon),
                     args.once_a_day, args.write_status)
    elif args.commande == 'archive':
        if args.lister or args.search is not None:
            if args.ids or args.anciennete:
                journal.echec("invalid_combination")
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --list / --search ne se combinent pas avec des identifiants ni avec --older-than.")
                sys.exit(1)
            lister_archive(args.search, args.format, pager=reglages.obtenir('general', 'pager', args.pager))
        else:
            if args.ids and args.anciennete:
                journal.echec("invalid_combination")
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Indiquez des identifiants OU --older-than, pas les deux.")
                sys.exit(1)
            anciennete = None
            if args.anciennete is not None:
                anciennete = _parser_anciennete(args.anciennete)
                if anciennete is None:
                    journal.echec("invalid_duration")
                    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Durée non reconnue pour --older-than : '{args.anciennete}'. "
                          f"Format : {MSG_FORMAT_ANCIENNETE}.")
                    sys.exit(1)
            succes = archiver_taches(args.ids or None, anciennete)
    elif args.commande == 'unarchive':
        succes = desarchiver_taches(args.ids)
    elif args.commande == 'config':
        if args.action == 'path':
            afficher_chemin()
        elif args.action == 'init':
            succes = initialiser_config(args.force)
        else:
            afficher_config(args.format)
    elif args.commande == 'stats':
        afficher_stats(args.with_archive)
    elif args.commande == 'reset':
        reinitialiser_base()
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
    except SystemExit as e:
        journal.terminer(e.code if isinstance(e.code, int) else (0 if e.code is None else 1))
        raise
    except Exception:
        journal.critique()
        journal.terminer(1)
        raise
    journal.terminer(0)
