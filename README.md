# todo-cli

[![Tests](https://github.com/lanig35/todo-cli/actions/workflows/tests.yml/badge.svg)](https://github.com/lanig35/todo-cli/actions/workflows/tests.yml)

Gestionnaire de tâches en ligne de commande en Python, sans dépendance obligatoire.
Les tâches sont stockées dans une base DBM locale, avec sauvegarde automatique après chaque modification.

## Fonctionnalités

- Saisie rapide : `todo add "Appeler Paul demain !high #pro"`
- Tâches avec titre, description, priorité (`low`, `medium`, `high`), échéance et tags
- Dates relatives : `demain`, `+3d`, `+2w`, `vendredi`…
- Report d'échéance en une commande (`postpone`), sur une ou plusieurs tâches
- Actions en lot par filtre : `todo done --tag courses`, `todo task postpone --overdue --to demain` (aperçu `--dry-run`, confirmation)
- Tâches récurrentes (quotidiennes, hebdomadaires, mensuelles, annuelles)
- Dépendances entre tâches (`--after`) : une tâche attend que d'autres soient terminées
- Formats de sortie `text`, `table`, `plain` (pipes) et `json`, choisis automatiquement selon le terminal
- Filtres, recherche, tris, filtres par date, pagination et pager automatique
- Tâches en retard affichées en premier
- Agenda : les tâches à faire jour par jour (`agenda`)
- Rapports : tags utilisés, tâches bloquées, en retard, qui traînent, bilan des tâches terminées (`report`)
- Projets : plusieurs listes indépendantes (perso, travail…), chacune avec son archive, ses sauvegardes et son `undo` (`project`, `-p`)
- Journal des actions et des erreurs, lisible avec `journalctl -t todo`
- Configuration par fichier INI, variables d'environnement et options (`todo config`)
- `report review` : revue hebdomadaire en lecture seule, avec rappel (`reminder`) et envoi par cron
- `remind` : rappel des tâches en retard (terminal, `cron`, invite du shell)
- `next` : la prochaine tâche à traiter ; `undo` : annuler la dernière modification
- Notes datées sur les tâches (`note`, ou `-m` sur `done`, `undone`, `postpone`, `edit`, `remove`)
- Vues enregistrées : une commande de lecture et ses filtres mémorisés sous un nom, par projet (`view save`, `view run`)
- Hooks : une commande de votre choix lancée après chaque modification (`[hooks] on_done`, `on_change`…), ou un webhook HTTP intégré (`webhook_url`)
- Interface texte `todo tui` (curses), cliente de l'API : utilisable en SSH
- Interface web (Flask + Jinja + Bootstrap) servie par `todo serve`, à côté de l'API
- API REST (Flask, optionnelle) : `todo serve` pour gérer les tâches à distance, avec jeton obligatoire et `ETag` / `If-Match`
- Pièces jointes : des fichiers copiés dans le stockage de la tâche (`attachment add`, `open`, `save`), avec corbeille et `undo`
- Suivi du temps : instant de démarrage (`task start`, plusieurs tâches en cours à la fois), délai jusqu'à la fin, rapports `active` et `cycle`
- Date de complétion et statistiques
- Archivage des tâches terminées (consultation, recherche, récupération)
- Sauvegardes automatiques et restauration
- Export et import JSON (`export`, `import`), indépendants du format de la base
- Couleurs automatiquement désactivées hors terminal (pipes, redirections) et avec `NO_COLOR`

## Installation

Python 3.11 ou plus est requis (développé avec Python 3.13). Aucune dépendance obligatoire.

**Avec pipx (recommandé)** : la commande `todo` est installée dans un environnement isolé.

```bash
pipx install git+https://github.com/lanig35/todo-cli          # dernière version de main
pipx install git+https://github.com/lanig35/todo-cli@v2.5.0   # une version précise (tag)
pipx upgrade todo-cli                                          # mise à jour ; pipx uninstall todo-cli pour retirer
```

Depuis un clone (`pipx install .`), ou pour tester une branche :
`pipx install git+https://github.com/lanig35/todo-cli@nom-de-branche`. Les extras facultatifs
s'ajoutent avec `pipx install "todo-cli[seed,completion] @ git+https://github.com/lanig35/todo-cli"`.

**Sans installation** : le lanceur `todo.py` fonctionne depuis un clone.

```bash
git clone https://github.com/lanig35/todo-cli.git
cd todo-cli
ln -s "$PWD/todo.py" ~/.local/bin/todo     # optionnel : disposer de la commande `todo`
```

Dépendances optionnelles :

| Paquet | Usage |
|---|---|
| `faker` | commande `admin seed` (génération de tâches factices) ; extra `seed` |
| `argcomplete` | autocomplétion du shell (`register-python-argcomplete todo`) ; extra `completion` |
| `less` | pager pour les longues listes (présent sur la plupart des systèmes) |

Dans les exemples ci-dessous, `todo` désigne la commande installée, ou `./todo.py` / le lien créé ci-dessus.

## Utilisation

## Organisation des commandes

Depuis la 2.0, les commandes sont rangées en **groupes** (`todo GROUPE ACTION`, comme `arduino-cli`), et les
plus courantes ont un **raccourci** de premier niveau.

| Groupe | Actions |
|---|---|
| `task` | `add`, `list`, `show`, `edit`, `done`, `start`, `unstart`, `undone`, `remove`, `move`, `postpone`, `next` |
| `note` | `add`, `list`, `edit`, `delete` |
| `attachment` | `add`, `list`, `check`, `open`, `save`, `remove`, `gc` |
| `archive` | `add`, `list`, `purge`, `restore` |
| `reminder` | `check`, `enable`, `disable`, `status` |
| `project` | `current`, `list`, `create`, `use`, `rename`, `delete` |
| `report` | `stats`, `agenda`, `tags`, `blocked`, `overdue`, `stale`, `done`, `active`, `cycle` |
| `hooks` | `queue`, `flush`, `clear` (file d'attente du webhook) |
| `server` | `serve` (API REST + interface web), `tui` (interface texte) |
| `view` | `save`, `run`, `list`, `show`, `rename`, `remove` |
| `config` | `show` (ou `list`), `path`, `init` |
| `admin` | `undo`, `restore`, `reset`, `seed`, `doctor` |
| `data` | `export`, `import` |

Raccourcis : `todo add`, `list`, `show`, `done`, `next`, `agenda`, `undo`, `serve` (= `task add`, `task list`, … `report agenda`,
`admin undo`). `todo GROUPE --help` détaille un groupe.

### Migration depuis la 1.x et la 2.x

Les commandes de la syntaxe 1.x ont été **supprimées en 3.0**. Elles ne font plus rien : `todo edit …`, `todo remind`,
`todo archive --list`… s'arrêtent avec le code 2 et un message qui indique la commande actuelle
(« la commande `todo edit` a été supprimée en 3.0 : utilisez `todo task edit` »). Les scripts, crontabs et alias
qui les appellent doivent être mis à jour avec la table ci-dessous ; les sorties (`--format json`), les codes de
sortie, les réglages et le vocabulaire du journal sont inchangés. `TODO_NO_DEPRECATION` n'a plus d'effet.

| 1.x (supprimé) | à utiliser |
|---|---|
| `edit`, `undone`, `remove`, `postpone` | `task edit`, `task undone`, `task remove`, `task postpone` |
| `note ID texte` / `note ID` | `note add ID texte` / `note list ID` |
| `note ID --edit N texte` / `--delete N` | `note edit ID N texte` / `note delete ID N` |
| `archive` / `archive --list` / `--search` | `archive add` / `archive list` / `archive list --search` |
| `archive --purge` | `archive purge` |
| `unarchive` | `archive restore` |
| `remind` | `reminder check` |
| `remind --enable` / `--disable` / `--status` | `reminder enable` / `disable` / `status` |
| `stats` | `report stats` |
| `reset`, `restore`, `seed` | `admin reset`, `admin restore`, `admin seed` |
| `export`, `import` | `data export`, `data import` |

### Ajouter une tâche

```bash
todo add "Préparer la réunion"
todo add "Rapport mensuel" --prio high --due vendredi --tags pro,rapport --desc "Chiffres de octobre"
todo add "Sauvegarde serveur" --repeat weekly --due lundi
```

#### Saisie rapide

La date, la priorité, les tags et la répétition peuvent s'écrire directement dans le titre :

```bash
todo add "Appeler Paul demain !high #pro"
todo add "Envoyer la facture @vendredi #compta"
todo add "Sauvegarde du serveur ~weekly #admin"
```

| Marqueur | Effet | Exemples |
|---|---|---|
| Date (avec ou sans `@`, voir `date_prefix`) | échéance | `demain`, `@lundi`, `+3d`, `2026-12-25` (mêmes formats que `--due`) |
| `!priorité` | priorité | `!high` `!medium` `!low`, `!haute` `!moyenne` `!basse`, `!h` `!m` `!l` |
| `#tag` | tag (minuscules) | `#pro #urgent` : un tag commence par une lettre, `#42` reste dans le titre |
| `~répétition` | tâche récurrente | `~weekly`, `~2w`, `~mensuel` |

- Les marqueurs sont retirés du titre, et une ligne « ⚡ Compris dans le titre » indique ce qui a été
  interprété.
- Un mot qui ressemble à un marqueur sans en être un (`!bravo`, `#42`, un `!` isolé) reste dans le
  titre. Si le titre se réduirait à rien (`todo add demain`), il est conservé tel quel.
- Un marqueur de même nature répété : le dernier l'emporte (les tags s'additionnent).
- Une **option explicite** (`--due`, `--prio`, `--tags`, `--repeat`) est prioritaire sur le
  marqueur équivalent, qui reste alors dans le titre. `--desc` n'est pas concerné.
- `--literal` désactive entièrement la saisie rapide (`todo add --literal "Réunion demain"`).
- **Exiger le `@` pour les dates** : avec `todo config set add.date_prefix required` (ou
  `TODO_ADD_DATE_PREFIX=required`), seule `@demain` est une échéance ; `demain` reste dans le titre
  (`todo add "Réunion lundi @vendredi"` → titre « Réunion lundi », échéance vendredi). Par défaut
  (`optional`), `demain` et `@demain` comptent tous deux comme des dates.
- Dans un shell, mettez le titre entre guillemets : `#` commence un commentaire et `!` déclenche
  l'historique de bash.

### Lister

```bash
todo list                                  # tout, les retards en premier
todo list --status todo --prio high        # à faire, priorité haute
todo list --tag pro --sort alpha           # par tag, tri alphabétique
todo list --any-tag pro,perso --not-prio low   # l'un des deux tags, sans les priorités basses
todo list --search reunion                 # titre, description, tags et notes ; « Réunion » est trouvée sans accent
todo list --search appel --search-in notes # uniquement dans les notes
todo list --overdue --today                # en retard ou pour aujourd'hui
todo list --due-after demain --due-before +7d    # la semaine à venir
todo list --limit 15                       # 15 premières tâches
todo list --start 16 --limit 15            # les 15 suivantes
todo list --format json                    # sortie JSON (compatible jq)
```

Options de `list` :

| Option | Effet |
|---|---|
| `--status todo\|done` | filtre sur l'avancement |
| `--search TEXTE` | recherche dans le titre, la description, les tags et les notes, sans tenir compte des accents ni de la casse |
| `--search-in CHAMPS` | limite `--search` à `title`, `description`, `tags`, `notes` (séparés par des virgules ; défaut `all`) |
| `--tag TAGS` | tâches portant ce tag ; répétable ou séparé par des virgules : **tous** les tags indiqués (`--tag pro,tel`) |
| `--any-tag TAGS` | tâches portant **au moins un** de ces tags (`--any-tag tel,perso`) |
| `--no-tag` | tâches sans aucun tag (refusé avec `--tag` / `--any-tag`) |
| `--not-tag TAGS` | écarte les tâches portant l'un de ces tags |
| `--prio low\|medium\|high` | filtre sur la priorité ; plusieurs possibles, séparées par des virgules (`--prio high,medium`) |
| `--not-prio PRIO` | écarte cette priorité (ou plusieurs, séparées par des virgules) |
| `--recurring`, `--no-recurring` | seulement les tâches récurrentes, ou non récurrentes |
| `--created-after DATE`, `--created-before DATE` | créées à partir de / au plus tard à cette date, incluse (mêmes formats que `--done-after`) |
| `--id ID` | tâche dont l'identifiant commence par `ID` ; répétable ou séparé par des virgules |
| `--overdue` | tâches à faire dont l'échéance est dépassée |
| `--today` | tâches à faire dont l'échéance est aujourd'hui (avec `--overdue` : l'un ou l'autre) |
| `--due-before DATE` | échéance au plus tard à cette date, **incluse** |
| `--due-after DATE` | échéance à partir de cette date, **incluse** |
| `--blocked`, `--ready` | tâches à faire qui attendent une dépendance (`--after`), ou qui sont libres |
| `--no-due` | tâches sans échéance (ne se combine pas avec `--due-before` / `--due-after`) |
| `--has-notes`, `--no-notes` | tâches qui ont au moins une note, ou aucune |
| `--has-files`, `--no-files` | tâches qui ont au moins une pièce jointe, ou aucune |
| `--started`, `--not-started` | tâches démarrées (`task start`), ou jamais démarrées ; avec `--status todo` : les tâches en cours |
| `--done-after DATE`, `--done-before DATE` | terminées à partir de / au plus tard à cette date, **incluse** (voir ci-dessous) |
| `--sort alpha\|status\|priority\|due` | critère de tri |
| `--overdue-first`, `--no-overdue-first` | regroupe (par défaut) ou non les retards en tête |
| `--limit N`, `--start N` | tranche de la liste (`--start` commence à 1, comme la numérotation affichée) |
| `--pager`, `--no-pager` | utilise ou non un pager (par défaut : oui, si l'affichage dépasse l'écran) |
| `--format auto\|text\|table\|plain\|json` | format de sortie (voir « Formats de sortie ») |

Notes :

- Les filtres `--due-before` et `--due-after` excluent les tâches sans échéance et les tâches
  terminées, sauf avec `--status done`.
- `--done-after` / `--done-before` portent sur la date de fin : `AAAA-MM-JJ`, `aujourd'hui`, `hier`,
  ou une durée écoulée (`7d`, `2w`, `1m`, `1y` = il y a 7 jours, 2 semaines…). Les dates futures sont
  refusées. Les tâches sans date de fin (anciennes tâches terminées) sont exclues.
- Sans `--sort`, l'ordre est déterministe : tâches à faire avant terminées, puis échéance, puis
  priorité (haute d'abord), puis date de création.
- La numérotation affichée est la position dans la liste filtrée, **pas** un identifiant : pour
  `done`, `remove`, etc., utilisez l'identifiant `(id: …)`.
- Le pager (`less`, ou la commande de `$PAGER`) n'est utilisé que dans un terminal et seulement si
  la liste dépasse l'écran. Il n'intervient jamais en mode JSON ni dans un pipe.

### Terminer, rouvrir, modifier, supprimer

Les commandes qui ciblent une tâche acceptent un **préfixe d'identifiant** (affiché dans `list`),
à condition qu'il soit unique.

```bash
todo show a1b2c3            # détail complet d'une tâche
todo show a1b2c3 --format json | jq '.notes[].texte'   # le même, en JSON (un objet, comme dans `list --format json`)
todo done a1b2c3            # terminer (enregistre la date de complétion)
todo done a1b2c3 d4e5f6     # ... ou plusieurs tâches d'un coup
todo task undone a1b2c3          # rouvrir
todo task edit a1b2c3 --title "Nouveau titre" --prio low --due +3d --tags "pro,dev"
todo task edit a1b2c3 --due none --tags "" --desc ""    # supprimer échéance, tags et description
todo task remove a1b2c3          # supprimer (un ou plusieurs identifiants)
```

#### Plusieurs tâches à la fois

`done` et `remove` acceptent un ou plusieurs identifiants :

```bash
todo done a1b2c3 d4e5f6 9a8b7c
todo task remove a1b2c3 d4e5f6
```

- Tous les préfixes sont résolus **avant** la moindre modification. Un identifiant inconnu ou ambigu
  est signalé, les autres sont traités quand même, et un bilan est affiché
  (« Bilan : 2 tâche(s) validée(s), 1 échec(s). »).
- Une tâche désignée deux fois n'est traitée qu'une seule fois (sinon `done` créerait deux
  occurrences d'une tâche récurrente).
- Une seule sauvegarde est faite pour tout le lot.
- Le code de sortie est `1` si au moins un identifiant n'a pas pu être traité, `0` sinon : on peut
  donc s'en servir dans un script. Terminer une tâche déjà terminée n'est pas une erreur.
  `show`, `undone` et `edit`, qui ne ciblent qu'une tâche, gardent le code `0` même si
  l'identifiant est introuvable.

#### Actions en lot par filtre

Plutôt que de recopier des identifiants, `done`, `undone`, `postpone`, `remove` et `edit` acceptent les filtres de
`list` pour désigner les tâches visées :

```bash
todo task postpone --overdue --to demain     # tout ce qui est en retard, reporté à demain
todo done --tag courses                      # toutes les tâches « courses » à faire sont terminées
todo task edit --tag pro --add-tag urgent --prio high     # ajoute un tag et change la priorité de toutes les tâches « pro »
todo task remove --status done --done-before 6m -y        # supprime les tâches terminées depuis plus de 6 mois
todo done --tag courses --dry-run            # montre les tâches visées, sans rien modifier
todo task undone --all                       # rouvre toutes les tâches terminées
```

- **Filtres** : ceux de `list` (`--tag`, `--any-tag`, `--no-tag`, `--not-tag`, `--prio`, `--not-prio`,
  `--recurring`, `--created-after` / `--created-before`, `--id`, `--search` / `--search-in`, `--overdue`, `--today`,
  `--due-before` / `--due-after`, `--no-due`, `--blocked` / `--ready`, `--has-notes` / `--no-notes`,
  `--done-after` / `--done-before`), combinés par ET. Sur `remove` et `edit`, `--status todo|done` choisit les tâches
  à faire ou terminées ; `done` et `postpone` ne visent que les tâches à faire, `undone` que les terminées.
  Sur `edit`, `--prio` est la **nouvelle** priorité (pas un filtre) : `--not-prio` reste disponible.
- **Garde-fous** : sans identifiant ni filtre, la commande refuse (code 2) ; `--all` vise toutes les tâches
  concernées et ne se combine pas avec un filtre ; identifiants et filtres ne se mélangent pas. Une sélection vide
  n'est pas une erreur (message, code 0).
- **Aperçu** : `--dry-run` liste les tâches visées sans rien modifier ; avec `--format json|plain|table`
  (et `--columns`), le même rendu que `list` (`todo done --tag x --dry-run --format json | jq`).
- **Confirmation** : à partir de `[general] batch_confirm` tâches (5 par défaut ; 0 = jamais), `todo` demande
  `(y/N)` ; `-y` / `--yes` la passe. Sans terminal pour poser la question (cron, pipe), un lot de cette taille
  s'arrête avec le code 1 tant que `-y` n'est pas donné. Des identifiants écrits à la main ne demandent jamais de
  confirmation.
- **Cohérence** : la sélection est calculée d'abord puis figée ; une seule sauvegarde pour tout le lot, donc un
  seul `todo undo`. Bilan et code de sortie comme pour plusieurs identifiants. `done` sur des tâches récurrentes crée
  une occurrence suivante par tâche ; le lot ne rattrape pas ces nouvelles occurrences.
- **`edit` en lot** : `--title` est refusé (un même titre pour toutes les tâches n'a pas de sens). `--add-tag TAGS` et
  `--remove-tag TAGS` ajoutent ou retirent des tags sans remplacer la liste (ils servent aussi sur une seule
  tâche) ; ils ne se combinent pas avec `--tags`, qui la remplace.

### Notes

Une tâche a une `description` (ce qu'il faut faire) et des **notes** : un journal daté, en ajout
seul, de ce qui se passe autour d'elle.

```bash
todo note add a1b2c3 "appelé le client, rappeler jeudi"   # ajoute une note (500 caractères au plus)
todo note list a1b2c3                                       # liste les notes de la tâche
todo note list a1b2c3 --format json | jq -r '.notes[].texte'
todo note edit a1b2c3 2 "texte corrigé"               # corrige la note n°2 (date conservée)
todo note delete a1b2c3 1                            # supprime la note n°1
todo done a1b2c3 -m "validé par Paul"                  # -m / --note : action + note en une commande
todo task undone a1b2c3 -m "le client a rappelé"
todo task postpone a1b2c3 d4e5f6 --to +3d -m "client absent"
todo task edit a1b2c3 -m "à traiter avec Julie"             # une note seule suffit pour edit
todo task remove a1b2c3 -m "doublon de a9f8e7"
```

- Chaque note enregistre sa date, son texte et l'**action** qui l'a produite (`note`, `done`,
  `undone`, `postpone`, `edit`, `start`, `unstart`) ; `show` les affiche de la plus ancienne à la plus récente, et `list`
  signale une tâche annotée par `📝N`. Il n'y a pas de note automatique : seul ce que vous écrivez
  est enregistré.
- Avec plusieurs identifiants, la même note est ajoutée à chaque tâche réellement traitée (pas à celle
  déjà terminée, ni à celle dont l'échéance ne change pas). Une note vide est refusée avant toute
  modification.
- `done` sur une tâche récurrente : la note reste sur l'occurrence terminée ; la suivante repart sans note.
- Les notes font partie de la tâche : elles suivent l'archivage (`archive`, `archive restore`), les
  sauvegardes et `undo`, apparaissent dans les sorties `--format json` (`"notes": [...]`) et sont
  incluses dans `list --search` et `archive list --search`.
- Les notes sont **numérotées** à partir de 1 (la plus ancienne) dans `todo note list ID` et `show`. `note edit ID N texte`
  remplace le texte de la note N : elle garde sa date et son origine, et reçoit une marque
  `[modifiée AAAA-MM-JJ HH:MM]` (champ `modifiee` en JSON). `note delete ID N` la supprime ; les suivantes sont
  renumérotées. Les deux sont annulables avec `undo`, et tracés au journal (`note_edited`, `note_deleted`,
  sans le texte sauf `[log] titles = true`).
- **`remove -m`** : la tâche disparaît, ses notes aussi. Le motif est donc écrit **au journal**
  (`journalctl -t todo`), avec le titre, seul souvenir de la suppression.
- Journal : l'ajout d'une note est tracé sans son texte (seulement sa longueur `note_len`), sauf si
  `[log] titles = true`.

### Pièces jointes

Une tâche peut porter des **fichiers** (contrat, facture, capture d'écran…). Ils sont **copiés** dans le stockage du
projet : la tâche reste autonome si l'original disparaît ou change. Comme les notes, les pièces sont numérotées à partir de 1.

```bash
todo attachment add a1b2c3 facture.pdf scan.png --comment "reçu en octobre"   # copie un ou plusieurs fichiers
todo attachment add a1b2c3 ~/Videos/demo.mkv --link   # ne copie rien : garde un lien vers le fichier
todo attachment check                             # fichiers manquants, modifiés ou orphelins (toutes les tâches)
todo attachment list a1b2c3                       # pièces de la tâche (sans identifiant : de toutes les tâches)
todo attachment open a1b2c3 1                     # ouvre la pièce n°1 (xdg-open), ou affiche son chemin
todo attachment save a1b2c3 1 --to ~/Documents    # en extrait une copie (--force pour écraser)
todo attachment remove a1b2c3 1                   # la détache : le fichier va à la corbeille
todo attachment gc --older-than 30d               # vide la corbeille (définitif ; sans durée : tout)
todo list --has-files                             # tâches qui ont des pièces ; `list` les marque 📎N
```

- **Stockage** : `<dossier du projet>/attachments/<id de la tâche>/<nom>` (voir *Stockage*), en 0600 dans des dossiers 0700.
  Le réglage `[attachments] dir` (ou `TODO_ATTACHMENTS_DIR`) choisit un autre dossier, par exemple sur un disque
  sauvegardé : les copies vont alors dans `<dir>/<projet>/<id de la tâche>/<nom>` (`default` pour le projet par
  défaut). `~` est accepté ; un chemin relatif part du dossier de stockage, pas du dossier courant. Le dossier
  `<dir>` n'est jamais modifié (seuls `<dir>/<projet>` et dessous passent en 0700). Les fichiers déjà copiés **ne
  sont pas déplacés** quand on change le réglage : `attachment check` les signale manquants tant que vous ne les
  avez pas copiés à la main (`mv <ancien>/attachments/* <dir>/<projet>/`). `project rename` déplace les pièces avec
  le projet, `project delete` les met dans `<dir>/.trash/<nom>-AAAAMMJJ-HHMMSS/`. Les pièces ajoutées avec `--link`
  ne sont pas concernées (elles restent où elles sont).
  Les métadonnées (nom, date, taille, empreinte SHA-256, commentaire) sont dans la tâche : elles apparaissent dans
  `show`, `--format json` (`"pieces_jointes"`) et `attachment list --format json|plain|table`, où `chemin` et
  `present` indiquent si le fichier est bien là (`lien` pour une pièce liée ; en `plain`, c'est la dernière colonne).
- **`--link`** : pour un gros fichier ou un document qui vit ailleurs (dépôt, synchronisation), la pièce ne
  copie rien et mémorise le **chemin absolu** (`lien`), la taille et l'empreinte du moment. Pas de limite de
  taille ; `open` et `save` travaillent sur le fichier d'origine, `remove` et `task remove` ne le touchent jamais.
  Contrepartie : si le fichier bouge ou change, la pièce n'est plus fiable (voir `check`).
- **`check [ID]`** : relit chaque pièce (copies et liens, tâches archivées comprises) et la compare à ce qui a été
  enregistré : `ok`, `manquant`, `modifie` (taille ou SHA-256) ou `en_corbeille` (copie retirée, récupérable) ;
  signale aussi les **fichiers orphelins** de `attachments/` (aucune pièce ne les référence). Code de sortie 1 s'il
  y a une pièce manquante ou modifiée ; orphelins et fichiers en corbeille sont des informations. `--format plain` :
  `id`, `numero`, `nom`, `etat`, `chemin` (les orphelins ont l'état `orphelin` et un numéro vide) ; `json` :
  `{"verifiees", "ok", "en_corbeille", "manquantes", "modifiees", "orphelins", "pieces"}`.
- **Nom** : celui du fichier, sans dossier ; un nom déjà pris par une autre pièce de la tâche devient `nom-2.ext`,
  `nom-3.ext`… Les caractères de contrôle sont remplacés, un nom qui commence par un point reçoit un `_`.
- **Limites** : `[attachments] max_size` (10 Mo par défaut ; 0 = pas de limite) ; commentaire de 200 caractères au
  plus. Tous les fichiers sont vérifiés avant la première copie : un seul invalide et rien n'est joint.
  Un lien symbolique est suivi à la copie, jamais à l'ouverture.
- **`open`** : lance `[attachments] opener` s'il est défini (`less`, `evince`… ; la commande garde le terminal),
  sinon `xdg-open` dans une session graphique, sinon affiche seulement le chemin du fichier (utile en terminal seul :
  `less "$(todo attachment open ID 1 --format plain)"`).
- **Corbeille et `undo`** : les sauvegardes et `undo` ne portent que sur la base, pas sur les fichiers. Pour que
  `undo` reste cohérent, rien n'est effacé tout de suite : `attachment remove`, `task remove` et `archive purge`
  déplacent les fichiers dans `attachments/.trash/`, et un fichier absent y est cherché et remis en place à
  l'accès (`open`, `save`). Seul `attachment gc` vide la corbeille (confirmation, `-y` pour la passer) ; après
  cela, `undo` rend la tâche mais plus ses fichiers. L'archivage laisse les fichiers en place.
- **Projets** : chaque projet a ses pièces ; `task move` emmène les fichiers avec la tâche.
- **Sauvegardes** : le dossier `attachments/` n'est **pas** dans les sauvegardes de la base ; sauvegardez-le avec
  `rsync` ou l'outil de votre choix. `data export` n'emporte que les métadonnées (aucun fichier) et `data import
  --update` conserve les pièces de la tâche existante.

### Vues enregistrées

Une **vue** mémorise une commande de lecture et ses options sous un nom, pour la rejouer en une ligne. Les vues sont propres
à chaque projet.

```bash
todo view save retards --overdue --prio high --sort due    # `list` est sous-entendu quand on ne donne que des options
todo view save semaine agenda --days 7                       # ou une autre commande de lecture : next, agenda, report …
todo view run retards                                        # = todo list --overdue --prio high --sort due
todo view run retards --format json                          # des options en plus s'ajoutent (et l'emportent)
todo view list                                               # les vues du projet (--format text|table|plain|json)
todo view show retards                                       # la commande équivalente : todo list --overdue …
todo view rename retards urgent
todo view remove urgent
```

- **Commandes mémorisables** : seulement des lectures — `list` (ou `task list`), `next`, `agenda`, `stats`, `report …`. Une
  commande qui modifie quelque chose (`done`, `add`…) est refusée à l'enregistrement.
- **Validation** : la ligne est analysée à l'enregistrement, une option invalide est refusée tout de suite. Elle est
  mémorisée telle que tapée et rejouée par le même analyseur que la commande d'origine : tout nouveau filtre fonctionne sans
  migration. Les options propres à `view save` (`--replace`, `--format`) se placent **avant** le nom.
- **Nom** : lettres, chiffres, `-` et `_` (40 caractères au plus). Enregistrer sous un nom existant demande `--replace`.
- **Projets** : `todo -p travail view save …` ou `todo view save … -p travail` ; `view run NOM -p travail` lit les vues de
  `travail`. Les options globales (`--no-color`, `--log-level`…) s'appliquent aux vues comme aux autres commandes.
- **Stockage** : `views.json` dans le dossier du projet (voir *Stockage*), en 0600, écrit de façon atomique. Ce sont des
  préférences et non des tâches : ni sauvegardées avec la base, ni concernées par `undo`, `restore` ou `reset`, ni exportées ;
  elles suivent le projet quand il est renommé ou mis à la corbeille. Un fichier illisible n'est jamais écrasé.
- **Hooks** : les vues ne déclenchent aucun hook ; `view run` rejoue une lecture et ne modifie rien.
- La complétion du shell propose les noms des vues du projet visé.

### Hooks

Un **hook** est une commande de votre choix lancée automatiquement **après** une commande qui a modifié des tâches
(notification, synchronisation, journal personnel…). Rien n'est lancé tant qu'aucun hook n'est défini.

```ini
[hooks]
on_done = notify-send "todo" "Terminée"
on_add = sh -c 'echo "$TODO_PROJECT: $TODO_TITLE" >> ~/todo-ajouts.log'
on_change = rsync -a ~/.local/share/todo/ serveur:todo/
```

- **Événements** : `on_add`, `on_done`, `on_undone`, `on_start`, `on_unstart`, `on_edit`, `on_postpone`, `on_remove`, `on_move`
  (une exécution par tâche touchée) et `on_change` (après toute commande qui modifie quelque chose, y compris `undo`, `import`
  ou `archive` ; une seule exécution si la commande ne vise aucune tâche). Le hook propre à la commande passe avant `on_change`.
- **Pas de shell** : la commande est découpée comme le fait un shell, puis lancée directement. Pour des variables, des pipes ou
  des redirections, écrivez `sh -c '…'`.
- **Données** : jamais insérées dans la commande (un titre ne peut donc pas injecter de code), mais fournies par l'environnement
  — `TODO_EVENT`, `TODO_ID`, `TODO_TITLE`, `TODO_PROJECT`, `TODO_COUNT`, `TODO_IDS` (liste séparée par des virgules) — et par
  l'entrée standard, qui reçoit la tâche en JSON (comme `show --format json`) ; pour une tâche supprimée ou déplacée, seulement
  `{"id", "titre"}`.
- **Lots** : au-delà de 20 tâches touchées, une seule exécution a lieu, avec `TODO_COUNT` et `TODO_IDS` (entrée standard :
  `{"event", "ids"}`).
- **Garde-fous** : un hook ne change jamais le code de sortie de `todo` ; un échec, une commande introuvable ou un dépassement de
  `timeout` donnent seulement un avertissement sur stderr (et une ligne `WARNING … hook` dans le journal). La sortie standard du
  hook est renvoyée sur stderr, pour ne pas polluer `--format json`. Un hook qui appelle `todo` ne déclenche pas d'autre hook
  (`TODO_IN_HOOK=1`). Rien n'est lancé pour une lecture ni pour `--dry-run`. `TODO_HOOKS_ENABLED=0` coupe tout.
- **Confiance** : un hook s'exécute avec vos droits ; il vient de votre configuration ou de votre environnement, jamais du contenu
  des tâches.

#### Exemples

Commande directe (texte fixe, aucune donnée de la tâche) :

```ini
[hooks]
on_done = notify-send "todo" "Une tâche est terminée"
```

Avec `sh -c`, pour lire les variables ; les apostrophes simples empêchent le shell *appelant* de les développer, c'est le
`sh` lancé par le hook qui le fait, et le titre reste une simple donnée :

```ini
[hooks]
on_done = sh -c 'notify-send "Terminée" "$TODO_TITLE"'
on_add  = sh -c 'echo "$(date +%F) [$TODO_PROJECT] $TODO_TITLE" >> ~/todo-ajouts.log'
```

Script shell lisant la tâche en JSON sur l'entrée standard (ici avec `jq`), `~/bin/todo-hook.sh` (à rendre exécutable) :

```sh
#!/bin/sh
priorite=$(jq -r '.priorite')
echo "$TODO_EVENT: $TODO_TITLE (priorité $priorite)" >> ~/todo-activite.log
```

```ini
[hooks]
on_change = /home/vous/bin/todo-hook.sh
```

Programme Python, `~/bin/todo_hook.py` :

```python
#!/usr/bin/env python3
import json, os, sys

evenement = os.environ["TODO_EVENT"]       # add, done, remove…
projet = os.environ["TODO_PROJECT"]
if int(os.environ["TODO_COUNT"]) > 20:     # lot : {"event": …, "ids": […]}
    print(f"{evenement}: {len(json.load(sys.stdin)['ids'])} tâches dans {projet}", file=sys.stderr)
else:
    tache = json.load(sys.stdin)           # la tâche complète (ou {"id", "titre"} si elle n'existe plus)
    print(f"{evenement}: {tache['titre']} (échéance {tache.get('date_echeance')})", file=sys.stderr)
```

```ini
[hooks]
on_add = python3 /home/vous/bin/todo_hook.py
```

Quelques rappels : donnez des **chemins absolus** (`~` n'est développé que par un shell) ; ce que le hook affiche part sur
stderr ; pour garder une trace, écrivez dans un fichier. Pour voir ce que reçoit un hook, sans rien écrire :

```bash
TODO_HOOKS_ON_ADD="sh -c 'env | grep TODO_'" todo add Essai
```

#### Hooks « avant » : contrôler une action

Les hooks `on_*` réagissent **après** coup. `before_add` et `before_done` sont lancés **avant** que la commande ne modifie
quoi que ce soit, et peuvent **la refuser** :

```ini
[hooks]
before_add  = python3 /home/vous/bin/exige_tag.py      # lancé avant `add`
before_done = /home/vous/bin/verifie_terminer.sh       # lancé avant `done`, pour chaque tâche
```

- **Décision** : code de sortie 0 = l'action a lieu ; **non nul = elle est refusée**, avec le message du hook (ce qu'il écrit,
  sur la sortie standard ou d'erreur, s'affiche sur stderr) et le code de sortie 1 pour `todo`. Rien n'est écrit : pas de tâche
  créée, pas de sauvegarde, aucun hook `on_*` ni webhook (rien n'a changé).
- **Données** : mêmes variables que les autres hooks (`TODO_EVENT`, `TODO_ID`, `TODO_TITLE`, `TODO_PROJECT`, `TODO_COUNT`,
  `TODO_IDS`), plus `TODO_PHASE=before`. L'entrée standard reçoit la tâche en JSON : pour `add`, **la tâche à créer** (après
  analyse de la saisie rapide, avec l'`id` qu'elle recevra) ; pour `done`, la tâche **telle qu'elle est avant** d'être terminée.
- **Lots** : `done a b c` lance le hook une fois par tâche ; les tâches refusées restent à faire, les autres sont terminées, et
  la commande se termine par le code 1 (comme pour un identifiant introuvable). Avec `--format json`, `errors` contient
  `"hook_refused"`.
- **Par précaution, ce qui ne peut pas décider refuse** : commande introuvable, mal écrite ou dépassant `timeout` (10 s par défaut ;
  le hook tient le verrou de la base pendant qu'il tourne, restez rapide). Message explicite à chaque fois (`hook_refused`,
  `hook_unavailable`, `hook_timeout`, `hook_invalid` au journal). **Pour passer outre** en cas de panne : `TODO_HOOKS_ENABLED=0 todo add …`.
- **Où ça s'applique** : à `add` et `done` tapés par vous. Pas aux tâches créées autrement (occurrence suivante d'une tâche récurrente,
  `import`, `admin seed`) ni à `--dry-run`. Un hook qui appelle lui-même `todo` ne déclenche pas d'autre hook (`TODO_IN_HOOK`).
- Un hook « avant » ne peut que **refuser** ; il ne modifie pas la tâche.

Exemple : refuser les tâches sans tag, `~/bin/exige_tag.py` :

```python
#!/usr/bin/env python3
import json, sys

tache = json.load(sys.stdin)              # la tâche à créer
if not tache["tags"]:
    print("Ajoutez au moins un tag (#tag).")
    sys.exit(1)                           # refus : rien n'est créé
```

```bash
$ todo add "Écrire le rapport"
Ajoutez au moins un tag (#tag).
 ❌ Refusé par le hook before_add : « python3 » a retourné le code 1.
$ todo add "Écrire le rapport #pro"       # accepté
```

**Un hook « avant » ne doit pas appeler `todo`** : il s'exécute pendant que la commande tient le verrou de la base, un `todo`
lancé par le hook attendrait donc ce verrou (jusqu'au délai `timeout`, puis l'action serait refusée). Il décide d'après la tâche
reçue sur l'entrée standard et les variables `TODO_*`. Les hooks « après » (`on_*`) n'ont pas cette limite : la base est libérée
avant qu'ils ne partent, ils peuvent lancer `todo`.

#### Webhook HTTP intégré

Pour prévenir un service web, pas besoin d'écrire de hook : un **POST JSON** part vers l'adresse de votre choix
(hôte, port et chemin compris) après chaque commande qui modifie quelque chose.

```ini
[hooks]
webhook_url = http://localhost:8080/todo        # http:// ou https:// ; vide = désactivé
webhook_events = add, done, remove              # facultatif : seulement ces événements (vide ou `change` = tous)
webhook_token = mon-jeton                       # facultatif : envoyé dans « Authorization: Bearer mon-jeton »
webhook_secret = mon-secret                     # facultatif : signature HMAC-SHA256 du corps (en-tête X-Todo-Signature)
webhook_retry = true                            # garder les envois ratés dans une file et les renvoyer (défaut : oui)
```

Variables : `TODO_HOOKS_WEBHOOK_URL`, `TODO_HOOKS_WEBHOOK_EVENTS`, `TODO_HOOKS_WEBHOOK_TOKEN`. Les événements sont ceux des hooks
(`add`, `done`, `undone`, `start`, `unstart`, `edit`, `postpone`, `remove`, `move`) ; les commandes qui ne visent aucune tâche
(`undo`, `import`, `archive`…) ne sont envoyées que si `webhook_events` est vide ou contient `change`.

Corps de la requête (une requête par commande, pas par tâche), en-têtes `Content-Type: application/json`,
`X-Todo-Event: done`, `User-Agent: todo-cli/VERSION` :

```json
{"event": "done", "project": "default", "count": 1, "ids": ["0d6a0a67-16c5-4995-8e2b-eea56700c8ad"],
 "version": "3.6.0", "time": "2026-11-22T22:30:12+0100",
 "tasks": [{"id": "0d6a0a67-…", "titre": "Rapport", "statut": "TERMINE", "priorite": "high", "tags": ["pro"], "…": "…"}]}
```

`tasks` contient les tâches comme `show --format json` (réduites à `{"id", "titre"}` pour une tâche supprimée ou déplacée) ;
au-delà de 20 tâches, il est omis et seuls `count` et `ids` sont envoyés. Le corps contient aussi `delivery`, l'identifiant
unique de l'événement. Délai : `[hooks] timeout`. Comme pour les hooks, un échec donne un simple avertissement (stderr et journal)
et ne change jamais le résultat de la commande. Le webhook s'ajoute aux hooks `on_*` éventuels.

**Envois ratés : file d'attente.** Un événement dont l'envoi échoue pour une raison passagère (serveur arrêté, réseau coupé,
délai dépassé, HTTP 5xx, 408, 425, 429, ou 401/403/404 qu'un jeton ou une URL corrigés résolvent) n'est pas perdu : il est mis dans
la file du projet (`webhook_queue.json`, à côté de la base, hors sauvegardes) et **renvoyé dans l'ordre** à la prochaine commande
qui modifie quelque chose, ou tout de suite par `todo hooks flush`. Les autres refus (400, 413, 422…) sont définitifs :
l'événement est abandonné avec un avertissement.

```bash
todo hooks queue            # événements en attente : type, date, nombre d'essais, dernière erreur (--format text|table|plain|json)
todo hooks flush            # renvoie toute la file maintenant ; code 1 s'il en reste
todo hooks clear            # vide la file sans rien envoyer
```

- **Attente croissante** : 30 s, 1 min, 2 min… 1 h entre deux tentatives automatiques, pour qu'une panne ne ralentisse pas chaque
  commande du délai `timeout`. Une commande ordinaire renvoie au plus 50 événements ; `hooks flush` renvoie tout.
- **Bornes** : `webhook_queue_max` événements au plus (500 ; les plus anciens sautent) et `webhook_retention` jours (7), avec un
  avertissement quand des événements sont abandonnés. `webhook_retry = false` revient à un seul essai sans file.
- **Livraison « au moins une fois »** : un événement peut arriver deux fois (la réponse s'est perdue alors que le serveur l'avait
  reçu). Il garde le même `delivery` (corps et en-tête `X-Todo-Delivery`) à chaque essai ; le récepteur l'utilise pour ignorer un
  doublon. `X-Todo-Attempt` donne le numéro de l'essai.
- **Signature** : avec `webhook_secret`, `X-Todo-Signature: sha256=<hex>` est le HMAC-SHA256 des octets exacts du corps ; le récepteur
  le recalcule avec le même secret (et compare en temps constant) pour s'assurer que la requête vient bien de todo.
- Les files sont **par projet** (`-p PROJET`) ; l'ordre est conservé à l'intérieur d'un projet.

Pour tester sans serveur : `python3 -m http.server` ne reçoit pas de POST ; un récepteur de quelques lignes suffit :

```bash
python3 - <<'PY'
import http.server
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        print(self.headers["X-Todo-Event"], self.rfile.read(int(self.headers["Content-Length"])).decode(), flush=True)
        self.send_response(204); self.end_headers()
http.server.HTTPServer(("127.0.0.1", 8080), H).serve_forever()
PY
```

Un récepteur complet avec Flask (`pip install flask`) est fourni dans
[`examples/hooks/flask_webhook.py`](examples/hooks/flask_webhook.py) : il vérifie le jeton, valide le JSON, journalise chaque
événement (`events.jsonl`), tient à jour l'état des tâches (`tasks.json`, lisible par `GET /tasks`) et réagit aux tâches
terminées ; il vérifie aussi la signature HMAC et ignore les doublons (`delivery`). Lancement :
`TODO_WEBHOOK_TOKEN=mon-jeton TODO_WEBHOOK_SECRET=mon-secret python3 examples/hooks/flask_webhook.py`, avec
`webhook_url = http://127.0.0.1:8080/todo`, `webhook_token = mon-jeton` et `webhook_secret = mon-secret`.

#### Exemple : envoyer les modifications dans Redis

Avec `redis-cli`, un événement dans un *stream* par modification (`sh -c` pour lire les variables) :

```ini
[hooks]
on_change = sh -c 'redis-cli XADD todo:events "*" event "$TODO_EVENT" project "$TODO_PROJECT" id "$TODO_ID" title "$TODO_TITLE"'
```

Ou la tâche complète (JSON lu sur l'entrée standard) dans une clé :

```ini
[hooks]
on_add = sh -c 'redis-cli -x SET todo:derniere_tache'
```

Le script [`examples/hooks/redis_hook.py`](examples/hooks/redis_hook.py) fait mieux, sans aucune dépendance (petit client Redis
intégré) : pour chaque tâche touchée, un `XADD todo:events` (journal des événements, avec la tâche en JSON) et un
`HSET todo:tasks:<projet> <id> <json>` qui tient à jour l'état courant (`HDEL` à la suppression ou au déplacement).

```ini
[hooks]
on_change = python3 /home/vous/todo-cli/examples/hooks/redis_hook.py
```

Variables lues par le script : `REDIS_HOST` (127.0.0.1), `REDIS_PORT` (6379), `REDIS_PASSWORD`, `REDIS_STREAM` (todo:events),
`REDIS_MAXLEN` (10000). Lecture : `redis-cli XRANGE todo:events - +` ou `redis-cli HGETALL todo:tasks:default`. Avec `redis-py`
(`pip install redis`), la même chose tient en quelques lignes : `r.xadd(...)`, `r.hset(...)`, avec `json.load(sys.stdin)` pour la tâche.

### API REST

`todo serve` lance un petit serveur HTTP (JSON) pour gérer ses tâches depuis une autre machine, un script ou, plus tard, une
interface web. Flask est une dépendance **optionnelle** :

```bash
pip install flask                       # ou : pip install 'todo-cli[server]'
export TODO_SERVER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
todo serve                              # http://127.0.0.1:8765/api/v1/   (--host, --port ; [server] host, port)
```

Le serveur **ne touche pas à la base** : chaque requête lance `todo … --format json` dans un sous-processus. Verrous, hooks
(y compris les hooks « avant », qui peuvent refuser : `409`), journal, archivage automatique, `undo` et sauvegardes sont ceux
de la ligne de commande ; une tâche modifiée par l'API s'annule avec `todo undo`. Les écritures du serveur sont sérialisées.

**Sécurité.** Un jeton est obligatoire (`Authorization: Bearer …`) : sans `TODO_SERVER_TOKEN` ou `[server] token`, le serveur
refuse de démarrer. Seul `GET /api/v1/health` est public. Il écoute sur `127.0.0.1` par défaut ; pour l'exposer, placez-le
derrière un proxy HTTPS (nginx, Caddy…) : le jeton circule sinon en clair. Aucune valeur de requête n'est interprétée par un
shell ni ne peut passer pour une option du CLI. Pas de CORS : les navigateurs ne peuvent appeler l'API que depuis la même origine.

| Méthode et chemin | Rôle |
|---|---|
| `GET /health` | `{"ok": true, "version": …}` (sans jeton) |
| `GET /projects` | projets et compteurs (`project list`) |
| `GET /tasks` | liste `{"tasks": […]}` ; filtres en paramètres : `status`, `search`, `tag`, `any_tag`, `not_tag`, `prio`, `not_prio`, `due_before`, `due_after`, `created_*`, `done_*`, `sort`, `limit`, `start` ; booléens `overdue`, `today`, `no_due`, `blocked`, `ready`, `started`, `no_tag`, `has_notes`, `all_projects`… |
| `POST /tasks` | ajoute une tâche → `201`, `Location`, `ETag` |
| `GET /tasks/ID` | une tâche (identifiant complet ou préfixe), avec `ETag` |
| `PATCH /tasks/ID` | modifie ; `null` supprime `date_echeance` / `recurrence` |
| `DELETE /tasks/ID` | supprime (corbeille, `undo` possible) |
| `POST /tasks/ID/done` `undone` `start` `unstart` `postpone` `move` | actions ; corps facultatif : `note`, `at` (start), `to` (postpone : date, move : projet) |
| `GET /next`, `/agenda`, `/stats` | `next`, `report agenda`, `report stats` (`n`, `tag`, `prio`, `days`, `from`, `all_projects`) |
| `GET /views`, `/views/NOM` | vues enregistrées et leur exécution |

`?project=NOM` (sur toutes les routes sauf `health`) choisit le projet, sinon c'est le projet courant. Les corps JSON reprennent
les noms de champs de la sortie : `titre`, `description`, `priorite`, `date_echeance`, `tags` (liste), `recurrence`, `apres`
(liste d'identifiants) ; `PATCH` accepte en plus `ajouter_tags`, `retirer_tags`, `note`. À l'ajout, le titre est pris tel
quel ; `"saisie_rapide": true` active la saisie rapide (`Appeler Paul demain !high #pro`).

```bash
H="Authorization: Bearer $TODO_SERVER_TOKEN"; API=http://127.0.0.1:8765/api/v1
curl -H "$H" -X POST -d '{"titre": "Appeler Paul", "priorite": "high", "date_echeance": "demain"}' \
     -H 'Content-Type: application/json' $API/tasks
curl -H "$H" "$API/tasks?status=todo&tag=pro&limit=10"
curl -H "$H" -X POST $API/tasks/3f2a/done                      # préfixe d'identifiant accepté
```

```python
import json, os, urllib.request
def appel(methode, chemin, corps=None):
    r = urllib.request.Request("http://127.0.0.1:8765/api/v1" + chemin, method=methode,
        data=json.dumps(corps).encode() if corps is not None else None,
        headers={"Authorization": "Bearer " + os.environ["TODO_SERVER_TOKEN"], "Content-Type": "application/json"})
    with urllib.request.urlopen(r) as rep:
        return json.load(rep)
tache = appel("POST", "/tasks", {"titre": "Faire les courses", "tags": ["maison"]})["tasks"][0]
appel("POST", f"/tasks/{tache['id']}/done")
```

**Modifications concurrentes (`ETag`).** `GET /tasks/ID` renvoie un `ETag` (empreinte de la tâche). Une écriture
(`PATCH`, `DELETE`, action) qui envoie `If-Match: "<etag>"` n'est appliquée que si la tâche n'a pas changé depuis : sinon `412
Precondition Failed`, avec l'`ETag` courant. Sans `If-Match`, l'écriture est inconditionnelle. La vérification est faite
sous le verrou du serveur : elle protège des autres clients de l'API, pas d'un `todo` lancé en même temps dans un terminal.

**Erreurs.** Corps `{"error": {"code": "unknown_id", "message": "…"}}` ; `code` reprend les raisons du journal. `400` requête
mal formée ou paramètre inconnu, `401` jeton, `404` tâche, projet ou vue inconnus, `409` conflit (hook « avant » qui refuse,
dépendance, ambiguïté d'identifiant), `412` `If-Match`, `413` corps trop gros, `422` valeur invalide (date, priorité…),
`503` base verrouillée, `504` délai dépassé. Une action qui ne change rien (tâche déjà terminée) répond `200` avec `count: 0`.

Réglages `[server]` : `host` (127.0.0.1), `port` (8765), `token`, `timeout` (30 s par requête), `max_body` (64 Ko).
Le serveur intégré (Werkzeug, multi-threads) suffit pour un usage personnel. Avec un autre serveur WSGI, gardez **un seul
processus** (les écritures sont sérialisées par un verrou de processus), par exemple :
`gunicorn -w 1 --threads 4 -b 127.0.0.1:8765 'todo_cli.serveur:creer_application()'`.

### Interface web

Le même `todo serve` sert, à la racine, une interface web (Flask + Jinja + Bootstrap 5) : `http://127.0.0.1:8765/`. On s'y
connecte avec le **jeton du serveur** (celui de l'API). Elle offre : la liste des tâches (recherche, tag, statut, priorité, tri),
l'ajout (case « saisie rapide » pour `Appeler Paul demain !high #pro`), la fiche d'une tâche (modifier, notes, reporter,
déplacer vers un autre projet, démarrer, terminer, supprimer), l'agenda (7, 14 ou 30 jours), les statistiques, les vues
enregistrées (menu « Vues ») et le changement de projet (menu en haut à droite). L'affichage suit le thème clair ou sombre du
système et s'adapte au téléphone.

Comme l'API, l'interface ne touche pas à la base : chaque action lance le CLI (hooks, journal, verrous et `todo undo` inclus ;
un hook « avant » qui refuse s'affiche comme un message d'erreur). Une fiche modifiée ailleurs entre l'ouverture du formulaire
et l'enregistrement n'est pas écrasée : un message demande de la relire.

**Sécurité.** Cookie de session signé (HttpOnly, SameSite=Lax, 12 h) dont la clé dérive du jeton : changer le jeton déconnecte
tout le monde. Jeton CSRF sur chaque formulaire, échappement automatique de Jinja (un titre contenant du HTML s'affiche tel
quel), en-têtes `Content-Security-Policy` (aucun script ni style en ligne), `X-Frame-Options: DENY`, `Cache-Control: no-store`,
redirections limitées au site. Derrière un proxy HTTPS, le cookie reste utilisable ; pensez à le servir en HTTPS dès que le
serveur n'est pas sur `127.0.0.1`.

**Bootstrap** est chargé depuis le CDN jsDelivr (version fixée, empreintes SRI) : le navigateur a besoin d'un accès à Internet.
Sans lui, les pages restent utilisables mais sans mise en forme. `[server] web = false` (ou `TODO_SERVER_WEB=0`) ne sert que l'API.

### Déploiement (production) et OpenAPI

`todo serve` est le serveur de développement de Flask. Pour un usage permanent : **gunicorn** (un seul processus, plusieurs
threads) lancé par **systemd**, derrière un proxy **HTTPS** (Caddy ou nginx), avec `TODO_SERVER_PROXY=1` (cookie de session
« Secure », en-têtes `X-Forwarded-*`). Le guide complet (installation, jeton, unité systemd durcie, configurations Caddy et
nginx, tunnel SSH, sauvegardes, mise à jour) est dans [`docs/deploiement.md`](docs/deploiement.md) ; en voici l'essentiel :

```bash
pip install 'todo-cli[deploy]'          # Flask + gunicorn
TODO_SERVER_TOKEN=… TODO_SERVER_PROXY=1 gunicorn --workers 1 --threads 8 --timeout 60 \
    --bind 127.0.0.1:8765 'todo_cli.serveur:creer_application()'
```

**Un seul `--workers`** : les écritures et la vérification `If-Match` sont sérialisées par un verrou de processus.

L'API est décrite en **OpenAPI 3.0** (`todo_cli/openapi.json`), servie sans jeton sur `GET /api/v1/openapi.json` : importable dans
Swagger UI, Redoc, Postman, Insomnia ou `openapi-generator` pour produire un client dans un autre langage. Le serveur propose aussi
sa propre **Swagger UI** sur `/api/v1/docs` (page publique ; le bouton « Authorize » prend le jeton ; Swagger UI est chargé depuis jsDelivr, avec
version fixée et empreintes SRI, donc le navigateur doit pouvoir joindre ce CDN). Les tests vérifient que
le document décrit exactement les routes réelles et que les réponses respectent ses schémas. Réglage `[server] proxy`
(`TODO_SERVER_PROXY`) : derrière un proxy HTTPS de confiance seulement.

### Interface texte (TUI)

`todo tui` ouvre une interface en terminal (curses) qui est un **client de l'API REST** : elle marche en SSH et peut parler à un
serveur `todo serve` situé sur une autre machine.

```bash
pip install requests                      # ou : pip install 'todo-cli[tui]'
export TODO_CLIENT_TOKEN="…"              # le jeton du serveur (à défaut TODO_SERVER_TOKEN ou [client] token)
todo tui                                  # serveur sur http://127.0.0.1:8765
todo tui --url https://todo.example.org -p perso
```

| Touches | Action |
|---|---|
| `j` `k` `↑` `↓` `PgUp` `PgDn` `Home` `End` | naviguer |
| `Entrée` | fiche de la tâche (`Échap` pour revenir) |
| `a` | ajouter, en saisie rapide (`Appeler Paul demain !high #pro`) |
| `d` `s` `p` `m` `x` | terminer ou rouvrir · démarrer ou arrêter · reporter · déplacer · supprimer |
| `e` `n` `!` | modifier le titre · ajouter une note · changer la priorité (dans la fiche aussi : `D` description, `w` échéance, `t` tags) |
| `/` `t` `f` `F` `o` `c` | rechercher · tag · statut · priorité · tri · réinitialiser les filtres |
| `P` | changer de projet |
| `g` `S` | agenda · statistiques |
| `r` `?` `q` | recharger · aide · quitter |

Les appels réseau tournent dans un fil : l'écran reste vivant pendant que le serveur répond. Les modifications faites depuis une
fiche envoient `If-Match` : si la tâche a changé ailleurs entre-temps, elle est relue au lieu d'être écrasée. Réglages
`[client]` : `url`, `token`, `timeout`. Le jeton ne se passe jamais en argument (visible dans `ps`) ; `config show` le masque.
Le client Python (`todo_cli.client.Client`) peut aussi s'utiliser seul dans un script.

### Suivi du temps

`todo` retient le moment où une tâche est **démarrée** et celui où elle est **terminée**. Ce n'est pas un chronomètre :
on peut avoir plusieurs tâches en cours en même temps, et le délai est **calendaire** (du démarrage à la fin, nuits et
week-ends compris), pas un temps de travail effectif.

```bash
todo task start a1b2c3                      # démarre maintenant (une ou plusieurs tâches : start a1b2c3 d4e5f6)
todo task start a1b2c3 --at 14:30           # rattrape un oubli : 14:30 aujourd'hui, hier 9:15, 2026-11-20 16:00, 2d 10:00
todo task start --tag pro --not-started     # par filtre, comme `done` (aperçu --dry-run, confirmation en lot)
todo task unstart a1b2c3                    # annule un démarrage posé par erreur
todo done a1b2c3                            # termine : le délai démarrage → fin est connu
todo list --started --status todo           # les tâches en cours
todo report active                          # ... avec le temps écoulé, la plus ancienne d'abord
todo report cycle --since 1m --by tag       # délais moyen, médian, min et max des tâches terminées, par tag
```

- **Pas de nouveau statut** : « en cours » se déduit (démarrée et pas terminée). Le contrat `todo` / `done` ne change pas, et
  terminer une tâche jamais démarrée reste possible (aucun délai n'est alors calculé).
- **`--at`** : `HH:MM` (aujourd'hui) ou une date **passée** suivie de `HH:MM` (`hier`, `AAAA-MM-JJ`, `3d` = il y a 3 jours) ;
  un instant futur est refusé. Une tâche déjà démarrée garde son instant : `unstart` puis `start --at` pour le corriger.
- **Règles** : une tâche terminée ne se démarre pas (`undone` d'abord) ; une tâche bloquée par une dépendance (`--after`) se
  démarre, avec un avertissement ; `task undone` **efface** la date de démarrage ; l'occurrence suivante d'une tâche
  récurrente repart sans démarrage ; `-m` ajoute une note (action `start` / `unstart`).
- **Affichage** : `list` marque une tâche en cours `▶ 2 j 3 h` ; `show` donne la date de démarrage et le temps écoulé, ou, une
  fois terminée, le **délai** ; colonne `started` pour `--columns`. Le champ `demarree` (`AAAA-MM-JJ HH:MM`, `null` si la tâche n'a pas
  été démarrée) figure dans les sorties JSON, `show --format plain`, l'export et l'import ; il suit les tâches archivées et déplacées.
- **`report cycle`** : ne mesure que les tâches terminées **et** démarrées ; celles qui ne l'ont pas été sont comptées à part
  (`sans_demarrage`). `--by tag` compte une tâche pour chacun de ses tags, `--by prio` la range par priorité.

### Reporter une échéance

```bash
todo task postpone a1b2c3                  # +1 jour (valeur par défaut)
todo task postpone a1b2c3 d4e5f6 --to +2d  # plusieurs tâches, de 2 jours
todo task postpone a1b2c3 --to +1w         # une semaine
todo task postpone a1b2c3 --to lundi       # date fixe
todo task postpone a1b2c3 --to 2026-12-01  # date fixe
```

`--to` accepte :

- un **décalage** `+Nd`, `+Nw`, `+Nm` ou `+Ny`, appliqué à partir de la plus tardive de l'échéance
  actuelle et d'aujourd'hui. Reporter de 2 jours une tâche en retard (ou sans échéance) donne donc
  « aujourd'hui + 2 jours », et non une date déjà passée ;
- une **date fixe**, avec les mêmes formats que `--due` (`2026-12-01`, `demain`, `lundi`…).

La commande affiche l'ancienne et la nouvelle échéance. Elle suit les mêmes règles que `done` et
`remove` pour plusieurs identifiants (bilan, une seule sauvegarde, code de sortie `1` en cas
d'échec). Une tâche terminée ne peut pas être reportée (`undone` d'abord). Pour une tâche
récurrente, les prochaines occurrences partent de la nouvelle échéance.

### Dates

`--due` (sur `add` et `edit`), `--due-before` et `--due-after` acceptent :

| Format | Exemple |
|---|---|
| Date absolue | `2026-12-25` |
| Mots | `aujourd'hui`, `demain`, `apres-demain` (accents et casse indifférents) |
| Décalage | `+3d` (jours), `+2w` (semaines), `+1m` (mois), `+1y` (années) |
| Jour de la semaine | `lundi`… `dimanche` (ou `monday`… `sunday`) : la **prochaine** occurrence, jamais aujourd'hui |

Les dates relatives sont converties en date absolue au moment de la saisie. Un décalage en mois
sur une fin de mois est ramené au dernier jour valide (31 janvier + 1 mois = 28 février).
Les dates relatives vers le passé (`hier`, `-3d`) ne sont pas encore prises en charge.

### Tâches récurrentes

```bash
todo add "Relever les compteurs" --repeat monthly --due 2026-12-01
todo task edit a1b2c3 --repeat 2w        # modifier la récurrence
todo task edit a1b2c3 --repeat none      # l'arrêter
```

Valeurs acceptées : `daily`, `weekly`, `monthly`, `yearly`, ou `3d`, `2w`, `1m`, `1y`.

- Une tâche récurrente a toujours une échéance (aujourd'hui par défaut).
- `done` termine la tâche et crée l'occurrence suivante, avec le même titre, la même description,
  la même priorité et les mêmes tags.
- L'échéance suivante part de l'échéance d'origine de la série (pas de dérive) et est toujours postérieure
  à aujourd'hui : les occurrences manquées ne s'accumulent pas. Un mois court n'entraîne pas de glissement :
  « tous les mois à partir du 31 janvier » donne 28 février, **31** mars, 30 avril, **31** mai… (champ
  `ancre` des tâches, en JSON). Modifier l'échéance (`edit --due`), la répétition ou reporter
  (`postpone`) repart de la nouvelle date. Les séries commencées avant cette correction repartent de leur
  échéance actuelle.
- Terminer une tâche avant son échéance saute à l'occurrence suivante.
- `undone` sur une tâche récurrente supprime l'occurrence qu'elle avait créée (refusé si celle-ci
  est déjà terminée).
- `remove` n'arrête pas la série : utilisez `edit --repeat none`.

### Dépendances entre tâches

Une tâche peut attendre que d'autres soient terminées avec `--after` (identifiants ou préfixes, séparés
par des virgules) :

```bash
todo add "Livrer le rapport" --after a1b2c3,d4e5f6   # à la création
todo task edit 7890ab --after a1b2c3                 # remplace les dépendances
todo task edit 7890ab --after none                   # supprime les dépendances
todo list --blocked                                  # les tâches qui attendent encore
todo list --ready                                    # les tâches à faire qui ne sont pas bloquées
```

- Une tâche à faire est **bloquée** tant qu'au moins une de ses dépendances est encore à faire. `list` la
  marque `🔒 après a1b2c3` ; `next` ne la propose jamais (et indique combien de tâches attendent quand il
  ne reste que celles-là).
- Une dépendance **terminée, archivée ou supprimée** ne bloque plus : la tâche est libre. Rouvrir une
  dépendance (`undone`) la bloque de nouveau.
- Les dépendances **circulaires** (une tâche qui s'attendrait elle-même, directement ou par d'autres) sont refusées.
- `done` reste possible sur une tâche bloquée, avec un avertissement.
- L'occurrence suivante d'une tâche récurrente n'hérite pas des dépendances.
- `show` détaille chaque dépendance et son état ; en `plain`, `apres<TAB>id1,id2`. En `json`, `apres` liste
  les identifiants et `bloquee_par` (dans `list` et `next`) ceux qui bloquent encore. Colonnes `after` et
  `blocked` disponibles avec `--columns`.

### Rappel des tâches en retard

```bash
todo reminder check                 # retards et tâches du jour ; rien d'affiché s'il n'y en a pas
todo reminder check --soon 3        # + les échéances des 3 prochains jours
todo reminder check --limit 10      # 10 tâches listées au plus (5 par défaut)
todo reminder check --once-a-day    # une seule fois par jour
todo reminder check --write-status  # n'affiche rien ; met à jour un résumé d'une ligne (pour cron)
todo reminder disable       # coupe les rappels ; `reminder enable` les réactive ; `reminder status` indique l'état
```

`remind` est **silencieuse quand il n'y a rien à signaler** et ne modifie jamais les tâches (ni
sauvegarde). Les tâches sont classées comme dans `next` : retards d'abord (priorité haute, puis les
plus anciens), puis tâches du jour. L'en-tête compte tout, même au-delà de `--limit`.

`--once-a-day` n'affiche le rappel qu'une fois par jour : le premier terminal ouvert après qu'il y a
quelque chose à signaler. S'il n'y a rien, la journée n'est pas « consommée » : un retard qui
apparaît plus tard dans la journée sera affiché au terminal suivant.

#### À l'ouverture du terminal

Ajoutez à `~/.bashrc`, en gardant le test d'interactivité pour ne rien afficher dans `scp`, `rsync`
ou les scripts :

```bash
if [[ $- == *i* ]] && command -v todo >/dev/null; then
    todo reminder check --once-a-day
fi
```

#### Avec cron

Un job `cron` n'a pas de terminal : sa sortie part par e-mail local, ou est perdue si aucun serveur de
messagerie n'est installé (cas d'une Debian de base). Deux usages :

```cron
# crontab -e
# 1. Mise à jour du résumé d'une ligne toutes les 15 minutes (aucune sortie, donc aucun e-mail)
*/15 * * * *  /home/vous/bin/todo reminder check --write-status

# 2. Rappel complet par e-mail local, en semaine à 9 h (nécessite un serveur de messagerie local)
0 9 * * 1-5   /home/vous/bin/todo reminder check
```

Utilisez le chemin complet de `todo`, `cron` n'ayant pas votre `PATH`. Si vous avez redirigé le stockage
avec `TODO_DB_DIR`, définissez-la aussi dans la crontab.

`--write-status` écrit un résumé d'une ligne, sans couleur (`⚠ 2 en retard · 1 aujourd'hui `), dans
`~/.local/share/todo/remind_status` ; le fichier est vide quand il n'y a rien. Pour l'afficher dans
l'invite du shell sans lancer Python à chaque commande :

```bash
# ~/.bashrc
PS1='$(cat ~/.local/share/todo/remind_status 2>/dev/null)\u@\h:\w\$ '
```

#### Désactiver les rappels

- `todo reminder disable` coupe les rappels de façon durable : `remind`, `--once-a-day` et
  `--write-status` deviennent muets, et le résumé de l'invite est vidé tout de suite. Les lignes de
  `~/.bashrc` et de la crontab peuvent rester en place. `todo reminder enable` les remet en route ;
  `--status` indique l'état.
- La variable d'environnement `TODO_NO_REMIND` (non vide) coupe les rappels dans une session
  seulement, par exemple `TODO_NO_REMIND=1 bash`. Le réglage `[remind] enabled = false` du fichier de
  configuration les coupe aussi (voir *Configuration*).
- Le reste du programme n'est pas concerné : `list`, `next`, `agenda`… fonctionnent normalement.

Les fichiers d'état (`remind_off`, `remind_last`, `remind_status`) sont dans le dossier de stockage,
hors de la base : ils ne sont ni sauvegardés ni modifiés par `restore` ou `reset`.

#### Sortie JSON (jq)

`todo reminder check --format json` émet **toujours** un document JSON, même quand il n'y a rien à signaler
(le mode texte, lui, reste muet) : un script peut donc l'analyser sans cas particulier. Le nombre de
tâches n'est pas limité (`--limit` ne s'applique qu'au texte) ; `--soon N` fonctionne comme en texte.

```bash
todo reminder check --format json | jq '.compteurs.retards'
todo reminder check --format json --soon 3 | jq -r '.retards[] | "\(.jours_restants)j \(.titre)"'
```

Le document contient `date`, `actif`, `desactive_par` (la liste des interrupteurs qui coupent les
rappels), `bientot_jours`, `compteurs` et trois listes `retards`, `aujourdhui`, `a_venir`. Chaque
tâche a les champs de `list --format json` plus `jours_restants` (négatif = en retard). Si les rappels
sont désactivés, les listes sont vides et `desactive_par` en donne la raison.

Avec `--enable`, `--disable` ou `--status`, `--format json` décrit l'état des rappels :
`{"actif": …, "desactive_par": […], "dernier_rappel": …}`. Il ne se combine pas avec `--once-a-day`
ni `--write-status` (erreur, code 1).

### La prochaine tâche

```bash
todo next                    # la tâche à traiter maintenant
todo next -n 3               # les trois prochaines
todo next --tag pro --prio high
todo next --format json
```

Classement des tâches à faire : d'abord celles **en retard**, puis celles **du jour**, puis les
autres ; dans chaque groupe, la priorité haute d'abord, puis l'échéance la plus proche (les tâches
sans échéance en dernier), puis la date de création. Les tâches terminées sont ignorées.

### Agenda

```bash
todo agenda                      # 7 jours à partir d'aujourd'hui
todo agenda --days 14            # deux semaines
todo agenda --from lundi --days 7   # la semaine prochaine
todo agenda --format json        # sortie JSON (compatible jq)
```

Les tâches **à faire** sont regroupées par jour d'échéance. Chaque jour de la fenêtre apparaît, même
sans tâche (« rien de prévu »). Au sein d'un jour, la priorité haute passe en premier.

- Une section **En retard** précède les jours quand la fenêtre commence aujourd'hui ou avant ; elle
  est omise avec un `--from` situé dans le futur.
- Le pied de page compte les tâches **plus tard** (après la fenêtre) et **sans échéance**.
- Une tâche récurrente apparaît une seule fois, à son échéance actuelle : les occurrences futures
  ne sont pas projetées.
- `--days` va de 1 à 366 ; `--from` accepte les mêmes formats que `--due`. Le pager automatique et
  `--no-pager` fonctionnent comme pour `list`.

### Formats de sortie

`--format` choisit la forme de la sortie de `list`, `show`, `next`, `agenda`, `archive list`, `note list`,
`report stats`, `config show` et `reminder` (les commandes d'écriture ont leur propre sortie JSON, voir plus bas) :

| Format | Pour | Contenu |
|---|---|---|
| `text` | lire dans un terminal | l'affichage décoré (émojis, couleurs, titres, pied de page) |
| `table` | lire, de façon compacte | un tableau encadré aux colonnes alignées, sans couleur ; la colonne la plus large est tronquée (`…`) pour tenir dans le terminal |
| `plain` | enchaîner des commandes | une ligne par enregistrement, champs séparés par une **tabulation**, sans couleur, titre ni pied de page ; rien si le résultat est vide |
| `json` | scripts et `jq` | documents JSON (inchangé) |

**Choix automatique** : sans `--format`, la sortie est en `text` dans un terminal et en `plain` dans un pipe
ou une redirection. Le défaut se règle par `[general] format` (`auto`, `text`, `table` ou `plain`) ou la
variable `TODO_FORMAT` ; l'option l'emporte sur les deux.

```bash
todo list --status todo | grep -i facture                      # pipe : plain automatiquement
todo list | cut -f1,6                                          # identifiant et titre
todo list --tag pro | awk -F'\t' '$3 == "high" {print $1}' | xargs todo done
todo show a1b2c3 | grep '^echeance'
todo list --format table                                       # tableau dans le terminal
todo list --columns id,created,title                           # choisir les colonnes (tableau, ou plain dans un pipe)
todo list --format plain --columns id,title | grep -i budget
```

**Choisir les colonnes** (`--columns`, sur `list`, `next` et `archive list`, pour `table` et `plain`) : noms
séparés par des virgules, affichés dans l'ordre indiqué. Colonnes disponibles : `id`, `status`, `prio`,
`due`, `tags`, `title`, `notes`, `files` (nombre de pièces jointes), `started` (instant de démarrage, `AAAA-MM-JJ HH:MM`), `created`, `done`, `archived`, `recurrence`, `description`, `after`, `blocked`, `project` (vide hors `--all-projects` ; les trois
dates s'affichent `AAAA-MM-JJ`, vides si absentes). L'`id` est obligatoire : il est ajouté en tête s'il
manque. Sans `--format`, `--columns` donne un tableau dans un terminal et du `plain` dans un pipe ;
avec `--format text` ou `json`, il est refusé (le JSON contient déjà tous les champs).

**Sortie JSON des commandes d'écriture** : `add`, `task edit`, `done`, `task undone`, `task start`, `task unstart`,
`task postpone`, `task move` et `task remove` acceptent `--format json`. La commande s'exécute normalement, mais ses
messages (« ✅ Tâche ajoutée… », avertissements, erreurs) partent sur **stderr** ; **stdout** ne reçoit qu'un objet JSON,
pratique pour un script ou une API qui pilote `todo` :

```bash
$ todo add "Écrire le rapport !high #pro" --format json 2>/dev/null
{"ok": true, "action": "add", "project": "default", "count": 1, "failed": 0,
 "tasks": [{"id": "0d6a0a67-16c5-…", "titre": "Écrire le rapport", "priorite": "high", "statut": "A FAIRE", "…": "…"}],
 "errors": []}
$ todo done 0d6a0a67 --format json | jq -r '.tasks[0].statut'
TERMINE
$ todo done zzzz --format json 2>/dev/null; echo $?
{"ok": false, "action": "done", "count": 0, "failed": 1, "tasks": [], "errors": ["unknown_id"], …}
1
```

- `tasks` : les tâches touchées, **relues après la commande**, comme `show --format json` (identifiant complet,
  `bloquee_par`, `suivante` = occurrence créée quand on termine une tâche récurrente). Pour `remove` et `move`, qui les font
  disparaître du projet, seulement `{"id", "titre"}` ; `move` ajoute `"to"` (projet cible).
- `ok` vaut `true` quand le code de sortie est 0 ; `errors` liste les raisons techniques des refus (`unknown_id`,
  `empty_title`, `invalid_target_project`…, celles du journal). Un lot partiel donne `ok: false`, `count` = tâches modifiées et
  `failed` = identifiants en échec. Une commande qui ne touche rien (tâche déjà terminée) donne `ok: true`, `count: 0`.
- Le code de sortie est celui de la commande ; une erreur d'usage détectée par `argparse` (code 2) n'écrit pas de JSON.
- Seule l'option **explicite** `--format json` active cette sortie : ni `[general] format` ni `TODO_FORMAT` ne la déclenchent
  (un script qui règle `TODO_FORMAT=json` pour ses `list` garde les messages des commandes d'écriture). Les autres valeurs
  (`text`, `plain`, `table`) ne changent rien. Avec `--dry-run`, `--format` règle toujours l'aperçu.
- Les hooks et le webhook se déclenchent comme d'habitude ; la sortie d'un hook va sur stderr, donc jamais dans le JSON.

**Colonnes par défaut** : le réglage `[general] columns` (variable `TODO_COLUMNS`) fixe les colonnes quand
`--columns` n'est pas donné, par exemple `todo config set general.columns id,title,due,created`. Il suit la
précédence habituelle (option > variable > fichier > défaut `id,status,prio,due,tags,title,notes`), est
validé à l'écriture et normalisé (l'`id` est ajouté en tête s'il manque). Il ne change que les colonnes : il
n'impose pas le format tableau dans un terminal (seul `--columns` le fait) et il est sans effet sur `text`
et `json`.

Le format `plain` est un contrat stable (colonnes et ordre ne changent pas) :

- `list`, `next`, `archive list` : `id` (complet), `statut` (`todo`/`done`), `priorite`, `echeance`
  (vide si aucune), `tags` (séparés par des virgules), `titre`, `notes` (nombre de notes). Ce sont les colonnes
  par défaut (mêmes que `table`, qui réduit l'id à 8 caractères) ; pour en changer, `--columns` ou le réglage
  `[general] columns` (voir ci-dessous).
- `show` : une ligne `clé<TAB>valeur` par champ renseigné (`id`, `titre`, `statut`, `priorite`, `creee`,
  `echeance`, `terminee`, `repetition`, `suivante`, `apres`, `tags`, `description`) et une ligne
  `note<TAB>date<TAB>texte` par note.
- `agenda` : `quand` (`retard` ou la date), `id`, `priorite`, `titre` ; les jours sans tâche n'apparaissent pas.
- `note list` : `numéro`, `date`, `texte`. `report stats` : `indicateur<TAB>valeur`.
- `config show` : `réglage`, `valeur`, `origine` (`défaut`, `fichier`, `variable X` ou `option`) ; par exemple
  `todo config show | awk -F'\t' '$3 != "défaut"'` liste ce qui a été modifié.
- `reminder check` : `catégorie` (`retard`, `aujourdhui` ou `a_venir`), `jours_restants`, `id`, `priorite`,
  `titre`, sans limite de nombre (comme `json`) et sans rien d'affiché quand il n'y a rien à signaler.
  `reminder status`, `enable` et `disable` : `actif<TAB>true|false`, puis une ligne `desactive_par<TAB>cause`
  par cause et `dernier_rappel<TAB>date` s'il y en a un.
- Les tabulations et sauts de ligne contenus dans un titre ou une description sont remplacés par une espace.

**Exceptions du choix automatique** : les rappels (`reminder`) restent en `text` quand rien n'est demandé,
même dans un pipe, pour que les e-mails de cron et l'invite du shell restent lisibles ; `plain` ou `table`
doivent être demandés (option, `TODO_FORMAT` ou fichier). `--once-a-day` et `--write-status` ne produisent que
du texte : ils ignorent `table` et `plain` (et refusent `json`).

Les autres commandes (`config path`, `config init`, `data export` et `import`, actions comme `add` ou `done`…)
n'ont pas de rendu tabulaire : `table` et `plain` y donnent le même affichage que `text`, et `json` reste
disponible quand elles le prévoient.

Quand le lecteur d'un pipe se ferme avant la fin (`todo list | head`), `todo` s'arrête sans message d'erreur.

### Archivage

Les tâches terminées peuvent être rangées hors de la liste, sans être supprimées :

```bash
todo archive add                      # archive toutes les tâches terminées
todo archive add --older-than 30d     # seulement celles terminées depuis au moins 30 jours
todo archive add a1b2c3 d4e5f6        # ou des tâches précises (elles doivent être terminées)
todo archive add --tag projet-x       # toutes les tâches terminées portant ce tag
todo archive add --tag projet-x --older-than 2w   # idem, terminées depuis au moins 2 semaines
todo archive list               # consulter l'archive
todo archive list --search facture     # chercher dans l'archive (mêmes règles ; `--search-in` disponible)
todo archive list --tag pro --prio high         # filtrer par tag et priorité
todo archive list --done-after 2w --has-notes   # terminées depuis 2 semaines, avec notes
todo archive list --older-than 6m --sort alpha  # terminées depuis au moins 6 mois, par titre
todo archive restore a1b2c3             # remettre une tâche dans la liste
todo archive purge --older-than 1y   # supprimer DÉFINITIVEMENT de l'archive ce qui date de plus d'un an
todo report stats --with-archive         # statistiques incluant l'historique archivé
```

- **Archiver par tag** : `archive add --tag TAGS` (répétable ou séparé par des virgules : tous les tags)
  archive les tâches **terminées** portant ce tag, par exemple à la fin d'un projet. Les tâches à faire qui le
  portent restent dans la liste (leur nombre est indiqué) : seules les tâches terminées s'archivent. Il se
  combine avec `--older-than` (ET) mais pas avec des identifiants.
- **Archivage automatique** : avec `todo config set archive.auto_days 30` (variable
  `TODO_ARCHIVE_AUTO_DAYS`), les tâches terminées depuis au moins 30 jours sont archivées **une fois par
  jour**, à la première commande qui modifie la base (`add`, `done`, `edit`…). Les commandes de lecture
  (`list`, `next`, `show`…) et celles qui touchent déjà à l'archive ou à l'historique (`archive`, `undo`,
  `restore`, `reset`, `import`) ne le déclenchent pas. Le bilan tient en une ligne sur la sortie d'erreur, une
  sauvegarde est faite (`undo` revient donc en arrière) et la date du dernier passage est gardée dans le
  fichier `archive_auto` du dossier de stockage. `0` (défaut) désactive la fonction.
- **Filtres de `archive list`** (et de `archive --list`) : `--search` / `--search-in`, les filtres de sélection de
  `list` (`--tag`, `--any-tag`, `--no-tag`, `--not-tag`, `--prio`, `--not-prio`, `--recurring`, `--no-recurring`,
  `--created-after` / `--created-before`, `--id`),
  `--has-notes` / `--no-notes`, `--done-after` / `--done-before` (date de fin), `--archived-after` /
  `--archived-before` (date d'archivage, mêmes formats), `--older-than` (terminées depuis au moins cette
  durée, comme pour `archive add`), `--sort done|archived|alpha|priority` (défaut `done`, la plus récemment
  terminée d'abord) et `--limit` / `--start`. Ils se combinent (ET).
- Les tâches archivées disparaissent de `list`, `agenda` et `stats` (sauf `--with-archive`).
- `--older-than` accepte `30d`, `2w`, `6m`, `1y` et se base sur la date de complétion. Une ancienne
  tâche terminée sans date de complétion est ignorée (son âge est inconnu) : archivez-la par
  identifiant.
- `--older-than` et des identifiants ne se combinent pas. `--list`, `--search` (et `--format json`,
  `--no-pager`) consultent l'archive, de la tâche terminée le plus récemment à la plus ancienne.
- **`archive --purge`** supprime définitivement des tâches **de l'archive** : celles désignées par
  identifiant, celles terminées depuis au moins `--older-than`, ou toute l'archive. Les cibles sont
  affichées (titres, au plus 5) et une confirmation est demandée (`-y` pour la passer, par exemple dans
  un cron) ; la liste courante n'est jamais touchée. Une sauvegarde suit, donc `todo undo` rétablit la
  purge. `--purge` ne se combine pas avec `--list`, `--search` ni les filtres de liste.
  Cette commande remplace l'ancien `clear-done` (qui supprimait d'un coup toutes les tâches terminées
  de la liste) : archivez-les d'abord (`todo archive add`), puis purgez l'archive selon l'âge voulu ; pour
  supprimer des tâches précises sans passer par l'archive, `todo task remove`.
- Seules les tâches terminées s'archivent. Pour une tâche récurrente, l'occurrence suivante reste
  dans la liste ; rouvrir l’ancienne (`task undone`) demande de la récupérer d’abord avec `archive restore`.
- Archive et liste sont **sauvegardées et restaurées ensemble** : `restore` ramène les deux à l'état
  de la sauvegarde, de sorte qu'une tâche n'apparaisse jamais des deux côtés. `reset` ne vide que la
  liste et conserve l'archive, sauf avec `reset --include-archive`.
- `archive` et `unarchive` traitent plusieurs identifiants comme `done` et `remove` (bilan, une seule
  sauvegarde, code de sortie `1` en cas d'échec).

### Statistiques

```bash
todo report stats
```

Progression, charge active par priorité, tags les plus utilisés, retards et échéances du jour,
et rythme de complétion (aujourd'hui et sur 7 jours).

### Rapports

Le groupe `report` rassemble des vues d'ensemble en lecture seule (statistiques, agenda, et les rapports ci-dessous).
Chacun existe dans les quatre formats (`text`, `table`, `plain`, `json`) et accepte `--format` et `--pager` / `--no-pager`.

```bash
todo report tags                      # tags utilisés, avec le nombre de tâches à faire et terminées
todo report tags --sort alpha --with-archive
todo report blocked                   # tâches qui attendent une dépendance (--after), et ce qu'elles attendent
todo report overdue                   # tâches en retard, les plus en retard d'abord
todo report stale                     # tâches sans échéance créées il y a au moins 30 jours
todo report stale --older-than 2w     # ... il y a au moins 2 semaines (7d, 2w, 6m, 1y, hier, AAAA-MM-JJ)
todo report done                      # bilan des tâches terminées ces 7 derniers jours, jour par jour
todo report done --since 1m --until 2w --with-archive
todo report active                    # tâches en cours (démarrées, pas terminées), la plus ancienne d'abord
todo report cycle --by tag            # délai démarrage → fin des tâches terminées, par tag (voir « Suivi du temps »)
todo report review                    # revue hebdomadaire : semaine écoulée, points à traiter, semaine à venir (voir plus bas)
```

| Rapport | Contenu | Options |
|---|---|---|
| `tags` | chaque tag avec ses tâches à faire, terminées et le total ; trié par total décroissant puis nom ; les tâches sans tag sont comptées à part | `--sort count\|alpha`, `--with-archive` |
| `blocked` | tâches à faire qui attendent au moins une dépendance encore à faire, avec les tâches attendues | — |
| `overdue` | tâches à faire dont l'échéance est passée, avec le nombre de jours de retard ; les plus en retard d'abord | — |
| `stale` | tâches à faire **sans échéance**, créées il y a au moins `--older-than` (30d par défaut), les plus anciennes d'abord : celles qu'on oublie | `--older-than DURÉE` |
| `done` | tâches terminées entre `--since` (7d par défaut) et `--until` (aujourd'hui), dates incluses, regroupées par jour, le plus récent d'abord | `--since`, `--until`, `--with-archive` |
| `active` | tâches **démarrées et pas terminées**, la plus ancienne d'abord, avec le temps écoulé | — |
| `cycle` | délai démarrage → fin (nombre, moyenne, médiane, plus court, plus long) des tâches terminées entre `--since` (30d par défaut) et `--until`, avec ou sans regroupement | `--since`, `--until`, `--by tag\|prio`, `--with-archive` |
| `review` | revue hebdomadaire (voir ci-dessous) | `--days`, `--older-than`, `--limit` |

Les dates de `--since`, `--until` et `--older-than` suivent les formats de `--done-after` : `7d`, `2w`, `1m`, `1y`,
`hier`, `aujourd'hui` ou `AAAA-MM-JJ` ; une date future est refusée. L'archive n'est lue qu'avec `--with-archive`.

Sorties `plain` (champs séparés par des tabulations, identifiant complet, rien si le rapport est vide) :

| Rapport | Colonnes |
|---|---|
| `tags` | `tag`, `a_faire`, `terminees`, `total` |
| `blocked` | `id`, `priorite`, `titre`, `attend` (identifiants des tâches attendues, séparés par des virgules) |
| `overdue` | `id`, `jours_retard`, `priorite`, `echeance`, `titre` |
| `stale` | `id`, `age_jours`, `priorite`, `titre` |
| `done` | `terminee` (date et heure), `id`, `priorite`, `titre` |
| `active` | `id`, `ecoule_minutes`, `demarree` (`AAAA-MM-JJ HH:MM`), `priorite`, `titre` |
| `cycle` | `groupe` (`tout`, un tag, `(sans tag)` ou une priorité), `nombre`, `moyenne`, `mediane`, `min`, `max` (en minutes) |

Sorties `json` : un objet par rapport. `tags` : `{"avec_archive", "tags": [{"tag", "a_faire", "terminees", "total"}],
"sans_tag": {"a_faire", "terminees"}}`. `blocked`, `overdue`, `stale` : `{"total", "taches": [...]}` (les tâches
au format de `list --format json`, plus `attend` pour `blocked`, `jours_retard` pour `overdue`, `age_jours` pour
`stale` ; `overdue` ajoute `date`, `stale` ajoute `avant`). `done` : `{"depuis", "jusqu_a", "avec_archive", "total",
"jours": [{"date", "taches": [...]}]}`. `active` : `{"date", "total", "taches": [...]}` (chaque tâche avec `ecoule_minutes`). `cycle` : `{"depuis", "jusqu_a",
"avec_archive", "par", "mesurees", "sans_demarrage", "unite": "minutes", "groupes": [{"nom", "nombre", "moyenne", "mediane", "min", "max"}],
"taches": [...]}` (chaque tâche avec `delai_minutes`).

#### Revue hebdomadaire

`todo report review` est un rapport **en lecture seule** (il ne modifie rien) à lire une fois par semaine. Il tient en six sections :

| Section | Contenu |
|---|---|
| Terminées cette semaine | tâches terminées pendant les `--days` derniers jours (7 par défaut, aujourd'hui compris), archive comprise |
| En retard | échéance dépassée, les plus en retard d'abord |
| En cours | démarrées (`task start`) et pas terminées, avec le temps écoulé |
| Bloquées | en attente d'une dépendance encore à faire |
| Qui traînent | sans échéance, créées il y a au moins `--older-than` (30d par défaut) |
| Semaine à venir | échéances des `--days` prochains jours, jour par jour ; le reste est compté (« plus tard », « sans échéance ») |

L'en-tête donne le bilan (terminées, créées, à faire, en retard). En format `text`, chaque section est limitée à `--limit` tâches (10 par
défaut) et indique la commande qui donne la suite. `plain` et `table` : une ligne par tâche, colonnes `section` (`terminee`, `retard`,
`en_cours`, `bloquee`, `traine`, `a_venir`), `id`, `priorite`, `date`, `titre`. `json` : `{"date", "depuis", "jusqu_a", "jours", "bilan",
"terminees", "en_retard", "en_cours", "bloquees", "qui_trainent", "a_venir"}` (chaque section `{"total", "taches": [...]}` ; `a_venir`
regroupe les tâches par `jours` et ajoute `plus_tard` et `sans_echeance`). Réglages `[review]` : `days`, `stale`, `limit`, `day`.
Comme les autres rapports, elle peut être enregistrée comme vue (`todo view save revue report review --days 14`).

Pour **être prévenu** : `[review] day = fri` (ou `TODO_REVIEW_DAY=fri`) fait signaler le jour de la revue par `todo reminder check`
(ligne « 📋 Jour de la revue hebdomadaire », y compris quand aucune tâche n'est en retard ; `--once-a-day` l'affiche une seule fois ;
`--write-status` l'ajoute au résumé de l'invite ; `--format json` ajoute la clé `revue`). Pour **recevoir le rapport** par courriel :
`examples/cron/revue-hebdomadaire.sh` (options : `REVUE_DEST`, `REVUE_SUJET`, `REVUE_OPTIONS`, `REVUE_PROJET`, `TODO_BIN`) :

```cron
# Rappel dans le terminal le vendredi (réglage [review] day = fri), et rapport par courriel le vendredi à 17 h
0 17 * * 5   TODO_BIN=/home/vous/bin/todo REVUE_DEST=vous@example.org /home/vous/bin/revue-hebdomadaire.sh
```

Sans commande `mail`, le script écrit le rapport sur sa sortie : `cron` l'envoie alors à `MAILTO`.

```bash
todo report overdue --format json | jq -r '.taches[] | "\(.jours_retard) j  \(.titre)"'
todo report tags --format plain | awk -F'\t' '$2 > 0 {print $1}'     # tags qui ont des tâches à faire
todo report done --since 7d --format plain | cut -f1,4                 # le bilan de la semaine pour un compte rendu
```

### Couleurs

Par défaut (`auto`), les couleurs ne sont utilisées que si la sortie est un terminal : dans un pipe
ou une redirection (`todo list | grep …`, `todo list > fichier`), aucun code d'échappement n'est écrit.
Elles sont aussi désactivées si la variable d'environnement `NO_COLOR` est définie avec une valeur
non vide ([no-color.org](https://no-color.org)) ou si `TERM=dumb`.

```bash
todo list --no-color          # désactive les couleurs
todo --no-color list          # idem : l'option peut précéder ou suivre la commande
todo list --color always      # force les couleurs, par exemple pour `| less -R`
todo list --color never       # équivaut à --no-color
```

Un choix explicite (`--color always` ou `never`) l'emporte toujours sur `NO_COLOR` et sur la
détection du terminal ; si les deux options sont données, la dernière gagne. La sortie `--format json`
ne contient jamais de couleur. En mode `auto`, les avertissements écrits sur `stderr` sont colorés
seulement si `stderr` est lui-même un terminal, indépendamment de la sortie standard
(`todo list 2> erreurs.log` n'y met aucun code d'échappement).

### Projets

Un **projet** est une liste de tâches indépendante (`perso`, `travail`…) : chacun a sa propre base, son archive,
ses sauvegardes, son `undo` et son verrou. Le projet `default` est celui d'avant la 2.18 : il reste à la racine du
stockage, sans migration. Les autres vivent dans `<stockage>/projects/<nom>/`. La configuration, le journal et
l'état du rappel sont communs à tous les projets.

```bash
todo project create travail          # crée le projet (jamais créé implicitement)
todo project list                    # projets, nombre de tâches à faire, terminées, archivées ; * = courant
todo -p travail add "Préparer la réunion"       # --project/-p : sur toutes les commandes, avant ou après la commande
todo task list --project travail
todo project use travail             # projet courant persistant ([general] project)
todo project current                 # nom et origine du projet courant
todo project rename travail bureau
todo project delete bureau           # déplace le projet dans <stockage>/.trash/ (récupérable à la main)
```

Le projet courant se choisit, de la plus forte priorité à la plus faible, par l'option `--project/-p`, la variable
`TODO_PROJECT`, le réglage `[general] project` (écrit par `project use`), sinon `default`. `todo project current`
indique le nom et l'origine (`option`, `variable TODO_PROJECT`, `fichier`, `défaut`) ; avec `--format plain`, il
n'écrit que le nom, utilisable dans un script. `config show` l'affiche aussi (`general.project`).

- Les noms sont en minuscules, chiffres, `-` et `_` (32 caractères au plus, première lettre ou chiffre).
  `default` ne peut être ni renommé ni supprimé.
- Un projet inexistant est refusé (code 1, avec une suggestion s'il ressemble à un autre), jamais créé en silence.
- `project delete` refuse le projet courant et un projet qui contient des tâches sans `--force` ; il demande
  confirmation (`-y` pour la passer, obligatoire sans terminal). Le dossier est déplacé dans `.trash/` sous le
  nom `<projet>-AAAAMMJJ-HHMMSS` : pour le récupérer, déplacez-le vers `projects/<nom>/`.
- `project rename` met aussi à jour `[general] project` s'il désignait l'ancien nom.
- Les dépendances (`--after`) ne traversent pas les projets, et `export` / `import` visent le projet choisi.
- La complétion du shell propose les projets existants pour `--project` et les commandes `project`.
- Le journal ajoute `project=NOM` à ses messages quand le projet n'est pas `default`.

#### Vues sur tous les projets

`--all-projects` (lecture seule) fait porter `list`, `next`, `agenda`, `report tags|blocked|overdue|stale|done|active|cycle` et
`stats` sur tous les projets à la fois :

```bash
todo list --all-projects --overdue          # tout ce qui est en retard, tous projets confondus
todo next --all-projects -n 3
todo report overdue --all-projects --format plain
```

- Chaque tâche indique son projet : colonne `project` (insérée juste après l'`id` en `table` et `plain`, y compris avec
  `--columns`), champ `projet` en JSON, marque `[projet]` en `text`. Sans `--all-projects`, aucune sortie ne change.
- Les identifiants affichés ne sont pas directement actionnables : utilisez-les avec le projet voulu
  (`todo done 3f2a9c1b -p travail`). Les commandes qui modifient n'acceptent pas `--all-projects`.
- `--all-projects` et `--project` s'excluent. Un verrou partagé est pris sur chaque projet.

Le **rappel** (`reminder check`, résumé d'une ligne, `--format json`) couvre tous les projets par défaut, même si
un projet courant est choisi (`project use`, `TODO_PROJECT`) : il sert à ne rien oublier. `todo reminder check
--project travail` le restreint à un projet. Les tâches y portent la marque du projet quand il en existe plusieurs
(JSON : champ `projet`) ; avec un seul projet, la sortie est identique à celle d'avant. `reminder enable|disable`
et les fichiers `remind_*` sont communs à tous les projets.

#### Déplacer des tâches entre projets

```bash
todo task move 3f2a9c1b --to travail              # une tâche (ou plusieurs identifiants) vers le projet travail
todo task move --tag pro --to travail --dry-run   # par filtre, comme done/postpone/remove (confirmation dès 5 tâches, -y)
todo task move 3f2a9c1b --to default -p travail   # dans l'autre sens : -p désigne la source
```

La tâche garde son identifiant, son statut, ses dates, ses tags, ses notes et sa récurrence. Le projet de destination
doit exister (`project create`). Les deux projets sont verrouillés pendant l'opération ; la cible est écrite avant que la
source soit modifiée, donc un incident ne peut laisser qu'un doublon, jamais perdre une tâche.

- **Dépendances** : elles ne traversent pas les projets. Une tâche déplacée n'attend plus ce qui reste dans la source,
  et ce qui l'attendait dans la source ne l'attend plus (avertissement dans les deux cas). Des tâches déplacées
  ensemble gardent leurs liens.
- **Récurrence** : l'occurrence suivante d'une tâche terminée, si elle reste dans la source, n'est plus reliée.
- **`undo`** : chaque projet a ses sauvegardes, donc `undo` ne défait un déplacement que d'un côté à la fois. Annuler dans
  la source remet la tâche dans la source sans la retirer de la cible, et inversement (`undo -p CIBLE`) ; la commande le
  rappelle après chaque déplacement.

### Annuler la dernière modification

```bash
todo undo        # revient à l'état d'avant la dernière modification
todo undo        # ... et un second `undo` la rétablit
```

`undo` s'appuie sur les sauvegardes : il indique ce qu'il change (« retirer 'X' », « rétablir 'Y' »,
« remettre dans leur état précédent 'Z' »), sans confirmation puisqu'il est lui-même réversible.
Il couvre toutes les commandes qui modifient les tâches (`add`, `done`, `edit`, `remove`,
`postpone`, `archive`, `restore`, `reset`…).

- Il ne remonte que d'**un** pas : relancer `undo` revient à l'état de départ au lieu de remonter
  plus loin. Pour revenir plus en arrière, utilisez `todo admin restore` (5 sauvegardes conservées).
- Il n'y a rien à annuler tant qu'une seule modification a été faite (aucun état antérieur) ;
  la commande renvoie alors le code de sortie `1`.
- Après un `reset`, `undo` rétablit les tâches vidées.

### Configuration

Les valeurs par défaut se règlent dans un fichier de configuration (format INI). Priorité, de la plus
forte à la plus faible :

1. l'**option** de la ligne de commande (`--limit 10`) ;
2. la **variable d'environnement** (`TODO_LIST_LIMIT=10`) ;
3. le **fichier de configuration** ;
4. la valeur **par défaut** du programme.

```bash
todo config init     # crée ~/.config/todo/config.ini : un modèle où tout est en commentaire
todo config show     # valeurs effectives et leur origine (option, variable, fichier ou défaut)
todo config path     # chemin du fichier
```

Le fichier est, par ordre de priorité : celui de l'option **`--config FICHIER`**, `$TODO_CONFIG` s'il est
défini, `$XDG_CONFIG_HOME/todo/config.ini`, puis `~/.config/todo/config.ini`. Un fichier absent n'est pas une
erreur, sauf s'il est désigné par `--config` : `todo` s'arrête alors avec le code 1 (`config set`, `config
init` et `config path` peuvent le créer ou l'afficher). `config show` indique d'où vient le chemin.

#### Lire et modifier un réglage

Les réglages se désignent par `section.clé`, comme dans `config show` (`list.limit`, `general.format`…).

```bash
todo config get list.limit                # valeur effective, seule sur une ligne : utilisable dans un script
todo config get list.limit --format json  # {"cle", "valeur", "origine", "variable"}
todo config get list.limit --file         # valeur écrite dans le fichier, sans environnement ni défaut (code 1 si absente)
todo config set list.limit 20             # vérifie la valeur et l'écrit dans le fichier (créé au besoin)
todo config unset list.limit              # retire la ligne : retour à la valeur par défaut
```

- `set` applique les règles du fichier (type, minimum, choix) : une valeur invalide est refusée et le fichier
  n'est pas touché. Les booléens (`yes`, `on`, `1`…) sont écrits `true` ou `false`.
- Seule la ligne du réglage est modifiée : commentaires, ordre et autres clés restent tels quels. Avec un
  fichier issu de `config init`, la valeur s'écrit juste sous sa valeur par défaut commentée. Un fichier
  qui n'existe pas est d'abord créé à partir du modèle commenté ; un fichier illisible n'est jamais modifié.
- Si une variable d'environnement (`TODO_LIST_LIMIT`…) définit déjà le réglage, `set` et `unset` le signalent
  sur stderr : elle l'emporte sur le fichier.
- `set` et `unset` acceptent `--format json` ; le journal garde la clé modifiée, jamais la valeur.

```bash
todo --config ~/essai.ini config set general.db_dir /tmp/essai-todo   # un environnement d'essai complet
todo --config ~/essai.ini add "Tester"
```

`--config` s'écrit en toutes lettres (pas d'abréviation) et peut se placer avant ou après la commande.

Exemple de fichier :

```ini
[general]
color = auto            # auto | always | never
format = auto           # auto | text | table | plain
pager = true
columns = id,status,prio,due,tags,title,notes   # colonnes de table/plain (list, next, archive list)
lock_timeout = 10       # secondes d'attente si la base est utilisée par une autre instance
batch_confirm = 5       # actions en lot par filtre : confirmation à partir de ce nombre de tâches (0 = jamais)

[attachments]
max_size = 10           # taille maximale d'une pièce jointe, en Mo (0 = pas de limite)
dir =                   # dossier des pièces jointes copiées (vide = attachments/ dans chaque projet)
opener =                # commande d'ouverture (less, evince…) ; vide = xdg-open, sinon seul le chemin est affiché

[hooks]
enabled = true          # false : aucun hook n'est lancé
timeout = 10            # secondes accordées à un hook
on_add =                # commande lancée pour chaque tâche ajoutée (idem on_done, on_undone, on_start, on_unstart,
                        # on_edit, on_postpone, on_remove, on_move) ; vide = rien
before_add =            # commande lancée AVANT add ; un code de sortie non nul refuse l'ajout
before_done =           # commande lancée AVANT done, pour chaque tâche ; un code non nul refuse
on_change =             # commande lancée après toute commande qui modifie quelque chose
webhook_url =           # http://hôte:port/chemin : reçoit un POST JSON après chaque modification ; vide = désactivé
webhook_events =        # add, done, remove… (séparés par des virgules) ; vide = tous
webhook_token =         # envoyé en « Authorization: Bearer … » ; vide = aucun
webhook_secret =        # signature HMAC-SHA256 du corps (X-Todo-Signature) ; vide = non signé
webhook_retry = true    # file d'attente et renvoi des envois ratés
webhook_queue_max = 500 # événements gardés au plus dans la file
webhook_retention = 7   # jours avant d'abandonner un événement de la file

[list]
limit = 30              # 0 = pas de limite
overdue_first = true

[add]
priority = medium
date_prefix = optional  # required : une date doit s'écrire @demain dans le titre

[remind]
enabled = true
limit = 5
soon = 0
```

| Section | Clé | Défaut | Variable d'environnement | Option qui l'emporte |
|---|---|---|---|---|
| `general` | `db_dir` | `~/.local/share/todo` | `TODO_DB_DIR` | — |
| `general` | `project` | `default` | `TODO_PROJECT` | `--project`, `-p` |
| `general` | `color` | `auto` | `TODO_COLOR` (puis `NO_COLOR`) | `--color`, `--no-color` |
| `general` | `format` | `auto` | `TODO_FORMAT` | `--format` |
| `general` | `pager` | `true` | `TODO_PAGER` | `--pager`, `--no-pager` |
| `general` | `keep_backups` | `5` (minimum 2) | `TODO_KEEP_BACKUPS` | — |
| `general` | `columns` | `id,status,prio,due,tags,title,notes` | `TODO_COLUMNS` | `--columns` |
| `general` | `lock_timeout` | `10` (secondes, 0 = pas d'attente) | `TODO_LOCK_TIMEOUT` | — |
| `general` | `batch_confirm` | `5` (0 = jamais de confirmation) | `TODO_BATCH_CONFIRM` | `-y` |
| `attachments` | `max_size` | `10` (Mo ; 0 = pas de limite) | `TODO_ATTACHMENTS_MAX_SIZE` | — |
| `attachments` | `dir` | *(vide : `<dossier du projet>/attachments`)* | `TODO_ATTACHMENTS_DIR` | — |
| `attachments` | `opener` | *(vide : `xdg-open` en session graphique, sinon affiche le chemin)* | `TODO_ATTACHMENTS_OPENER` | — |
| `hooks` | `enabled` | `true` | `TODO_HOOKS_ENABLED` | — |
| `hooks` | `timeout` | `10` (secondes) | `TODO_HOOKS_TIMEOUT` | — |
| `hooks` | `webhook_url` | *(vide : désactivé)* | `TODO_HOOKS_WEBHOOK_URL` | — |
| `hooks` | `webhook_events` | *(vide : tous)* | `TODO_HOOKS_WEBHOOK_EVENTS` | — |
| `hooks` | `webhook_token` | *(vide : aucun en-tête)* | `TODO_HOOKS_WEBHOOK_TOKEN` | — |
| `hooks` | `webhook_secret` | *(vide : non signé)* | `TODO_HOOKS_WEBHOOK_SECRET` | — |
| `hooks` | `webhook_retry` | `true` | `TODO_HOOKS_WEBHOOK_RETRY` | — |
| `hooks` | `webhook_queue_max` | `500` | `TODO_HOOKS_WEBHOOK_QUEUE_MAX` | — |
| `hooks` | `webhook_retention` | `7` (jours) | `TODO_HOOKS_WEBHOOK_RETENTION` | — |
| `hooks` | `before_add`, `before_done` | *(vide)* | `TODO_HOOKS_BEFORE_ADD`, `TODO_HOOKS_BEFORE_DONE` | — |
| `hooks` | `on_add`, `on_done`, `on_undone`, `on_start`, `on_unstart`, `on_edit`, `on_postpone`, `on_remove`, `on_move`, `on_change` | *(vide)* | `TODO_HOOKS_ON_DONE`… | — |
| `list` | `limit` | `0` (illimité) | `TODO_LIST_LIMIT` | `--limit` |
| `list` | `overdue_first` | `true` | `TODO_LIST_OVERDUE_FIRST` | `--overdue-first`, `--no-overdue-first` |
| `add` | `priority` | `medium` | `TODO_ADD_PRIORITY` | `--prio` (et `+`/`!priorité` dans le titre) |
| `add` | `date_prefix` | `optional` (ou `required`) | `TODO_ADD_DATE_PREFIX` | — |
| `archive` | `auto_days` | `0` (désactivé ; en jours) | `TODO_ARCHIVE_AUTO_DAYS` | — |
| `agenda` | `days` | `7` (1 à 366) | `TODO_AGENDA_DAYS` | `--days` |
| `next` | `count` | `1` | `TODO_NEXT_COUNT` | `-n`, `--count` |
| `remind` | `enabled` | `true` | `TODO_REMIND_ENABLED` | — (voir ci-dessous) |
| `remind` | `limit` | `5` | `TODO_REMIND_LIMIT` | `--limit` |
| `remind` | `soon` | `0` | `TODO_REMIND_SOON` | `--soon` |
| `log` | `level` | `info` | `TODO_LOG_LEVEL` | `--log-level` |
| `log` | `target` | `auto` | `TODO_LOG_TARGET` | — |
| `log` | `file` | `~/.local/state/todo/todo.log` | `TODO_LOG_FILE` | — |
| `log` | `socket` | `/dev/log` | `TODO_LOG_SOCKET` | — |
| `log` | `titles` | `false` | `TODO_LOG_TITLES` | — |

- Booléens : `true`/`false`, `yes`/`no`, `on`/`off`, `1`/`0` (majuscules acceptées). Dans le fichier,
  les commentaires commencent par `#` ou `;`, y compris en fin de ligne ; sections et clés ne
  distinguent pas les majuscules.
- Une variable d'environnement **vide** est ignorée, comme si elle n'était pas définie.
- **Erreurs tolérées** : une clé ou une section inconnue, ou une valeur invalide (fichier ou variable),
  est signalée sur `stderr` puis ignorée, avec une suggestion en cas de faute de frappe (« vouliez-vous
  dire 'limit' ? »). Les autres réglages s'appliquent. Un fichier à la syntaxe invalide est ignoré en
  entier, avec un avertissement.
- **Couleurs** : l'ordre est `--color` > `TODO_COLOR` > `NO_COLOR` > fichier > auto. `NO_COLOR` étant
  une variable d'environnement, elle l'emporte sur `color = always` du fichier.
- **Rappels** : `enabled = false` (ou `TODO_REMIND_ENABLED=false`) coupe les rappels, comme
  `todo reminder disable` et `TODO_NO_REMIND`. Les interrupteurs se **cumulent** : un seul suffit pour
  couper, sauf que `TODO_REMIND_ENABLED=true` l'emporte sur `enabled = false` du fichier.
- **Sortie JSON** : `todo config --format json` fonctionne pour `show` (réglages et origines),
  `path` (`{"fichier", "existe"}`) et `init` (`{"fichier", "cree", "ecrase"}` ; en cas d'échec, le
  document ajoute `erreur` — `existe_deja` ou `ecriture_impossible` — et `detail`, avec le code 1).
  Par exemple : `todo config --format json | jq -r '.reglages[] | select(.origine != "défaut") | .cle'`.
- `db_dir` et `keep_backups` sont lus au démarrage : il n'y a pas d'option de ligne de commande
  équivalente, mais `TODO_DB_DIR=/autre/dossier todo list` fonctionne pour un usage ponctuel.

### Complétion du shell

La touche Tab complète les groupes, les actions, les options et les valeurs d'`--format`, ainsi que, pour
`config`, les clés (`todo config get list.<Tab>`) et les valeurs possibles d'un réglage (`todo config set
general.color <Tab>` propose `auto always never`, un booléen propose `true false`, `config unset` propose les
clés écrites dans le fichier). `--config FICHIER` est pris en compte.

```bash
pipx inject todo-cli argcomplete                 # ou : pipx install "todo-cli[completion] @ git+https://github.com/lanig35/todo-cli"
echo 'eval "$(register-python-argcomplete todo)"' >> ~/.bashrc        # bash
register-python-argcomplete --shell fish todo > ~/.config/fish/completions/todo.fish   # fish
```

Appuyer sur Tab ne produit **jamais** d'erreur ni de trace, n'écrit rien dans le journal ni dans les logs, et ne
crée aucun dossier : en cas de problème, la complétion est simplement vide. `_ARC_DEBUG=1 todo <Tab>` affiche
alors la raison. Une version récente d'`argcomplete` est nécessaire : les 3.1.x livrées avec certaines
distributions ne fonctionnent pas avec Python 3.13 (la 3.7 a été vérifiée).

### Journal

Les actions et les erreurs sont tracées dans le journal système, **en plus** des messages affichés
dans le terminal :

```bash
journalctl -t todo                     # tout ce que todo a écrit
journalctl -t todo -p warning          # refus et erreurs seulement
journalctl -t todo --since today -o cat
journalctl TODO_COMMAND=done           # avec python3-systemd (champs structurés, voir plus bas)
```

Exemple de messages :

```
INFO    add ids=265a96c5 exit=0
INFO    done ids=265a96c5,de6b5818 total=3 failed=1 exit=1   (WARNING si la commande échoue en partie)
WARNING done refus reason=unknown_id prefix=zzzz
INFO    edit ids=265a96c5 fields=titre,priorité exit=0
WARNING add refus reason=invalid_date
INFO    restore backup=20261112_201500_123456 exit=0
```

- **Actions tracées (INFO)** : `add`, `edit`, `done`, `undone`, `remove`, `postpone`, `archive`,
  `unarchive`, `restore`, `undo`, `reset`, `seed`, `config init` et
  `remind --enable` / `--disable`. Une ligne par commande, avec les identifiants concernés (20 au plus,
  puis `count=N`) ; pour `edit`, les **champs** modifiés mais pas leurs valeurs.
- **Erreurs (WARNING)** : un message `refus reason=…` à chaque erreur affichée (identifiant inconnu ou
  ambigu, date invalide, entrée illisible, erreur d'usage de la ligne de commande…), les avertissements
  de configuration, et `sortie exit=N` quand une commande échoue sans message plus précis.
- **Exceptions (CRITICAL)** : une erreur inattendue est journalisée avec sa trace complète, qui reste
  aussi affichée sur `stderr`.
- **Lectures** (`list`, `show`, `stats`, `agenda`, `next`, `remind`…) : rien au niveau `info`, pour ne
  pas encombrer le journal (`remind` s'exécute à chaque ouverture de terminal). Le niveau `debug` les
  ajoute : `todo --log-level debug list`.
- **Discrétion** : le journal système est lisible par les administrateurs de la machine, donc **aucun
  titre, description ni tag** n'y figure par défaut, seulement des identifiants. `[log] titles = true`
  (ou `TODO_LOG_TITLES=1`) ajoute les titres.

**Niveaux** : `off`, `error`, `warning`, `info` (défaut) et `debug`.

**Destinations** (`[log] target`) :

| Valeur | Effet |
|---|---|
| `auto` (défaut) | journald s'il est joignable, sinon le fichier de log |
| `journal` | journald uniquement ; s'il est introuvable, un avertissement est affiché et le fichier prend le relais |
| `file` | fichier tournant `~/.local/state/todo/todo.log` (512 Ko, 3 anciennes versions) |
| `off` | aucun journal |

- Sans module supplémentaire, les messages passent par le socket syslog `/dev/log`, que journald écoute :
  ils sont identifiés par `todo` (`journalctl -t todo`) et leur gravité est reconnue par `-p`.
- Si le paquet Debian **`python3-systemd`** est installé (`sudo apt install python3-systemd`), todo
  l'utilise automatiquement et ajoute des champs structurés filtrables : `TODO_COMMAND`, `TODO_EVENT`,
  `TODO_IDS`, `TODO_REASON`, `TODO_EXIT`… (par exemple `journalctl TODO_COMMAND=remove TODO_IDS=a1b2c3d4`).
- Le journal **ne bloque jamais** une commande : s'il est injoignable ou si le fichier de log n'est pas
  inscriptible, la commande se déroule normalement, sans message d'erreur.
- Pour lire ses propres messages sans `sudo`, il faut soit un journal persistant (`/var/log/journal`
  existe, ce qui est le cas sur une Debian standard : `journalctl --user -t todo`), soit appartenir au
  groupe `systemd-journal` ou `adm`.
- `[log] socket` indique un autre socket syslog si `/dev/log` n'est pas le bon.

### Export et import JSON

L'export est un fichier JSON lisible, indépendant du backend DBM : c'est le moyen de transférer vos
tâches d'une machine à l'autre, ou d'en garder une copie hors du dossier de stockage.

```bash
todo data export sauvegarde.json            # tâches + archive, dans un fichier (refus d'écraser sans --force)
todo data export | jq '.taches[] | .titre'  # sans fichier (ou `-`) : sortie standard
todo data export --no-archive > actives.json
todo data import sauvegarde.json            # ajoute ce qui manque
todo data import sauvegarde.json --dry-run  # montre ce qui serait importé, sans rien modifier
```

Le document contient `format` (`todo-cli`), `version`, `exporte_le`, `compteurs`, et les listes `taches` et
`archive` (chaque tâche avec son `id`, ses notes, sa récurrence… ; les archivées ont en plus
`date_archivage`).

**Import** : le fichier peut être un export, ou la sortie de `list --format json`. Trois modes :

| Option | Identifiant déjà présent (dans la liste ou l'archive) |
|---|---|
| *(aucune)* | la tâche du fichier est **ignorée** : l'import ne détruit jamais rien |
| `--update` | le contenu du fichier **remplace** la tâche, et elle va là où le fichier la place (liste ou archive) |
| `--replace` | la liste et l'archive sont **vidées** avant l'import (confirmation demandée, `-y` pour passer outre) |

- Tout le fichier est vérifié **avant** la moindre modification. Une entrée invalide (titre vide, priorité,
  statut, échéance ou récurrence incorrects, identifiant en double dans le fichier…) est signalée par sa
  position (`taches[3]`) et ignorée ; les autres sont importées, et le code de sortie vaut 1.
- Une entrée sans `id` en reçoit un nouveau. Un fichier de version plus récente que celle que `todo` sait
  lire est refusé.
- Une sauvegarde est faite après un import qui modifie quelque chose : `todo undo` l'annule.
- `--format json` donne le bilan (`ajoutees`, `mises_a_jour`, `ignorees`, `supprimees`, `invalides`) ;
  `-` lit le fichier sur l'entrée standard (avec `--replace`, ajoutez `-y`).

### Sauvegardes et restauration

Une sauvegarde est créée après chaque modification ; les 5 plus récentes sont conservées.

```bash
todo admin restore             # liste les sauvegardes (1 = la plus récente)
todo admin restore 3           # restaure la n°3, après confirmation
todo admin restore 3 -y        # sans confirmation
```

Avant toute restauration, l'état actuel est lui-même sauvegardé : une restauration peut être
annulée en restaurant cette sauvegarde (la n°2 juste après).

Autres commandes : `todo admin reset` (vide la liste, avec confirmation et sauvegarde préalable ; `--include-archive` vide aussi l'archive, la confirmation en indique alors les effectifs, et `undo` rétablit tout) et
`todo admin seed [N]` (ajoute N tâches factices, nécessite `faker`).

### Diagnostic de la base (`admin doctor`)

`todo admin doctor` contrôle l'état de la base, du stockage et de la configuration et signale ce qui cloche. Il lit les entrées
**brutes** (la lecture normale corrige en silence une priorité invalide ou une récurrence incorrecte, ce qui cacherait les anomalies) et
**ne modifie rien** sans `--fix`.

```bash
todo admin doctor                       # projet courant + environnement
todo admin doctor --all-projects        # tous les projets
todo admin doctor --strict              # code de sortie 1 aussi pour un avertissement (cron, CI)
todo admin doctor --no-attachments      # sans vérifier les pièces jointes (empreintes : long avec de gros fichiers)
todo admin doctor --format json | jq '.constats[] | select(.niveau == "erreur")'
todo admin doctor --fix --dry-run       # montre ce qui serait réparé
todo admin doctor --fix                 # répare, après confirmation (--yes pour la passer)
```

Chaque constat a un **niveau** (`erreur`, `avertissement`, `info`), un **code** stable, une portée (le projet, ou `environnement`),
l'identifiant de la tâche concernée et un indicateur `reparable`. Le code de sortie vaut `1` s'il y a au moins une erreur
(`--strict` : ou un avertissement), `0` sinon ; les `info` ne comptent jamais. Formats : `text`, `table`, `plain`
(`niveau`, `code`, `portée`, `id`, `message`, séparés par des tabulations) et `json` (`ok`, `bilan`, `projets`, `constats` et, avec `--fix`,
`reparations`).

| Niveau | Code | Contrôle |
|---|---|---|
| erreur | `unreadable_entry` | entrée de la base ou de l'archive illisible (JSON invalide) : ignorée par `todo` |
| erreur | `invalid_status` | statut autre que `A FAIRE` ou `TERMINE` |
| erreur | `dependency_cycle`, `self_dependency` | dépendances circulaires, tâche qui s'attend elle-même |
| erreur | `unknown_db_format`, `views_file_invalid` | base DBM illisible ou format inconnu ; fichier des vues illisible |
| erreur | `attachment_missing` | pièce jointe dont le fichier (copie ou lien) est introuvable |
| avertissement | `invalid_priority`, `invalid_started`, `todo_with_done_date`, `invalid_tags`, `invalid_dependencies` | valeurs incorrectes, **réparables** |
| avertissement | `missing_title`, `invalid_due`, `invalid_recurrence`, `recurrence_without_due`, `invalid_dates` | titre, échéance, récurrence ou dates incorrects (à corriger avec `task edit`) |
| avertissement | `duplicate_in_archive`, `archived_not_done` | tâche à la fois dans la liste et l'archive ; tâche archivée non terminée |
| avertissement | `attachment_modified`, `attachment_orphan` | pièce dont le contenu a changé ; fichier du stockage que rien ne référence (`attachment gc`) |
| avertissement | `config_warning`, `unknown_env_var`, `hook_command_not_found`, `invalid_webhook_url` | réglage inconnu ou invalide ; variable `TODO_…` inconnue (avec suggestion) ; commande de hook introuvable ; adresse de webhook invalide |
| avertissement | `webhook_queue_unreadable`, `storage_group_writable`, `low_disk_space`, `invalid_project_dir` | file du webhook illisible ; dossier de stockage modifiable par d'autres comptes ; moins de 50 Mo libres ; dossier de projet au nom invalide |
| info | `missing_dependency` | dépendance vers une tâche qui n'existe plus (elle ne bloque plus ; **réparable**) |
| info | `done_without_date`, `missing_next`, `attachment_in_trash`, `no_backup`, `webhook_queue_pending`, `dbm_dumb` | informations : ancienne tâche terminée sans date, occurrence suivante introuvable, pièce dans la corbeille, aucune sauvegarde, événements du webhook en attente, moteur `dbm.dumb` |

**Réparation (`--fix`).** Elle ne corrige que ce qui ne perd aucune information utile : priorité invalide remplacée par `medium`,
instant de démarrage invalide retiré, date de fin sur une tâche à faire retirée, éléments invalides de `tags` et `apres` retirés,
dépendances vers des tâches disparues retirées. Les autres champs (notes, pièces jointes, champs inconnus…) ne sont pas touchés. Elle prend le
verrou exclusif, **sauvegarde avant et après** (`todo undo` annule la réparation) et s'applique à **un seul projet**
(`-p PROJET` ; incompatible avec `--all-projects`). Les entrées illisibles, les statuts, les dates, les récurrences et les cycles ne sont jamais
modifiés : le diagnostic les signale, à vous de les corriger (`task edit`, `data import --update`, `undo`). Sans terminal, `--fix` demande
`--yes` (ou `--dry-run`).

### Codes de sortie

| Code | Signification |
|---|---|
| `0` | succès, ou rien à faire (`done` sur une tâche déjà terminée, `undone` sur une tâche déjà à faire, `edit` dont les valeurs sont déjà en place) |
| `1` | erreur : identifiant introuvable ou ambigu, liste vide, entrée corrompue, valeur invalide, fichier illisible, opération refusée… |
| `2` | erreur d'usage de la ligne de commande (option inconnue, valeur hors des choix proposés) |
| `130` | interruption au clavier (Ctrl-C) |

Cela vaut pour **toutes** les commandes, y compris `show`, `edit` et `undone` (qui renvoyaient `0` jusqu'ici,
même quand l'identifiant n'existait pas). Avec plusieurs identifiants
(`done`, `remove`, `postpone`, `archive`…), le code est `1` dès qu'un seul pose problème, les autres étant
quand même traités. Les messages d'erreur sont écrits sur la sortie standard, sauf ceux de l'import et de
l'export, sur la sortie d'erreur ; avec `--format json`, un script doit donc tester le code de sortie avant
d'analyser la sortie :

```bash
if todo show a1b2c3 --format json > tache.json; then jq .titre tache.json; fi
```

## Organisation du code

`todo.py` n'est plus qu'un lanceur ; la logique est dans le paquet `todo_cli/` :

| Module | Rôle |
|---|---|
| `cli.py` | définition de la ligne de commande (argparse) et aiguillage |
| `taches.py` | ajout, fin, réouverture, modification, suppression, report |
| `notes.py` | notes des tâches (commande `note`, option `-m`) |
| `vues.py` | vues enregistrées : fichier `views.json`, validation, groupe `view` |
| `ecriture_json.py` | sortie JSON des commandes d'écriture (`--format json`) |
| `hooks.py` | hooks : commandes lancées après une modification |
| `openapi.json` | Description OpenAPI 3.0 de l'API (servie par `/api/v1/openapi.json`, présentée par `/api/v1/docs`) |
| `client.py` | Client Python (`requests`) de l'API REST |
| `tui.py`, `tui_modele.py` | TUI curses (mise en page, boucle) et son modèle sans écran |
| `web.py` + `templates/`, `static/` | Interface web (pages Jinja, Bootstrap, session, CSRF) |
| `serveur.py` | API REST Flask (`todo serve`) : sous-processus du CLI, jeton, `ETag`, erreurs |
| `webhook.py` | webhook HTTP : envoi, signature HMAC, file d'attente et renvoi |
| `pieces_jointes.py` | pièces jointes : copie ou lien, vérification, corbeille, groupe `attachment` |
| `archive.py` | archivage, consultation de l'archive, récupération |
| `journal.py` | journal des actions et erreurs (journald, syslog, fichier) |
| `reglages.py` | registre des réglages, lecture du fichier INI, précédence option > variable > fichier > défaut |
| `configuration.py` | commande `config` (show, path, init) |
| `saisie.py` | saisie rapide (marqueurs dans le titre) |
| `dependances.py` | dépendances entre tâches (`--after`) : blocage, cycles |
| `filtres.py` | filtres communs à `list` et `archive list` (sans échéance, notes, dates de fin et d'archivage) |
| `lot.py` | actions en lot par filtre : aperçu (`--dry-run`) et confirmation |
| `verrou.py` | verrou `flock` de la base (partagé en lecture, exclusif en écriture ; un par projet) |
| `rappel.py` | commande `remind` (rappel des retards) |
| `prochaine.py` | commande `next` |
| `deplacement.py` | `task move` : déplacement de tâches entre projets, dépendances et sauvegardes |
| `projets.py` | groupe `project` : current, list, create, use, rename, delete (corbeille) |
| `diagnostic.py` | `admin doctor` : diagnostic de la base, du stockage et de la configuration, réparations sûres |
| `rapports.py` | rapports `report tags`, `blocked`, `overdue`, `stale`, `done`, `active`, `cycle` |
| `agenda.py` | vue agenda (tâches regroupées par jour) |
| `formats.py` | formats de sortie (text, table, plain, json, choix automatique) et catalogue des colonnes `--columns` |
| `affichage.py` | détail d'une tâche, liste (tri, filtres, pagination, pager), statistiques |
| `dates.py` | dates relatives, récurrences, libellés d'échéance |
| `stockage.py` | lecture de la base DBM, normalisation, résolution des identifiants |
| `echange.py` | export et import JSON |
| `sauvegardes.py` | sauvegardes, rotation, restauration, remise à zéro |
| `couleurs.py` | codes ANSI et règles d'activation des couleurs |
| `config.py` | constantes métier, chemins du stockage et projet courant, résolus à l'exécution (`config.DB_NAME`…) |
| `seed.py` | génération de tâches factices |

Le lien symbolique `~/.local/bin/todo` continue de fonctionner : le lanceur retrouve le paquet à côté
du vrai fichier. Dossier `todo_cli/` et `todo.py` doivent rester ensemble.

## Tests

La suite `pytest` pilote le programme de l'extérieur (sous-processus, base temporaire via
`TODO_DB_DIR`, pseudo-terminal pour les couleurs et le pager) : elle ne dépend pas de l'organisation
interne du code.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"               # installe todo en mode éditable, avec pytest, pytest-xdist, faker, flask, requests
python -m pytest -m smoke             # non-régression rapide : environ 300 tests, 1 à 2 minutes
python -m pytest -n auto              # suite complète en parallèle (≈ 1 500 tests ; plus de 15 minutes sans -n)
```

**Au quotidien**, on ne lance pas toute la suite : `-m smoke` après chaque modification, plus le fichier de la fonction touchée
(`python -m pytest tests/test_hooks.py`) ou `-k mot`. La suite complète tourne en intégration continue (`-n auto`) et avant une
version. Le sous-ensemble `smoke` est défini dans `tests/conftest.py` : les fichiers courts en entier, les 3 premiers tests (cas
nominaux) des autres, et quelques tests bout en bout. Pour trouver les tests lents : `python -m pytest --durations=20 -n auto`.
Deux tests du suivi du temps (`test_suivi_temps.py`) dépendent de l'heure de la journée et peuvent échouer tôt le matin.

Le fichier `pyproject.toml` décrit le paquet (nom, extras, commande `todo`) et la configuration de pytest.
La version n'y est écrite nulle part : elle est lue dans `todo_cli/__init__.py`, comme `todo --version` et
le CHANGELOG.

### Intégration continue

Le workflow `.github/workflows/tests.yml` lance la suite sur Python 3.13 (Debian 13)
à chaque PR et à chaque push sur `main`. Un nouveau push sur une branche annule l'exécution précédente.
Pour exiger un résultat vert avant la fusion : *Settings → Branches → Branch protection rules → Require
status checks to pass* (cocher `pytest (Python`3.13`).

## Stockage

| Élément | Emplacement |
|---|---|
| Base (projet `default`) | `~/.local/share/todo/todo_db*` |
| Autres projets | `~/.local/share/todo/projects/<nom>/` (mêmes fichiers : base, archive, sauvegardes, verrou) |
| Projets supprimés | `~/.local/share/todo/.trash/<nom>-AAAAMMJJ-HHMMSS/` |
| Vues enregistrées | `<dossier du projet>/views.json` |
| Pièces jointes | `<dossier du projet>/attachments/<id de la tâche>/<nom>` (ou `<attachments.dir>/<projet>/<id de la tâche>/<nom>`) ; corbeille : `attachments/.trash/<id>/<horodatage>/` |
| Journal (cible `file`) | `~/.local/state/todo/todo.log` |
| État du rappel | `~/.local/share/todo/remind_off`, `remind_last`, `remind_status` |
| Archive (projet `default`) | `~/.local/share/todo/todo_archive*` |
| Sauvegardes (projet `default`) | `~/.local/share/todo/backups/AAAAMMJJ_HHMMSS_µs/` (base et archive) |

La variable d'environnement `TODO_DB_DIR` (ou `db_dir` dans le fichier de configuration) redirige tout
le stockage vers un autre dossier (utile pour les tests). Pour plusieurs listes séparées, utilisez plutôt les projets.

### Accès concurrent

Chaque commande qui touche à la base prend un verrou (`flock`) sur le fichier `todo.lock` du dossier de
stockage : **partagé** pour les lectures (`list`, `show`, `next`, `agenda`, `stats`, `export`, `note ID`,
`archive list`, `reminder`…), qui peuvent donc s'exécuter ensemble, et **exclusif** pour les écritures, qui
attendent la fin des autres commandes. Deux `todo` lancés en même temps (cron, deux terminaux, un outil de
synchronisation) ne peuvent plus s'écraser.

- L'attente est limitée par `general.lock_timeout` (10 s par défaut). Au-delà, la commande échoue avec le
  code `1` et un message ; `0` échoue immédiatement.
- Le verrou est rendu par le système à la fin du processus, même après un plantage ou Ctrl-C : il n'y a
  jamais de verrou périmé à supprimer. Le fichier `todo.lock` peut rester sur le disque, sans contenu.
- Les commandes `config` n'en prennent pas. Les confirmations interactives (`reset`, `import`,
  `archive purge`…) gardent le verrou pendant que la question est posée : répondez ou annulez.
- Le verrou est local à la machine. Il ne protège pas un dossier partagé par le réseau dont le système
  de fichiers ne gère pas `flock`, ni deux machines qui se synchronisent un même dossier de stockage.
- Sans le module `fcntl` (Windows), le programme fonctionne sans verrou.

> **Portabilité** : le format DBM dépend du backend Python (`gdbm`, `ndbm`, `dumb`). Un fichier créé
> sur une machine n'est pas toujours lisible sur une autre. Pour transférer vos tâches, vérifiez
> que les deux machines utilisent le même backend, ou passez par `todo data export` / `todo data import`, qui ne
> dépendent pas du backend.

Les anciennes entrées (créées avant l'ajout d'un champ, par exemple la date de complétion ou la
récurrence) restent lisibles : les champs manquants prennent une valeur par défaut. Une entrée
illisible est ignorée avec un avertissement au lieu de faire échouer la commande.

## Versions et compatibilité

```bash
todo --version      # todo 2.5.0
```

Les versions suivent le [versionnement sémantique](https://semver.org/lang/fr/) : `1.0.1` corrige un
défaut, `1.1.0` ajoute une fonctionnalité sans rien casser, `2.0.0` casse la compatibilité. Le
[journal des changements](CHANGELOG.md) décrit chaque version.

Sont considérés comme stables à partir de la 1.0 : les commandes et options décrites dans ce README, les
champs des sorties `--format json`, les codes de sortie, le format de l'export JSON (`format`, `version`) et
la lisibilité des bases existantes (les champs ajoutés par les versions suivantes sont facultatifs à la lecture).

## Licence

[MIT](LICENSE)
