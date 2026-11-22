"""Filtres de `list` (--no-due, --has-notes, --no-notes, --done-*) et de `archive list`."""
import pytest

from outils import jour


@pytest.fixture
def garni(todo):
    todo.seed(
        dict(cle="aaaa0001-0", titre="Sans echeance"),
        dict(cle="aaaa0002-0", titre="Avec echeance", echeance=jour(3)),
        dict(cle="aaaa0003-0", titre="Finie vieille", statut="TERMINE", terminee=jour(-40) + " 10:00", tags=["pro"], priorite="high"),
        dict(cle="aaaa0004-0", titre="Finie moyenne", statut="TERMINE", terminee=jour(-10) + " 10:00", priorite="low"),
        dict(cle="aaaa0005-0", titre="Finie recente", statut="TERMINE", terminee=jour(0) + " 08:00", tags=["pro"], priorite="low"),
        dict(cle="aaaa0006-0", titre="Finie sans date", statut="TERMINE", terminee=None),
    )
    todo("note", "add", "aaaa0001", "une note")
    todo("note", "add", "aaaa0003", "autre note")
    return todo


def titres(r):
    assert r.code == 0, r.texte
    return {t["titre"] for t in r.json()}


def liste(todo, *args):
    return titres(todo("list", *args, "--format", "json"))


def archive(todo, *args):
    return titres(todo("archive", "list", *args, "--format", "json"))


@pytest.fixture
def archive_garnie(garni):
    garni("archive", "add")
    return garni


# ------------------------------------------------------------------ list
def test_no_due(garni):
    assert liste(garni, "--no-due", "--status", "todo") == {"Sans echeance"}
    assert "Avec echeance" not in liste(garni, "--no-due")


def test_no_due_refuse_avec_plage(garni):
    assert garni("list", "--no-due", "--due-before", "demain").code == 1


def test_has_notes_et_no_notes(garni):
    assert liste(garni, "--has-notes") == {"Sans echeance", "Finie vieille"}
    assert liste(garni, "--no-notes") == {"Avec echeance", "Finie moyenne", "Finie recente", "Finie sans date"}


def test_has_notes_et_no_notes_exclusifs(garni):
    assert garni("list", "--has-notes", "--no-notes").code == 2


@pytest.mark.parametrize("options, attendus", [
    (["--done-after", "30d"], {"Finie moyenne", "Finie recente"}),
    (["--done-after", "hier"], {"Finie recente"}),
    (["--done-after", "aujourd'hui"], {"Finie recente"}),
    (["--done-before", "30d"], {"Finie vieille"}),
    (["--done-before", jour(-10)], {"Finie vieille", "Finie moyenne"}),     # borne incluse
    (["--done-after", "2w", "--done-before", "hier"], {"Finie moyenne"}),
    (["--done-after", "60d", "--done-before", "20d"], {"Finie vieille"}),
])
def test_done_avant_apres(garni, options, attendus):
    assert liste(garni, *options) == attendus


def test_done_exclut_les_taches_sans_date_et_les_a_faire(garni):
    assert "Finie sans date" not in liste(garni, "--done-after", "1y")
    assert "Sans echeance" not in liste(garni, "--done-after", "1y")


@pytest.mark.parametrize("valeur", ["demain", "+3d", "lundi", "n'importe quoi"])
def test_done_refuse_les_dates_futures_ou_inconnues(garni, valeur):
    r = garni("list", "--done-after", valeur)
    assert r.code == 1 and "--done-after" in r.texte


def test_done_plage_vide(garni):
    r = garni("list", "--done-after", "1d", "--done-before", "10d")
    assert r.code == 1 and "Plage vide" in r.texte


def test_filtres_se_combinent_avec_les_autres(garni):
    assert liste(garni, "--has-notes", "--tag", "pro") == {"Finie vieille"}
    assert liste(garni, "--no-notes", "--status", "done", "--prio", "low") == {"Finie moyenne", "Finie recente"}


# ------------------------------------------------------------------ archive list
def test_archive_tag_et_prio(archive_garnie):
    assert archive(archive_garnie, "--tag", "pro") == {"Finie vieille", "Finie recente"}
    assert archive(archive_garnie, "--tag", "PRO", "--prio", "high") == {"Finie vieille"}
    assert archive(archive_garnie, "--prio", "low") == {"Finie moyenne", "Finie recente"}


def test_archive_notes(archive_garnie):
    assert archive(archive_garnie, "--has-notes") == {"Finie vieille"}
    assert archive(archive_garnie, "--no-notes") == {"Finie moyenne", "Finie recente", "Finie sans date"}


@pytest.mark.parametrize("options, attendus", [
    (["--done-after", "30d"], {"Finie moyenne", "Finie recente"}),
    (["--done-before", "30d"], {"Finie vieille"}),
    (["--older-than", "30d"], {"Finie vieille"}),
    (["--older-than", "1d"], {"Finie vieille", "Finie moyenne"}),
])
def test_archive_dates_de_fin(archive_garnie, options, attendus):
    assert archive(archive_garnie, *options) == attendus


def test_archive_dates_d_archivage(archive_garnie):
    tout = {"Finie vieille", "Finie moyenne", "Finie recente", "Finie sans date"}
    assert archive(archive_garnie, "--archived-after", "aujourd'hui") == tout
    assert archive(archive_garnie, "--archived-before", "hier") == set()
    assert archive(archive_garnie, "--archived-after", "aujourd'hui", "--archived-before", "aujourd'hui") == tout


def test_archive_older_than_invalide(archive_garnie):
    r = archive_garnie("archive", "list", "--older-than", "bientot")
    assert r.code == 1 and "--older-than" in r.texte


def test_archive_plage_vide(archive_garnie):
    r = archive_garnie("archive", "list", "--archived-after", "1d", "--archived-before", "10d")
    assert r.code == 1 and "Plage vide" in r.texte


def titres_ordonnes(todo, *args):
    return [t["titre"] for t in todo("archive", "list", *args, "--format", "json").json()]


def test_archive_tris(archive_garnie):
    assert titres_ordonnes(archive_garnie)[:3] == ["Finie recente", "Finie moyenne", "Finie vieille"]
    assert titres_ordonnes(archive_garnie, "--sort", "alpha") == sorted(titres_ordonnes(archive_garnie), key=str.lower)
    assert titres_ordonnes(archive_garnie, "--sort", "priority")[0] == "Finie vieille"   # high d'abord


def test_archive_limit_et_start(archive_garnie):
    complet = titres_ordonnes(archive_garnie)
    assert titres_ordonnes(archive_garnie, "--limit", "2") == complet[:2]
    assert titres_ordonnes(archive_garnie, "--limit", "2", "--start", "3") == complet[2:4]
    assert titres_ordonnes(archive_garnie, "--start", "9") == []


def test_archive_texte_indique_la_tranche(archive_garnie):
    r = archive_garnie("archive", "list", "--limit", "1", "--format", "text")
    assert "1 sur 4 tâche(s) archivée(s)" in r.texte


def test_archive_aucun_resultat(archive_garnie):
    r = archive_garnie("archive", "list", "--tag", "inconnu", "--format", "text")
    assert "ne correspond à vos critères" in r.texte


def test_archive_list_et_filtres(archive_garnie):
    assert titres(archive_garnie("archive", "list", "--tag", "pro", "--format", "json")) == {"Finie vieille", "Finie recente"}


def test_archive_purge_refuse_les_filtres(archive_garnie):
    assert archive_garnie("archive", "purge", "--tag", "pro", "-y").code == 2       # `purge` n'a pas ces filtres
