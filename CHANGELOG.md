# Journal des changements

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet le
[versionnement sémantique](https://semver.org/lang/fr/).

## [3.4.0] - 2026-11-22

### Ajouté

- **Hooks** : section `[hooks]` (`on_add`, `on_done`, `on_undone`, `on_start`, `on_unstart`, `on_edit`, `on_postpone`,
  `on_remove`, `on_move`, `on_change`, `timeout`, `enabled`) ; variables `TODO_HOOKS_*`. La commande est lancée sans shell après
  toute commande qui a modifié des tâches, une fois par tâche (une seule au-delà de 20). Les données passent par
  l'environnement (`TODO_EVENT`, `TODO_ID`, `TODO_TITLE`, `TODO_PROJECT`, `TODO_COUNT`, `TODO_IDS`) et par l'entrée standard
  (la tâche en JSON). Un hook n'influe jamais sur le code de sortie ; ses échecs sont signalés sur stderr et journalisés.

## [3.3.0] - 2026-11-22

### Ajouté

- **`attachment add --link`** : référence un fichier sans le copier. La pièce mémorise le chemin absolu (`lien`), la taille et
  l'empreinte SHA-256 ; pas de limite de taille ; `open` et `save` travaillent sur le fichier d'origine, que `attachment remove`
  et `task remove` ne touchent jamais.
- **`attachment check [ID]`** : vérifie les pièces (copies et liens, tâches archivées comprises) : manquantes, modifiées (taille ou
  SHA-256), en corbeille, et fichiers orphelins du dossier `attachments/`. Code de sortie 1 s'il y a une pièce manquante ou
  modifiée ; formats text, table, plain et json.

### Modifié

- `attachment list --format plain` gagne une dernière colonne : `lien` (vide pour une copie). `show` et `list --format json` portent `lien`.

## [3.2.0] - 2026-11-22

### Ajouté

- **Suivi du temps** : champ `demarree` (instant de démarrage, `AAAA-MM-JJ HH:MM`) à côté de la date de complétion.
  `task start ID… [--at HEURE]` (une ou plusieurs tâches, ou par filtre comme `done`) et `task unstart` ; plusieurs tâches
  peuvent être en cours en même temps. `--at` rattrape un oubli (`14:30`, `hier 9:15`, `2026-11-20 16:00`), jamais dans le futur.
- Pas de nouveau statut : « en cours » = démarrée et pas terminée. `task undone` efface le démarrage ; l'occurrence suivante
  d'une tâche récurrente repart sans démarrage ; démarrer une tâche bloquée donne un avertissement.
- Filtres `--started` / `--not-started`, colonne `started`, marque `▶ durée` dans `list`, date de démarrage, temps écoulé et délai
  dans `show` ; `demarree` dans les sorties JSON, `show --format plain`, l'export et l'import.
- Rapports **`report active`** (tâches en cours et temps écoulé) et **`report cycle`** (délai démarrage → fin : nombre, moyenne,
  médiane, min, max, par tag ou par priorité, sur une période) en text, table, plain et json.
- Les notes peuvent porter l'action `start` / `unstart` (`-m`).

### Limite assumée

- Les délais sont **calendaires**, pas un temps de travail effectif.

## [3.1.0] - 2026-11-22

### Ajouté

- **Pièces jointes** : groupe `attachment` (`add`, `list`, `open`, `save`, `remove`, `gc`). Les fichiers sont copiés
  dans `<dossier du projet>/attachments/<id>/` (droits 0600/0700) ; la tâche garde leurs métadonnées (nom, date,
  taille, SHA-256, commentaire) dans `pieces_jointes`.
- `show` liste les pièces ; `list` marque les tâches `📎N`, gagne la colonne `files` et les filtres `--has-files` /
  `--no-files` ; le JSON de `show`, `list` et `attachment list` les contient.
- Réglages `[attachments] max_size` (10 Mo, 0 = illimité) et `opener` ; variables `TODO_ATTACHMENTS_MAX_SIZE` et
  `TODO_ATTACHMENTS_OPENER`.
- **Corbeille** `attachments/.trash/` : `attachment remove`, `task remove` et `archive purge` n'effacent jamais un fichier ;
  `undo` redevient complet (le fichier absent est remis en place à l'accès). `attachment gc [--older-than DURÉE]` la vide.
- `task move` emmène les fichiers dans le projet cible.

### Modifié

- `data import --update` conserve les pièces jointes de la tâche remplacée (l'export ne contient que leurs
  métadonnées, pas les fichiers, qui ne font pas partie des sauvegardes de la base).

## [3.0.0] - 2026-11-21

Version majeure : seule la suppression de la syntaxe 1.x, annoncée depuis la 2.0, est incompatible. Les projets
(2.18 à 2.20), les actions en lot (2.16) et les rapports (2.17) sont arrivés en 2.x ; les données, les sorties
(`--format json`, `plain`), les codes de sortie, les réglages et le vocabulaire du journal ne changent pas.

### Supprimé

- **Syntaxe 1.x** : les commandes plates `edit`, `undone`, `remove`, `postpone`, `note ID…`, `archive` (avec ou sans
  options), `unarchive`, `remind`, `stats`, `reset`, `restore`, `seed`, `export` et `import` ne s'exécutent plus. Elles
  s'arrêtent avec le code 2 et un message qui indique la commande actuelle, sans rien modifier ni lire.
- Variable `TODO_NO_DEPRECATION` : il n'y a plus d'avertissement de dépréciation à masquer (elle est ignorée).

### Migration depuis la 2.x

| Supprimé en 3.0 | À utiliser |
|---|---|
| `todo edit`, `undone`, `remove`, `postpone` | `todo task edit`, `task undone`, `task remove`, `task postpone` |
| `todo note ID texte` / `todo note ID` | `todo note add ID texte` / `todo note list ID` |
| `todo note ID --edit N texte` / `--delete N` | `todo note edit ID N texte` / `todo note delete ID N` |
| `todo archive` / `archive --list` / `archive --search X` | `todo archive add` / `archive list` / `archive list --search X` |
| `todo archive --purge` | `todo archive purge` |
| `todo unarchive` | `todo archive restore` |
| `todo remind` | `todo reminder check` |
| `todo remind --enable` / `--disable` / `--status` | `todo reminder enable` / `disable` / `status` |
| `todo stats` | `todo report stats` |
| `todo reset`, `restore`, `seed` | `todo admin reset`, `admin restore`, `admin seed` |
| `todo export`, `import` | `todo data export`, `data import` |

Inchangés : `add`, `list`, `show`, `done`, `next`, `agenda`, `undo` (raccourcis) et `config`. À vérifier dans vos
crontabs, `~/.bashrc`, alias et scripts, par exemple : `grep -nE 'todo +(edit|undone|remove|postpone|stats|reset|restore|seed|export|import|unarchive|remind|archive|note)' ~/.bashrc ~/bin/*`.

### Modifié

- Retrait du parseur de la syntaxe 1.x et de ses avertissements (code plus simple, `todo --help` et la complétion
  ne décrivent plus que les groupes).

## [2.20.0] - 2026-11-21

### Ajouté

- **`task move`** : déplace une ou plusieurs tâches vers un autre projet (`todo task move ID… --to travail`), par
  identifiants ou par filtre (`--tag`, `--overdue`, `--all`…, avec `--dry-run`, confirmation dès 5 tâches, `-y`).
  La tâche garde son identifiant et tous ses champs. Les deux projets sont verrouillés ; la cible est écrite avant la
  source. Les dépendances ne traversent pas les projets (liens supprimés avec avertissement ; des tâches déplacées
  ensemble gardent les leurs). Limite assumée : `undo` agit sur un projet à la fois, ce que la commande rappelle.

## [2.19.0] - 2026-11-21

### Ajouté

- **Vues sur tous les projets** : `--all-projects` sur `list`, `next`, `agenda`, `report tags|blocked|overdue|stale|done`
  et `stats` (lecture seule, incompatible avec `--project`). Chaque tâche indique son projet : colonne `project`
  (après l'`id`) en `table` et `plain`, champ `projet` en JSON, marque `[projet]` en `text`. Sans l'option, les
  sorties sont inchangées. Un verrou partagé est pris sur chaque projet.
- Colonne `project` disponible dans `--columns` et `[general] columns`.

### Modifié

- **Rappel** : `reminder check` (texte, `plain`, `table`, JSON, `--once-a-day`, `--write-status`) couvre désormais
  tous les projets par défaut ; `--project` le restreint à un projet. Avec un seul projet, la sortie est identique
  à celle d'avant ; avec plusieurs, les tâches portent la marque du projet (JSON : champ `projet`).

## [2.18.0] - 2026-11-21

### Ajouté

- **Projets** : plusieurs listes de tâches indépendantes (perso, travail…), chacune avec sa base, son archive, ses
  sauvegardes, son `undo` et son verrou. Le projet `default` reste à la racine du stockage (aucune migration) ; les
  autres sont dans `<stockage>/projects/<nom>/`. La configuration, le journal et l'état du rappel restent communs.
  - Option globale `--project/-p` (toutes les commandes), variable `TODO_PROJECT`, réglage `[general] project`.
  - Groupe `project` : `current` (nom et origine), `list` (compteurs), `create`, `use` (écrit `[general] project`),
    `rename`, `delete` (déplace le projet dans `<stockage>/.trash/`, refuse le projet courant et un projet non vide
    sans `--force`).
  - Un projet inexistant est refusé avec une suggestion, jamais créé implicitement. Complétion des noms de projet.
  - Le journal ajoute `project=NOM` quand le projet n'est pas `default`.

## [2.17.0] - 2026-11-21

### Ajouté

- **Nouveaux rapports** (groupe `report`, lecture seule, formats `text`, `table`, `plain`, `json`, `--pager`) :
  - `report tags` : tags utilisés avec le nombre de tâches à faire, terminées et le total (`--sort count|alpha`,
    `--with-archive`) ;
  - `report blocked` : tâches qui attendent une dépendance, avec les tâches attendues ;
  - `report overdue` : tâches en retard, les plus en retard d'abord, avec les jours de retard ;
  - `report stale` : tâches à faire sans échéance créées il y a au moins `--older-than` (30d par défaut) ;
  - `report done` : bilan des tâches terminées sur une période (`--since` 7d par défaut, `--until`,
    `--with-archive`), regroupé par jour.
  Les colonnes `plain` et les objets `json` de chaque rapport sont décrits dans le README.

## [2.16.0] - 2026-11-21

### Ajouté

- **Actions en lot par filtre** : `done`, `undone`, `postpone`, `remove` et `edit` acceptent les filtres de `list`
  à la place des identifiants (`todo postpone --overdue --to demain`, `todo done --tag courses`). `--all` vise toutes
  les tâches concernées ; `--dry-run` montre la sélection sans rien modifier (formats `text`, `table`, `plain`,
  `json`, `--columns`) ; une confirmation est demandée à partir de `[general] batch_confirm` tâches (5 par défaut,
  0 = jamais ; `TODO_BATCH_CONFIRM`), `-y` la passe et elle est obligatoire sans terminal. La sélection est figée
  avant toute modification, avec une seule sauvegarde (un seul `undo`).
- `edit` : `--add-tag` et `--remove-tag` ajoutent ou retirent des tags sans remplacer la liste.
- `undone` et `edit` acceptent plusieurs identifiants (bilan, une seule sauvegarde, code de sortie `1` en cas d'échec).

### Modifié

- Sans identifiant ni filtre, `done`, `undone`, `postpone` et `remove` s'arrêtent avec une erreur d'usage (code 2).
- `edit` : `--title` est refusé quand plusieurs tâches sont visées.

## [2.15.0] - 2026-11-20

### Modifié

- **Emplacement du stockage résolu à l'exécution** (aucun changement visible) : la base, l'archive, les
  sauvegardes, les fichiers d'état du rappel et le verrou ne sont plus des constantes calculées à l'import,
  mais des chemins déduits à la demande du dossier de stockage courant (`TODO_DB_DIR`, `--config`, fichier
  de configuration). Les dossiers sont créés au démarrage de la commande, après lecture de `--config`.
  C'est le préalable aux projets (plusieurs listes de tâches) prévus ensuite.

## [2.14.0] - 2026-11-19

### Ajouté

- **`archive add --tag TAGS`** : archive toutes les tâches terminées portant ce tag (répétable ou séparé par
  des virgules : tous les tags), avec `--older-than` en option. Les tâches à faire qui le portent restent en
  place, et leur nombre est indiqué.
- **Archivage automatique** : réglage `[archive] auto_days` (`TODO_ARCHIVE_AUTO_DAYS`, 0 = désactivé, défaut).
  Archive les tâches terminées depuis au moins N jours, une fois par jour, à la première commande qui
  modifie la base ; bilan sur stderr, sauvegarde (donc `undo`), état dans `archive_auto`.

## [2.13.0] - 2026-11-19

### Ajouté

- **Dépendances entre tâches** : `--after IDS` sur `add` et `edit` (`none` pour supprimer). Une tâche à faire
  est bloquée tant qu'une de ses dépendances est à faire ; `next` ne la propose pas, `list` la marque
  `🔒`, `done` avertit mais aboutit. Une dépendance terminée, archivée ou supprimée ne bloque plus ;
  les dépendances circulaires sont refusées.
- **`list --blocked` / `--ready`**, colonnes `after` et `blocked` pour `--columns`.
- Champ `apres` (ids) dans les tâches, `show` et l'export/import JSON (les anciens fichiers restent
  lisibles) ; `bloquee_par` dans `list --format json` et `next --format json`.

## [2.12.0] - 2026-11-19

### Ajouté

- **Filtres de sélection** pour `list` et `archive list` : `--tag` répétable ou séparé par des virgules
  (tous les tags), `--any-tag` (au moins un), `--no-tag`, `--not-tag`, `--prio` multiple (`high,medium`),
  `--not-prio`, `--recurring` / `--no-recurring`, `--created-after` / `--created-before` (mêmes formats que
  `--done-after`) et `--id` (début d'identifiant). Ils se combinent entre eux (ET) et avec les filtres existants.

### Modifié

- `--tag` et `--prio` de `list` / `archive list` acceptent plusieurs valeurs ; l'usage à une seule valeur
  est inchangé. `next` garde ses options `--tag` / `--prio` à valeur unique.

## [2.11.0] - 2026-11-19

### Ajouté

- **Réglage `[general] columns`** (variable `TODO_COLUMNS`) : colonnes par défaut des formats `table` et
  `plain` pour `list`, `next` et `archive list`, quand `--columns` n'est pas donné. Validé et normalisé
  par `config set` (l'id est ajouté en tête s'il manque). Il ne change pas le format choisi.

### Modifié

- Les colonnes par défaut redeviennent `id,status,prio,due,tags,title,notes` : la date de création
  (introduite en 2.10.0 dans le défaut) s'obtient avec `--columns …,created` ou en l'ajoutant au réglage.

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

[3.4.0]: https://github.com/lanig35/todo-cli/releases/tag/v3.4.0
[3.3.0]: https://github.com/lanig35/todo-cli/releases/tag/v3.3.0
[3.2.0]: https://github.com/lanig35/todo-cli/releases/tag/v3.2.0
[3.1.0]: https://github.com/lanig35/todo-cli/releases/tag/v3.1.0
[3.0.0]: https://github.com/lanig35/todo-cli/releases/tag/v3.0.0
[2.20.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.20.0
[2.19.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.19.0
[2.18.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.18.0
[2.17.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.17.0
[2.16.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.16.0
[2.15.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.15.0
[2.14.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.14.0
[2.13.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.13.0
[2.12.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.12.0
[2.11.0]: https://github.com/lanig35/todo-cli/releases/tag/v2.11.0
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
