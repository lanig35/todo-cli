# Journal des changements

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet le
[versionnement sémantique](https://semver.org/lang/fr/).

## [2.10.0] - 2026-11-19

### Ajouté

- **`--columns COLONNES`** (`list`, `next`, `archive list`) : choix et ordre des colonnes des formats
  `table` et `plain` parmi `id`, `status`, `prio`, `due`, `tags`, `title`, `notes`, `created`, `done`,
  `archived`, `recurrence`, `description`. L'id est obligatoire (placé en tête s'il manque). Sans
  `--format`, un terminal donne un tableau ; `text` et `json` refusent l'option.
- **Colonne de création** (`creee` / `CRÉÉE`, date `AAAA-MM-JJ`) dans les colonnes par défaut de `table` et `plain`.

### Modifié

- Les sorties `plain` de `list`, `next` et `archive list` ont une 8ᵉ colonne par défaut (la date de
  création, ajoutée à la fin : les positions 1 à 7 sont inchangées).

## [2.9.0] - 2026-11-18

### Ajouté

- **`list`** : `--no-due` (tâches sans échéance), `--has-notes` / `--no-notes`, `--done-after` /
  `--done-before` (date de fin ; `AAAA-MM-JJ`, `aujourd'hui`, `hier` ou durée écoulée `7d`, `2w`, `1m`, `1y`).
- **`archive list`** (et `archive --list`) : `--tag`, `--prio`, `--has-notes` / `--no-notes`,
  `--done-after` / `--done-before`, `--archived-after` / `--archived-before`, `--older-than`,
  `--sort done|archived|alpha|priority` et `--limit` / `--start`. Un filtre sans `--list` suffit avec
  l'ancienne syntaxe.

### Modifié

- `archive --list --older-than DUREE` n'est plus refusé : l'option filtre alors la liste. Il reste
  incompatible avec des identifiants. `archive --purge` refuse les nouveaux filtres.

## [2.8.0] - 2026-11-18

### Ajouté

- **Verrou de la base** (`flock` sur `todo.lock`, dans le dossier de stockage) : les commandes de lecture
  prennent un verrou partagé, les autres un verrou exclusif. Deux instances lancées en même temps ne
  s'écrasent plus. Libéré par le système à la fin du processus (jamais de verrou périmé).
- **Réglage `[general] lock_timeout`** (10 s par défaut, `TODO_LOCK_TIMEOUT`) : durée maximale d'attente ;
  ensuite la commande échoue avec le code 1 et un message. `0` échoue immédiatement.
- Les commandes `config` ne prennent aucun verrou ; la complétion non plus.

## [2.7.0] - 2026-11-18

### Ajouté

- **Réglage `[add] date_prefix`** (`optional` par défaut, `required`) : avec `required`, la saisie rapide
  ne reconnaît une date que précédée de `@` (`@demain`, `@+3d`, `@2026-12-25`) ; `demain` reste alors
  dans le titre. Variable `TODO_ADD_DATE_PREFIX`. Le comportement par défaut est inchangé.

## [2.6.0] - 2026-11-18

### Ajouté

- **`--search-in CHAMPS`** (`list`, `archive list`) : limite `--search` à certains champs parmi `title`,
  `description`, `tags`, `notes` (séparés par des virgules ; `all` par défaut). `--search-in notes` ne
  cherche que dans les notes. Sans `--search`, l'option est refusée.

### Modifié

- **La recherche ignore les accents et la casse** : `--search reunion` trouve « Réunion » et
  `--search ÉTÉ` trouve « ete ». S'applique à `list --search` et `archive --search`.

## [2.5.0] - 2026-11-18

### Ajouté

- **Complétion du shell** des clés de réglage (`config get|set|unset`) et des valeurs possibles d'un réglage
  (choix, `true`/`false`, fichiers pour un chemin) ; `config unset` propose les clés écrites dans le fichier ;
  `--config` est pris en compte pendant la complétion.

### Corrigé

- **Appuyer sur Tab ne produit plus ni erreur ni entrée dans le journal** : une exception pendant la
  complétion (par exemple un `argcomplete` incompatible) était écrite sur le terminal et journalisée en
  CRITICAL. Désormais la complétion est silencieuse (rien dans les logs, aucun dossier créé, pas
  d'avertissement de configuration) ; `_ARC_DEBUG=1` affiche la trace.
- Les messages d'aide ne citent plus les anciennes commandes : `todo reminder enable` (au lieu de `todo remind
  --enable`), `todo archive restore`, `todo admin restore`, `todo note add`.

## [2.4.0] - 2026-11-18

### Ajouté

- **`config get CLE`** : valeur effective d'un réglage (`section.clé`), seule sur une ligne ; `--format json`
  donne aussi l'origine ; `--file` donne la valeur écrite dans le fichier.
- **`config set CLE VALEUR`** : valide la valeur et l'écrit dans le fichier de configuration (créé au besoin
  à partir du modèle commenté), en ne touchant qu'à la ligne du réglage. Avertit si une variable
  d'environnement l'emporte.
- **`config unset CLE`** : retire le réglage du fichier.
- **Option générale `--config FICHIER`** : utilise un autre fichier de configuration (prioritaire sur
  `TODO_CONFIG`), y compris pour trouver le stockage. Un fichier introuvable désigné ainsi est une erreur.
- `config show` indique l'origine du chemin du fichier (`fichier_origine` en JSON).

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

[2.10.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.10.0
[2.9.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.9.0
[2.8.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.8.0
[2.7.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.7.0
[2.6.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.6.0
[2.5.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.5.0
[2.4.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.4.0
[2.3.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.3.0
[2.2.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.2.0
[2.1.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.1.0
[2.0.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.0.0
[1.0.0]: https://github.com/lanig35/todo-cli/releases/tag/v1.0.0
