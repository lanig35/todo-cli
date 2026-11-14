# todo-cli

Gestionnaire de tâches en ligne de commande en Python, sans dépendance obligatoire.
Les tâches sont stockées dans une base DBM locale, avec sauvegarde automatique après chaque modification.

## Fonctionnalités

- Saisie rapide : `todo add "Appeler Paul demain !high #pro"`
- Tâches avec titre, description, priorité (`low`, `medium`, `high`), échéance et tags
- Dates relatives : `demain`, `+3d`, `+2w`, `vendredi`…
- Report d'échéance en une commande (`postpone`), sur une ou plusieurs tâches
- Tâches récurrentes (quotidiennes, hebdomadaires, mensuelles, annuelles)
- Filtres, recherche, tris, filtres par date, pagination et pager automatique
- Tâches en retard affichées en premier
- Agenda : les tâches à faire jour par jour (`agenda`)
- Journal des actions et des erreurs, lisible avec `journalctl -t todo`
- Configuration par fichier INI, variables d'environnement et options (`todo config`)
- `remind` : rappel des tâches en retard (terminal, `cron`, invite du shell)
- `next` : la prochaine tâche à traiter ; `undo` : annuler la dernière modification
- Notes datées sur les tâches (`note`, ou `-m` sur `done`, `undone`, `postpone`, `edit`, `remove`)
- Date de complétion et statistiques
- Archivage des tâches terminées (consultation, recherche, récupération)
- Sauvegardes automatiques et restauration
- Couleurs automatiquement désactivées hors terminal (pipes, redirections) et avec `NO_COLOR`

## Installation

Python 3 est requis (développé et testé avec Python 3.13).

```bash
git clone https://github.com/lanig35/todo-cli.git
cd todo-cli
chmod +x todo.py
ln -s "$PWD/todo.py" ~/.local/bin/todo     # optionnel : disposer de la commande `todo`
```

Dépendances optionnelles :

| Paquet | Usage |
|---|---|
| `faker` | commande `seed` (génération de tâches factices) |
| `argcomplete` | autocomplétion du shell (`register-python-argcomplete todo`) |
| `less` | pager pour les longues listes (présent sur la plupart des systèmes) |

Dans les exemples ci-dessous, `todo` désigne `./todo.py` ou le lien créé ci-dessus.

## Utilisation

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
| Date (avec ou sans `@`) | échéance | `demain`, `@lundi`, `+3d`, `2026-12-25` (mêmes formats que `--due`) |
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
- Dans un shell, mettez le titre entre guillemets : `#` commence un commentaire et `!` déclenche
  l'historique de bash.

### Lister

```bash
todo list                                  # tout, les retards en premier
todo list --status todo --prio high        # à faire, priorité haute
todo list --tag pro --sort alpha           # par tag, tri alphabétique
todo list --search rapport                 # recherche dans titre, description et tags
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
| `--search TEXTE` | recherche dans le titre, la description et les tags |
| `--tag TAG` | tâches portant ce tag |
| `--prio low\|medium\|high` | filtre sur la priorité |
| `--overdue` | tâches à faire dont l'échéance est dépassée |
| `--today` | tâches à faire dont l'échéance est aujourd'hui (avec `--overdue` : l'un ou l'autre) |
| `--due-before DATE` | échéance au plus tard à cette date, **incluse** |
| `--due-after DATE` | échéance à partir de cette date, **incluse** |
| `--sort alpha\|status\|priority\|due` | critère de tri |
| `--overdue-first`, `--no-overdue-first` | regroupe (par défaut) ou non les retards en tête |
| `--limit N`, `--start N` | tranche de la liste (`--start` commence à 1, comme la numérotation affichée) |
| `--pager`, `--no-pager` | utilise ou non un pager (par défaut : oui, si l'affichage dépasse l'écran) |
| `--format table\|json` | format de sortie |

Notes :

- Les filtres `--due-before` et `--due-after` excluent les tâches sans échéance et les tâches
  terminées, sauf avec `--status done`.
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
todo done a1b2c3            # terminer (enregistre la date de complétion)
todo done a1b2c3 d4e5f6     # ... ou plusieurs tâches d'un coup
todo undone a1b2c3          # rouvrir
todo edit a1b2c3 --title "Nouveau titre" --prio low --due +3d --tags "pro,dev"
todo edit a1b2c3 --due none --tags "" --desc ""    # supprimer échéance, tags et description
todo remove a1b2c3          # supprimer (un ou plusieurs identifiants)
todo clear-done             # supprimer toutes les tâches terminées
```

#### Plusieurs tâches à la fois

