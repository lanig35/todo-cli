"""Formats de sortie (`--format`) : text, table, plain, json, et le choix automatique.

- text  : l'affichage décoré (émojis, couleurs, titres), pensé pour un terminal ;
- table : un vrai tableau à colonnes alignées, sans émoji ni couleur ;
- plain : une ligne par enregistrement, champs séparés par des tabulations, sans couleur, titre ni pied
          de page, colonnes stables (comme `git --porcelain`) : fait pour `grep`, `cut`, `awk`, `xargs` ;
- json  : documents JSON compatibles `jq`.

`auto` (le défaut) choisit `text` dans un terminal et `plain` dans un pipe ou une redirection. Une commande
sans rendu tabulaire (config, remind, import…) affiche `text` pour `table` et `plain`.
"""
import re
import shutil
import sys
import unicodedata

FORMATS = ('auto', 'text', 'table', 'plain', 'json')

# Champs disponibles pour les listes de tâches (list, next, archive list) : nom -> (en-tête de table, valeur).
# La valeur reçoit la tâche et `court` (table : id réduit à 8 caractères ; plain : id complet).
CHAMPS_TACHES = {
    'id': ('ID', lambda t, court: t['id'][:8] if court else t['id']),
    'status': ('STATUT', lambda t, court: 'done' if t['statut'] == "TERMINE" else 'todo'),
    'prio': ('PRIO', lambda t, court: t['priorite']),
    'due': ('ÉCHÉANCE', lambda t, court: t['date_echeance'] or ""),
    'tags': ('TAGS', lambda t, court: ",".join(t['tags'])),
    'title': ('TITRE', lambda t, court: t['titre']),
    'notes': ('NOTES', lambda t, court: len(t.get('notes') or [])),
    'created': ('CRÉÉE', lambda t, court: (t.get('date_creation') or "")[:10]),
    'done': ('TERMINÉE', lambda t, court: (t.get('date_terminee') or "")[:10]),
    'archived': ('ARCHIVÉE', lambda t, court: (t.get('date_archivage') or "")[:10]),
    'recurrence': ('RÉPÉTITION', lambda t, court: t.get('recurrence') or ""),
    'description': ('DESCRIPTION', lambda t, court: t['description']),
    'after': ('APRÈS', lambda t, court: ",".join(d[:8] if court else d for d in t.get('apres', []))),
    'project': ('PROJET', lambda t, court: t.get('projet') or ""),
    'blocked': ('BLOQUÉE', lambda t, court: 'yes' if t.get('bloquee_par') else 'no'),
}
# Colonnes par défaut, dans l'ordre (réglage [general] columns)
COLONNES_DEFAUT = ('id', 'status', 'prio', 'due', 'tags', 'title', 'notes')


def colonnes_tache(valeur):
    """Colonnes désignées par --columns (noms séparés par des virgules) ; ValueError si l'une est inconnue.

    L'id est obligatoire : s'il n'est pas cité, il est placé en tête. Un nom répété n'est gardé qu'une fois.
    """
    noms = []
    for nom in str(valeur).split(","):
        nom = nom.strip().lower()
        if not nom:
            continue
        if nom not in CHAMPS_TACHES:
            raise ValueError(f"colonne inconnue : {nom} (attendues : {', '.join(CHAMPS_TACHES)})")
        if nom not in noms:
            noms.append(nom)
    if not noms:
        raise ValueError(f"aucune colonne indiquée (attendues : {', '.join(CHAMPS_TACHES)})")
    return tuple(noms) if 'id' in noms else ('id', *noms)


def resoudre(fmt, flux=None):
    """`auto` devient `plain` quand la sortie n'est pas un terminal, `text` sinon ; les autres valeurs passent."""
    if fmt not in (None, 'auto'):
        return fmt
    flux = flux or sys.stdout
    try:
        return 'text' if flux.isatty() else 'plain'
    except (AttributeError, ValueError):
        return 'plain'


def _propre(valeur):
    """Valeur sur une seule ligne, sans tabulation (qui sépare les champs)."""
    return re.sub(r"[\t\r\n]+", " ", "" if valeur is None else str(valeur)).strip()


def ligne_plain(*champs):
    return "\t".join(_propre(c) for c in champs)


def imprimer_plain(lignes):
    """Écrit les lignes `plain` (listes de champs) : une ligne chacune, rien s'il n'y en a pas."""
    for champs in lignes:
        print(ligne_plain(*champs))


def _largeur(texte):
    """Largeur d'affichage (les caractères larges, comme les idéogrammes ou les émojis, comptent double)."""
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in texte)


def _tronquer(texte, largeur):
    if _largeur(texte) <= largeur:
        return texte
    sortie, n = "", 0
    for c in texte:
        w = _largeur(c)
        if n + w > largeur - 1:
            break
        sortie, n = sortie + c, n + w
    return sortie + "…"


def tableau(entetes, lignes, largeur_max=None):
    """Tableau encadré à colonnes alignées ; la dernière colonne est tronquée (…) pour tenir dans le terminal."""
    lignes = [[_propre(c) for c in ligne] for ligne in lignes]
    n = len(entetes)
    largeurs = [max([_largeur(entetes[i])] + [_largeur(l[i]) for l in lignes]) for i in range(n)]
    if largeur_max is None:
        largeur_max = shutil.get_terminal_size((100, 24)).columns if sys.stdout.isatty() else 10 ** 6
    # Trop large pour le terminal : on rogne la colonne la plus large (la dernière en cas d'égalité), jusqu'à 4 minimum
    while sum(largeurs) + 3 * (n - 1) + 4 > largeur_max:
        i = max(range(n), key=lambda k: (largeurs[k], k))
        if largeurs[i] <= 4:
            break
        largeurs[i] -= 1

    def rangee(cellules):
        morceaux = []
        for i, c in enumerate(cellules):
            c = _tronquer(c, largeurs[i])
            morceaux.append(c + " " * (largeurs[i] - _largeur(c)))
        return "│ " + " │ ".join(morceaux) + " │"

    def filet(g, m, d):
        return g + m.join("─" * (w + 2) for w in largeurs) + d

    sortie = [filet("┌", "┬", "┐"), rangee(entetes), filet("├", "┼", "┤")]
    sortie += [rangee(l) for l in lignes]
    sortie.append(filet("└", "┴", "┘"))
    return "\n".join(sortie)


def ligne_tache(t, court=True, colonnes=COLONNES_DEFAUT):
    """Champs d'une tâche pour `colonnes` (plain : id complet ; table : préfixe de 8)."""
    return tuple(CHAMPS_TACHES[c][1](t, court) for c in colonnes)


def sortie_taches(fmt, taches, colonnes=None):
    """Rend une liste de tâches en `plain` ou `table` ; renvoie False pour tout autre format."""
    colonnes = colonnes or COLONNES_DEFAUT
    if fmt == 'plain':
        imprimer_plain(ligne_tache(t, False, colonnes) for t in taches)
    elif fmt == 'table':
        print(tableau([CHAMPS_TACHES[c][0] for c in colonnes], [ligne_tache(t, True, colonnes) for t in taches]))
    else:
        return False
    return True
