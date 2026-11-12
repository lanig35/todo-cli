import json
import os

import pytest

from outils import jour


def titres_liste(todo, *args, env=None):
    return [t["titre"] for t in todo("list", "--format", "json", *args, env=env).json()]


@pytest.fixture
def dix(todo):
    todo.seed(*[dict(cle=f"conf{i:04d}-0", titre=f"T{i:02d}", echeance=jour(i + 1)) for i in range(10)])
    return todo


def reglage(todo, cle, env=None):
    """(valeur, origine) d'un réglage d'après `config show --format json`."""
    d = {r["cle"]: r for r in todo("config", "show", "--format", "json", env=env).json()["reglages"]}
    return d[cle]["valeur"], d[cle]["origine"]


# ---------------------------------------------------------------- précédence : option > variable > fichier > défaut
def test_limit_precedence(dix):
    assert len(titres_liste(dix)) == 10                                         # défaut : illimité
    dix.config("[list]\nlimit = 4\n")
    assert len(titres_liste(dix)) == 4                                          # fichier
    assert len(titres_liste(dix, env={"TODO_LIST_LIMIT": "3"})) == 3            # variable > fichier
    assert len(titres_liste(dix, "--limit", "2", env={"TODO_LIST_LIMIT": "3"})) == 2   # option > variable
    dix.config("[list]\nlimit = 0\n")
    assert len(titres_liste(dix)) == 10                                         # 0 = illimité


def test_limit_du_fichier_se_combine_avec_start(dix):
    dix.config("[list]\nlimit = 3\n")
    assert titres_liste(dix, "--start", "5") == ["T04", "T05", "T06"]


def test_overdue_first_precedence(todo):
    todo.seed(dict(cle="conf0001-0", titre="Zebre-retard", echeance=jour(-3)),
              dict(cle="conf0002-0", titre="Alpha", echeance=jour(5)))
    assert titres_liste(todo, "--sort", "alpha")[0] == "Zebre-retard"           # défaut : retards d'abord
    todo.config("[list]\noverdue_first = false\n")
    assert titres_liste(todo, "--sort", "alpha") == ["Alpha", "Zebre-retard"]   # fichier
    assert titres_liste(todo, "--sort", "alpha", "--overdue-first")[0] == "Zebre-retard"   # option > fichier
    assert titres_liste(todo, "--sort", "alpha", env={"TODO_LIST_OVERDUE_FIRST": "yes"})[0] == "Zebre-retard"
    todo.config("[list]\noverdue_first = true\n")
    assert titres_liste(todo, "--sort", "alpha", "--no-overdue-first") == ["Alpha", "Zebre-retard"]


def test_add_priority_precedence(todo):
    todo("add", "defaut")
    todo.config("[add]\npriority = high\n")
    todo("add", "fichier")
    todo("add", "variable", env={"TODO_ADD_PRIORITY": "low"})
    todo("add", "option", "--prio", "medium", env={"TODO_ADD_PRIORITY": "low"})
    todo("add", "marqueur !low")                                                # le marqueur du titre > réglage
    prio = {t["titre"]: t["priorite"] for t in todo.taches().values()}
    assert prio == {"defaut": "medium", "fichier": "high", "variable": "low", "option": "medium", "marqueur": "low"}


def test_agenda_days_et_next_count(dix):
    dix.config("[agenda]\ndays = 2\n[next]\ncount = 3\n")
    assert len(dix("agenda", "--format", "json").json()["jours"]) == 2
    assert len(dix("agenda", "--format", "json", "--days", "4").json()["jours"]) == 4
    assert len(dix("next", "--format", "json").json()) == 3
    assert len(dix("next", "--format", "json", "-n", "1").json()) == 1
    assert len(dix("next", "--format", "json", env={"TODO_NEXT_COUNT": "5"}).json()) == 5


def test_keep_backups(todo):
    todo.config("[general]\nkeep_backups = 3\n")
    for i in range(6):
        todo("add", f"T{i}")
    assert len(todo.sauvegardes()) == 3
    for i in range(3):
        todo("add", f"U{i}", env={"TODO_KEEP_BACKUPS": "2"})
    assert len(todo.sauvegardes()) == 2


