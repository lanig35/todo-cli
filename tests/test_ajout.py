import pytest

from outils import AUJOURDHUI, jour, prochain


def test_ajout_simple(todo):
    r = todo("add", "Acheter du pain")
    assert r.code == 0 and "Tâche ajoutée" in r.texte
    t = todo.une("Acheter du pain")
    assert t["statut"] == "A FAIRE" and t["priorite"] == "medium"
    assert t["date_echeance"] is None and t["tags"] == [] and t["recurrence"] is None


def test_ajout_complet(todo):
    todo("add", "Rapport", "--prio", "high", "--due", "2026-12-25", "--tags", "pro, rapport",
         "--desc", "Chiffres")
    t = todo.une("Rapport")
    assert t["priorite"] == "high" and t["date_echeance"] == "2026-12-25"
    assert t["description"] == "Chiffres"
    assert t["tags"] == ["pro", "rapport"]  # espaces retirés


@pytest.mark.parametrize("saisie, attendu", [
    ("aujourd'hui", jour(0)), ("Aujourd'hui", jour(0)), ("demain", jour(1)), ("DEMAIN", jour(1)),
    ("après-demain", jour(2)), ("apres-demain", jour(2)),
    ("+3d", jour(3)), ("+2w", jour(14)), ("2026-02-03", "2026-02-03"),
])
def test_dates_relatives(todo, saisie, attendu):
    assert todo("add", "X", "--due", saisie).code == 0
    assert todo.echeance("X") == attendu


@pytest.mark.parametrize("n, nom", [(0, "lundi"), (2, "mercredi"), (6, "dimanche")])
def test_jour_de_semaine_est_la_prochaine_occurrence(todo, n, nom):
    todo("add", "X", "--due", nom)
    attendu = prochain(n)
    assert todo.echeance("X") == attendu.strftime("%Y-%m-%d")
    assert attendu > AUJOURDHUI  # jamais aujourd'hui


def test_jour_de_semaine_anglais(todo):
    todo("add", "X", "--due", "friday")
    assert todo.echeance("X") == prochain(4).strftime("%Y-%m-%d")


def test_decalage_en_mois_ramene_en_fin_de_mois(todo):
    todo("add", "X", "--due", "+1m")
    d = todo.echeance("X")
    assert d > jour(27) and d <= jour(31)


@pytest.mark.parametrize("saisie", ["hier", "blabla", "2026-13-45", "+3x"])
def test_dates_invalides(todo, saisie):
    r = todo("add", "X", "--due", saisie)
    assert r.code == 1 and "Date non reconnue" in r.texte
    assert todo.taches() == {}


def test_decalage_negatif_refuse(todo):
    r = todo("add", "X", "--due=-3d")
    assert r.code == 1 and "Date non reconnue" in r.texte


def test_titre_vide_refuse(todo):
    r = todo("add", "   ")
    assert r.code == 1 and "titre" in r.texte.lower()
    assert todo.taches() == {}


@pytest.mark.parametrize("saisie, attendu", [
    ("daily", "1d"), ("weekly", "1w"), ("monthly", "1m"), ("yearly", "1y"), ("3d", "3d"), ("2w", "2w"),
])
def test_recurrence_normalisee(todo, saisie, attendu):
    todo("add", "X", "--repeat", saisie)
    assert todo.une("X")["recurrence"] == attendu


def test_recurrence_a_une_echeance_par_defaut(todo):
    todo("add", "X", "--repeat", "weekly")
    assert todo.echeance("X") == jour(0)


def test_recurrence_invalide(todo):
    r = todo("add", "X", "--repeat", "foo")
    assert r.code == 1 and "Répétition non reconnue" in r.texte
    assert todo.taches() == {}


def test_une_sauvegarde_par_modification(todo):
    todo("add", "A")
    assert len(todo.sauvegardes()) == 1