`done` et `remove` acceptent un ou plusieurs identifiants :

```bash
todo done a1b2c3 d4e5f6 9a8b7c
todo remove a1b2c3 d4e5f6
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

### Notes

Une tâche a une `description` (ce qu'il faut faire) et des **notes** : un journal daté, en ajout
seul, de ce qui se passe autour d'elle.

```bash
todo note a1b2c3 "appelé le client, rappeler jeudi"   # ajoute une note (500 caractères au plus)
todo note a1b2c3                                       # liste les notes de la tâche
todo note a1b2c3 --format json | jq -r '.notes[].texte'
todo done a1b2c3 -m "validé par Paul"                  # -m / --note : action + note en une commande
todo undone a1b2c3 -m "le client a rappelé"
todo postpone a1b2c3 d4e5f6 --to +3d -m "client absent"
todo edit a1b2c3 -m "à traiter avec Julie"             # une note seule suffit pour edit
todo remove a1b2c3 -m "doublon de a9f8e7"
```

- Chaque note enregistre sa date, son texte et l'**action** qui l'a produite (`note`, `done`,
  `undone`, `postpone`, `edit`) ; `show` les affiche de la plus ancienne à la plus récente, et `list`
  signale une tâche annotée par `📝N`. Il n'y a pas de note automatique : seul ce que vous écrivez
  est enregistré.
- Avec plusieurs identifiants, la même note est ajoutée à chaque tâche réellement traitée (pas à celle
  déjà terminée, ni à celle dont l'échéance ne change pas). Une note vide est refusée avant toute
  modification.
- `done` sur une tâche récurrente : la note reste sur l'occurrence terminée ; la suivante repart sans note.
- Les notes font partie de la tâche : elles suivent l'archivage (`archive`, `unarchive`), les
  sauvegardes et `undo`, apparaissent dans les sorties `--format json` (`"notes": [...]`) et sont
  incluses dans `list --search` et `archive --search`. Une note ne peut être ni modifiée ni supprimée.
- **`remove -m`** : la tâche disparaît, ses notes aussi. Le motif est donc écrit **au journal**
  (`journalctl -t todo`), avec le titre, seul souvenir de la suppression.
- Journal : l'ajout d'une note est tracé sans son texte (seulement sa longueur `note_len`), sauf si
  `[log] titles = true`.

### Reporter une échéance

```bash
todo postpone a1b2c3                  # +1 jour (valeur par défaut)
todo postpone a1b2c3 d4e5f6 --to +2d  # plusieurs tâches, de 2 jours
todo postpone a1b2c3 --to +1w         # une semaine
todo postpone a1b2c3 --to lundi       # date fixe
todo postpone a1b2c3 --to 2026-12-01  # date fixe
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
todo edit a1b2c3 --repeat 2w        # modifier la récurrence
todo edit a1b2c3 --repeat none      # l'arrêter
```

Valeurs acceptées : `daily`, `weekly`, `monthly`, `yearly`, ou `3d`, `2w`, `1m`, `1y`.

- Une tâche récurrente a toujours une échéance (aujourd'hui par défaut).
- `done` termine la tâche et crée l'occurrence suivante, avec le même titre, la même description,
  la même priorité et les mêmes tags.
- L'échéance suivante part de l'échéance d'origine (pas de dérive) et est toujours postérieure à
  aujourd'hui : les occurrences manquées ne s'accumulent pas.
- Terminer une tâche avant son échéance saute à l'occurrence suivante.
- `undone` sur une tâche récurrente supprime l'occurrence qu'elle avait créée (refusé si celle-ci
  est déjà terminée).
- `remove` n'arrête pas la série : utilisez `edit --repeat none`.

### Rappel des tâches en retard

```bash
todo remind                 # retards et tâches du jour ; rien d'affiché s'il n'y en a pas
todo remind --soon 3        # + les échéances des 3 prochains jours
todo remind --limit 10      # 10 tâches listées au plus (5 par défaut)
todo remind --once-a-day    # une seule fois par jour
todo remind --write-status  # n'affiche rien ; met à jour un résumé d'une ligne (pour cron)
todo remind --disable       # coupe les rappels ; --enable les réactive ; --status indique l'état
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
    todo remind --once-a-day
fi
```

#### Avec cron

Un job `cron` n'a pas de terminal : sa sortie part par e-mail local, ou est perdue si aucun serveur de
messagerie n'est installé (cas d'une Debian de base). Deux usages :

```cron
# crontab -e
# 1. Mise à jour du résumé d'une ligne toutes les 15 minutes (aucune sortie, donc aucun e-mail)
*/15 * * * *  /home/vous/bin/todo remind --write-status

