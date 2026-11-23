"""--format json sur les commandes d'écriture : un objet JSON sur stdout, les messages sur stderr."""
import json

import pytest

from outils import jour


@pytest.fixture
def v(todo):
    todo.seed({"cle": "a1", "titre": "Rapport", "priorite": "high", "echeance": jour(1)},
              {"cle": "a2", "titre": "Courses"},
              {"cle": "a3", "titre": "Appel", "tags": ["pro"]})
    return todo


def objet(r):
    """stdout ne contient que le JSON."""
    return json.loads(r.out)


def test_add(todo):
    r = todo("add", "Écrire le rapport", "--prio", "high", "--tags", "pro", "--format", "json")
    o = objet(r)
    assert r.code == 0 and o["ok"] is True and o["action"] == "add" and o["project"] == "default"
    assert o["count"] == 1 and o["failed"] == 0 and o["errors"] == []
    (t,) = o["tasks"]
    assert t["titre"] == "Écrire le rapport" and t["priorite"] == "high" and t["tags"] == ["pro"] and t["statut"] == "A FAIRE"
    assert t["id"] == todo.une("Écrire le rapport")["id"] and len(t["id"]) == 36 and t["bloquee_par"] == []
    assert "Tâche ajoutée" in r.err and "Tâche ajoutée" not in r.out          # le message habituel part sur stderr


def test_add_saisie_rapide_et_recurrence(todo):
    o = objet(todo("add", "Sport demain !low #loisir ~weekly", "--format", "json"))
    t = o["tasks"][0]
    assert t["titre"] == "Sport" and t["priorite"] == "low" and t["tags"] == ["loisir"] and t["recurrence"] and t["date_echeance"]


def test_add_avec_dependance(v):
    o = objet(v("add", "Suite", "--after", "a1", "--format", "json"))
    assert o["tasks"][0]["apres"] == ["a1"] and o["tasks"][0]["bloquee_par"] == ["a1"]


def test_add_titre_vide(todo):
    r = todo("add", " ", "--format", "json")
    o = objet(r)
    assert r.code == 1 and o["ok"] is False and o["count"] == 0 and o["errors"] == ["empty_title"] and o["tasks"] == []


def test_done(v):
    r = v("done", "a1", "--format", "json")
    o = objet(r)
    assert r.code == 0 and o["ok"] and o["action"] == "done" and o["count"] == 1
    assert o["tasks"][0]["id"] == "a1" and o["tasks"][0]["statut"] == "TERMINE" and o["tasks"][0]["date_terminee"]
    assert v.une("Rapport")["statut"] == "TERMINE"


def test_done_tache_recurrente_donne_la_suivante(todo):
    todo("add", "Arroser", "--repeat", "daily")
    i = todo.une("Arroser")["id"]
    t = objet(todo("done", i, "--format", "json"))["tasks"][0]
    assert t["suivante"] and t["suivante"] != i


def test_done_lot(v):
    o = objet(v("done", "a1", "a2", "--format", "json"))
    assert o["count"] == 2 and [t["id"] for t in o["tasks"]] == ["a1", "a2"]
    o = objet(v("done", "--all", "-y", "--format", "json"))
    assert [t["id"] for t in o["tasks"]] == ["a3"]


def test_done_deja_terminee(v):
    v("done", "a1")
    r = v("done", "a1", "--format", "json")
    o = objet(r)
    assert r.code == 0 and o["ok"] and o["count"] == 0 and o["tasks"] == []


def test_identifiant_inconnu(v):
    r = v("done", "zzzz", "--format", "json")
    o = objet(r)
    assert r.code == 1 and o["ok"] is False and o["failed"] == 1 and o["errors"] == ["unknown_id"] and "zzzz" in r.err


def test_lot_partiel(v):
    r = v("done", "a1", "zzzz", "--format", "json")
    o = objet(r)
    assert r.code == 1 and o["ok"] is False and o["count"] == 1 and o["tasks"][0]["id"] == "a1" and o["failed"] == 1
    assert v.une("Rapport")["statut"] == "TERMINE"


def test_undone(v):
    v("done", "a1")
    o = objet(v("task", "undone", "a1", "--format", "json"))
    assert o["action"] == "undone" and o["tasks"][0]["statut"] == "A FAIRE" and o["tasks"][0]["date_terminee"] is None