def test_keep_backups_minimum_deux(todo):
    todo.config("[general]\nkeep_backups = 1\n")
    r = todo("add", "A")
    assert "keep_backups" in r.err and "minimum" in r.err
    assert reglage(todo, "general.keep_backups") == (5, "défaut")


def test_db_dir(todo, tmp_path):
    ailleurs = tmp_path / "ailleurs"
    todo.config(f"[general]\ndb_dir = {ailleurs}\n")
    todo("add", "X", env={"TODO_DB_DIR": None})                                  # sans variable : le fichier décide
    assert any(n.startswith("todo_db") for n in os.listdir(ailleurs))
    assert not any(n.startswith("todo_db") for n in os.listdir(todo.db_dir))     # variable de test absente du dossier
    todo("add", "Y")                                                             # avec la variable : elle l'emporte
    assert any(n.startswith("todo_db") for n in os.listdir(todo.db_dir))


def test_db_dir_tilde(todo, tmp_path):
    todo.config("[general]\ndb_dir = ~/mes-taches\n")
    todo("add", "X", env={"TODO_DB_DIR": None, "HOME": str(tmp_path)})
    assert any(n.startswith("todo_db") for n in os.listdir(tmp_path / "mes-taches"))


def test_color_precedence(todo):
    todo.seed(dict(cle="conf0001-0", titre="T", echeance=jour(-1)))
    assert "\x1b" not in todo("list").out                                        # défaut : pas de couleur dans un pipe
    todo.config("[general]\ncolor = always\n")
    assert "\x1b[" in todo("list").out                                           # fichier
    assert "\x1b" not in todo("list", env={"TODO_COLOR": "never"}).out           # variable > fichier
    assert "\x1b[" in todo("list", "--color", "always", env={"TODO_COLOR": "never"}).out    # option > variable
    assert "\x1b" not in todo("list", "--no-color").out                          # option > fichier


def test_no_color_est_une_variable_donc_plus_forte_que_le_fichier(todo):
    todo.seed(dict(cle="conf0001-0", titre="T"))
    todo.config("[general]\ncolor = always\n")
    assert "\x1b" not in todo("list", env={"NO_COLOR": "1"}).out
    assert "\x1b[" in todo("list", env={"NO_COLOR": "1", "TODO_COLOR": "always"}).out    # TODO_COLOR > NO_COLOR
    assert "\x1b[" in todo("list", "--color", "always", env={"NO_COLOR": "1"}).out       # option > NO_COLOR
    assert reglage(todo, "general.color", env={"NO_COLOR": "1"}) == ("never", "variable NO_COLOR")
    assert "\x1b[" in todo("list", env={"NO_COLOR": ""}).out                              # vide = non définie


def test_color_dans_un_terminal(todo):
    todo.seed(dict(cle="conf0001-0", titre="T"))
    todo.config("[general]\ncolor = never\n")
    assert todo.pty("list").nb_couleurs == 0
    assert todo.pty("list", "--color", "always").nb_couleurs > 0
    todo.config("")
    assert todo.pty("list").nb_couleurs > 0


