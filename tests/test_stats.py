from outils import jour


def test_stats_base_vide(todo):
    r = todo("stats")
    assert r.code == 0


def test_stats_contenu(todo):
    todo.seed(
        dict(cle="ssss0001-0", titre="A", priorite="high", echeance=jour(-1), tags=["pro"]),
        dict(cle="ssss0002-0", titre="B", priorite="medium", echeance=jour(0), tags=["pro", "dev"]),
        dict(cle="ssss0003-0", titre="C", priorite="low"),
        dict(cle="ssss0004-0", titre="D", statut="TERMINE", terminee=jour(0) + " 08:00"),
    )
    r = todo("stats")
    assert r.code == 0
    assert "4 tâche(s) au total" in r.texte and "25% terminées (1/4)" in r.texte
    assert "#pro : 2" in r.texte and "#dev : 1" in r.texte
    assert "En retard        : 1" in r.texte and "Pour aujourd'hui : 1" in r.texte
    assert "1 terminée(s) aujourd'hui" in r.texte
