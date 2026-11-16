"""Arbre de commandes 2.0 : groupes, raccourcis, anciennes syntaxes dépréciées."""
import pytest

from outils import jour


@pytest.fixture
def base(todo):
    todo.seed(
        {"cle": "a" * 8, "titre": "retard", "echeance": jour(-3)},
        {"cle": "b" * 8, "titre": "fini", "statut": "TERMINE", "terminee": "2026-01-02 10:00"},
    )
    return todo


def test_groupe_task(todo):
    assert todo("task", "add", "Alpha", "--prio", "high").code == 0
    assert todo("task", "list").sortie.count("Alpha") == 1
    ident = todo.id_de("Alpha")
    assert todo("task", "show", ident).code == 0
    assert todo("task", "edit", ident, "--title", "Beta").code == 0
    assert todo("task", "done", ident).code == 0
    assert todo("task", "undone", ident).code == 0
    assert todo("task", "postpone", ident, "--to", "+2d").code == 0
    assert todo("task", "remove", ident).code == 0
    assert todo.taches() == {}


def test_raccourcis_identiques_aux_groupes(base):
    assert base("list", "--format", "json").out == base("task", "list", "--format", "json").out
    assert base("next", "--format", "json").out == base("task", "next", "--format", "json").out
    assert base("agenda", "--format", "json").out == base("report", "agenda", "--format", "json").out


def test_undo_raccourci_et_admin(base):
    base("add", "autre")                      # un état antérieur doit exister pour annuler
    base("done", base.id_de("retard"))
    assert base("undo").code == 0
    assert base.une("retard")["statut"] == "A FAIRE"
    assert base("admin", "undo").code == 0
    assert base.une("retard")["statut"] == "TERMINE"


def test_notes_groupe(base):
    ident = base.id_de("retard")
    assert base("note", "add", ident, "premiere").code == 0
    assert base("note", "add", ident, "seconde").code == 0
    assert [n["texte"] for n in base("note", "list", ident, "--format", "json").json()["notes"]] == ["premiere", "seconde"]
    assert base("note", "edit", ident, "2", "corrigee").code == 0
    assert base("note", "delete", ident, "1").code == 0
    notes = base("note", "list", ident, "--format", "json").json()["notes"]
    assert [n["texte"] for n in notes] == ["corrigee"]


def test_archive_groupe(base):
    assert base("archive", "add").code == 0
    assert "fini" in base("archive", "list").sortie
    assert "fini" in base("archive", "list", "--search", "fin").sortie
    assert base("archive", "purge", "-y").code == 0
    assert "fini" not in base("archive", "list").sortie


def test_archive_restore(base):
    base("archive", "add")
    ident = base("archive", "list", "--format", "json").json()[0]["id"]
    assert base("archive", "restore", ident[:8]).code == 0
    assert "fini" in base("list", "--status", "done").sortie


def test_reminder_groupe(base):
    assert "retard" in base("reminder", "check").sortie
    assert base("reminder", "disable").code == 0
    assert base("reminder", "status", "--format", "json").json()["actif"] is False
    assert base("reminder", "check").out == ""
    assert base("reminder", "enable", "--format", "json").json()["actif"] is True


def test_report_stats_admin_data(base, tmp_path):
    assert base("report", "stats").code == 0
    fichier = tmp_path / "e.json"
    assert base("data", "export", str(fichier)).code == 0
    assert base("data", "import", str(fichier), "--dry-run").code == 0
    assert base("admin", "restore").code == 0
    assert base("admin", "seed", "3").code == 0
    assert base("admin", "reset", entree="y\n").code == 0
    assert base.taches() == {}


def test_config_list_alias_de_show(todo):
    assert todo("config", "list", "--format", "json").json() == todo("config", "show", "--format", "json").json()


# --- anciennes syntaxes -------------------------------------------------------------------------------
ANCIENNES = [
    (("edit", "{id}", "--title", "X"), "task edit"),
    (("remove", "{id}"), "task remove"),
    (("postpone", "{id}"), "task postpone"),
    (("note", "{id}", "texte"), "note add"),
    (("note", "{id}"), "note list"),
    (("archive",), "archive add"),
    (("archive", "--list"), "archive list"),
    (("archive", "--purge", "-y"), "archive purge"),
    (("remind",), "reminder check"),
    (("remind", "--disable"), "reminder disable"),
    (("stats",), "report stats"),
    (("restore",), "admin restore"),
    (("export", "-"), "data export"),
]


@pytest.mark.parametrize("ligne, attendu", ANCIENNES)
def test_ancienne_syntaxe_avertit(base, ligne, attendu):
    ident = base.id_de("retard")
    r = base(*[a.format(id=ident) for a in ligne], env={"TODO_NO_DEPRECATION": None})
    assert r.code == 0
    assert "dépréciée" in r.err and f"`todo {attendu}`" in r.err
    assert "dépréciée" not in r.out


def test_avertissement_masquable(base):
    r = base("stats", env={"TODO_NO_DEPRECATION": "1"})
    assert r.code == 0 and "dépréciée" not in r.err


@pytest.mark.parametrize("ligne", [("list",), ("task", "list"), ("config",), ("add", "x"), ("next",), ("undo",)])
def test_syntaxes_courantes_sans_avertissement(base, ligne):
    r = base(*ligne, env={"TODO_NO_DEPRECATION": None})
    assert "dépréciée" not in r.err


def test_ancienne_et_nouvelle_equivalentes(base):
    assert base("archive", "--list", "--format", "json").out == base("archive", "list", "--format", "json").out
    assert base("remind", "--status", "--format", "json").out == base("reminder", "status", "--format", "json").out


def test_journal_garde_le_vocabulaire(base):
    base("task", "done", base.id_de("retard"), env={"TODO_LOG_TARGET": "file"})
    assert any(l.startswith("INFO done ") for l in base.journal())
