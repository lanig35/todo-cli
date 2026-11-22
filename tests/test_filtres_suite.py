"""Filtres de sélection de list et archive list : tags (ET/OU/aucun/exclus), priorités, récurrence, création, id."""
import pytest

from outils import jour


@pytest.fixture
def garni(todo):
    todo.seed(
        dict(cle="aaaa0001-0", titre="Pro tel haute", tags=["pro", "tel"], priorite="high", creation=jour(-40) + " 09:00"),
        dict(cle="bbbb0002-0", titre="Pro moyenne", tags=["pro"], priorite="medium", creation=jour(-10) + " 09:00", recurrence="1w"),
        dict(cle="cccc0003-0", titre="Perso basse", tags=["perso"], priorite="low", creation=jour(0) + " 09:00"),
        dict(cle="dddd0004-0", titre="Sans tag", priorite="medium", creation=jour(-1) + " 09:00"),
        dict(cle="eeee0005-0", titre="Finie pro", tags=["pro"], priorite="low", statut="TERMINE", terminee=jour(-2) + " 10:00",
             creation=jour(-30) + " 09:00"),
    )
    return todo


def titres(r):
    assert r.code == 0, r.texte
    return {t["titre"] for t in r.json()}


def liste(todo, *args):
    return titres(todo("list", *args, "--format", "json"))


@pytest.mark.parametrize("options, attendus", [
    (["--tag", "pro"], {"Pro tel haute", "Pro moyenne", "Finie pro"}),
    (["--tag", "PRO"], {"Pro tel haute", "Pro moyenne", "Finie pro"}),
    (["--tag", "pro", "--tag", "tel"], {"Pro tel haute"}),                   # TOUS les tags
    (["--tag", "pro,tel"], {"Pro tel haute"}),
    (["--any-tag", "tel,perso"], {"Pro tel haute", "Perso basse"}),          # AU MOINS UN
    (["--any-tag", "tel", "--any-tag", "perso"], {"Pro tel haute", "Perso basse"}),
    (["--tag", "pro", "--any-tag", "tel,perso"], {"Pro tel haute"}),
    (["--no-tag"], {"Sans tag"}),
    (["--not-tag", "pro"], {"Perso basse", "Sans tag"}),
    (["--not-tag", "pro,perso"], {"Sans tag"}),
    (["--tag", "pro", "--not-tag", "tel"], {"Pro moyenne", "Finie pro"}),
])
def test_tags(garni, options, attendus):
    assert liste(garni, *options) == attendus


def test_no_tag_refuse_avec_tag(garni):
    assert garni("list", "--no-tag", "--tag", "pro").code == 1
    assert garni("list", "--no-tag", "--any-tag", "pro").code == 1


@pytest.mark.parametrize("options, attendus", [
    (["--prio", "high"], {"Pro tel haute"}),
    (["--prio", "high,medium"], {"Pro tel haute", "Pro moyenne", "Sans tag"}),
    (["--prio", "HIGH,Low"], {"Pro tel haute", "Perso basse", "Finie pro"}),
    (["--not-prio", "medium"], {"Pro tel haute", "Perso basse", "Finie pro"}),
    (["--not-prio", "medium,low"], {"Pro tel haute"}),
    (["--prio", "high,medium", "--not-prio", "high"], {"Pro moyenne", "Sans tag"}),
])
def test_priorites(garni, options, attendus):
    assert liste(garni, *options) == attendus


def test_priorite_inconnue(garni):
    r = garni("list", "--prio", "urgent")
    assert r.code == 2 and "priorité inconnue" in r.texte
    assert garni("list", "--not-prio", "high,zzz").code == 2


def test_recurrence(garni):
    assert liste(garni, "--recurring") == {"Pro moyenne"}
    assert "Pro moyenne" not in liste(garni, "--no-recurring") and len(liste(garni, "--no-recurring")) == 4
    assert garni("list", "--recurring", "--no-recurring").code == 2


@pytest.mark.parametrize("options, attendus", [
    (["--created-after", "15d"], {"Pro moyenne", "Perso basse", "Sans tag"}),
    (["--created-after", "hier"], {"Perso basse", "Sans tag"}),
    (["--created-before", "20d"], {"Pro tel haute", "Finie pro"}),
    (["--created-after", "35d", "--created-before", "20d"], {"Finie pro"}),
    (["--created-after", jour(-10), "--created-before", jour(-10)], {"Pro moyenne"}),     # bornes incluses
])
def test_creation(garni, options, attendus):
    assert liste(garni, *options) == attendus


def test_creation_dates_invalides(garni):
    r = garni("list", "--created-after", "demain")
    assert r.code == 1 and "--created-after" in r.texte
    r = garni("list", "--created-after", "1d", "--created-before", "10d")
    assert r.code == 1 and "Plage vide" in r.texte


def test_id(garni):
    assert liste(garni, "--id", "bbbb") == {"Pro moyenne"}
    assert liste(garni, "--id", "AAAA0001") == {"Pro tel haute"}
    assert liste(garni, "--id", "aaaa,cccc") == {"Pro tel haute", "Perso basse"}
    assert liste(garni, "--id", "aaaa", "--id", "dddd") == {"Pro tel haute", "Sans tag"}
    assert liste(garni, "--id", "zzzz") == set()


def test_combinaisons_avec_les_filtres_existants(garni):
    assert liste(garni, "--tag", "pro", "--status", "todo", "--prio", "high,medium") == {"Pro tel haute", "Pro moyenne"}
    assert liste(garni, "--search", "pro", "--not-tag", "tel", "--no-recurring") == {"Finie pro"}


def test_groupe_task_list(garni):
    assert titres(garni("task", "list", "--any-tag", "perso", "--format", "json")) == {"Perso basse"}


def test_ancienne_syntaxe_list(garni):
    assert titres(garni("list", "--tag", "pro", "--prio", "high", "--format", "json")) == {"Pro tel haute"}


# ------------------------------------------------------------------ archive list
@pytest.fixture
def archive(garni):
    garni("archive", "add")
    return garni


def arch(todo, *args):
    return titres(todo("archive", "list", *args, "--format", "json"))


def test_archive_selection(archive):
    assert arch(archive, "--tag", "pro") == {"Finie pro"}
    assert arch(archive, "--any-tag", "pro,perso") == {"Finie pro"}
    assert arch(archive, "--no-tag") == set()
    assert arch(archive, "--not-tag", "pro") == set()
    assert arch(archive, "--prio", "low,high") == {"Finie pro"}
    assert arch(archive, "--not-prio", "low") == set()
    assert arch(archive, "--created-before", "20d") == {"Finie pro"}
    assert arch(archive, "--id", "eeee") == {"Finie pro"}
    assert arch(archive, "--no-recurring") == {"Finie pro"} and arch(archive, "--recurring") == set()


def test_archive_list_filtres_et_purge_sans_filtres(archive):
    assert titres(archive("archive", "list", "--any-tag", "pro", "--format", "json")) == {"Finie pro"}
    assert titres(archive("archive", "list", "--prio", "low", "--format", "json")) == {"Finie pro"}
    assert archive("archive", "purge", "--any-tag", "pro", "-y").code == 2
