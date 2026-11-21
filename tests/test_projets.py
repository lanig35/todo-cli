"""Projets : listes de tâches indépendantes (base, archive, sauvegardes, verrou et undo par projet)."""
import json

import pytest

JOURNAL = {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"}


def plain(todo, *args, env=None):
    return [l.split("\t") for l in todo(*args, "--format", "plain", env=env).sortie.splitlines()]


def titres(todo, *args, env=None):
    return [l[5] for l in plain(todo, "list", *args, env=env)]


@pytest.fixture
def pro(todo):
    """Un projet `travail` contenant une tâche, à côté du projet `default` qui en contient une autre."""
    todo("add", "Perso")
    assert todo("project", "create", "travail").code == 0
    assert todo("add", "Pro", "-p", "travail").code == 0
    return todo


# ------------------------------------------------------------------ projet par défaut
def test_sans_projet_tout_reste_a_la_racine(todo):
    todo("add", "Ancien")
    assert list(todo.db_dir.glob("todo_db*")) and (todo.db_dir / "backups").is_dir()
    assert not (todo.db_dir / "projects").exists()
    assert plain(todo, "project", "current") == [["default"]]


def test_current_indique_l_origine(todo):
    r = todo("project", "current", "--format", "json").json()
    assert r["projet"] == "default" and r["origine"] == "défaut" and r["existe"] is True
    todo("project", "create", "x")
    assert todo("project", "current", "-p", "x", "--format", "json").json()["origine"] == "option"
    assert todo("project", "current", "--format", "json", env={"TODO_PROJECT": "x"}).json()["origine"] == "variable TODO_PROJECT"
    todo.config("[general]\nproject = x\n")
    assert todo("project", "current", "--format", "json").json()["origine"] == "fichier"
    assert "option --project" in todo("project", "current", "--format", "text", "-p", "x").sortie


# ------------------------------------------------------------------ create / list
def test_create_cree_le_dossier_du_projet(todo):
    r = todo("project", "create", "travail")
    assert r.code == 0 and "créé" in r.sortie
    assert (todo.db_dir / "projects" / "travail" / "backups").is_dir()


@pytest.mark.parametrize("nom", ["Travail", "../x", "a b", "", "_x", "x" * 33, "é"])
def test_create_refuse_un_nom_invalide(todo, nom):
    r = todo("project", "create", nom)
    assert r.code == 1 and "invalide" in r.texte
    assert not (todo.db_dir / "projects").exists()


def test_create_refuse_un_projet_existant(pro):
    assert pro("project", "create", "travail").code == 1
    assert pro("project", "create", "default").code == 1


def test_list_compteurs_et_courant(pro):
    pro("done", pro.id_de("Perso"))
    pro("add", "Autre", "-p", "travail")
    lignes = {l[0]: l for l in plain(pro, "project", "list")}
    assert lignes["default"] == ["default", "0", "1", "0", "1"]
    assert lignes["travail"] == ["travail", "2", "0", "0", "0"]
    r = pro("project", "list", "--format", "json").json()
    assert r["courant"] == "default" and [p["projet"] for p in r["projets"]] == ["default", "travail"]


def test_list_compte_l_archive(pro):
    ident = pro("list", "-p", "travail", "--format", "json").json()[0]["id"][:8]
    pro("done", ident, "-p", "travail")
    pro("archive", "add", "-p", "travail")
    lignes = {l[0]: l for l in plain(pro, "project", "list")}
    assert lignes["travail"][1:4] == ["0", "0", "1"]


def test_list_formats_text_et_table(pro):
    assert "travail" in pro("project", "list", "--format", "table").sortie and "COURANT" in pro("project", "list", "--format", "table").sortie
    x = pro("project", "list", "--format", "text").sortie
    assert "default" in x and "travail" in x and "projet courant" in x


# ------------------------------------------------------------------ sélection
def test_chaque_projet_a_sa_liste(pro):
    assert titres(pro) == ["Perso"]
    assert titres(pro, "-p", "travail") == ["Pro"]
    assert titres(pro, "--project", "travail") == ["Pro"]
    assert plain(pro, "-p", "travail", "list")[0][5] == "Pro"          # avant la commande
    assert plain(pro, "task", "list", "--project=travail")[0][5] == "Pro"


def test_la_variable_choisit_le_projet(pro):
    assert titres(pro, env={"TODO_PROJECT": "travail"}) == ["Pro"]


def test_priorite_option_variable_fichier_defaut(pro):
    pro("project", "create", "perso2")
    pro("add", "Deux", "-p", "perso2")
    pro.config("[general]\nproject = travail\n")
    assert titres(pro) == ["Pro"]
    assert titres(pro, env={"TODO_PROJECT": "perso2"}) == ["Deux"]
    assert titres(pro, "-p", "default", env={"TODO_PROJECT": "perso2"}) == ["Perso"]


def test_use_ecrit_le_reglage_persistant(pro):
    r = pro("project", "use", "travail")
    assert r.code == 0 and "general.project = travail" in r.sortie
    assert titres(pro) == ["Pro"]
    assert plain(pro, "project", "current") == [["travail"]]
    assert "project = travail" in pro.fichier_config.read_text()
    pro("project", "use", "default")
    assert titres(pro) == ["Perso"]


def test_use_previent_si_la_variable_l_emporte(pro):
    r = pro("project", "use", "travail", env={"TODO_PROJECT": "default"})
    assert r.code == 0 and "TODO_PROJECT" in r.err


def test_use_refuse_un_projet_inconnu(pro):
    r = pro("project", "use", "nope")
    assert r.code == 1 and "n'existe pas" in r.texte
    assert not pro.fichier_config.exists() or "project" not in pro.fichier_config.read_text()


def test_projet_inexistant_refuse_sans_rien_creer(pro):
    for args in (("list", "-p", "nope"), ("add", "X", "-p", "nope"), ("report", "tags", "-p", "nope"), ("undo", "-p", "nope")):
        r = pro(*args)
        assert r.code == 1 and "'nope' n'existe pas" in r.texte and "project create nope" in r.texte
    assert not (pro.db_dir / "projects" / "nope").exists()


def test_projet_inexistant_propose_le_plus_proche(pro):
    assert "vouliez-vous dire 'travail'" in pro("list", "-p", "travai").texte


def test_nom_invalide_dans_l_option(pro):
    r = pro("list", "-p", "../x")
    assert r.code == 1 and "invalide" in r.texte


def test_projet_courant_disparu_est_signale(pro):
    pro("project", "use", "travail")
    pro("project", "use", "default", env={"TODO_PROJECT": None})
    pro.config("[general]\nproject = fantome\n")
    assert pro("list").code == 1
    r = pro("project", "current")
    assert r.code == 1 and "fantome" in r.texte
    assert pro("project", "list").code == 0                           # le groupe `project` reste utilisable
    assert pro("list", "-p", "default").code == 0


def test_la_valeur_invalide_du_fichier_est_ignoree(pro):
    pro.config("[general]\nproject = Pas Valide\n")
    r = pro("project", "current")
    assert plain(pro, "project", "current") == [["default"]] and "project" in r.err.lower()


def test_config_set_valide_le_nom(pro):
    assert pro("config", "set", "general.project", "Mauvais Nom").code == 1
    assert pro("config", "set", "general.project", "travail").code == 0
    assert "general.project" in pro("config", "show").sortie


# ------------------------------------------------------------------ isolation
def test_les_fichiers_sont_par_projet(pro):
    dossier = pro.db_dir / "projects" / "travail"
    assert list(dossier.glob("todo_db*")) and (dossier / "todo.lock").exists()
    avant = pro.sauvegardes()
    pro("add", "Encore", "-p", "travail")
    assert len(list((dossier / "backups").iterdir())) >= 1
    assert pro.sauvegardes() == avant                                   # les sauvegardes de `default` n'ont pas bougé


def test_undo_est_par_projet(pro):
    pro("add", "Deux", "-p", "travail")
    pro("add", "Trois")
    assert pro("undo", "-p", "travail").code == 0
    assert titres(pro, "-p", "travail") == ["Pro"] and sorted(titres(pro)) == ["Perso", "Trois"]


def test_archive_par_projet(pro):
    ident = pro("list", "-p", "travail", "--format", "json").json()[0]["id"]
    pro("done", ident[:8], "-p", "travail")
    pro("archive", "add", "-p", "travail")
    assert plain(pro, "archive", "list", "-p", "travail")[0][5] == "Pro"
    assert plain(pro, "archive", "list") == []
    assert (pro.db_dir / "projects" / "travail").glob("todo_archive*")


def test_les_dependances_ne_traversent_pas_les_projets(pro):
    ident = pro("list", "--format", "json").json()[0]["id"][:8]
    r = pro("add", "Lié", "--after", ident, "-p", "travail")
    assert r.code == 1 and "Lié" not in titres(pro, "-p", "travail")


def test_export_et_import_visent_le_projet_choisi(pro, tmp_path):
    sortie = pro("export", "-p", "travail")
    assert sortie.code == 0 and "Pro" in sortie.out and "Perso" not in sortie.out
    fichier = tmp_path / "perso.json"
    fichier.write_text(pro("export").out, encoding="utf-8")
    assert pro("import", str(fichier), "-p", "travail").code == 0
    assert sorted(titres(pro, "-p", "travail")) == ["Perso", "Pro"] and titres(pro) == ["Perso"]


def test_le_rappel_et_la_configuration_restent_communs(pro):
    pro("reminder", "disable")
    assert (pro.db_dir / "remind_off").exists()
    assert not (pro.db_dir / "projects" / "travail" / "remind_off").exists()
    assert pro("reminder", "status", "-p", "travail", "--format", "json").json()["actif"] is False


def test_config_show_affiche_le_projet_et_son_origine(pro):
    ligne = [l for l in plain(pro, "config", "show") if l[0] == "general.project"][0]
    assert ligne[1:] == ["default", "défaut"]
    ligne = [l for l in plain(pro, "config", "show", env={"TODO_PROJECT": "travail"}) if l[0] == "general.project"][0]
    assert ligne[1:] == ["travail", "variable TODO_PROJECT"]


# ------------------------------------------------------------------ journal
def test_le_journal_nomme_le_projet(todo):
    todo("project", "create", "travail", env=JOURNAL)
    todo("add", "Pro", "-p", "travail", env=JOURNAL)
    todo("add", "Perso", env=JOURNAL)
    lignes = todo.journal()
    assert any(l.startswith("INFO add") and "project=travail" in l for l in lignes)
    assert not any("project=" in l for l in lignes if "Perso" in l or l.startswith("INFO add") and "travail" not in l)


# ------------------------------------------------------------------ rename
def test_rename(pro):
    r = pro("project", "rename", "travail", "bureau")
    assert r.code == 0 and "renommé" in r.sortie
    assert titres(pro, "-p", "bureau") == ["Pro"]
    assert pro("list", "-p", "travail").code == 1


def test_rename_suit_le_projet_courant_du_fichier(pro):
    pro("project", "use", "travail")
    pro("project", "rename", "travail", "bureau")
    assert plain(pro, "project", "current") == [["bureau"]]
    assert titres(pro) == ["Pro"]


@pytest.mark.parametrize("args", [("default", "x"), ("travail", "default"), ("travail", "perso"), ("nope", "x"), ("travail", "Mauvais")])
def test_rename_refus(pro, args):
    pro("project", "create", "perso")
    assert pro("project", "rename", *args).code == 1
    assert titres(pro, "-p", "travail") == ["Pro"]


# ------------------------------------------------------------------ delete
def test_delete_refuse_default_et_le_courant(pro):
    assert pro("project", "delete", "default", "-y").code == 1
    r = pro("project", "delete", "travail", "-y", "-p", "travail")
    assert r.code == 1 and "projet courant" in r.texte
    pro("project", "use", "travail")
    assert pro("project", "delete", "travail", "-y", "--force").code == 1


def test_delete_refuse_un_projet_non_vide_sans_force(pro):
    r = pro("project", "delete", "travail", "-y")
    assert r.code == 1 and "--force" in r.texte and "1 tâche" in r.texte
    assert titres(pro, "-p", "travail") == ["Pro"]


def test_delete_deplace_dans_la_corbeille(pro):
    r = pro("project", "delete", "travail", "-y", "--force")
    assert r.code == 0 and "corbeille" in r.sortie
    assert not (pro.db_dir / "projects" / "travail").exists()
    [corbeille] = list((pro.db_dir / ".trash").iterdir())
    assert corbeille.name.startswith("travail-") and list(corbeille.glob("todo_db*"))
    assert "travail" not in [l[0] for l in plain(pro, "project", "list")]


def test_delete_recuperable_a_la_main(pro):
    pro("project", "delete", "travail", "-y", "--force")
    [corbeille] = list((pro.db_dir / ".trash").iterdir())
    corbeille.rename(pro.db_dir / "projects" / "travail")
    assert titres(pro, "-p", "travail") == ["Pro"]


def test_delete_projet_vide_sans_force(todo):
    todo("project", "create", "vide")
    assert todo("project", "delete", "vide", "-y").code == 0


def test_delete_sans_terminal_exige_y(todo):
    todo("project", "create", "vide")
    r = todo("project", "delete", "vide")
    assert r.code == 1 and "-y" in r.texte and (todo.db_dir / "projects" / "vide").is_dir()


def test_delete_demande_confirmation_dans_un_terminal(todo):
    todo("project", "create", "vide")
    assert (todo.db_dir / "projects" / "vide").is_dir()
    todo.pty("project", "delete", "vide", delai=3)                      # personne ne répond : rien n'est supprimé
    assert (todo.db_dir / "projects" / "vide").is_dir()


def test_delete_inconnu(todo):
    assert todo("project", "delete", "nope", "-y").code == 1


def test_deux_suppressions_successives_ne_se_marchent_pas_dessus(todo):
    todo("project", "create", "vide")
    todo("project", "delete", "vide", "-y")
    todo("project", "create", "vide")
    assert todo("project", "delete", "vide", "-y").code == 0
    assert len(list((todo.db_dir / ".trash").iterdir())) >= 1


# ------------------------------------------------------------------ aide et formats
def test_aide_du_groupe(todo):
    r = todo("project", "--help").sortie
    for verbe in ("current", "list", "create", "use", "rename", "delete"):
        assert verbe in r
    assert "project" in todo("--help").sortie and "--project" in todo("list", "--help").sortie


@pytest.mark.parametrize("fmt", ["json", "plain", "table", "text"])
def test_formats_des_commandes_project(todo, fmt):
    for args in (("create", "p1"), ("current",), ("list",), ("rename", "p1", "p2"), ("delete", "p2", "-y")):
        r = todo("project", *args, "--format", fmt)
        assert r.code == 0, r.texte
        if fmt == "json":
            json.loads(r.out)