# 2. Rappel complet par e-mail local, en semaine à 9 h (nécessite un serveur de messagerie local)
0 9 * * 1-5   /home/vous/bin/todo remind
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

- `todo remind --disable` coupe les rappels de façon durable : `remind`, `--once-a-day` et
  `--write-status` deviennent muets, et le résumé de l'invite est vidé tout de suite. Les lignes de
  `~/.bashrc` et de la crontab peuvent rester en place. `todo remind --enable` les remet en route ;
  `--status` indique l'état.
- La variable d'environnement `TODO_NO_REMIND` (non vide) coupe les rappels dans une session
  seulement, par exemple `TODO_NO_REMIND=1 bash`. Le réglage `[remind] enabled = false` du fichier de
  configuration les coupe aussi (voir *Configuration*).
- Le reste du programme n'est pas concerné : `list`, `next`, `agenda`… fonctionnent normalement.

Les fichiers d'état (`remind_off`, `remind_last`, `remind_status`) sont dans le dossier de stockage,
hors de la base : ils ne sont ni sauvegardés ni modifiés par `restore` ou `reset`.

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

### Archivage

Les tâches terminées peuvent être rangées hors de la liste, sans être supprimées :

```bash
todo archive                      # archive toutes les tâches terminées
todo archive --older-than 30d     # seulement celles terminées depuis au moins 30 jours
todo archive a1b2c3 d4e5f6        # ou des tâches précises (elles doivent être terminées)
todo archive --list               # consulter l'archive
todo archive --search facture     # chercher dans l'archive (titre, description, tags)
todo unarchive a1b2c3             # remettre une tâche dans la liste
todo stats --with-archive         # statistiques incluant l'historique archivé
```

- Les tâches archivées disparaissent de `list`, `agenda` et `stats` (sauf `--with-archive`).
- `--older-than` accepte `30d`, `2w`, `6m`, `1y` et se base sur la date de complétion. Une ancienne
  tâche terminée sans date de complétion est ignorée (son âge est inconnu) : archivez-la par
  identifiant.
- `--older-than` et des identifiants ne se combinent pas. `--list`, `--search` (et `--format json`,
  `--no-pager`) consultent l'archive, de la tâche terminée le plus récemment à la plus ancienne.
- Seules les tâches terminées s'archivent. Pour une tâche récurrente, l'occurrence suivante reste
  dans la liste ; rouvrir l'ancienne (`undone`) demande de la récupérer d'abord avec `unarchive`.
- Archive et liste sont **sauvegardées et restaurées ensemble** : `restore` ramène les deux à l'état
  de la sauvegarde, de sorte qu'une tâche n'apparaisse jamais des deux côtés. `reset` ne vide que la
  liste et conserve l'archive.
