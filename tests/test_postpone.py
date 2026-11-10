import pytest

from outils import AUJOURDHUI, jour, prochain


def seed_dates(todo, **dates):
    todo.seed(*[dict(cle=f"pppp000{i}-0", titre=t, echeance=d) for i, (t, d) in enumerate(dates.items(), 1)])


def test_defaut_plus_un_jour(todo):
    seed_dates(todo, A=jour(5))
    r = todo("postpone", "pppp0001")
    assert r.code == 0 and f"{jour(5)} → {jour(6)}" in r.texte
    assert todo.echeance("A") == jour(6)


@pytest.mark.parametrize("cible, attendu", [
    ("+2d", jour(7)), ("+1w", jour(12)), ("2030-01-01", "2030-01-01"), ("demain", jour(1)),
])
def test_cibles(todo, cible, attendu):
    seed_dates(todo, A=jour(5))
    assert todo("postpone", "pppp0001", "--to", cible).code == 0
    assert todo.echeance("A") == attendu


def test_decalage_part_du_plus_tardif_entre_echeance_et_aujourdhui(todo):
    seed_dates(todo, Retard=jour(-10), Sans=None)
    todo("postpone", "pppp0001", "pppp0002", "--to", "+2d")
    assert todo.echeance("Retard") == jour(2)
    assert todo.echeance("Sans") == jour(2)


def test_jour_de_semaine(todo):
    seed_dates(todo, A=jour(1))
    todo("postpone", "pppp0001", "--to", "lundi")
    assert todo.echeance("A") == prochain(0).strftime("%Y-%m-%d")


def test_plusieurs_ids_une_sauvegarde(todo):
    seed_dates(todo, A=jour(1), B=jour(2), C=jour(3))
    assert todo.sauvegardes() == []
    r = todo("postpone", "pppp0001", "pppp0002", "--to", "+1d")
    assert r.code == 0
    assert (todo.echeance("A"), todo.echeance("B"), todo.echeance("C")) == (jour(2), jour(3), jour(3))
    assert len(todo.sauvegardes()) == 1


def test_echec_partiel(todo):
    seed_dates(todo, A=jour(1))
    r = todo("postpone", "pppp0001", "zzzz")
    assert r.code == 1 and "Bilan" in r.texte
    assert todo.echeance("A") == jour(2)


def test_tache_terminee_refusee(todo):
    todo.seed(dict(cle="pppp0001-0", titre="F", statut="TERMINE", echeance=jour(1)))
    r = todo("postpone", "pppp0001")
    assert r.code == 1
    assert todo.echeance("F") == jour(1)


def test_decalage_invalide(todo):
    seed_dates(todo, A=jour(1))
    r = todo("postpone", "pppp0001", "--to", "blabla")
    assert r.code == 1 and todo.echeance("A") == jour(1)


def test_recurrence_repart_de_la_nouvelle_echeance(todo):
    todo.seed(dict(cle="pppp0001-0", titre="R", echeance=jour(1), recurrence="1w"))
    todo("postpone", "pppp0001", "--to", "+3d")
    todo("done", "pppp0001")
    assert todo.une("R", "A FAIRE")["date_echeance"] == jour(4 + 7)