def test_pager_precedence(todo, tmp_path):
    import stat
    p = tmp_path / "pg.sh"
    p.write_text("#!/bin/sh\necho '<<PAGER>>'\ncat\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    todo.seed(*[dict(cle=f"conf{i:04d}-0", titre=f"T{i}") for i in range(40)])
    env = {"PAGER": str(p)}
    assert "<<PAGER>>" in todo.pty("list", lignes=15, env=env).texte
    todo.config("[general]\npager = false\n")
    assert "<<PAGER>>" not in todo.pty("list", lignes=15, env=env).texte                       # fichier
    assert "<<PAGER>>" in todo.pty("list", "--pager", lignes=15, env=env).texte                # option > fichier
    assert "<<PAGER>>" in todo.pty("list", lignes=15, env={**env, "TODO_PAGER": "true"}).texte  # variable > fichier
    todo.config("")
    assert "<<PAGER>>" not in todo.pty("list", "--no-pager", lignes=15, env=env).texte
    assert "<<PAGER>>" not in todo.pty("agenda", "--days", "30", "--no-pager", lignes=15, env=env).texte
    todo.config("[general]\npager = off\n")
    assert "<<PAGER>>" not in todo.pty("agenda", "--days", "30", lignes=15, env=env).texte


# ---------------------------------------------------------------- remind
@pytest.fixture
def retard(todo):
    todo.seed(*[dict(cle=f"conf{i:04d}-0", titre=f"R{i}", echeance=jour(-1 - i)) for i in range(4)],
              dict(cle="conf0009-0", titre="Bientot", echeance=jour(2)))
    return todo


def test_remind_reglages(retard):
    r = retard("remind").texte
    assert "R3" in r and "R0" in r and "Bientot" not in r                         # défauts : limit 5, soon 0
    retard.config("[remind]\nlimit = 2\nsoon = 3\n")
    r = retard("remind").texte
    assert "… et 3 autre(s)" in r and "1 dans les prochains jours" in r
    r = retard("remind", "--limit", "10").texte
    assert "autre(s)" not in r and "Bientot" in r
    assert "autre(s)" not in retard("remind", env={"TODO_REMIND_LIMIT": "10"}).texte


def test_remind_enabled(retard):
    retard.config("[remind]\nenabled = false\n")
    assert retard("remind").out == "" and retard("remind", "--once-a-day").out == ""
    assert "[remind] enabled" in retard("remind", "--status").texte
    assert "fichier" in retard("remind", "--status").texte
    retard("remind", "--write-status")
    assert (retard.db_dir / "remind_status").read_text() == ""
    assert "R0" in retard("remind", env={"TODO_REMIND_ENABLED": "true"}).texte       # variable > fichier
    assert retard("remind", env={"TODO_REMIND_ENABLED": "true", "TODO_NO_REMIND": "1"}).out == ""   # NO_REMIND coupe toujours
    assert "attention" in retard("remind", "--enable").texte.lower()                   # --enable ne passe pas outre le réglage


def test_remind_les_interrupteurs_se_cumulent(retard):
    retard("remind", "--disable")                                                  # fichier d'état
    assert retard("remind", env={"TODO_REMIND_ENABLED": "true"}).out == ""
    retard("remind", "--enable")
    assert "R0" in retard("remind", env={"TODO_REMIND_ENABLED": "true"}).texte


# ---------------------------------------------------------------- le fichier lui-même
def test_fichier_absent(todo):
    assert not todo.fichier_config.exists()
    r = todo("add", "A")
    assert r.code == 0 and r.err == ""


def test_syntaxe_commentaires_et_casse(dix):
    dix.config("""# commentaire
; autre commentaire
[LIST]
Limit = 2   # commentaire en fin de ligne
Overdue_First = OFF ; idem
""")
    r = dix("list", "--format", "json")
    assert r.err == "" and len(r.json()) == 2
    assert reglage(dix, "list.overdue_first") == (False, "fichier")


@pytest.mark.parametrize("texte", ["true", "True", "YES", "on", "1", "oui", "vrai"])
def test_booleens_vrais(todo, texte):
    todo.config(f"[remind]\nenabled = {texte}\n")
    assert reglage(todo, "remind.enabled") == (True, "fichier")


@pytest.mark.parametrize("texte", ["false", "No", "OFF", "0", "non", "faux"])
def test_booleens_faux(todo, texte):
    todo.config(f"[remind]\nenabled = {texte}\n")
    assert reglage(todo, "remind.enabled") == (False, "fichier")


def test_cle_inconnue_avec_suggestion(todo):
    todo.config("[list]\nlimite = 3\n")
    r = todo("add", "A")
    assert r.code == 0 and "clé inconnue 'limite'" in r.err and "vouliez-vous dire 'limit'" in r.err
    assert todo.fichier_config.name in r.err


def test_section_inconnue(todo):
    todo.config("[listing]\nlimit = 3\n")
    r = todo("add", "A")
    assert r.code == 0 and "section inconnue [listing]" in r.err and "[list]" in r.err


@pytest.mark.parametrize("cle, valeur, morceau", [
    ("list.limit", "abc", "n'est pas un entier"), ("list.limit", "-1", "inférieur au minimum"),
    ("agenda.days", "400", "supérieur au maximum"), ("general.color", "rouge", "n'est pas dans"),
    ("remind.enabled", "peut-être", "n'est pas un booléen"), ("add.priority", "urgent", "n'est pas dans"),
])
def test_valeur_invalide_ignoree(todo, cle, valeur, morceau):
    section, nom = cle.split(".")
    todo.config(f"[{section}]\n{nom} = {valeur}\n[next]\ncount = 2\n")
    r = todo("config", "show", "--format", "json")
    assert r.code == 0 and f"{nom} ignorée" in r.err and morceau in r.err
    valeurs = {x["cle"]: x for x in r.json()["reglages"]}
    assert valeurs[cle]["origine"] == "défaut"
    assert valeurs["next.count"] == {**valeurs["next.count"], "valeur": 2, "origine": "fichier"}   # le reste s'applique


def test_fichier_illisible_ignore(todo):
    todo.config("limit = 3\n[list]\nlimit = 2\n")                         # clé avant toute section : erreur de syntaxe
    r = todo("list", "--format", "json")
    assert r.code == 0 and r.json() == [] and "ignorée" in r.err
    assert reglage(todo, "list.limit") == (0, "défaut")


def test_fichier_non_utf8(todo):
    todo.fichier_config.write_bytes(b"[list]\nlimit = \xff\xfe\n")
    r = todo("list")
    assert r.code == 0 and "ignorée" in r.err


def test_les_avertissements_vont_sur_stderr_et_une_seule_fois(dix):
    dix.config("[list]\nlimite = 3\nlimit = abc\n")
    r = dix("list", "--format", "json")
    assert len(r.json()) == 10                                           # stdout reste du JSON valide
    assert r.err.count("limite") == 1 and r.err.count("abc") == 1
    assert r.out.count("⚠") == 0


def test_variable_invalide_ignoree_avec_avertissement(dix):
    dix.config("[list]\nlimit = 4\n")
    r = dix("list", "--format", "json", env={"TODO_LIST_LIMIT": "beaucoup"})
    assert len(r.json()) == 4 and "TODO_LIST_LIMIT" in r.err               # retombe sur le fichier


def test_variable_vide_ignoree(dix):
    dix.config("[list]\nlimit = 4\n")
    r = dix("list", "--format", "json", env={"TODO_LIST_LIMIT": ""})
    assert len(r.json()) == 4 and r.err == ""


def test_todo_config_vers_un_autre_fichier(dix, tmp_path):
    autre = tmp_path / "autre.ini"
    autre.write_text("[list]\nlimit = 1\n")
    assert len(titres_liste(dix, env={"TODO_CONFIG": str(autre)})) == 1
    assert len(titres_liste(dix)) == 10


# ---------------------------------------------------------------- commande config
def test_config_show(todo):
    todo.config("[list]\nlimit = 7\n")
    r = todo("config", "show", env={"TODO_ADD_PRIORITY": "high", "NO_COLOR": "1"}).texte
    assert str(todo.fichier_config) in r
    assert "list.limit" in r and "7" in r and "fichier" in r
    assert "add.priority" in r and "variable TODO_ADD_PRIORITY" in r
    assert "general.color" in r and "variable NO_COLOR" in r
    assert "agenda.days" in r and "défaut" in r
    assert "Priorité : option > variable d'environnement > fichier > défaut" in r
    assert todo("config").texte == todo("config", "show").texte            # show est l'action par défaut


def test_config_show_fichier_absent_et_limit_illimite(todo):
    r = todo("config", "show").texte
    assert "absent" in r and "0 (illimité)" in r


def test_config_show_json(todo):
    todo.config("[remind]\nlimit = 9\n")
    d = todo("config", "show", "--format", "json").json()
    assert d["fichier"] == str(todo.fichier_config) and d["fichier_existe"] is True
    par_cle = {r["cle"]: r for r in d["reglages"]}
    assert par_cle["remind.limit"] == {"cle": "remind.limit", "valeur": 9, "origine": "fichier", "variable": "TODO_REMIND_LIMIT"}
    assert par_cle["general.db_dir"]["origine"] == "variable TODO_DB_DIR"
    assert par_cle["general.pager"]["valeur"] is True
    assert d["rappels_coupes_par_commande"] is False
    todo("remind", "--disable")
    assert todo("config", "show", "--format", "json").json()["rappels_coupes_par_commande"] is True
    assert "remind --disable" in todo("config", "show").texte


def test_config_path(todo, tmp_path):
    assert todo("config", "path").out.strip() == str(todo.fichier_config)
    r = todo("config", "path", env={"TODO_CONFIG": None, "XDG_CONFIG_HOME": str(tmp_path / "xdg")})
    assert r.out.strip() == str(tmp_path / "xdg" / "todo" / "config.ini")
    r = todo("config", "path", env={"TODO_CONFIG": None, "XDG_CONFIG_HOME": None, "HOME": str(tmp_path)})
    assert r.out.strip() == str(tmp_path / ".config" / "todo" / "config.ini")
    r = todo("config", "path", env={"TODO_CONFIG": "~/x.ini", "HOME": str(tmp_path)})
    assert r.out.strip() == str(tmp_path / "x.ini")


def test_config_init(todo, tmp_path):
    cible = tmp_path / "sous" / "dossier" / "config.ini"
    r = todo("config", "init", env={"TODO_CONFIG": str(cible)})
    assert r.code == 0 and str(cible) in r.texte and cible.is_file()          # crée aussi les dossiers
    r = todo("config", "init", env={"TODO_CONFIG": str(cible)})
    assert r.code == 1 and "existe déjà" in r.texte and "--force" in r.texte
    cible.write_text("# modifié\n")
    assert todo("config", "init", "--force", env={"TODO_CONFIG": str(cible)}).code == 0
    assert cible.read_text().startswith("# Configuration de todo-cli")


def test_config_init_impossible(todo, tmp_path):
    bloc = tmp_path / "fichier"
    bloc.write_text("x")
    r = todo("config", "init", env={"TODO_CONFIG": str(bloc / "config.ini")})   # le « dossier » est un fichier
    assert r.code == 1 and "impossible d'écrire" in r.texte and "Traceback" not in r.err


def test_le_modele_est_valide_et_neutre(todo):
    todo("config", "init")
    texte = todo.fichier_config.read_text()
    assert todo("config", "show").err == ""                                       # aucun avertissement
    for r in todo("config", "show", "--format", "json").json()["reglages"]:
        assert r["origine"] in ("défaut", "variable TODO_DB_DIR"), r             # rien n'est modifié par le modèle
        assert r["cle"].split(".")[1] in texte and r["variable"] in texte        # chaque réglage est documenté
    assert all(l.startswith("#") or l.startswith("[") or not l.strip() for l in texte.splitlines())


def test_le_modele_decommente_s_applique(todo):
    todo("config", "init")
    texte = todo.fichier_config.read_text().replace("# limit = 0", "limit = 2", 1)
    todo.config(texte)
    assert reglage(todo, "list.limit") == (2, "fichier")
    assert todo("config", "show").err == ""


def test_config_dans_l_aide(todo):
    assert "config" in todo("--help").out
    aide = todo("list", "--help").out
    assert "--overdue-first" in aide and "--no-overdue-first" in aide and "--no-pager" in aide


def test_aucune_creation_de_fichier_hors_init(todo):
    todo("add", "A"); todo("list"); todo("config", "show"); todo("config", "path")
    assert not todo.fichier_config.exists()
