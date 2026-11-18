"""Recherche : insensible aux accents et à la casse, et limitée à certains champs avec --search-in."""
import pytest


@pytest.fixture
def garni(todo):
    todo("add", "Réunion budget", "--literal", "--desc", "Préparer l'ÉTÉ", "--tags", "équipe")
    todo("add", "Courses", "--literal")
    todo("note", todo.id_de("Courses"), "penser à la réunion de demain")
    todo("add", "Garage", "--literal")
    return todo


def titres(r):
    return {t["titre"] for t in r.json()}


@pytest.mark.parametrize("motif", ["reunion", "RÉUNION", "réunion", "Reunion"])
def test_search_ignore_accents_et_casse(garni, motif):
    assert titres(garni("list", "--search", motif, "--format", "json")) == {"Réunion budget", "Courses"}


def test_search_accents_dans_description_et_tags(garni):
    assert titres(garni("list", "--search", "ete", "--format", "json")) == {"Réunion budget"}
    assert titres(garni("list", "--search", "equipe", "--format", "json")) == {"Réunion budget"}
    assert titres(garni("list", "--search", "équipe", "--format", "json")) == {"Réunion budget"}


def test_search_aucune_correspondance(garni):
    assert garni("list", "--search", "zzz", "--format", "json").json() == []


@pytest.mark.parametrize("champs, attendus", [
    ("notes", {"Courses"}),
    ("title", {"Réunion budget"}),
    ("title,notes", {"Réunion budget", "Courses"}),
    ("all", {"Réunion budget", "Courses"}),
    ("tags", set()),
    ("description", set()),
])
def test_search_in_limite_les_champs(garni, champs, attendus):
    r = garni("list", "--search", "reunion", "--search-in", champs, "--format", "json")
    assert titres(r) == attendus


def test_search_in_description_et_tags(garni):
    assert titres(garni("list", "--search", "ete", "--search-in", "description", "--format", "json")) == {"Réunion budget"}
    assert titres(garni("list", "--search", "equipe", "--search-in", "tags", "--format", "json")) == {"Réunion budget"}


def test_search_in_champ_inconnu(garni):
    r = garni("list", "--search", "x", "--search-in", "corps")
    assert r.code == 2 and "champ inconnu" in r.texte


def test_search_in_sans_search(garni):
    r = garni("list", "--search-in", "notes")
    assert r.code == 1 and "--search" in r.sortie


def test_search_in_groupe_task_list(garni):
    assert titres(garni("task", "list", "--search", "reunion", "--search-in", "notes", "--format", "json")) == {"Courses"}


def test_archive_search_accents_et_champs(garni):
    garni("done", garni.id_de("Courses"))
    garni("done", garni.id_de("Réunion budget"))
    garni("archive", "add")
    assert titres(garni("archive", "list", "--search", "REUNION", "--format", "json")) == {"Réunion budget", "Courses"}
    assert titres(garni("archive", "list", "--search", "reunion", "--search-in", "notes", "--format", "json")) == {"Courses"}
    assert titres(garni("archive", "--search", "reunion", "--search-in", "title", "--format", "json")) == {"Réunion budget"}


def test_archive_search_in_sans_search(garni):
    r = garni("archive", "list", "--search-in", "notes")
    assert r.code == 1 and "--search" in r.sortie
