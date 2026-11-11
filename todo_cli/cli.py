"""Définition de la ligne de commande (argparse) et aiguillage vers les commandes."""
import argparse
import sys
from .agenda import afficher_agenda
from .archive import MSG_FORMAT_ANCIENNETE, _parser_anciennete, archiver_taches, desarchiver_taches, lister_archive
from .affichage import afficher_stats, afficher_tache, lister_taches
from .config import PRIORITES
from . import couleurs
from .dates import MSG_FORMATS_DATE, _resoudre_date
from .sauvegardes import reinitialiser_base, restaurer_base
from .seed import peupler_fausses_taches
from .taches import ajouter_tache, marquer_terminee, modifier_tache, nettoyer_terminees, reporter_taches, rouvrir_tache, supprimer_tache


def _date_filtre(valeur, option):
    """Résout la valeur d'une option de filtre de date (absolue ou relative), ou quitte avec une erreur."""
    if valeur is None:
        return None
    date_obj = _resoudre_date(valeur)
    if date_obj is None:
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
    parser_agenda.add_argument('--days', type=_entier_positif, default=7, metavar='N',
                               help='Nombre de jours affichés (défaut : 7)')
    parser_agenda.add_argument('--from', dest='depuis', type=str, default=None, metavar='DATE',
                               help="Premier jour affiché (défaut : aujourd'hui ; mêmes formats que --due)")
    parser_agenda.add_argument('--no-pager', action='store_true', help="N'utilise pas de pager, même pour un long affichage")
    parser_agenda.add_argument('--format', choices=['table', 'json'], default='table', help='Format de sortie')
    parser_archive = subparsers.add_parser('archive', help='Archiver les tâches terminées (ou consulter l\'archive)')
    parser_archive.add_argument('ids', nargs='*', help='Identifiants (ou préfixes) de tâches terminées à archiver ; sans identifiant : toutes les tâches terminées')
    parser_archive.add_argument('--older-than', dest='anciennete', type=str, default=None, metavar='DUREE',
                                help='Ne retient que les tâches terminées depuis au moins cette durée (30d, 2w, 6m, 1y)')
    parser_archive.add_argument('--list', dest='lister', action='store_true', help="Affiche l'archive au lieu d'archiver")
    parser_archive.add_argument('--search', type=str, default=None, help="Recherche dans l'archive (titre, description, tags) ; implique --list")
    parser_archive.add_argument('--no-pager', action='store_true', help="N'utilise pas de pager, même pour un long affichage")
    parser_archive.add_argument('--format', choices=['table', 'json'], default='table', help="Format de sortie de --list")
    parser_unarchive = subparsers.add_parser('unarchive', help="Remettre des tâches archivées dans la liste")
    parser_unarchive.add_argument('ids', nargs='+', help="Identifiants (ou préfixes) des tâches archivées à récupérer")
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

    args = parser.parse_args()
    couleurs._configurer_couleurs(getattr(args, 'couleur', None))

    # Moteur d'aiguillage vers l'action requise.
    # `succes` passe à False si un identifiant de done / remove / postpone n'a pas pu être traité :
    # le code de sortie vaut alors 1, ce qui permet de s'en servir dans un script.
    succes = True
    if args.commande == 'add':
        ajouter_tache(args.titre, args.desc, args.prio, args.due, args.tags, repeter=args.repeat)
    elif args.commande == 'list':
        avant = _date_filtre(args.due_before, '--due-before')
        apres = _date_filtre(args.due_after, '--due-after')
        if avant is not None and apres is not None and apres > avant:
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Plage vide : --due-after ({apres}) est postérieure à --due-before ({avant}).")
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
        if args.days > 366:
            print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --days est limité à 366 jours.")
            sys.exit(1)
        afficher_agenda(_date_filtre(args.depuis, '--from'), args.days, args.format, pager=not args.no_pager)
    elif args.commande == 'archive':
        if args.lister or args.search is not None:
            if args.ids or args.anciennete:
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} --list / --search ne se combinent pas avec des identifiants ni avec --older-than.")
                sys.exit(1)
            lister_archive(args.search, args.format, pager=not args.no_pager)
        else:
            if args.ids and args.anciennete:
                print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Indiquez des identifiants OU --older-than, pas les deux.")
                sys.exit(1)
            anciennete = None
            if args.anciennete is not None:
                anciennete = _parser_anciennete(args.anciennete)
                if anciennete is None:
                    print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Durée non reconnue pour --older-than : '{args.anciennete}'. "
                          f"Format : {MSG_FORMAT_ANCIENNETE}.")
                    sys.exit(1)
            succes = archiver_taches(args.ids or None, anciennete)
    elif args.commande == 'unarchive':
        succes = desarchiver_taches(args.ids)
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
    """Lance `main()` et traduit Ctrl+C en code de sortie 130."""
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n {couleurs.CLR_DIM}Interrompu.{couleurs.CLR_RESET}")
        sys.exit(130)
