# todo-cli

Gestionnaire de tâches en ligne de commande en Python, sans dépendance obligatoire.
Les tâches sont stockées dans une base DBM locale, avec sauvegarde automatique après chaque modification.

## Fonctionnalités

- Tâches avec titre, description, priorité (`low`, `medium`, `high`), échéance et tags
- Dates relatives : `demain`, `+3d`, `+2w`, `vendredi`…
- Report d'échéance en une commande (`postpone`), sur une ou plusieurs tâches
- Tâches récurrentes (quotidiennes, hebdomadaires, mensuelles, annuelles)
- Filtres, recherche, tris, filtres par date, pagination et pager automatique
- Tâches en retard affichées en premier
- Agenda : les tâches à faire jour par jour (`agenda`)
- `next` : la prochaine tâche à traiter ; `undo` : annuler la dernière modification
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
| `--no-overdue-first` | ne regroupe pas les retards en tête |
| `--limit N`, `--start N` | tranche de la liste (`--start` commence à 1, comme la numérotation affichée) |
| `--no-pager` | n'utilise pas de pager |
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
| `archive.py` | archivage, consultation de l'archive, récupération |
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
| Archive | `~/.local/share/todo/todo_archive*` |
| Sauvegardes | `~/.local/share/todo/backups/AAAAMMJJ_HHMMSS_µs/` (base et archive) |

La variable d'environnement `TODO_DB_DIR` redirige tout le stockage vers un autre dossier
(utile pour les tests ou pour avoir plusieurs listes séparées).

> **Portabilité** : le format DBM dépend du backend Python (`gdbm`, `ndbm`, `dumb`). Un fichier créé
> sur une machine n'est pas toujours lisible sur une autre. Pour transférer vos tâches, vérifiez
> que les deux machines utilisent le même backend.

Les anciennes entrées (créées avant l'ajout d'un champ, par exemple la date de complétion ou la
récurrence) restent lisibles : les champs manquants prennent une valeur par défaut. Une entrée
illisible est ignorée avec un avertissement au lieu de faire échouer la commande.

## Licence

[MIT](LICENSE)
