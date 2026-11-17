"""config get / set / unset et option --config (fichier de configuration autre que celui par défaut)."""
import configparser

import pytest


def lire(fichier):
    c = configparser.ConfigParser(interpolation=None)
    c.read(fichier, encoding="utf-8")
    return c


# --- get ---------------------------------------------------------------------------------------------------------
def test_get_valeur_par_defaut(todo):
    assert todo("config", "get", "list.limit").out == "0\n"
    assert todo("config", "get", "general.pager").out == "true\n"
    assert todo("config", "get", "add.priority").out == "medium\n"


def test_get_valeur_effective_et_origine(todo):
    todo.config("[list]\nlimit = 12\n")
    assert todo("config", "get", "list.limit").out == "12\n"
    d = todo("config", "get", "list.limit", "--format", "json").json()
    assert d == {"cle": "list.limit", "valeur": 12, "origine": "fichier", "variable": "TODO_LIST_LIMIT"}
    d = todo("config", "get", "list.limit", "--format", "json", env={"TODO_LIST_LIMIT": "3"}).json()
    assert d["valeur"] == 3 and d["origine"] == "variable TODO_LIST_LIMIT"
    assert todo("config", "get", "list.limit", env={"TODO_LIST_LIMIT": "3"}).out == "3\n"


def test_get_booleen_json_natif(todo):
    assert todo("config", "get", "general.pager", "--format", "json").json()["valeur"] is True


def test_get_file_ignore_environnement_et_defauts(todo):
    todo.config("[list]\nlimit = 12\n")
    assert todo("config", "get", "list.limit", "--file", env={"TODO_LIST_LIMIT": "3"}).out == "12\n"
    r = todo("config", "get", "agenda.days", "--file")
    assert r.code == 1 and r.out == "" and "agenda.days" in r.err
    r = todo("config", "get", "agenda.days", "--file", "--format", "json")
    assert r.code == 1 and r.json()["valeur"] is None


def test_get_cle_inconnue_avec_suggestion(todo):
    r = todo("config", "get", "list.limite")
    assert r.code == 1 and "list.limit" in r.texte and r.out.count("\n") <= 1
    assert todo("config", "get", "limit").code == 1
    j = todo("config", "get", "nimporte.quoi", "--format", "json")
    assert j.code == 1 and j.json()["erreur"] == "unknown_setting"


@pytest.mark.parametrize("args", [("get",), ("get", "a", "b"), ("set", "list.limit"), ("unset",), ("show", "list.limit"), ("path", "x")])
def test_config_arguments_invalides(todo, args):
    assert todo("config", *args).code == 2


# --- set ---------------------------------------------------------------------------------------------------------
def test_set_cree_le_fichier_a_partir_du_modele(todo):
    assert not todo.fichier_config.exists()
    r = todo("config", "set", "list.limit", "20")
    assert r.code == 0 and "list.limit = 20" in r.sortie
    texte = todo.fichier_config.read_text()
    assert "# Configuration de todo-cli" in texte                       # le modèle commenté est conservé
    assert lire(todo.fichier_config)["list"]["limit"] == "20"
    assert todo("list").code == 0
    assert todo("config", "get", "list.limit").out == "20\n"


def test_set_sous_la_valeur_par_defaut_commentee(todo):
    todo("config", "init")
    todo("config", "set", "list.limit", "5")
    lignes = todo.fichier_config.read_text().splitlines()
    i = lignes.index("limit = 5")
    assert lignes[i - 1] == "# limit = 0"


def test_set_remplace_et_garde_le_reste(todo):
    todo.config("# mon fichier\n[general]\ncolor = always  # toujours\npager = false\n\n[list]\nlimit = 3\n")
    todo("config", "set", "list.limit", "9")
    todo("config", "set", "general.color", "never")
    texte = todo.fichier_config.read_text()
    assert texte == "# mon fichier\n[general]\ncolor = never\npager = false\n\n[list]\nlimit = 9\n"


def test_set_ajoute_section_manquante_et_fin_de_section(todo):
    todo.config("[general]\ncolor = never\n\n\n[list]\noverdue_first = no\n")
    todo("config", "set", "remind.soon", "2")
    todo("config", "set", "general.pager", "off")
    c = lire(todo.fichier_config)
    assert c["remind"]["soon"] == "2" and c["general"]["pager"] == "false" and c["list"]["overdue_first"] == "no"


