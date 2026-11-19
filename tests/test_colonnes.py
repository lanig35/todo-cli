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


def test_colonnes_par_defaut_sans_creation(base):
    lignes = {l[5]: l for l in champs(base("list", "--format", "plain"))}
    assert all(len(l) == 7 for l in lignes.values()) and lignes["Appeler Paul"][6] == "0"
    table = base("list", "--format", "table").out
    assert "CRÉÉE" not in table and "NOTES" in table.splitlines()[1]


# ------------------------------------------------------------------ réglage [general] columns
def test_reglage_par_defaut(base):
    assert base("config", "get", "general.columns").sortie.strip() == "id,status,prio,due,tags,title,notes"


def test_reglage_par_variable_d_environnement(base):
    r = base("list", "--format", "plain", "--status", "todo", env={"TODO_COLUMNS": "title,created"})
    assert champs(r) == [["a" * 8 + "-0", "Appeler Paul", "2026-03-04"]]      # id ajouté en tête


def test_reglage_par_fichier_de_configuration(base):
    base.config("[general]\ncolumns = id, title, created\n")
    assert champs(base("list", "--format", "plain", "--status", "todo")) == [["a" * 8 + "-0", "Appeler Paul", "2026-03-04"]]
    assert "CRÉÉE" in base("list", "--format", "table").out.splitlines()[1]


def test_option_prioritaire_sur_variable_et_fichier(base):
    base.config("[general]\ncolumns = id,created\n")
    r = base("list", "--format", "plain", "--status", "todo", "--columns", "id,title", env={"TODO_COLUMNS": "id,prio"})
    assert champs(r) == [["a" * 8 + "-0", "Appeler Paul"]]
    r = base("list", "--format", "plain", "--status", "todo", env={"TODO_COLUMNS": "id,prio"})
    assert champs(r) == [["a" * 8 + "-0", "high"]]                              # variable > fichier


def test_reglage_vaut_pour_next_et_archive_list(base):
    env = {"TODO_COLUMNS": "id,created"}
    assert champs(base("next", "--format", "plain", env=env)) == [["a" * 8 + "-0", "2026-03-04"]]
    base("archive", "add")
    assert champs(base("archive", "list", "--format", "plain", env=env)) == [["b" * 8 + "-0", "2026-02-01"]]


def test_reglage_sans_effet_sur_text_et_json(base):
    env = {"TODO_COLUMNS": "id,created"}
    r = base("list", "--format", "text", env=env)
    assert r.code == 0 and "Appeler Paul" in r.sortie
    assert base("list", "--format", "json", env=env).json()[0]["titre"]


def test_reglage_n_impose_pas_le_tableau_dans_un_terminal(base):
    """Seule l'option --columns transforme le texte en tableau ; le réglage ne change que les colonnes."""
    r = base.pty("list", env={"TODO_COLUMNS": "id,title", "TODO_FORMAT": None})
    assert "┌" not in r.texte


def test_config_set_normalise_et_valide(base):
    assert base("config", "set", "general.columns", "title,created").code == 0
    assert base("config", "get", "general.columns").sortie.strip() == "id,title,created"
    r = base("config", "set", "general.columns", "foo")
    assert r.code == 1 and "colonne inconnue" in r.texte
    assert base("config", "get", "general.columns").sortie.strip() == "id,title,created"   # inchangé


def test_variable_invalide_signalee_et_ignoree(base):
    r = base("list", "--format", "plain", env={"TODO_COLUMNS": "foo"})
    assert "TODO_COLUMNS" in r.texte and all(len(l) == 7 for l in champs(r))


def test_config_show_indique_l_origine(base):
    lignes = {l[0]: l for l in champs(base("config", "show", "--format", "plain", env={"TODO_COLUMNS": "id,title"}))}
    assert lignes["general.columns"][1:] == ["id,title", "variable TODO_COLUMNS"]


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
