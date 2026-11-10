import pytest

from outils import AUJOURDHUI, jour

NOMS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


@pytest.fixture
def garni(todo):
    todo.seed(
        dict(cle="agen0001-0", titre="Retard", priorite="high", echeance=jour(-5)),
        dict(cle="agen0002-0", titre="Aujourdhui-bas", priorite="low", echeance=jour(0)),
        dict(cle="agen0003-0", titre="Aujourdhui-haut", priorite="high", echeance=jour(0), tags=["pro"]),
        dict(cle="agen0004-0", titre="Demain", echeance=jour(1), recurrence="1w"),
        dict(cle="agen0005-0", titre="Dans3", echeance=jour(3)),
        dict(cle="agen0006-0", titre="Loin", echeance=jour(30)),
        dict(cle="agen0007-0", titre="Sans"),
        dict(cle="agen0008-0", titre="Fini", statut="TERMINE", echeance=jour(1), terminee=jour(0) + " 08:00"),
    )
    return todo


def test_agenda_vide(todo):
    r = todo("agenda")
    assert r.code == 0 and r.texte.count("rien de prévu") == 7


def test_agenda_par_defaut(garni):
    r = garni("agenda").texte
    assert "En retard (1)" in r and "Retard" in r and "[5 j.]" in r
    assert r.index("Aujourdhui-haut") < r.index("Aujourdhui-bas")      # priorité haute d'abord
    assert "— aujourd'hui" in r and "— demain" in r
    assert "↻ chaque semaine" in r and "#pro" in r and "(id: agen0003)" in r
    assert "Fini" not in r                                              # terminées exclues
    assert "Loin" not in r
    assert "Plus tard : 1 · Sans échéance : 1" in r
    assert r.count("rien de prévu") == 4                                # 7 jours dont 3 occupés


def test_ordre_des_sections(garni):
    r = garni("agenda").texte
    assert r.index("En retard") < r.index("Retard") < r.index("— aujourd'hui") < r.index("— demain") < r.index("Dans3")


def test_libelle_des_jours(garni):
    assert NOMS[AUJOURDHUI.weekday()].capitalize() in garni("agenda").texte


def test_days(garni):
    r = garni("agenda", "--days", "2").texte
    assert "Dans3" not in r and "Plus tard : 2" in r                    # Dans3 et Loin
    assert garni("agenda", "--days", "40").texte.count("Loin") == 1


@pytest.mark.parametrize("val", ["0", "-1", "abc"])
def test_days_invalide(garni, val):
    assert garni("agenda", "--days", val).code == 2


def test_days_limite(garni):
    r = garni("agenda", "--days", "367")
    assert r.code == 1 and "366" in r.texte


def test_from(garni):
    r = garni("agenda", "--from", "+2d", "--days", "3").texte
    assert "Dans3" in r and "Demain" not in r
    assert "En retard" not in r                                          # fenêtre dans le futur : pas de retards
    assert "Plus tard : 1" in r


def test_from_invalide(garni):
    r = garni("agenda", "--from", "blabla")
    assert r.code == 1 and "Date non reconnue" in r.texte


def test_json(garni):
    d = garni("agenda", "--format", "json", "--days", "4").json()
    assert d["debut"] == jour(0) and d["fin"] == jour(3)
    assert [t["titre"] for t in d["en_retard"]] == ["Retard"]
    assert [j["date"] for j in d["jours"]] == [jour(i) for i in range(4)]
    par_jour = {j["date"]: [t["titre"] for t in j["taches"]] for j in d["jours"]}
    assert par_jour[jour(0)] == ["Aujourdhui-haut", "Aujourdhui-bas"]
    assert par_jour[jour(1)] == ["Demain"] and par_jour[jour(2)] == [] and par_jour[jour(3)] == ["Dans3"]
    assert d["plus_tard"] == 1 and d["sans_echeance"] == 1


def test_pas_de_sauvegarde(garni):
    avant = garni.sauvegardes()
    garni("agenda")
    assert garni.sauvegardes() == avant


def test_pas_de_couleur_dans_un_pipe_et_couleur_dans_un_terminal(garni):
    assert "\x1b" not in garni("agenda").out and "\x1b" not in garni("agenda", "--format", "json").out
    assert "\x1b[" in garni("agenda", "--color", "always").out
    assert garni.pty("agenda", "--days", "2").nb_couleurs > 0


def test_pager_sur_long_affichage(garni, tmp_path):
    import stat
    p = tmp_path / "pg.sh"
    p.write_text("#!/bin/sh\necho '<<PAGER>>'\ncat\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    assert "<<PAGER>>" in garni.pty("agenda", "--days", "30", lignes=15, env={"PAGER": str(p)}).texte
    assert "<<PAGER>>" not in garni.pty("agenda", "--days", "30", "--no-pager", lignes=15, env={"PAGER": str(p)}).texte
    assert "<<PAGER>>" not in garni.pty("agenda", "--format", "json", "--days", "30", lignes=15,
                                        env={"PAGER": str(p)}).texte


def test_agenda_dans_l_aide(todo):
    assert "agenda" in todo("--help").out
