"""--columns : choix des colonnes des formats table et plain (list, next, archive list) ; date de création par défaut."""
import pytest

from outils import jour


@pytest.fixture
def base(todo):
    todo.seed(
        {"cle": "a" * 8 + "-0", "titre": "Appeler Paul", "echeance": jour(1), "priorite": "high", "tags": ["pro", "tel"],
         "creation": "2026-03-04 09:30", "recurrence": "1w", "description": "au sujet\ndu devis"},
        {"cle": "b" * 8 + "-0", "titre": "Fini", "statut": "TERMINE", "terminee": jour(-1) + " 10:00", "creation": "2026-02-01 08:00"},
    )
    return todo


def champs(r):
    assert r.code == 0, r.texte
    return [l.split("\t") for l in r.out.splitlines()]


def test_creation_dans_le_defaut_de_plain_et_de_table(base):
    lignes = {l[5]: l for l in champs(base("list", "--format", "plain"))}
    assert lignes["Appeler Paul"][-1] == "2026-03-04" and lignes["Fini"][-1] == "2026-02-01"
    table = base("list", "--format", "table").out
    assert "CRÉÉE" in table.splitlines()[1] and "2026-03-04" in table


def test_creation_dans_next_et_archive(base):
    assert champs(base("next", "--format", "plain"))[0][-1] == "2026-03-04"
    base("archive", "add")
    assert champs(base("archive", "list", "--format", "plain"))[0][-1] == "2026-02-01"


def test_colonnes_choisies_dans_l_ordre_demande(base):
    lignes = champs(base("list", "--format", "plain", "--columns", "id,title,created", "--status", "todo"))
    assert lignes == [["a" * 8 + "-0", "Appeler Paul", "2026-03-04"]]


def test_id_toujours_present_et_place_en_tete_s_il_manque(base):
    assert champs(base("list", "--format", "plain", "--columns", "title", "--status", "todo")) == [["a" * 8 + "-0", "Appeler Paul"]]
    # cité, il garde la place demandée
    assert champs(base("list", "--format", "plain", "--columns", "title,id", "--status", "todo")) == [["Appeler Paul", "a" * 8 + "-0"]]


def test_colonnes_repetees_une_seule_fois(base):
    assert champs(base("list", "--format", "plain", "--columns", "id,title,title", "--status", "todo"))[0] == ["a" * 8 + "-0", "Appeler Paul"]


def test_tous_les_champs(base):
    ligne = champs(base("list", "--format", "plain", "--status", "todo",
                        "--columns", "id,status,prio,due,tags,title,notes,created,done,archived,recurrence,description"))[0]
    assert ligne == ["a" * 8 + "-0", "todo", "high", jour(1), "pro,tel", "Appeler Paul", "0", "2026-03-04", "", "", "1w", "au sujet du devis"]


def test_done_et_archived(base):
    base("archive", "add")
    ligne = champs(base("archive", "list", "--format", "plain", "--columns", "id,title,done,archived"))[0]
    assert ligne[1:] == ["Fini", jour(-1), jour(0)]


def test_table_avec_colonnes_choisies_id_court(base):
    lignes = base("list", "--format", "table", "--columns", "title,created", "--status", "todo").out.splitlines()
    assert "ID" in lignes[1] and "TITRE" in lignes[1] and "CRÉÉE" in lignes[1] and "DESCRIPTION" not in lignes[1]
    assert "aaaaaaaa" in lignes[3] and "aaaaaaaa-0" not in lignes[3]


def test_columns_sans_format_dans_un_terminal_donne_un_tableau(base):
    r = base.pty("list", "--columns", "id,title")
    assert "┌" in r.texte and "TITRE" in r.texte and "MA TO-DO LIST" not in r.texte


def test_columns_dans_un_pipe_donne_plain(base):
    # l'environnement de test force TODO_FORMAT=text : on le retire pour retrouver le choix automatique
    r = base("list", "--columns", "id,title", "--status", "todo", env={"TODO_FORMAT": None})
    assert champs(r) == [["a" * 8 + "-0", "Appeler Paul"]]


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_columns_refusee_avec_text_et_json(base, fmt):
    r = base("list", "--format", fmt, "--columns", "id")
    assert r.code == 1 and "--columns" in r.texte


def test_colonne_inconnue_ou_vide(base):
    r = base("list", "--columns", "foo")
    assert r.code == 2 and "colonne inconnue" in r.texte
    assert base("list", "--columns", ",").code == 2


def test_columns_sur_next_et_archive_list(base):
    assert champs(base("next", "--format", "plain", "--columns", "title"))[0] == ["a" * 8 + "-0", "Appeler Paul"]
    base("archive", "add")
    assert champs(base("archive", "list", "--format", "plain", "--columns", "title"))[0][1] == "Fini"
    assert champs(base("archive", "--format", "plain", "--columns", "title"))[0][1] == "Fini"   # ancienne syntaxe : implique --list


def test_columns_avec_les_groupes(base):
    assert champs(base("task", "list", "--format", "plain", "--columns", "created", "--status", "todo"))[0][1] == "2026-03-04"
    assert champs(base("task", "next", "--format", "plain", "--columns", "created"))[0][1] == "2026-03-04"
