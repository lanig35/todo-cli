"""Vues enregistrées : view save / run / list / show / rename / remove, stockées par projet dans views.json."""
import json
import os
import stat

import pytest

from outils import jour


@pytest.fixture
def v(todo):
    todo.seed({"cle": "a1", "titre": "Rapport", "priorite": "high", "echeance": jour(-3)},
              {"cle": "a2", "titre": "Courses", "priorite": "low", "echeance": jour(2)},
              {"cle": "a3", "titre": "Appel", "priorite": "high"},
              {"cle": "a4", "titre": "Facture", "priorite": "medium", "echeance": jour(-1)})
    return todo


def titres(r):
    return [l.split("\t")[5] for l in r.sortie.splitlines()]


def fichier(todo, projet=None):
    base = todo.db_dir if projet is None else todo.db_dir / "projects" / projet
    return base / "views.json"


# ------------------------------------------------------------------ save / run
def test_save_puis_run(v):
    r = v("view", "save", "retards", "--overdue", "--prio", "high", "--format", "text")
    assert r.code == 0 and "enregistrée" in r.sortie and "todo list --overdue --prio high" in r.sortie
    assert titres(v("view", "run", "retards", "--format", "plain")) == ["Rapport"]


def test_commande_explicite_et_groupe(v):
    assert v("view", "save", "a", "list", "--prio", "high").code == 0
    assert v("view", "save", "b", "task", "list", "--prio", "low").code == 0
    assert sorted(titres(v("view", "run", "a", "--format", "plain"))) == ["Appel", "Rapport"]
    assert titres(v("view", "run", "b", "--format", "plain")) == ["Courses"]


def test_sans_option_equivaut_a_list(v):
    v("view", "save", "tout")
    assert json.loads(fichier(v).read_text())["vues"]["tout"]["args"] == ["list"]
    assert len(titres(v("view", "run", "tout", "--format", "plain"))) == 4


def test_options_ajoutees_au_run(v):
    v("view", "save", "hautes", "--prio", "high")
    r = v("view", "run", "hautes", "--format", "json")
    assert r.code == 0 and {t["titre"] for t in r.json()} == {"Rapport", "Appel"}
    assert len(titres(v("view", "run", "hautes", "--limit", "1", "--format", "plain"))) == 1
    assert titres(v("view", "run", "hautes", "--prio", "low", "--format", "plain")) == ["Courses"]      # la dernière valeur l'emporte


def test_autres_commandes_de_lecture(v):
    assert v("view", "save", "p", "next").code == 0
    assert v("view", "save", "r", "report", "overdue").code == 0
    assert v("view", "save", "ag", "agenda").code == 0
    assert v("view", "run", "p", "--format", "plain").code == 0 and v("view", "run", "ag", "--format", "plain").code == 0
    assert "Rapport" in v("view", "run", "r", "--format", "plain").sortie


def test_run_ne_modifie_pas_la_base(v):
    v("view", "save", "x", "--overdue")
    avant = v("list", "--format", "json").out
    v("view", "run", "x")
    assert v("list", "--format", "json").out == avant and v.sauvegardes() == []


# ------------------------------------------------------------------ refus
@pytest.mark.parametrize("ligne", [("done", "a1"), ("add", "x"), ("task", "remove", "a1"), ("view", "list"), ("export",)])
def test_commande_d_ecriture_refusee(v, ligne):
    r = v("view", "save", "mauvaise", *ligne)
    assert r.code != 0 and not fichier(v).exists()


def test_option_inconnue_refusee_a_l_enregistrement(v):
    r = v("view", "save", "x", "list", "--nimporte")
    assert r.code == 2 and not fichier(v).exists()


@pytest.mark.parametrize("nom", ["", "-x", "a b", "é", "x" * 41, "a/b"])
def test_nom_invalide(v, nom):
    r = v("view", "save", nom, "--overdue")
    assert r.code != 0 and not fichier(v).exists()


