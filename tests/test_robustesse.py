import json


def test_entree_corrompue_ignoree_avec_avertissement(todo):
    todo.seed(dict(cle="rrrr0001-0", titre="Bonne"))
    todo.seed_brut("rrrr0002-0", b"\xff pas du json")
    r = todo("list", "--format", "json")
    assert r.code == 0
    assert [t["titre"] for t in r.json()] == ["Bonne"]  # stdout reste du JSON valide
    assert "rrrr0002" in r.err


def test_anciennes_entrees_sans_champs_recents(todo):
    todo.seed_brut("oooo0001-0", json.dumps({"titre": "Vieille", "statut": "A FAIRE"}).encode())
    t = todo.une("Vieille")
    assert t["priorite"] == "medium" and t["tags"] == [] and t["recurrence"] is None
    assert t["date_terminee"] is None
    assert todo("done", "oooo0001").code == 0
    assert todo.une("Vieille")["statut"] == "TERMINE"


def test_toutes_les_commandes_sur_base_vide(todo):
    for cmd in (["list"], ["stats"], ["restore"], ["clear-done"]):
        assert todo(*cmd).code == 0, cmd


def test_commande_inconnue_et_sans_commande(todo):
    assert todo("nimporte").code == 2
    assert todo().code in (0, 1, 2)


def test_aide(todo):
    r = todo("--help")
    assert r.code == 0 and "usage" in r.out.lower()
    for sous in ("add", "list", "done", "undone", "show", "edit", "remove", "postpone", "restore"):
        assert sous in r.out


def test_titre_avec_caracteres_speciaux(todo):
    titre = "Été — 100 % “guillemets” 日本語 😀"
    todo("add", titre, "--tags", "é,日本")
    t = todo.une(titre)
    assert t["tags"] == ["é", "日本"]


def test_stockage_dans_todo_db_dir(todo):
    todo("add", "A")
    assert any(n.startswith("todo_db") for n in __import__("os").listdir(todo.db_dir))
    assert (todo.db_dir / "backups").is_dir()
