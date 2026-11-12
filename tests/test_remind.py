import os

import pytest

from outils import jour


@pytest.fixture
def garni(todo):
    todo.seed(
        dict(cle="remi0001-0", titre="Retard-bas", priorite="low", echeance=jour(-10)),
        dict(cle="remi0002-0", titre="Retard-haut", priorite="high", echeance=jour(-1)),
        dict(cle="remi0003-0", titre="Retard-haut-ancien", priorite="high", echeance=jour(-5)),
        dict(cle="remi0004-0", titre="Aujourdhui", priorite="medium", echeance=jour(0)),
        dict(cle="remi0005-0", titre="Dans2j", echeance=jour(2)),
        dict(cle="remi0006-0", titre="Loin", echeance=jour(30)),
        dict(cle="remi0007-0", titre="Sans-echeance"),
        dict(cle="remi0008-0", titre="Fini-en-retard", statut="TERMINE", echeance=jour(-20)),
    )
    return todo


def etat(todo, nom):
    return todo.db_dir / nom


def lire(todo, nom):
    return etat(todo, nom).read_text(encoding="utf-8")


# ---------------------------------------------------------------- contenu
@pytest.mark.parametrize("taches", [
    [],
    [dict(cle="remi0001-0", titre="Futur", echeance=jour(3))],
    [dict(cle="remi0001-0", titre="Sans")],
    [dict(cle="remi0001-0", titre="Fini", statut="TERMINE", echeance=jour(-3))],
])
def test_silencieux_sans_rien_a_signaler(todo, taches):
    todo.seed(*taches)
    r = todo("remind")
    assert r.code == 0 and r.out == "" and r.err == ""


def test_silencieux_sans_base(todo):
    r = todo("remind")
    assert r.code == 0 and r.out == "" and r.err == ""


def test_retards_et_aujourdhui(garni):
    r = garni("remind").texte
    assert "3 tâche(s) en retard · 1 pour aujourd'hui" in r
    for attendu in ("Retard-haut", "Retard-haut-ancien", "Retard-bas", "Aujourdhui", "[RETARD : 5 j.]",
                    "[AUJOURD'HUI]", "(id: remi0003)"):
        assert attendu in r
    for absent in ("Dans2j", "Loin", "Sans-echeance", "Fini-en-retard"):
        assert absent not in r
    assert "→ todo list --overdue" in r


def test_ordre(garni):
    r = garni("remind").texte
    # priorité haute d'abord, puis la plus ancienne ; retards avant le jour
    assert r.index("Retard-haut-ancien") < r.index("Retard-haut ") < r.index("Retard-bas") < r.index("Aujourdhui")


def test_seulement_aujourdhui(todo):
    todo.seed(dict(cle="remi0001-0", titre="Du-jour", echeance=jour(0)))
    r = todo("remind").texte
    assert "1 pour aujourd'hui" in r and "en retard" not in r and "→ todo next" in r


def test_limit(garni):
    r = garni("remind", "--limit", "2").texte
    assert "Retard-haut-ancien" in r and "Retard-haut " in r and "Retard-bas" not in r
    assert "… et 2 autre(s)" in r
    assert "3 tâche(s) en retard · 1 pour aujourd'hui" in r        # l'en-tête compte tout
    assert "autre(s)" not in garni("remind", "--limit", "4").texte


@pytest.mark.parametrize("opt, val", [("--limit", "0"), ("--limit", "x"), ("--soon", "0"), ("--soon", "-1")])
def test_valeurs_invalides(garni, opt, val):
    assert garni("remind", opt, val).code == 2


def test_soon(garni):
    assert "Dans2j" not in garni("remind").texte
    assert "Dans2j" not in garni("remind", "--soon", "1").texte
    r = garni("remind", "--soon", "2", "--limit", "10").texte
    assert "Dans2j" in r and "1 dans les prochains jours" in r and "Loin" not in r
    assert r.index("Aujourdhui") < r.index("Dans2j")


