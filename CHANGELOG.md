# Journal des changements

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet le
[versionnement sémantique](https://semver.org/lang/fr/).

## [2.3.0] - 2026-11-17

### Ajouté

- **`pyproject.toml`** : `todo` s'installe comme un paquet (`pipx install git+https://github.com/lanig35/todo-cli`)
  et fournit la commande `todo`. Extras facultatifs : `seed` (faker), `completion` (argcomplete) et `dev`
  (pytest, faker). Python 3.11 ou plus. Le lanceur `todo.py` reste utilisable depuis un clone.

### Changé

- `requirements-dev.txt` et `pytest.ini` sont remplacés par `pyproject.toml` (`pip install -e ".[dev]"`) ; la
  CI s'y conforme et vérifie que la commande installée répond.

### Corrigé

- Python 3.11 : l'ancienne syntaxe `note ID --edit N texte` (dépréciée) était refusée par `argparse`.

## [2.2.0] - 2026-11-17

### Ajouté

- `--format table` et `--format plain` pour `config show` (réglage, valeur, origine) et pour `reminder`
  (`check` : une ligne par tâche, sans limite ; `status`, `enable`, `disable` : l'état des rappels).
- Colonne `notes` (nombre de notes), ajoutée à la fin, dans les formats `table` et `plain` de `list`, `next`
  et `archive list`.

### Changé

- `config show` en `auto` donne `plain` dans un pipe (comme `list`). Les rappels restent en `text` sans
  demande explicite, pour garder des e-mails de cron lisibles.

### Corrigé

- `todo ... | head` (lecteur du tube fermé) ne provoque plus de trace d'erreur.

## [2.1.0] - 2026-11-17

### Ajouté

- **Formats de sortie** : `--format auto|text|table|plain|json` pour `list`, `show`, `next`, `agenda`,
  `archive list`, `note list` et `report stats` (qui gagne aussi `json`).
  - `table` : vrai tableau aligné, sans couleur.
  - `plain` : une ligne par enregistrement, champs séparés par des tabulations, colonnes stables, pour
    `grep`, `cut`, `awk` et `xargs`.
- **Choix automatique** : sans `--format`, `text` dans un terminal et `plain` dans un pipe ou une redirection.
  Réglage `[general] format` et variable `TODO_FORMAT`.

### Changé

- L'affichage décoré s'appelle désormais `text` ; `--format table` désigne le nouveau tableau.
- **Dans un pipe ou une redirection**, la sortie par défaut de ces commandes est maintenant `plain` : un
  script qui lisait l'ancien affichage décoré doit ajouter `--format text` (ou définir `TODO_FORMAT=text`).

## [2.0.0] - 2026-11-16

### Changé

- **Commandes en groupes** (`todo GROUPE ACTION`) : `task`, `note`, `archive`, `reminder`, `report`, `config`,
  `admin`, `data`. Raccourcis de premier niveau : `add`, `list`, `show`, `done`, `next`, `agenda`, `undo`.
- Nouvelles actions : `note add|list|edit|delete`, `archive add|list|purge|restore`,
  `reminder check|enable|disable|status`, `config list` (synonyme de `show`).

### Déprécié

- Les commandes 1.x (`edit`, `undone`, `remove`, `postpone`, `note ID`, `archive` avec options, `unarchive`,
  `remind`, `stats`, `reset`, `restore`, `seed`, `export`, `import`) restent acceptées avec un avertissement
  sur la sortie d'erreur ; suppression prévue en 3.0. `TODO_NO_DEPRECATION=1` masque l'avertissement.

### Inchangé

- Sorties `--format json`, codes de sortie, réglages, format d'export et vocabulaire du journal.

## [1.0.0] - 2026-11-16

Première version stable. Les commandes, les sorties `--format json`, les codes de sortie et le format de
l'export décrits dans le README sont désormais couverts par la compatibilité (voir « Versions et
compatibilité »).

### Fonctionnalités

- **Tâches** : titre, description, priorité (`low`, `medium`, `high`), échéance et tags ; dates relatives
  (`demain`, `+3d`, `vendredi`…) ; **saisie rapide** (`todo add "Appeler Paul demain !high #pro ~weekly"`) ;
  tâches **récurrentes** (quotidiennes, hebdomadaires, mensuelles, annuelles).
- **Actions** : `add`, `edit`, `done`, `undone`, `remove`, `postpone` (une ou plusieurs tâches à la fois).
- **Notes datées** : `note`, `-m` sur `done`, `undone`, `postpone`, `edit` et `remove` (le motif d'une
  suppression va au journal) ; notes numérotées, modifiables (`--edit N`) et supprimables (`--delete N`).
- **Consultation** : `list` (filtres, recherche, tris, dates, pagination, pager, retards en premier),
  `show`, `agenda`, `next`, `stats`.
- **Rappels** : `remind` (terminal, `cron` avec `--once-a-day` et `--write-status`, invite du shell),
  désactivable.
- **Archive** : `archive`, `unarchive`, `archive --list`, `--search`, et `archive --purge` pour supprimer
  définitivement (par identifiant, par ancienneté ou en bloc).
- **Sauvegardes** : une sauvegarde après chaque modification (5 conservées), `restore`, `undo` (un second
  `undo` rétablit), `reset` (`--include-archive` pour vider aussi l'archive).
- **Échange** : `export` et `import` JSON, indépendants du format de la base (modes par défaut, `--update`,
  `--replace`, `--dry-run`).
- **Sorties JSON** (`--format json`, compatibles `jq`) : `list`, `next`, `show`, `remind`, `note`,
  `config`, `import`, `archive --list`.
- **Configuration** : fichier INI (`~/.config/todo/config.ini`), variables d'environnement et options,
  dans cet ordre de priorité (`todo config show | path | init`).
- **Journal** : actions et erreurs écrites pour `journalctl -t todo` (ou dans un fichier).
- **Qualité** : suite de tests `pytest` en boîte noire, intégration continue GitHub Actions, aucune
  dépendance obligatoire.

### Par rapport aux versions de développement

Pour qui utilisait le dépôt avant la 1.0 :

- **`clear-done` est supprimée.** Archivez les tâches terminées (`todo archive`), puis purgez l'archive
  (`todo archive --purge --older-than 90d`) ; `todo remove` supprime des tâches précises.
- **`show`, `edit` et `undone` renvoient `1` en cas d'erreur** (identifiant introuvable ou ambigu, liste
  vide, entrée corrompue…), comme les autres commandes, au lieu de `0`.
- **Récurrences mensuelles corrigées** : « tous les mois à partir du 31 janvier » donne 28 février,
  31 mars, 30 avril… au lieu de rester sur le 28. Les séries déjà commencées repartent de leur
  échéance actuelle.
- Les tâches portent désormais les champs `notes` et `ancre` ; les anciennes bases restent lisibles
  sans migration.

[2.3.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.3.0
[2.2.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.2.0
[2.1.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.1.0
[2.0.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.0.0
[1.0.0]: https://github.com/lanig35/todo-cli/releases/tag/v1.0.0
