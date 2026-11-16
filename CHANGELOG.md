# Journal des changements

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet le
[versionnement sémantique](https://semver.org/lang/fr/).

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

[1.0.0]: https://github.com/lanig35/todo-cli/releases/tag/v1.0.0