def test_soon_seul(todo):
    todo.seed(dict(cle="remi0001-0", titre="Bientot", echeance=jour(2)))
    assert todo("remind").out == ""
    assert "Bientot" in todo("remind", "--soon", "3").texte


def test_ne_modifie_rien(garni):
    avant = garni.sauvegardes()
    garni("remind"); garni("remind", "--write-status"); garni("remind", "--once-a-day")
    assert garni.sauvegardes() == avant
    assert len(garni.taches()) == 8


# ---------------------------------------------------------------- once-a-day
def test_once_a_day(garni):
    assert "Retard-bas" in garni("remind", "--once-a-day").texte
    assert garni("remind", "--once-a-day").out == ""
    assert garni("remind", "--once-a-day").out == ""
    assert "Retard-bas" in garni("remind").texte                    # sans l'option : toujours affiché


def test_once_a_day_se_reaffiche_le_lendemain(garni):
    garni("remind", "--once-a-day")
    etat(garni, "remind_last").write_text(jour(-1))
    assert "Retard-bas" in garni("remind", "--once-a-day").texte
    assert lire(garni, "remind_last").strip() == jour(0)


def test_once_a_day_ne_consomme_pas_le_rappel_quand_il_n_y_a_rien(todo):
    assert todo("remind", "--once-a-day").out == ""
    assert not etat(todo, "remind_last").exists()
    todo("add", "Maintenant", "--due", "aujourd'hui")
    assert "Maintenant" in todo("remind", "--once-a-day").texte    # affiché dès qu'il y a quelque chose


def test_once_a_day_fichier_illisible_ou_absurde(garni):
    etat(garni, "remind_last").write_text("n'importe quoi")
    assert "Retard-bas" in garni("remind", "--once-a-day").texte


def test_once_a_day_incompatible_avec_write_status(garni):
    r = garni("remind", "--once-a-day", "--write-status")
    assert r.code == 1 and "ne s'utilise pas avec" in r.texte


# ---------------------------------------------------------------- write-status
def test_write_status(garni):
    r = garni("remind", "--write-status")
    assert r.code == 0 and r.out == "" and r.err == ""
    assert lire(garni, "remind_status") == "⚠ 3 en retard · 1 aujourd'hui "
    assert not os.path.exists(str(etat(garni, "remind_status")) + ".tmp")


def test_write_status_soon(garni):
    garni("remind", "--write-status", "--soon", "2")
    assert lire(garni, "remind_status") == "⚠ 3 en retard · 1 aujourd'hui · 1 à venir "


def test_write_status_se_vide_quand_il_n_y_a_plus_rien(todo):
    todo("add", "T", "--due", "aujourd'hui")
    todo("remind", "--write-status")
    assert lire(todo, "remind_status").startswith("⚠ ")
    todo("done", todo.id_de("T"))
    todo("remind", "--write-status")
    assert lire(todo, "remind_status") == ""


def test_write_status_sans_couleur_et_sans_toucher_au_stamp(garni):
    garni("remind", "--write-status", "--color", "always")
    assert "\x1b" not in lire(garni, "remind_status")
    assert not etat(garni, "remind_last").exists()


def test_write_status_sur_base_vide(todo):
    assert todo("remind", "--write-status").code == 0
    assert lire(todo, "remind_status") == ""


# ---------------------------------------------------------------- activer / désactiver
def test_disable_enable(garni):
    garni("remind", "--write-status")
    r = garni("remind", "--disable")
    assert r.code == 0 and "désactivés" in r.texte and "todo remind --enable" in r.texte
    assert garni("remind").out == "" and garni("remind", "--once-a-day").out == ""
    assert lire(garni, "remind_status") == ""                      # le résumé de l'invite disparaît tout de suite
    garni("remind", "--write-status")
    assert lire(garni, "remind_status") == ""                      # et ne revient pas tant que c'est désactivé
    r = garni("remind", "--enable")
    assert r.code == 0 and "activés" in r.texte
    assert "Retard-bas" in garni("remind").texte
    garni("remind", "--write-status")
    assert lire(garni, "remind_status") != ""


