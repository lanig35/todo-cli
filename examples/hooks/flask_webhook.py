#!/usr/bin/env python3
"""Récepteur d'exemple pour le webhook HTTP de todo-cli, avec Flask (pip install flask).

    python3 flask_webhook.py                      # écoute sur http://127.0.0.1:8080
    TODO_WEBHOOK_TOKEN=mon-jeton python3 flask_webhook.py

Côté todo :
    [hooks]
    webhook_url = http://127.0.0.1:8080/todo
    webhook_token = mon-jeton          # si le récepteur exige un jeton

Le récepteur vérifie le jeton, valide le JSON, journalise chaque événement dans events.jsonl et tient à jour l'état
courant des tâches (tasks.json). `GET /tasks` les renvoie. Il répond vite (204) : todo n'attend que `[hooks] timeout` secondes.
"""
import hmac
import json
import os
import threading
from pathlib import Path

from flask import Flask, abort, jsonify, request

app = Flask(__name__)
JETON = os.environ.get("TODO_WEBHOOK_TOKEN", "")
DOSSIER = Path(os.environ.get("TODO_WEBHOOK_DIR", "."))
verrou = threading.Lock()                     # Flask peut traiter plusieurs requêtes à la fois


def lire_etat():
    try:
        return json.loads((DOSSIER / "tasks.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


@app.post("/todo")
def recevoir():
    if JETON:                                 # « Authorization: Bearer … » envoyé par todo si webhook_token est défini
        recu = request.headers.get("Authorization", "")
        if not hmac.compare_digest(recu, f"Bearer {JETON}"):
            abort(401)
    corps = request.get_json(silent=True)
    if not isinstance(corps, dict) or "event" not in corps:
        abort(400, "JSON attendu : {event, project, count, ids, tasks…}")

    evenement, projet = corps["event"], corps.get("project", "default")
    with verrou:
        with (DOSSIER / "events.jsonl").open("a", encoding="utf-8") as f:          # journal d'événements
            f.write(json.dumps(corps, ensure_ascii=False) + "\n")
        etat = lire_etat()
        courant = etat.setdefault(projet, {})
        if evenement in ("remove", "move"):                                         # la tâche a quitté le projet
            for identifiant in corps.get("ids", []):
                courant.pop(identifiant, None)
        else:                                                                       # add, done, edit… : tâche à jour
            for tache in corps.get("tasks", []):
                if "statut" in tache:                                               # tâche complète (pas {"id", "titre"})
                    courant[tache["id"]] = tache
        (DOSSIER / "tasks.json").write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")

    if evenement == "done":                                                         # exemple de réaction
        for tache in corps.get("tasks", []):
            print(f"✅ [{projet}] terminée : {tache.get('titre')}", flush=True)
    return "", 204


@app.get("/tasks")
def taches():
    projet = request.args.get("project", "default")
    return jsonify(list(lire_etat().get(projet, {}).values()))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8080")))
