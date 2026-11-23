#!/usr/bin/env python3
"""Hook todo-cli : envoie chaque modification dans Redis (sans dépendance : petit client RESP intégré).

Pour chaque tâche touchée :
  - XADD todo:events * event … project … id … title … task <json>   (journal d'événements, un « stream »)
  - HSET todo:tasks:<projet> <id> <json>                            (état courant de la tâche ; HDEL si supprimée/déplacée)

Réglages todo (fichier de configuration) :
    [hooks]
    on_add    = python3 /chemin/vers/redis_hook.py
    on_change = python3 /chemin/vers/redis_hook.py     # ou seulement on_change pour tout couvrir (undo, import…)

Variables d'environnement lues par le script : REDIS_HOST (127.0.0.1), REDIS_PORT (6379), REDIS_PASSWORD (aucun),
REDIS_STREAM (todo:events), REDIS_MAXLEN (10000, taille maximale du stream).

Lecture : redis-cli XRANGE todo:events - + ; redis-cli HGETALL todo:tasks:default
"""
import json
import os
import socket
import sys


class Redis:
    """Le strict nécessaire du protocole RESP : envoyer une commande, lire une réponse."""

    def __init__(self, hote, port, delai=5):
        self.sock = socket.create_connection((hote, port), timeout=delai)
        self.lecteur = self.sock.makefile("rb")

    def commande(self, *mots):
        morceaux = [str(m).encode("utf-8") for m in mots]
        self.sock.sendall(b"*%d\r\n" % len(morceaux) + b"".join(b"$%d\r\n%s\r\n" % (len(m), m) for m in morceaux))
        return self._lire()

    def _lire(self):
        ligne = self.lecteur.readline().rstrip(b"\r\n")
        type_, reste = ligne[:1], ligne[1:]
        if type_ == b"-":
            raise RuntimeError(reste.decode("utf-8", "replace"))
        if type_ == b"$":                      # chaîne : longueur puis données
            n = int(reste)
            return None if n < 0 else self.lecteur.read(n + 2)[:-2].decode("utf-8", "replace")
        if type_ == b"*":                      # tableau
            return [self._lire() for _ in range(int(reste))]
        return reste.decode("utf-8", "replace") if type_ == b"+" else int(reste)


def main():
    evenement = os.environ["TODO_EVENT"]
    projet = os.environ["TODO_PROJECT"]
    identifiant = os.environ["TODO_ID"]
    titre = os.environ["TODO_TITLE"]
    donnees = json.load(sys.stdin)             # la tâche ; {"id", "titre"} si elle n'existe plus ; {"event", "ids"} pour un gros lot
    r = Redis(os.environ.get("REDIS_HOST", "127.0.0.1"), int(os.environ.get("REDIS_PORT", "6379")))
    if os.environ.get("REDIS_PASSWORD"):
        r.commande("AUTH", os.environ["REDIS_PASSWORD"])
    r.commande("XADD", os.environ.get("REDIS_STREAM", "todo:events"), "MAXLEN", "~", os.environ.get("REDIS_MAXLEN", "10000"), "*",
               "event", evenement, "project", projet, "id", identifiant, "title", titre,
               "task", json.dumps(donnees, ensure_ascii=False))
    if identifiant:                            # état courant : une entrée par tâche, dans un hash par projet
        cle = f"todo:tasks:{projet}"
        if evenement in ("remove", "move"):
            r.commande("HDEL", cle, identifiant)
        elif "statut" in donnees:              # tâche complète (pas le JSON réduit d'une tâche disparue)
            r.commande("HSET", cle, identifiant, json.dumps(donnees, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as e:       # Redis arrêté, mot de passe refusé… : un message court, pas une trace
        sys.exit(f"redis_hook : {e}")