def test_la_desactivation_persiste_d_un_appel_a_l_autre(garni):
    garni("remind", "--disable")
    for _ in range(3):
        assert garni("remind").out == ""


def test_status(todo):
    assert "activés" in todo("remind", "--status").texte
    todo("remind", "--disable")
    assert "désactivés" in todo("remind", "--status").texte
    todo("remind", "--enable")
    assert "activés" in todo("remind", "--status").texte and "désactivés" not in todo("remind", "--status").texte


def test_status_indique_le_dernier_rappel(garni):
    garni("remind", "--once-a-day")
    assert jour(0) in garni("remind", "--status").texte


def test_enable_reautorise_once_a_day_immediatement(garni):
    garni("remind", "--once-a-day")
    garni("remind", "--disable")
    garni("remind", "--enable")
    assert "Retard-bas" in garni("remind", "--once-a-day").texte


def test_variable_d_environnement(garni):
    env = {"TODO_NO_REMIND": "1"}
    assert garni("remind", env=env).out == ""
    assert garni("remind", "--once-a-day", env=env).out == ""
    assert "TODO_NO_REMIND" in garni("remind", "--status", env=env).texte
    assert "Retard-bas" in garni("remind", env={"TODO_NO_REMIND": ""}).texte    # vide = non définie
    r = garni("remind", "--enable", env=env)
    assert "TODO_NO_REMIND" in r.texte                              # avertit que la variable reste active


@pytest.mark.parametrize("a, b", [("--enable", "--disable"), ("--status", "--disable"), ("--write-status", "--enable"),
                                  ("--write-status", "--status")])
def test_actions_exclusives(garni, a, b):
    assert garni("remind", a, b).code == 2


def test_les_autres_commandes_ignorent_l_etat(garni):
    garni("remind", "--disable")
    assert "Retard-bas" in garni("list").texte
    assert garni("next").code == 0 and garni("agenda").code == 0


# ---------------------------------------------------------------- fichiers d'état et sauvegardes
def test_les_fichiers_d_etat_survivent_a_restore_et_reset(garni):
    garni("remind", "--disable")
    garni("add", "X")
    garni("add", "Y")
    garni("restore", "2", "-y")
    garni("reset", entree="y\n")
    assert etat(garni, "remind_off").exists()
    assert garni("remind").out == ""


def test_les_fichiers_d_etat_ne_sont_pas_dans_les_sauvegardes(garni):
    garni("remind", "--once-a-day")
    garni("remind", "--write-status")
    garni("add", "X")
    dossier = garni.db_dir / "backups" / garni.sauvegardes()[-1]
    assert not [f for f in os.listdir(dossier) if f.startswith("remind")]


def test_un_dossier_non_inscriptible_n_empeche_pas_le_rappel(garni):
    # remplace remind_last par un dossier : l'écriture du tampon échoue, le rappel doit quand même s'afficher
    os.mkdir(etat(garni, "remind_last"))
    r = garni("remind", "--once-a-day")
    assert r.code == 0 and "Retard-bas" in r.texte and "Traceback" not in r.err


# ---------------------------------------------------------------- couleurs
def test_couleurs(garni):
    assert "\x1b" not in garni("remind").out
    assert "\x1b[" in garni("remind", "--color", "always").out
    r = garni.pty("remind")
    assert r.nb_couleurs > 0 and "Retard-bas" in r.texte
    assert garni.pty("remind", "--no-color").nb_couleurs == 0


def test_aide(todo):
    assert "remind" in todo("--help").out
    aide = todo("remind", "--help").out
    for option in ("--once-a-day", "--write-status", "--disable", "--enable", "--soon", "--limit"):
        assert option in aide
