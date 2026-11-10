import json

import pytest

from outils import jour


@pytest.fixture
def garni(todo):
    todo.seed(
        dict(cle="aaaa0001-0000", titre="Zeta", priorite="low", echeance=jour(5), tags=["pro"]),
        dict(cle="aaaa0002-0000", titre="Alpha", priorite="high", echeance=jour(-3), tags=["perso", "pro"]),
        dict(cle="aaaa0003-0000", titre="Mike", priorite="medium", echeance=jour(0), description="contient rapport"),
        dict(cle="aaaa0004-0000", titre="Bravo", priorite="high", echeance=None),
        dict(cle="aaaa0005-0000", titre="Fini", statut="TERMINE", priorite="high", echeance=jour(-10),
             terminee=jour(-1) + " 09:00"),
        dict(cle="aaaa0006-0000", titre="Charlie", priorite="medium", echeance=jour(1)),
    )
    return todo


def titres(r):
    return [t["titre"] for t in r.json()]


def lister(todo, *args):
    return titres(todo("list", "--format", "json", *args))


def test_liste_vide(todo):
    r = todo("list")
    assert r.code == 0 and "liste est vide" in r.texte
    assert todo("list", "--format", "json").json() == []


def test_ordre_par_defaut(garni):
    # à faire avant terminées ; échéance (sans échéance en dernier) ; priorité haute d'abord
    assert lister(garni) == ["Alpha", "Mike", "Charlie", "Zeta", "Bravo", "Fini"]


@pytest.mark.parametrize("tri, attendu", [
    ("alpha", ["Alpha", "Bravo", "Charlie", "Fini", "Mike", "Zeta"]),
    ("priority", ["Alpha", "Bravo", "Mike", "Charlie", "Zeta", "Fini"]),
    ("due", ["Alpha", "Mike", "Charlie", "Zeta", "Bravo", "Fini"]),
])
def test_tris(garni, tri, attendu):
    got = lister(garni, "--sort", tri)
    assert sorted(got) == sorted(attendu)
    assert got[0] == "Alpha"  # le retard passe devant
    if tri == "alpha":
        assert got[1:] == sorted(got[1:])


def test_sans_retard_en_premier(garni):
    assert lister(garni, "--sort", "alpha", "--no-overdue-first") == \
        ["Alpha", "Bravo", "Charlie", "Fini", "Mike", "Zeta"]
    assert lister(garni, "--sort", "alpha")[0] == "Alpha"


def test_retard_en_premier_devant_un_tri_alpha(garni):
    garni.seed(dict(cle="aaaa0007-0000", titre="Aaa", echeance=jour(9)),
               dict(cle="aaaa0008-0000", titre="Zzz-retard", echeance=jour(-2)))
    got = lister(garni, "--sort", "alpha")
    assert got.index("Zzz-retard") < got.index("Aaa")
    got = lister(garni, "--sort", "alpha", "--no-overdue-first")
    assert got.index("Aaa") < got.index("Zzz-retard")


@pytest.mark.parametrize("args, attendu", [
    (["--status", "todo"], {"Alpha", "Mike", "Charlie", "Zeta", "Bravo"}),
    (["--status", "done"], {"Fini"}),
    (["--prio", "high"], {"Alpha", "Bravo", "Fini"}),
    (["--tag", "pro"], {"Alpha", "Zeta"}),
    (["--search", "rapport"], {"Mike"}),
    (["--search", "PERSO"], {"Alpha"}),
    (["--overdue"], {"Alpha"}),
    (["--today"], {"Mike"}),
    (["--overdue", "--today"], {"Alpha", "Mike"}),
    (["--status", "todo", "--prio", "high", "--tag", "pro"], {"Alpha"}),
    (["--search", "introuvable"], set()),
])
def test_filtres(garni, args, attendu):
    assert set(lister(garni, *args)) == attendu


def test_filtres_par_date(garni):
    assert set(lister(garni, "--due-before", jour(0))) == {"Alpha", "Mike"}       # borne incluse
    assert set(lister(garni, "--due-after", jour(1))) == {"Charlie", "Zeta"}      # borne incluse
    assert set(lister(garni, "--due-after", "demain", "--due-before", "+5d")) == {"Charlie", "Zeta"}
    # tâches sans échéance et terminées exclues
    assert "Bravo" not in lister(garni, "--due-before", jour(100))
    assert "Fini" not in lister(garni, "--due-before", jour(100))
    assert lister(garni, "--due-before", jour(100), "--status", "done") == ["Fini"]


def test_date_de_filtre_invalide(garni):
    r = garni("list", "--due-before", "nimporte")
    assert r.code != 0


def test_pagination(garni):
    tout = lister(garni)
    assert lister(garni, "--limit", "2") == tout[:2]
    assert lister(garni, "--start", "3") == tout[2:]
    assert lister(garni, "--start", "2", "--limit", "3") == tout[1:4]
    assert lister(garni, "--start", "6", "--limit", "10") == tout[5:]


def test_pagination_sur_liste_filtree(garni):
    todo_ = lister(garni, "--status", "todo")
    assert lister(garni, "--status", "todo", "--start", "2", "--limit", "2") == todo_[1:3]


def test_pagination_texte(garni):
    r = garni("list", "--limit", "2", "--start", "2", "--no-pager")
    assert "Affichage 2–3 sur 6" in r.texte and "--start 4 --limit 2" in r.texte
    assert "  2. " in r.texte and "  3. " in r.texte and "  1. " not in r.texte


def test_pagination_hors_liste(garni):
    r = garni("list", "--start", "99")
    assert r.code == 0 and "Aucune tâche à partir de la position 99" in r.texte
    assert garni("list", "--start", "99", "--format", "json").json() == []


@pytest.mark.parametrize("opt, val", [("--limit", "0"), ("--limit", "-1"), ("--start", "0"), ("--limit", "abc")])
def test_pagination_valeurs_invalides(garni, opt, val):
    assert garni("list", opt, val).code == 2


def test_json_valide_et_complet(garni):
    data = json.loads(garni("list", "--format", "json").out)
    assert len(data) == 6
    for t in data:
        assert {"id", "titre", "statut", "priorite", "date_creation", "date_echeance", "tags",
                "recurrence", "date_terminee", "description"} <= set(t)


def test_table_contient_id_et_marqueurs(garni):
    r = garni("list")
    assert "(id: aaaa0002)" in r.texte
    assert "RETARD" in r.texte and "AUJOURD" in r.texte and "DEMAIN" in r.texte
    assert "6 tâche(s)" in r.texte