def test_start_unstart(v):
    o = objet(v("task", "start", "a1", "--format", "json"))
    assert o["action"] == "start" and o["tasks"][0]["demarree"]
    o = objet(v("task", "unstart", "a1", "--format", "json"))
    assert o["action"] == "unstart" and o["tasks"][0]["demarree"] is None


def test_postpone(v):
    avant = v.une("Rapport")["date_echeance"]
    o = objet(v("task", "postpone", "a1", "--to", "+3d", "--format", "json"))
    assert o["action"] == "postpone" and o["tasks"][0]["date_echeance"] != avant == jour(1)
    assert o["tasks"][0]["date_echeance"] == v.une("Rapport")["date_echeance"]


def test_edit(v):
    o = objet(v("task", "edit", "a2", "--title", "Courses du soir", "--prio", "low", "--add-tag", "maison", "--format", "json"))
    t = o["tasks"][0]
    assert o["action"] == "edit" and t["titre"] == "Courses du soir" and t["priorite"] == "low" and t["tags"] == ["maison"]


def test_edit_sans_changement_est_une_erreur_ou_vide(v):
    r = v("task", "edit", "a2", "--format", "json")
    o = objet(r)
    assert o["action"] == "edit" and o["ok"] == (r.code == 0)


def test_remove(v):
    r = v("task", "remove", "a2", "-y", "--format", "json")
    o = objet(r)
    assert r.code == 0 and o["action"] == "remove" and o["tasks"] == [{"id": "a2", "titre": "Courses"}]
    assert "Courses" not in [t["titre"] for t in v.taches().values()]


def test_move(v):
    v("project", "create", "pro")
    o = objet(v("task", "move", "a3", "--to", "pro", "--format", "json"))
    assert o["action"] == "move" and o["to"] == "pro" and o["tasks"] == [{"id": "a3", "titre": "Appel"}]
    assert [t["titre"] for t in json.loads(v("-p", "pro", "list", "--format", "json").out)] == ["Appel"]
    assert "Appel" not in [t["titre"] for t in v.taches().values()]


def test_move_projet_inconnu(v):
    r = v("task", "move", "a3", "--to", "nope", "--format", "json")
    o = objet(r)
    assert r.code == 1 and o["ok"] is False and o["to"] == "nope" and o["errors"]


def test_projet(v):
    v("project", "create", "pro")
    o = objet(v("add", "Autre", "-p", "pro", "--format", "json"))
    assert o["project"] == "pro"


def test_forme_groupe_task(v):
    assert objet(v("task", "done", "a1", "--format", "json"))["action"] == "done"
    assert objet(v("task", "add", "T", "--format", "json"))["action"] == "add"


def test_autres_formats_ne_changent_rien(v):
    for fmt in ("text", "plain", "table"):
        r = v("done", "a1", "--format", fmt)
        assert "validée" in r.out or "déjà terminée" in r.out
        v("task", "undone", "a1")


def test_reglage_format_json_n_active_pas_la_sortie_json(v):
    """TODO_FORMAT=json (pour les listes) ne doit pas faire disparaître les messages des commandes d'écriture."""
    r = v("done", "a1", env={"TODO_FORMAT": "json"})
    assert "validée" in r.out and not r.out.lstrip().startswith("{")


def test_dry_run_garde_l_apercu(v):
    r = v("done", "--all", "--dry-run", "--format", "json")
    assert r.code == 0 and v.une("Rapport")["statut"] == "A FAIRE"
    apercu = json.loads(r.out)
    assert not (isinstance(apercu, dict) and "ok" in apercu)       # l'aperçu garde son format, pas l'objet d'écriture


def test_stdout_uniquement_json_meme_avec_hook_bavard(v, tmp_path):
    r = v("done", "a1", "--format", "json", env={"TODO_HOOKS_ON_DONE": "echo bonjour-du-hook"})
    assert r.code == 0 and "bonjour-du-hook" not in r.out and "bonjour-du-hook" in r.err
    assert objet(r)["ok"]


def test_hook_et_json_ensemble(v):
    r = v("done", "a1", "--format", "json", env={"TODO_HOOKS_ON_DONE": "false"})
    assert r.code == 0 and objet(r)["ok"] and "Hook on_done" in r.err


def test_journal_inchange(v):
    env = {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"}
    v("done", "a1", "--format", "json", env=env)
    assert any(l.startswith("INFO done") for l in v.journal())
