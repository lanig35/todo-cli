"""Codes de sortie : 0 = succès (ou rien à faire), 1 = erreur, y compris pour show, edit et undone."""
import json

import pytest


@pytest.fixture
def une(todo):
    todo("add", "Alpha")
    return todo, todo.id_de("Alpha")


COMMANDES_AVEC_ID = [
    ("show",), ("show", "--format", "json"), ("task", "edit", "--title", "x"), ("task", "undone",),
    ("done",), ("task", "remove",), ("task", "postpone", "--to", "+1d"), ("note", "add", "texte"), ("note", "list"),
]


def lancer(todo, commande, identifiant):
    """`commande` avec l'identifiant placé après le nom de la commande (et de son groupe : `task edit`, `note add`)."""
    n = 2 if commande[0] in ("task", "note") else 1
    return todo(*commande[:n], identifiant, *commande[n:])


@pytest.mark.parametrize("commande", COMMANDES_AVEC_ID, ids=lambda c: " ".join(c))
def test_identifiant_introuvable_donne_1(une, commande):
    todo, _ = une
    assert lancer(todo, commande, "zzzz").code == 1


@pytest.mark.parametrize("commande", COMMANDES_AVEC_ID, ids=lambda c: " ".join(c))
def test_base_vide_donne_1(todo, commande):
    assert lancer(todo, commande, "zzzz").code == 1


def test_identifiant_ambigu_donne_1(todo):
    todo.seed({"cle": "abc-0001", "titre": "A"}, {"cle": "abc-0002", "titre": "B"})
    for commande in (("show",), ("task", "edit", "--title", "x"), ("task", "undone",)):
        r = lancer(todo, commande, "abc")
        assert r.code == 1, commande


def test_entree_corrompue_donne_1(todo):
    todo.seed_brut("corrompu-1", b"\xff pas du json")
    for commande in (("show",), ("task", "edit", "--title", "x"), ("task", "undone",)):
        assert lancer(todo, commande, "corrompu").code == 1, commande


def test_show_json_erreur_sans_json_sur_stdout_et_code_1(une):
    todo, _ = une
    r = todo("show", "zzzz", "--format", "json")
    assert r.code == 1
    with pytest.raises(ValueError):
        json.loads(r.out)


def test_edit_sans_option_donne_1(une):
    todo, i = une
    assert todo("task", "edit", i).code == 1


def test_edit_recurrente_sans_echeance_donne_1(todo):
    todo("add", "Rituel", "--repeat", "weekly", "--due", "2030-01-01")
    r = todo("task", "edit", todo.id_de("Rituel"), "--due", "none")
    assert r.code == 1 and todo.une("Rituel")["date_echeance"] == "2030-01-01"


def test_undone_avec_occurrence_suivante_terminee_donne_1(todo):
    todo("add", "Rituel", "--repeat", "weekly", "--due", "2030-01-01")
    todo("done", todo.id_de("Rituel", "A FAIRE"))
    todo("done", todo.id_de("Rituel", "A FAIRE"))
    ancienne = min(todo.par_titre("Rituel", "TERMINE"), key=lambda t: t["date_echeance"])
    assert todo("task", "undone", ancienne["id"][:8]).code == 1


@pytest.mark.parametrize("option", [("--due", "n'importe quoi"), ("--repeat", "souvent"), ("--title", " ")])
def test_edit_valeur_invalide_donne_1(une, option):
    todo, i = une
    assert todo("task", "edit", i, *option).code == 1


def test_edit_priorite_hors_choix_donne_2(une):
    todo, i = une                                       # erreur d'usage d'argparse : 2, comme toute option invalide
    assert todo("task", "edit", i, "--prio", "urgent").code == 2


# ------------------------------------------------------------------ ce qui reste à 0 : rien à faire n'est pas une erreur
def test_show_reussi_donne_0(une):
    todo, i = une
    assert todo("show", i).code == 0 and todo("show", i, "--format", "json").code == 0


def test_edit_reussi_ou_sans_changement_donne_0(une):
    todo, i = une
    assert todo("task", "edit", i, "--title", "Autre").code == 0
    assert todo("task", "edit", i, "--title", "Autre").code == 0          # déjà en place : « Aucun changement »


def test_undone_sur_tache_deja_a_faire_donne_0(une):
    todo, i = une
    assert todo("task", "undone", i).code == 0


def test_undone_reussi_donne_0(une):
    todo, i = une
    todo("done", i)
    assert todo("task", "undone", i).code == 0 and todo.une("Alpha")["statut"] == "A FAIRE"


def test_done_sur_tache_deja_terminee_donne_0(une):
    todo, i = une
    todo("done", i)
    assert todo("done", i).code == 0


def test_erreur_au_journal_en_warning(une):
    todo, _ = une
    todo("show", "zzzz", env={"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"})
    assert "WARNING show refus reason=unknown_id prefix=zzzz" in "\n".join(todo.journal())
