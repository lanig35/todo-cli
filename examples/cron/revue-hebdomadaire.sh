#!/bin/sh
# Envoie la revue hebdomadaire de todo-cli par courriel (lecture seule : rien n'est modifié).
#
# Crontab, par exemple le vendredi à 17 h :
#   0 17 * * 5  /home/vous/bin/revue-hebdomadaire.sh
#
# Variables (toutes facultatives) :
#   TODO_BIN       commande todo           (défaut : todo)
#   REVUE_DEST     destinataire            (défaut : l'utilisateur courant)
#   REVUE_SUJET    objet du message        (défaut : « Revue hebdomadaire todo — AAAA-MM-JJ »)
#   REVUE_OPTIONS  options de `report review`, ex. « --days 14 --older-than 60d »
#   REVUE_PROJET   projet à passer en revue (défaut : projet courant) ; « all » = tous les projets
#
# Sans commande `mail`, le rapport est écrit sur la sortie standard : cron l'envoie alors lui-même
# à MAILTO (ou à l'utilisateur) si MAILTO est défini dans la crontab.
set -eu

TODO_BIN=${TODO_BIN:-todo}
DEST=${REVUE_DEST:-$(id -un)}
SUJET=${REVUE_SUJET:-"Revue hebdomadaire todo — $(date +%F)"}

# Un seul jeu d'options : texte sans couleur ni pager, adapté à un courriel.
PROJET=""
TOUS=""
if [ "${REVUE_PROJET:-}" = "all" ]; then
    TOUS="--all-projects"
elif [ -n "${REVUE_PROJET:-}" ]; then
    PROJET="-p $REVUE_PROJET"
fi

# shellcheck disable=SC2086  # les options sont volontairement découpées
RAPPORT=$("$TODO_BIN" --no-color $PROJET report review --format text --no-pager $TOUS ${REVUE_OPTIONS:-})

if command -v mail >/dev/null 2>&1; then
    printf '%s\n' "$RAPPORT" | mail -s "$SUJET" "$DEST"
else
    printf '%s\n' "$RAPPORT"
fi