- `archive` et `unarchive` traitent plusieurs identifiants comme `done` et `remove` (bilan, une seule
  sauvegarde, code de sortie `1` en cas d'échec).

### Statistiques

```bash
todo stats
```

Progression, charge active par priorité, tags les plus utilisés, retards et échéances du jour,
et rythme de complétion (aujourd'hui et sur 7 jours).

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
  plus loin. Pour revenir plus en arrière, utilisez `todo restore` (5 sauvegardes conservées).
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

Le fichier est `$TODO_CONFIG` s'il est défini, sinon `$XDG_CONFIG_HOME/todo/config.ini`, sinon
`~/.config/todo/config.ini`. Un fichier absent n'est pas une erreur. Exemple :

```ini
[general]
color = auto            # auto | always | never
pager = true

[list]
limit = 30              # 0 = pas de limite
overdue_first = true

[add]
priority = medium

[remind]
enabled = true
limit = 5
soon = 0
```

| Section | Clé | Défaut | Variable d'environnement | Option qui l'emporte |
|---|---|---|---|---|
| `general` | `db_dir` | `~/.local/share/todo` | `TODO_DB_DIR` | — |
| `general` | `color` | `auto` | `TODO_COLOR` (puis `NO_COLOR`) | `--color`, `--no-color` |
| `general` | `pager` | `true` | `TODO_PAGER` | `--pager`, `--no-pager` |
| `general` | `keep_backups` | `5` (minimum 2) | `TODO_KEEP_BACKUPS` | — |
| `list` | `limit` | `0` (illimité) | `TODO_LIST_LIMIT` | `--limit` |
| `list` | `overdue_first` | `true` | `TODO_LIST_OVERDUE_FIRST` | `--overdue-first`, `--no-overdue-first` |
| `add` | `priority` | `medium` | `TODO_ADD_PRIORITY` | `--prio` (et `+`/`!priorité` dans le titre) |
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
  `todo remind --disable` et `TODO_NO_REMIND`. Les interrupteurs se **cumulent** : un seul suffit pour
  couper, sauf que `TODO_REMIND_ENABLED=true` l'emporte sur `enabled = false` du fichier.
- `db_dir` et `keep_backups` sont lus au démarrage : il n'y a pas d'option de ligne de commande
  équivalente, mais `TODO_DB_DIR=/autre/dossier todo list` fonctionne pour un usage ponctuel.

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
  `unarchive`, `clear-done`, `restore`, `undo`, `reset`, `seed`, `config init` et
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

### Sauvegardes et restauration

Une sauvegarde est créée après chaque modification ; les 5 plus récentes sont conservées.

```bash
todo restore             # liste les sauvegardes (1 = la plus récente)
todo restore 3           # restaure la n°3, après confirmation
todo restore 3 -y        # sans confirmation
```

Avant toute restauration, l'état actuel est lui-même sauvegardé : une restauration peut être
annulée en restaurant cette sauvegarde (la n°2 juste après).

Autres commandes : `todo reset` (vide la base, avec confirmation et sauvegarde préalable) et
`todo seed [N]` (ajoute N tâches factices, nécessite `faker`).

## Organisation du code

`todo.py` n'est plus qu'un lanceur ; la logique est dans le paquet `todo_cli/` :

| Module | Rôle |
|---|---|
| `cli.py` | définition de la ligne de commande (argparse) et aiguillage |
| `taches.py` | ajout, fin, réouverture, modification, suppression, report |
| `notes.py` | notes des tâches (commande `note`, option `-m`) |
| `archive.py` | archivage, consultation de l'archive, récupération |
| `journal.py` | journal des actions et erreurs (journald, syslog, fichier) |
| `reglages.py` | registre des réglages, lecture du fichier INI, précédence option > variable > fichier > défaut |
| `configuration.py` | commande `config` (show, path, init) |
| `saisie.py` | saisie rapide (marqueurs dans le titre) |
| `rappel.py` | commande `remind` (rappel des retards) |
| `prochaine.py` | commande `next` |
| `agenda.py` | vue agenda (tâches regroupées par jour) |
| `affichage.py` | détail d'une tâche, liste (tri, filtres, pagination, pager), statistiques |
| `dates.py` | dates relatives, récurrences, libellés d'échéance |
| `stockage.py` | lecture de la base DBM, normalisation, résolution des identifiants |
| `sauvegardes.py` | sauvegardes, rotation, restauration, remise à zéro |
| `couleurs.py` | codes ANSI et règles d'activation des couleurs |
| `config.py` | emplacement du stockage et constantes |
| `seed.py` | génération de tâches factices |

Le lien symbolique `~/.local/bin/todo` continue de fonctionner : le lanceur retrouve le paquet à côté
du vrai fichier. Dossier `todo_cli/` et `todo.py` doivent rester ensemble.

## Tests

La suite `pytest` pilote le programme de l'extérieur (sous-processus, base temporaire via
`TODO_DB_DIR`, pseudo-terminal pour les couleurs et le pager) : elle ne dépend pas de l'organisation
interne du code.

```bash
pip install pytest
python -m pytest
```

## Stockage

| Élément | Emplacement |
|---|---|
| Base | `~/.local/share/todo/todo_db*` |
| Journal (cible `file`) | `~/.local/state/todo/todo.log` |
| État du rappel | `~/.local/share/todo/remind_off`, `remind_last`, `remind_status` |
| Archive | `~/.local/share/todo/todo_archive*` |
| Sauvegardes | `~/.local/share/todo/backups/AAAAMMJJ_HHMMSS_µs/` (base et archive) |

La variable d'environnement `TODO_DB_DIR` (ou `db_dir` dans le fichier de configuration) redirige tout
le stockage vers un autre dossier (utile pour les tests ou pour avoir plusieurs listes séparées).

> **Portabilité** : le format DBM dépend du backend Python (`gdbm`, `ndbm`, `dumb`). Un fichier créé
> sur une machine n'est pas toujours lisible sur une autre. Pour transférer vos tâches, vérifiez
> que les deux machines utilisent le même backend.

Les anciennes entrées (créées avant l'ajout d'un champ, par exemple la date de complétion ou la
récurrence) restent lisibles : les champs manquants prennent une valeur par défaut. Une entrée
illisible est ignorée avec un avertissement au lieu de faire échouer la commande.

## Licence

[MIT](LICENSE)
