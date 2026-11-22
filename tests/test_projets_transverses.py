"""Lecture transverse : --all-projects (list, next, agenda, report, stats) et rappel sur tous les projets."""
import fcntl
import json

import pytest

from outils import jour


def plain(todo, *args, env=None):
    return [l.split("\t") for l in todo(*args, "--format", "plain", env=env).sortie.splitlines()]


@pytest.fixture
def deux(todo):
    """`default` : Perso (en retard, #maison), Fait (terminée) ; `travail` : Pro (en retard, #pro), Plus tard, Archivée."""
    todo("add", "Perso", "--due", jour(-2), "--tags", "maison")
    todo("add", "Fait")
    todo("done", todo.id_de("Fait"))
    todo("project", "create", "travail")
    todo("add", "Pro", "-p", "travail", "--due", jour(-1), "--tags", "pro")
    todo("add", "Plus tard", "-p", "travail", "--due", jour(5), "--prio", "high")
    todo("add", "Archivée", "-p", "travail")
    ident = next(t["id"] for t in todo("list", "-p", "travail", "--format", "json").json() if t["titre"] == "Archivée")
    todo("done", ident[:8], "-p", "travail")
    todo("archive", "add", "-p", "travail")
    return todo


# ------------------------------------------------------------------ list
def test_list_rassemble_les_projets_et_ajoute_la_colonne(deux):
    lignes = plain(deux, "list", "--all-projects")
    assert {(l[1], l[6]) for l in lignes} == {("default", "Perso"), ("default", "Fait"), ("travail", "Pro"), ("travail", "Plus tard")}
    assert all(len(l) == 8 for l in lignes)


def test_list_json_porte_le_projet_seulement_en_mode_transverse(deux):
    avec = deux("list", "--all-projects", "--format", "json").json()
    assert {t["projet"] for t in avec} == {"default", "travail"}
    sans = deux("list", "--format", "json").json()
    assert all("projet" not in t for t in sans)
    assert all(len(l) == 7 for l in plain(deux, "list"))                # contrat plain inchangé : pas de colonne projet


def test_list_sans_option_reste_au_projet_courant(deux):
    assert sorted(l[5] for l in plain(deux, "list")) == ["Fait", "Perso"]


def test_list_colonnes(deux):
    l = plain(deux, "list", "--all-projects", "--columns", "id,title")[0]
    assert len(l) == 3 and l[1] in ("default", "travail")
    l = plain(deux, "list", "--all-projects", "--columns", "id,title,project")[0]
    assert len(l) == 3 and l[2] in ("default", "travail")


def test_list_filtres_et_tris_s_appliquent(deux):
    assert [l[6] for l in plain(deux, "list", "--all-projects", "--overdue")] == ["Perso", "Pro"]
    assert [l[6] for l in plain(deux, "list", "--all-projects", "--tag", "pro")] == ["Pro"]
    assert [l[6] for l in plain(deux, "list", "--all-projects", "--status", "done")] == ["Fait"]


def test_list_text_et_table_nomment_le_projet(deux):
    x = deux("list", "--all-projects", "--format", "text").sortie
    assert "[travail]" in x and "[default]" in x
    t = deux("list", "--all-projects", "--format", "table").sortie
    assert "PROJET" in t and "travail" in t


def test_list_transverse_ne_modifie_rien(deux):
    avant = deux.sauvegardes()
    deux("list", "--all-projects")
    assert deux.sauvegardes() == avant


def test_all_projects_et_project_s_excluent(deux):
    r = deux("list", "--all-projects", "-p", "travail")
    assert r.code == 1 and "--all-projects" in r.texte


def test_all_projects_refuse_sur_une_commande_qui_modifie(deux):
    assert deux("done", "abc", "--all-projects").code == 2
    assert deux("add", "X", "--all-projects").code == 2


def test_all_projects_sans_aucune_tache(todo):
    assert todo("list", "--all-projects", "--format", "json").json() == []
    assert todo("list", "--all-projects").code == 0


def test_all_projects_avec_un_projet_courant_inexistant(deux):
    deux.config("[general]\nproject = fantome\n")
    assert deux("list").code == 1
    assert len(plain(deux, "list", "--all-projects")) == 4


# ------------------------------------------------------------------ next, agenda, stats
def test_next_considere_tous_les_projets(deux):
    lignes = plain(deux, "next", "--all-projects", "-n", "3")
    assert [(l[1], l[6]) for l in lignes] == [("default", "Perso"), ("travail", "Pro"), ("travail", "Plus tard")]
    assert "[travail]" in deux("next", "--all-projects", "-n", "3", "--format", "text").sortie