def test_set_normalise_les_booleens_et_les_choix(todo):
    todo("config", "set", "general.pager", "NON")
    todo("config", "set", "general.format", "Table")
    c = lire(todo.fichier_config)
    assert c["general"]["pager"] == "false" and c["general"]["format"] == "table"


@pytest.mark.parametrize("cle, valeur", [("list.limit", "abc"), ("list.limit", "-1"), ("agenda.days", "400"),
                                         ("general.color", "rouge"), ("general.pager", "peut-etre"), ("general.db_dir", "")])
def test_set_valeur_invalide_refusee_sans_toucher_au_fichier(todo, cle, valeur):
    todo.config("[list]\nlimit = 3\n")
    r = todo("config", "set", cle, valeur)
    assert r.code == 1
    assert todo.fichier_config.read_text() == "[list]\nlimit = 3\n"


def test_set_cle_inconnue(todo):
    r = todo("config", "set", "list.limite", "3")
    assert r.code == 1 and "list.limit" in r.texte and not todo.fichier_config.exists()


def test_set_chemin_garde_le_texte_saisi(todo):
    todo("config", "set", "general.db_dir", "~/mes-taches")
    assert lire(todo.fichier_config)["general"]["db_dir"] == "~/mes-taches"


def test_set_avertit_si_une_variable_l_emporte(todo):
    r = todo("config", "set", "list.limit", "7", env={"TODO_LIST_LIMIT": "3"})
    assert r.code == 0 and "TODO_LIST_LIMIT" in r.err and "emporte" in r.err
    assert lire(todo.fichier_config)["list"]["limit"] == "7"
    assert todo("config", "set", "list.limit", "8").err == ""


def test_set_json(todo):
    d = todo("config", "set", "list.limit", "7", "--format", "json").json()
    assert d["cle"] == "list.limit" and d["valeur"] == 7 and d["fichier_cree"] is True and d["ancienne_valeur"] is None
    d = todo("config", "set", "list.limit", "8", "--format", "json").json()
    assert d["ancienne_valeur"] == "7" and d["fichier_cree"] is False and d["surcharge_par"] is None


def test_set_refuse_un_fichier_illisible(todo):
    todo.config("pas du tout\nun fichier ini\n")
    r = todo("config", "set", "list.limit", "7")
    assert r.code == 1 and todo.fichier_config.read_text() == "pas du tout\nun fichier ini\n"


def test_set_impossible_d_ecrire(todo):
    bloc = todo.dossier / "fichier"
    bloc.write_text("x")
    r = todo("config", "set", "list.limit", "7", env={"TODO_CONFIG": str(bloc / "c.ini")})
    assert r.code == 1 and "impossible d'écrire" in r.sortie


def test_set_n_ecrit_pas_si_rien_ne_change(todo):
    todo.config("[list]\nlimit = 7\n")
    avant = todo.fichier_config.stat().st_mtime_ns
    assert todo("config", "set", "list.limit", "7").code == 0
    assert todo.fichier_config.stat().st_mtime_ns == avant


def test_set_conserve_les_permissions(todo):
    todo.config("[list]\nlimit = 3\n")
    todo.fichier_config.chmod(0o600)
    todo("config", "set", "list.limit", "4")
    assert todo.fichier_config.stat().st_mode & 0o777 == 0o600


# --- unset ------------------------------------------------------------------------------------------------------
def test_unset_retire_la_ligne(todo):
    todo.config("# mon fichier\n[list]\nlimit = 3\noverdue_first = no\n")
    r = todo("config", "unset", "list.limit")
    assert r.code == 0
    assert todo.fichier_config.read_text() == "# mon fichier\n[list]\noverdue_first = no\n"
    assert todo("config", "get", "list.limit").out == "0\n"


def test_unset_apres_set_restitue_le_modele(todo):
    todo("config", "init")
    modele = todo.fichier_config.read_text()
    todo("config", "set", "list.limit", "5")
    todo("config", "unset", "list.limit")
    assert todo.fichier_config.read_text() == modele


def test_unset_reglage_absent_ou_fichier_absent_ne_fait_rien(todo):
    assert todo("config", "unset", "list.limit").code == 0 and not todo.fichier_config.exists()
    todo.config("[list]\nlimit = 3\n")
    d = todo("config", "unset", "agenda.days", "--format", "json").json()
    assert d["supprime"] is False and todo.fichier_config.read_text() == "[list]\nlimit = 3\n"
    assert todo("config", "unset", "list.limit", "--format", "json").json()["supprime"] is True


def test_unset_cle_inconnue(todo):
    assert todo("config", "unset", "list.limite").code == 1


