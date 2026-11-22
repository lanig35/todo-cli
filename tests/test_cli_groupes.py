"""Arbre de commandes : groupes, raccourcis, et refus de la syntaxe 1.x (supprimée en 3.0)."""
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


# --- syntaxe 1.x supprimée en 3.0 ----------------------------------------------------------------------
SUPPRIMEES = [
    (("edit", "{id}", "--title", "X"), "todo edit", "todo task edit"),
    (("undone", "{id}"), "todo undone", "todo task undone"),
    (("remove", "{id}"), "todo remove", "todo task remove"),
    (("postpone", "{id}", "--to", "+1d"), "todo postpone", "todo task postpone"),
    (("note", "{id}", "texte"), "todo note", "todo note add|list|edit|delete"),
    (("note", "{id}"), "todo note", "todo note add|list|edit|delete"),
    (("archive",), "todo archive", "todo archive add|list|purge"),
    (("archive", "--list"), "todo archive", "todo archive add|list|purge"),
    (("archive", "--purge", "-y"), "todo archive", "todo archive add|list|purge"),
    (("unarchive", "abcd"), "todo unarchive", "todo archive restore"),
    (("remind",), "todo remind", "todo reminder check|enable|disable|status"),
    (("remind", "--disable"), "todo remind", "todo reminder check|enable|disable|status"),
    (("stats",), "todo stats", "todo report stats"),
    (("reset",), "todo reset", "todo admin reset"),
    (("restore",), "todo restore", "todo admin restore"),
    (("seed", "3"), "todo seed", "todo admin seed"),
    (("export", "-"), "todo export", "todo data export"),
    (("import", "-"), "todo import", "todo data import"),
]


@pytest.mark.parametrize("ligne, ancienne, nouvelle", SUPPRIMEES)
def test_ancienne_syntaxe_est_refusee_avec_la_nouvelle(base, ligne, ancienne, nouvelle):
    avant = base("list", "--format", "json").out
    r = base(*[a.format(id=base.id_de("retard")) for a in ligne])
    assert r.code == 2 and r.out == ""
    assert f"`{ancienne}`" in r.err and "supprimée en 3.0" in r.err and f"`{nouvelle}`" in r.err
    assert "CHANGELOG" in r.err
    assert base("list", "--format", "json").out == avant and base.sauvegardes() == []


def test_ancienne_syntaxe_refusee_meme_avec_options_globales(base):
    r = base("-p", "default", "--color", "never", "stats")
    assert r.code == 2 and "`todo report stats`" in r.err
    assert base("stats", "--project", "default").code == 2


def test_ancienne_syntaxe_est_journalisee(base):
    base("edit", "{id}", env={"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "warning"})
    assert any("removed_command" in l and "edit" in l for l in base.journal())


def test_deprecation_n_existe_plus(base):
    """TODO_NO_DEPRECATION est ignorée : plus d'avertissement à masquer."""
    assert base("report", "stats", env={"TODO_NO_DEPRECATION": None}).err == ""
    assert base("report", "stats", env={"TODO_NO_DEPRECATION": "1"}).code == 0


@pytest.mark.parametrize("ligne", [("list",), ("task", "list"), ("config",), ("add", "x"), ("next",), ("undo",), ("archive", "list"),
                                   ("note", "list", "aaaaaaaa"), ("reminder", "status"), ("archive", "--help"), ("note", "--help")])
def test_syntaxes_actuelles_acceptees(base, ligne):
    r = base(*ligne)
    assert "supprimée en 3.0" not in r.err and r.code in (0, 1)


def test_archive_sans_action_demande_laquelle(base):
    r = base("archive", "--help")
    assert r.code == 0 and "add" in r.sortie and "purge" in r.sortie


def test_aide_generale_ne_liste_plus_les_anciennes_commandes(base):
    aide = base("--help").sortie
    for nom in ("undone", "unarchive", "postpone", "remind"):
        assert f" {nom} " not in aide.replace("\n", " ")


def test_journal_garde_le_vocabulaire(base):
    base("task", "done", base.id_de("retard"), env={"TODO_LOG_TARGET": "file"})
    assert any(l.startswith("INFO done ") for l in base.journal())