def test_vue_existante_sans_replace(v):
    v("view", "save", "x", "--overdue")
    r = v("view", "save", "x", "--prio", "low")
    assert r.code == 1 and "--replace" in r.texte
    assert json.loads(fichier(v).read_text())["vues"]["x"]["args"] == ["list", "--overdue"]
    assert v("view", "save", "--replace", "x", "--prio", "low").code == 0
    assert json.loads(fichier(v).read_text())["vues"]["x"]["args"] == ["list", "--prio", "low"]


def test_config_refusee_dans_une_vue(v):
    r = v("view", "save", "x", "--config", "/tmp/f.ini", "list")
    assert r.code != 0 and not fichier(v).exists()


def test_vue_inconnue_avec_suggestion(v):
    v("view", "save", "retards", "--overdue")
    r = v("view", "run", "ret")
    assert r.code == 1 and "retards" in r.texte
    r = v("view", "show", "zzz")
    assert r.code == 1 and "introuvable" in r.texte


def test_vue_inconnue_sans_aucune_vue(v):
    assert "aucune vue" in v("view", "run", "x").texte


# ------------------------------------------------------------------ list / show / rename / remove
def test_list_show(v):
    v("view", "save", "b", "--prio", "low")
    v("view", "save", "a", "--overdue")
    r = v("view", "list", "--format", "json")
    assert [x["vue"] for x in r.json()["vues"]] == ["a", "b"] and r.json()["vues"][0]["commande"] == "todo list --overdue"
    assert v("view", "list", "--format", "plain").sortie.splitlines()[0].split("\t")[:2] == ["a", "todo list --overdue"]
    assert "VUE" in v("view", "list", "--format", "table").sortie
    assert v("view", "show", "a", "--format", "text").sortie.strip() == "todo list --overdue"
    assert v("view", "show", "b", "--format", "json").json()["args"] == ["list", "--prio", "low"]


def test_list_sans_vue(v):
    assert v("view", "list", "--format", "text").code == 0 and "Aucune vue" in v("view", "list", "--format", "text").sortie
    assert v("view", "list", "--format", "json").json()["vues"] == []


def test_show_donne_une_commande_rejouable(v):
    v("view", "save", "x", "--search", "mon texte", "--tag", "a b")
    cmd = v("view", "show", "x", "--format", "text").sortie.strip()
    assert cmd == "todo list --search 'mon texte' --tag 'a b'"


def test_rename(v):
    v("view", "save", "a", "--overdue")
    v("view", "save", "b", "--prio", "low")
    assert v("view", "rename", "a", "c").code == 0
    assert [x["vue"] for x in v("view", "list", "--format", "json").json()["vues"]] == ["b", "c"]
    assert v("view", "rename", "c", "b").code == 1          # nom pris
    assert v("view", "rename", "zz", "d").code == 1
    assert v("view", "rename", "c", "c !").code != 0


def test_remove(v):
    v("view", "save", "a", "--overdue")
    assert v("view", "remove", "a").code == 0
    assert v("view", "remove", "a").code == 1
    assert v("view", "list", "--format", "json").json()["vues"] == []


# ------------------------------------------------------------------ projets
def test_vues_propres_a_chaque_projet(v):
    v("project", "create", "pro")
    v("view", "save", "x", "--overdue")
    assert v("view", "save", "-p", "pro", "y", "--prio", "low").code == 0
    assert [x["vue"] for x in v("view", "list", "--format", "json").json()["vues"]] == ["x"]
    assert [x["vue"] for x in v("-p", "pro", "view", "list", "--format", "json").json()["vues"]] == ["y"]
    assert [x["vue"] for x in v("view", "list", "-p", "pro", "--format", "json").json()["vues"]] == ["y"]
    assert fichier(v).exists() and fichier(v, "pro").exists()
    assert v("view", "run", "y").code == 1                      # y n'existe pas dans default