def test_agenda_transverse(deux):
    r = deux("agenda", "--all-projects", "--format", "json").json()
    assert {t["titre"] for t in r["en_retard"]} == {"Perso", "Pro"}
    assert {t["projet"] for t in r["en_retard"]} == {"default", "travail"}
    assert "[travail]" in deux("agenda", "--all-projects", "--format", "text", "--days", "10").sortie


def test_stats_transverses(deux):
    seul = deux("report", "stats", "--format", "json").json()
    tout = deux("report", "stats", "--all-projects", "--format", "json").json()
    assert tout["total"] == seul["total"] + 2
    avec = deux("report", "stats", "--all-projects", "--with-archive", "--format", "json").json()
    assert avec["total"] == tout["total"] + 1


# ------------------------------------------------------------------ rapports
def test_report_tags_additionne_les_projets(deux):
    tags = {l[0]: l for l in plain(deux, "report", "tags", "--all-projects")}
    assert set(tags) == {"maison", "pro"}


def test_report_overdue_et_blocked(deux):
    assert [(l[4]) for l in plain(deux, "report", "overdue", "--all-projects")] == ["Perso", "Pro"]
    assert plain(deux, "report", "blocked", "--all-projects") == []


def test_report_done_avec_archive(deux):
    assert [l[3] for l in plain(deux, "report", "done", "--all-projects")] == ["Fait"]
    assert sorted(l[3] for l in plain(deux, "report", "done", "--all-projects", "--with-archive")) == ["Archivée", "Fait"]


def test_report_stale_transverse(deux):
    deux.seed(dict(cle="vieille", titre="Vieille", creation=jour(-90) + " 08:00"))
    assert [l[3] for l in plain(deux, "report", "stale", "--all-projects")] == ["Vieille"]


# ------------------------------------------------------------------ verrous
def test_lecture_transverse_attend_le_verrou_de_chaque_projet(deux):
    with open(deux.db_dir / "projects" / "travail" / "todo.lock", "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        r = deux("list", "--all-projects", env={"TODO_LOCK_TIMEOUT": "0"})
    assert r.code == 1 and "travail" in r.texte
    assert deux("list", "--all-projects").code == 0


# ------------------------------------------------------------------ rappel
def test_rappel_couvre_tous_les_projets_par_defaut(deux):
    lignes = plain(deux, "reminder", "check")
    assert sorted(l[4] for l in lignes if l[0] == "retard") == ["Perso", "Pro"]
    x = deux("reminder", "check", "--format", "text").sortie
    assert "2 tâche(s) en retard" in x and "[travail]" in x and "[default]" in x


def test_rappel_malgre_un_projet_courant(deux):
    deux("project", "use", "travail")
    assert sorted(l[4] for l in plain(deux, "reminder", "check") if l[0] == "retard") == ["Perso", "Pro"]
    assert sorted(l[4] for l in plain(deux, "reminder", "check", env={"TODO_PROJECT": "default"}) if l[0] == "retard") == ["Perso", "Pro"]


def test_rappel_restreint_par_project(deux):
    assert [l[4] for l in plain(deux, "reminder", "check", "-p", "travail") if l[0] == "retard"] == ["Pro"]
    assert "[travail]" not in deux("reminder", "check", "-p", "travail", "--format", "text").sortie


def test_rappel_json_etiquete_le_projet_quand_il_y_en_a_plusieurs(deux, todo):
    r = deux("reminder", "check", "--format", "json").json()
    assert r["compteurs"]["retards"] == 2 and {t["projet"] for t in r["retards"]} == {"default", "travail"}


def test_rappel_json_inchange_avec_un_seul_projet(todo):
    todo("add", "Seule", "--due", jour(-1))
    r = todo("reminder", "check", "--format", "json").json()
    assert r["compteurs"]["retards"] == 1 and "projet" not in r["retards"][0]


def test_resume_une_ligne_agrege_les_projets(deux):
    assert deux("reminder", "check", "--write-status").code == 0
    resume = (deux.db_dir / "remind_status").read_text()
    assert "2" in resume


def test_rappel_coupe_pour_tous_les_projets(deux):
    deux("reminder", "disable")
    assert deux("reminder", "check").sortie == ""
    assert deux("reminder", "check", "-p", "travail").sortie == ""


def test_aide_des_commandes_transverses(deux):
    for args in (("list",), ("next",), ("agenda",), ("report", "tags"), ("report", "overdue"), ("report", "stats")):
        assert "--all-projects" in deux(*args, "--help").sortie
