"""Archivage par tag (`archive add --tag`) et archivage automatique ([archive] auto_days)."""
import datetime

import pytest

from outils import jour

AUTO = {"TODO_ARCHIVE_AUTO_DAYS": "30"}


@pytest.fixture
def garni(todo):
    todo.seed(
        dict(cle="aaaa0001-0", titre="Pro finie", statut="TERMINE", terminee=jour(-40) + " 10:00", tags=["pro"]),
        dict(cle="bbbb0002-0", titre="Pro finie recente", statut="TERMINE", terminee=jour(-2) + " 10:00", tags=["pro", "tel"]),
        dict(cle="cccc0003-0", titre="Pro a faire", tags=["pro"]),
        dict(cle="dddd0004-0", titre="Perso finie", statut="TERMINE", terminee=jour(-50) + " 10:00", tags=["perso"]),
        dict(cle="eeee0005-0", titre="Sans tag finie", statut="TERMINE", terminee=jour(-60) + " 10:00"),
    )
    return todo


def actives(todo):
    return {t["titre"] for t in todo("list", "--format", "json").json()}


def archivees(todo):
    return {t["titre"] for t in todo("archive", "list", "--format", "json").json()}


# ------------------------------------------------------------------ archive add --tag
def test_archive_add_tag_archive_les_terminees_de_ce_tag(garni):
    r = garni("archive", "add", "--tag", "pro")
    assert r.code == 0 and "2 tâche(s) archivée(s)" in r.sortie
    assert archivees(garni) == {"Pro finie", "Pro finie recente"}
    assert actives(garni) == {"Pro a faire", "Perso finie", "Sans tag finie"}


def test_archive_add_tag_signale_les_taches_a_faire_restantes(garni):
    assert "1 tâche(s) à faire portant ce(s) tag(s) restent" in garni("archive", "add", "--tag", "pro").sortie


def test_archive_add_tag_insensible_a_la_casse_et_repetable(garni):
    garni("archive", "add", "--tag", "PRO", "--tag", "tel")                  # tous les tags
    assert archivees(garni) == {"Pro finie recente"}
    garni("archive", "add", "--tag", "perso,pro")                            # aucune tâche n'a les deux
    assert archivees(garni) == {"Pro finie recente"}


def test_archive_add_tag_avec_older_than(garni):
    garni("archive", "add", "--tag", "pro", "--older-than", "30d")
    assert archivees(garni) == {"Pro finie"}


def test_archive_add_tag_sans_correspondance(garni):
    r = garni("archive", "add", "--tag", "inconnu")
    assert r.code == 0 and "Aucune tâche terminée portant #inconnu" in r.sortie and archivees(garni) == set()


def test_archive_add_tag_refuse_avec_des_identifiants(garni):
    r = garni("archive", "add", "aaaa", "--tag", "pro")
    assert r.code == 1 and "OU" in r.texte and archivees(garni) == set()


def test_archive_add_tag_est_annulable(garni):
    garni("add", "Derniere", "--literal")                                    # undo a besoin d'un état antérieur
    garni("archive", "add", "--tag", "pro")
    assert garni("undo").code == 0
    assert archivees(garni) == set()


# ------------------------------------------------------------------ archivage automatique
def test_desactive_par_defaut(garni):
    garni("add", "Nouvelle", "--literal")
    assert archivees(garni) == set()
    assert garni("config", "get", "archive.auto_days").sortie.strip() == "0"


def test_auto_archive_a_la_premiere_modification(garni):
    r = garni("add", "Nouvelle", "--literal", env=AUTO)
    assert r.code == 0 and "3 tâche(s) terminée(s) depuis plus de 30 jour(s) archivée(s)" in r.err
    assert archivees(garni) == {"Pro finie", "Perso finie", "Sans tag finie"}      # pas la terminée d'il y a 2 jours
    assert actives(garni) == {"Pro finie recente", "Pro a faire", "Nouvelle"}


def test_auto_archive_message_sur_stderr_pas_sur_stdout(garni):
    r = garni("add", "Nouvelle", "--literal", env=AUTO)
    assert "automatiquement" not in r.sortie and "automatiquement" in r.err


def test_auto_archive_une_fois_par_jour(garni):
    garni("add", "Un", "--literal", env=AUTO)
    garni.seed(dict(cle="ffff0006-0", titre="Vieille tardive", statut="TERMINE", terminee=jour(-90) + " 10:00"))
    r = garni("add", "Deux", "--literal", env=AUTO)
    assert "automatiquement" not in r.err and "Vieille tardive" in actives(garni)
    # le lendemain : le fichier d'état date d'hier
    (garni.db_dir / "archive_auto").write_text((datetime.date.today() - datetime.timedelta(days=1)).isoformat() + "\n")
    r = garni("add", "Trois", "--literal", env=AUTO)
    assert "1 tâche(s)" in r.err and "Vieille tardive" in archivees(garni)


@pytest.mark.parametrize("commande", [("list",), ("next",), ("show", "cccc"), ("agenda",), ("report", "stats")])
def test_auto_archive_ne_se_declenche_pas_sur_les_lectures(garni, commande):
    assert garni(*commande, env=AUTO).code == 0
    assert archivees(garni) == set() and not (garni.db_dir / "archive_auto").exists()


@pytest.mark.parametrize("commande", [("archive", "list"), ("archive", "add", "--tag", "zzz"), ("admin", "undo")])
def test_auto_archive_ne_se_declenche_pas_sur_les_commandes_d_archive_et_d_historique(garni, commande):
    garni("add", "Une", "--literal")
    garni("add", "Deux", "--literal")
    garni(*commande, env=AUTO)
    assert not (garni.db_dir / "archive_auto").exists()


def test_auto_archive_par_le_fichier_de_configuration(garni):
    garni.config("[archive]\nauto_days = 45\n")
    garni("add", "Nouvelle", "--literal")
    assert archivees(garni) == {"Perso finie", "Sans tag finie"}              # terminées depuis plus de 45 jours


def test_auto_archive_valeur_invalide_ignoree(garni):
    r = garni("add", "Nouvelle", "--literal", env={"TODO_ARCHIVE_AUTO_DAYS": "-5"})
    assert r.code == 0 and "TODO_ARCHIVE_AUTO_DAYS" in r.texte and archivees(garni) == set()


def test_auto_archive_ne_touche_pas_aux_taches_a_faire_ni_sans_date(garni):
    garni.seed(dict(cle="9999aaaa-0", titre="Finie sans date", statut="TERMINE", terminee=None))
    garni("add", "Nouvelle", "--literal", env=AUTO)
    assert "Finie sans date" in actives(garni) and "Pro a faire" in actives(garni)


def test_auto_archive_cree_une_sauvegarde_et_reste_annulable(garni):
    garni("add", "Une", "--literal")
    avant = len(garni.sauvegardes())
    garni("add", "Deux", "--literal", env=AUTO)
    assert len(garni.sauvegardes()) > avant
