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

# Colonnes communes à list, next et archive list (plain : mêmes colonnes, même ordre, depuis toujours)
COLONNES_TACHES = ('id', 'statut', 'priorite', 'echeance', 'tags', 'titre', 'notes')
ENTETES_TACHES = ('ID', 'STATUT', 'PRIO', 'ÉCHÉANCE', 'TAGS', 'TITRE', 'NOTES')


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


def ligne_tache(t, court=True):
    """Champs d'une tâche pour les colonnes COLONNES_TACHES (plain : id complet ; table : préfixe de 8)."""
    return (t['id'][:8] if court else t['id'],
            'done' if t['statut'] == "TERMINE" else 'todo',
            t['priorite'], t['date_echeance'] or "", ",".join(t['tags']), t['titre'], len(t.get('notes') or []))


def sortie_taches(fmt, taches):
    """Rend une liste de tâches en `plain` ou `table` ; renvoie False pour tout autre format."""
    if fmt == 'plain':
        imprimer_plain(ligne_tache(t, court=False) for t in taches)
    elif fmt == 'table':
        print(tableau(ENTETES_TACHES, [ligne_tache(t) for t in taches]))
    else:
        return False
    return True