def test_run_dans_un_autre_projet(v):
    v("project", "create", "pro")
    v("add", "Autre", "-p", "pro")
    v("view", "save", "tout", "-p", "pro")
    assert titres(v("view", "run", "tout", "-p", "pro", "--format", "plain")) == ["Autre"]
    assert titres(v("-p", "pro", "view", "run", "tout", "--format", "plain")) == ["Autre"]


def test_projet_inexistant(v):
    r = v("view", "list", "-p", "nope")
    assert r.code == 1 and "n'existe pas" in r.texte


def test_les_vues_suivent_le_projet_renomme(v):
    v("project", "create", "pro")
    v("view", "save", "-p", "pro", "y", "--prio", "low")
    assert v("project", "rename", "pro", "travail").code == 0
    assert [x["vue"] for x in v("-p", "travail", "view", "list", "--format", "json").json()["vues"]] == ["y"]


# ------------------------------------------------------------------ fichier
def test_fichier_prive_et_atomique(v):
    v("view", "save", "x", "--overdue")
    assert stat.S_IMODE(os.stat(fichier(v)).st_mode) == 0o600
    assert not [p for p in v.db_dir.iterdir() if p.name.startswith(".views-")]


def test_les_vues_ne_sont_pas_dans_les_sauvegardes_ni_touchees_par_undo_reset(v):
    v("view", "save", "x", "--overdue")
    v("add", "Autre")
    v("undo")
    v("admin", "reset", "-y")
    assert [x["vue"] for x in v("view", "list", "--format", "json").json()["vues"]] == ["x"]
    assert not list(v.db_dir.rglob("backups/**/views.json"))


def test_fichier_illisible_jamais_ecrase(v):
    fichier(v).write_text("{ pas du json")
    for ligne in (("view", "list"), ("view", "run", "x"), ("view", "save", "x", "--overdue"), ("view", "remove", "x")):
        r = v(*ligne)
        assert r.code == 1 and "illisible" in r.texte
    assert fichier(v).read_text() == "{ pas du json"


def test_fichier_de_structure_inattendue(v):
    fichier(v).write_text(json.dumps({"version": 1, "vues": {"x": {"args": "list"}}}))
    assert v("view", "list").code == 1


def test_vue_modifiee_a_la_main_en_commande_d_ecriture(v):
    fichier(v).write_text(json.dumps({"version": 1, "vues": {"x": {"args": ["done", "a1"], "creee": "2026-01-01 10:00"}}}))
    r = v("view", "run", "x")
    assert r.code == 2 and v.une("Rapport")["statut"] == "A FAIRE"
    fichier(v).write_text(json.dumps({"version": 1, "vues": {"y": {"args": ["view", "run", "y"], "creee": ""}}}))
    assert v("view", "run", "y").code == 1                    # pas de récursion


# ------------------------------------------------------------------ options globales, journal, hooks
def test_options_globales_conservees(v):
    v("view", "save", "x", "--overdue")
    r = v("view", "run", "x", "--format", "text", env={"TODO_COLOR": "always"})
    assert r.code == 0
    r = v("--no-color", "view", "run", "x", "--format", "text", env={"TODO_COLOR": "always"})
    assert "\x1b[" not in r.out


def test_journal(v):
    env = {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"}
    v("view", "save", "x", "--overdue", env=env)
    v("view", "run", "x", env=env)
    lignes = v.journal()
    assert any(l.startswith("INFO view_save") and "view=x" in l for l in lignes)


def test_les_vues_ne_declenchent_pas_de_hook(v, tmp_path):
    sortie = tmp_path / "h.log"
    env = {"TODO_HOOKS_ON_CHANGE": f"sh -c 'echo $TODO_EVENT >> {sortie}'"}
    v("view", "save", "x", "--overdue", env=env)
    v("view", "rename", "x", "y", env=env)
    v("view", "remove", "y", env=env)
    assert not sortie.exists()
