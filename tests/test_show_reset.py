"""show --format json et reset --include-archive."""
import json
import shutil
import subprocess

import pytest

from outils import jour

JOURNAL = {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"}


# ------------------------------------------------------------------ show --format json
def test_show_json_est_un_objet_comme_list(todo):
    todo("add", "Alpha", "--due", jour(2), "--tags", "a,b", "--repeat", "weekly")
    todo("note", "add", todo.id_de("Alpha"), "une note")
    i = todo.id_de("Alpha")
    d = todo("show", i, "--format", "json").json()
    assert isinstance(d, dict)
    assert d == todo.une("Alpha")                       # exactement l'élément de `list --format json`
    assert d["id"].startswith(i) and d["notes"][0]["texte"] == "une note" and d["tags"] == ["a", "b"]


def test_show_json_tache_terminee(todo):
    todo("add", "Fait")
    todo("done", todo.id_de("Fait"))
    d = todo("show", todo.id_de("Fait"), "--format", "json").json()
    assert d["statut"] != "A FAIRE" and d["date_terminee"]


def test_show_text_est_l_affichage_decore(todo):
    todo("add", "Alpha")
    i = todo.id_de("Alpha")
    assert todo("show", i).out == todo("show", i, "--format", "text").out
    assert "DÉTAIL DE LA TÂCHE" in todo("show", i).sortie


def test_show_json_sans_couleur_ni_decor(todo):
    todo("add", "Alpha")
    r = todo("show", todo.id_de("Alpha"), "--format", "json")
    assert "\x1b" not in r.out and r.out.lstrip().startswith("{")


def test_show_json_id_inconnu_n_ecrit_pas_de_json(todo):
    todo("add", "Alpha")
    r = todo("show", "zzzz", "--format", "json")
    assert "{" not in r.out


@pytest.mark.skipif(not shutil.which("jq"), reason="jq absent")
def test_show_json_avec_jq(todo):
    todo("add", "Alpha", "--tags", "x")
    sortie = todo("show", todo.id_de("Alpha"), "--format", "json").out
    r = subprocess.run(["jq", "-r", ".titre, .tags[0]"], input=sortie, capture_output=True, text=True)
    assert r.stdout.split() == ["Alpha", "x"]


# ------------------------------------------------------------------ reset --include-archive
@pytest.fixture
def avec_archive(todo):
    todo("add", "Active")
    todo("add", "Archivée")
    todo("done", todo.id_de("Archivée"))
    todo("archive", "add")
    return todo


def archive(todo):
    return todo("archive", "list", "--format", "json").json()


def test_reset_seul_garde_l_archive(avec_archive):
    avec_archive("admin", "reset", entree="y\n")
    assert avec_archive.taches() == {} and len(archive(avec_archive)) == 1


def test_reset_include_archive_vide_tout(avec_archive):
    r = avec_archive("admin", "reset", "--include-archive", entree="y\n")
    assert r.code == 0 and "Base et archive réinitialisées" in r.sortie
    assert avec_archive.taches() == {} and archive(avec_archive) == []


def test_reset_include_archive_message_de_confirmation(avec_archive):
    r = avec_archive("admin", "reset", "--include-archive", entree="n\n")
    assert "ET l'archive (1)" in r.texte and "1 tâche(s)" in r.texte and "annulée" in r.texte
    assert len(avec_archive.taches()) == 1 and len(archive(avec_archive)) == 1


def test_reset_include_archive_sans_confirmation_ne_fait_rien(avec_archive):
    avec_archive("admin", "reset", "--include-archive")          # entrée vide = refus
    assert len(avec_archive.taches()) == 1 and len(archive(avec_archive)) == 1


def test_reset_include_archive_liste_vide_archive_pleine(avec_archive):
    avec_archive("task", "remove", avec_archive.id_de("Active"))
    assert "déjà vide" in avec_archive("admin", "reset", entree="y\n").texte           # sans l'option : rien à purger
    assert len(archive(avec_archive)) == 1
    avec_archive("admin", "reset", "--include-archive", entree="y\n")
    assert archive(avec_archive) == []


def test_reset_include_archive_tout_est_vide(todo):
    r = todo("admin", "reset", "--include-archive")
    assert r.code == 0 and "déjà vides" in r.texte


def test_reset_include_archive_sauvegarde_puis_undo_rend_tout(avec_archive):
    avec_archive("admin", "reset", "--include-archive", entree="y\n")
    avec_archive("undo")
    assert [t["titre"] for t in avec_archive.taches().values()] == ["Active"]
    assert [t["titre"] for t in archive(avec_archive)] == ["Archivée"]


def test_reset_include_archive_restore(avec_archive):
    avec_archive("admin", "reset", "--include-archive", entree="y\n")
    avec_archive("admin", "restore", "2", "-y")
    assert len(avec_archive.taches()) == 1 and len(archive(avec_archive)) == 1


def test_reset_include_archive_au_journal(avec_archive):
    avec_archive("admin", "reset", "--include-archive", entree="y\n", env=JOURNAL)
    ligne = next(l for l in avec_archive.journal() if l.startswith("INFO reset"))
    assert "archive_included=True" in ligne and "count=2" in ligne


def test_reset_include_archive_supprime_aussi_les_entrees_illisibles(avec_archive):
    avec_archive.seed_brut("illisible", b"\xff pas du json")
    avec_archive("admin", "reset", "--include-archive", entree="y\n")
    assert avec_archive("admin", "restore").code == 0                      # la sauvegarde existe
    import dbm
    with dbm.open(str(avec_archive.db_dir / "todo_db"), "r") as db:
        assert len(db) == 0
