import pytest

from outils import jour


@pytest.fixture
def garni(todo):
    todo.seed(
        dict(cle="next0001-0", titre="Retard-bas", priorite="low", echeance=jour(-10)),
        dict(cle="next0002-0", titre="Retard-haut", priorite="high", echeance=jour(-1)),
        dict(cle="next0003-0", titre="Retard-haut-ancien", priorite="high", echeance=jour(-5)),
        dict(cle="next0004-0", titre="Aujourdhui-bas", priorite="low", echeance=jour(0)),
        dict(cle="next0005-0", titre="Aujourdhui-haut", priorite="high", echeance=jour(0), tags=["pro"]),
        dict(cle="next0006-0", titre="Futur-haut", priorite="high", echeance=jour(20)),
        dict(cle="next0007-0", titre="Futur-moyen-proche", priorite="medium", echeance=jour(2), tags=["pro"],
             description="détail"),
        dict(cle="next0008-0", titre="Sans-moyen", priorite="medium"),
        dict(cle="next0009-0", titre="Fini", statut="TERMINE", priorite="high", echeance=jour(-3)),
    )
    return todo


def prochaines(todo, *args):
    return [t["titre"] for t in todo("next", "--format", "json", *args).json()]


def test_ordre_complet(garni):
    assert prochaines(garni, "-n", "20") == [
        "Retard-haut-ancien", "Retard-haut", "Retard-bas",           # retards : priorité, puis plus ancien
        "Aujourdhui-haut", "Aujourdhui-bas",                         # aujourd'hui : priorité
        "Futur-haut", "Futur-moyen-proche", "Sans-moyen",            # reste : priorité, échéance, sans échéance en dernier
    ]


def test_une_seule_par_defaut(garni):
    assert prochaines(garni) == ["Retard-haut-ancien"]
    r = garni("next").texte
    assert "À FAIRE ENSUITE" in r and "Retard-haut-ancien" in r and "RETARD : 5 j." in r
    assert "7 autre(s) tâche(s) en attente" in r and "todo done next0003" in r
    assert "1." not in r                                              # pas de numérotation pour une seule


def test_plusieurs(garni):
    r = garni("next", "-n", "3").texte
    assert "1. " in r and "2. " in r and "3. " in r and "4. " not in r
    assert "5 autre(s) tâche(s) en attente" in r
    assert len(garni("next", "--count", "99", "--format", "json").json()) == 8


def test_filtres(garni):
    assert prochaines(garni, "--tag", "pro", "-n", "5") == ["Aujourdhui-haut", "Futur-moyen-proche"]
    assert prochaines(garni, "--prio", "medium", "-n", "5") == ["Futur-moyen-proche", "Sans-moyen"]
    assert prochaines(garni, "--tag", "PRO", "--prio", "high") == ["Aujourdhui-haut"]


def test_terminees_exclues(garni):
    assert "Fini" not in prochaines(garni, "-n", "50")


def test_description_et_tags_affiches(garni):
    r = garni("next", "--tag", "pro", "-n", "2").texte
    assert "#pro" in r and "↳ détail" in r and "[DEMAIN]" not in r


def test_recurrence_affichee(todo):
    todo("add", "R", "--repeat", "weekly")
    assert "↻ chaque semaine" in todo("next").texte


def test_rien_a_faire(todo):
    r = todo("next")
    assert r.code == 0 and "Rien à faire" in r.texte
    todo.seed(dict(cle="next0001-0", titre="F", statut="TERMINE"))
    assert "Rien à faire" in todo("next").texte
    assert todo("next", "--format", "json").json() == []


def test_aucune_correspondance(garni):
    r = garni("next", "--tag", "inconnu")
    assert r.code == 0 and "correspondant à ces critères" in r.texte


@pytest.mark.parametrize("val", ["0", "-2", "abc"])
def test_count_invalide(garni, val):
    assert garni("next", "-n", val).code == 2


def test_pas_de_sauvegarde(garni):
    n = garni.sauvegardes()
    garni("next")
    assert garni.sauvegardes() == n


def test_couleurs(garni):
    assert "\x1b" not in garni("next").out
    assert "\x1b[" in garni("next", "--color", "always").out
    assert garni.pty("next").nb_couleurs > 0