# --- journal ---------------------------------------------------------------------------------------------------------
def test_set_et_unset_au_journal_sans_la_valeur(todo):
    env = {"TODO_LOG_TARGET": "file"}
    todo("config", "set", "general.db_dir", "/tmp/secret-xyz", env={**env, "TODO_DB_DIR": str(todo.db_dir)})
    todo("config", "unset", "general.db_dir", env=env)
    texte = "\n".join(todo.journal())
    assert "setting=general.db_dir" in texte and "secret-xyz" not in texte
    assert "action=set" in texte and "action=unset" in texte


# --- --config ---------------------------------------------------------------------------------------------------------
def test_option_config_remplace_le_fichier_par_defaut(todo, tmp_path):
    autre = tmp_path / "autre.ini"
    autre.write_text("[list]\nlimit = 4\n")
    todo.config("[list]\nlimit = 9\n")
    assert todo("config", "get", "list.limit").out == "9\n"
    assert todo("--config", str(autre), "config", "get", "list.limit").out == "4\n"
    assert todo("config", "get", "list.limit", "--config", str(autre)).out == "4\n"
    assert todo("--config=" + str(autre), "config", "get", "list.limit").out == "4\n"


def test_option_config_l_emporte_sur_la_variable(todo, tmp_path):
    autre = tmp_path / "autre.ini"
    autre.write_text("[add]\npriority = high\n")
    r = todo("--config", str(autre), "config", "path", env={"TODO_CONFIG": str(todo.fichier_config)})
    assert r.out.strip() == str(autre)


def test_option_config_oriente_aussi_le_stockage(todo, tmp_path):
    autre = tmp_path / "autre.ini"
    base = tmp_path / "autre-base"
    autre.write_text(f"[general]\ndb_dir = {base}\n")
    r = todo("--config", str(autre), "add", "Ailleurs", env={"TODO_DB_DIR": None})
    assert r.code == 0 and base.is_dir()
    assert "Ailleurs" in todo("--config", str(autre), "list", env={"TODO_DB_DIR": None}).sortie
    assert "Ailleurs" not in todo("list").sortie


def test_option_config_fichier_introuvable_est_une_erreur(todo, tmp_path):
    r = todo("--config", str(tmp_path / "absent.ini"), "list")
    assert r.code == 1 and "introuvable" in r.err and "absent.ini" in r.err
    assert todo("--config", str(tmp_path / "absent.ini"), "config", "get", "list.limit").code == 1
    assert todo("--config", str(tmp_path / "absent.ini"), "config", "show").code == 1


def test_option_config_peut_creer_le_fichier(todo, tmp_path):
    autre = tmp_path / "sous" / "autre.ini"
    assert todo("--config", str(autre), "config", "path").out.strip() == str(autre)
    assert todo("--config", str(autre), "config", "set", "list.limit", "2").code == 0
    assert autre.is_file() and lire(autre)["list"]["limit"] == "2"
    autre2 = tmp_path / "init.ini"
    assert todo("--config", str(autre2), "config", "init").code == 0 and autre2.is_file()


def test_variable_config_absente_reste_tolerante(todo):
    assert todo.fichier_config.exists() is False and todo("list").code == 0


def test_show_indique_l_origine_du_fichier(todo, tmp_path):
    autre = tmp_path / "autre.ini"
    autre.write_text("")
    assert todo("--config", str(autre), "config", "show", "--format", "json").json()["fichier_origine"] == "option --config"
    assert todo("config", "show", "--format", "json").json()["fichier_origine"] == "variable TODO_CONFIG"
    assert "(option --config)" in todo("--config", str(autre), "config", "show", "--format", "text").sortie
    d = todo("config", "show", "--format", "json", env={"TODO_CONFIG": None, "XDG_CONFIG_HOME": str(tmp_path / "xdg")}).json()
    assert d["fichier_origine"] == "défaut" and d["fichier"] == str(tmp_path / "xdg" / "todo" / "config.ini")


def test_option_config_apres_double_tiret_est_un_texte(todo):
    assert todo("add", "--", "--config").code == 0
    assert todo("list").sortie.count("--config") == 1


def test_option_config_aussi_pour_les_anciennes_syntaxes(todo, tmp_path):
    autre = tmp_path / "autre.ini"
    autre.write_text("[add]\npriority = high\n")
    todo("--config", str(autre), "add", "Urgent")
    assert todo.une("Urgent")["priorite"] == "high"
