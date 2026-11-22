"""task move : déplacer des tâches d'un projet à un autre."""
import fcntl
import subprocess
import sys

import pytest

from outils import SCRIPT, jour


def plain(todo, *args, env=None):
    return [l.split("\t") for l in todo(*args, "--format", "plain", env=env).sortie.splitlines()]


def titres(todo, *args):
    return sorted(l[5] for l in plain(todo, "list", *args))


@pytest.fixture
def pro(todo):
    todo("project", "create", "travail")
    return todo


def ids(todo, *args):
    return {l[5]: l[0] for l in plain(todo, "list", *args)}


# ------------------------------------------------------------------ cas simples
def test_deplace_une_tache(pro):
    pro("add", "Rapport", "--due", jour(3), "--prio", "high", "--tags", "pro,x")
    pro("add", "Reste")
    ident = ids(pro)["Rapport"]
    pro("note", "add", ident[:8], "une note")
    r = pro("task", "move", ident[:8], "--to", "travail")
    assert r.code == 0 and "déplacée vers le projet travail" in r.sortie
    assert titres(pro) == ["Reste"] and titres(pro, "-p", "travail") == ["Rapport"]
    t = pro("show", ident[:8], "-p", "travail", "--format", "json").json()
    assert t["id"] == ident and t["priorite"] == "high" and t["date_echeance"] == jour(3)
    assert t["tags"] == ["pro", "x"] and [n["texte"] for n in t["notes"]] == ["une note"]


def test_conserve_statut_et_dates(pro):
    pro("add", "Faite")
    ident = ids(pro)["Faite"]
    pro("done", ident[:8])
    avant = pro("show", ident[:8], "--format", "json").json()
    pro("task", "move", ident[:8], "--to", "travail")
    apres = pro("show", ident[:8], "-p", "travail", "--format", "json").json()
    assert apres == avant


def test_deplace_plusieurs_et_bilan(pro):
    for t in ("A", "B", "C"):
        pro("add", t)
    d = ids(pro)
    r = pro("task", "move", d["A"][:8], d["B"][:8], "--to", "travail")
    assert r.code == 0 and "Bilan : 2 tâche(s) déplacée(s)" in r.sortie
    assert titres(pro) == ["C"] and titres(pro, "-p", "travail") == ["A", "B"]


def test_deplacement_par_filtre(pro):
    pro("add", "Lait", "--tags", "courses")
    pro("add", "Pain", "--tags", "courses")
    pro("add", "Autre")
    r = pro("task", "move", "--tag", "courses", "--to", "travail")
    assert r.code == 0
    assert titres(pro) == ["Autre"] and titres(pro, "-p", "travail") == ["Lait", "Pain"]


def test_dry_run_ne_modifie_rien(pro):
    pro("add", "Lait", "--tags", "courses")
    avant = pro.sauvegardes()
    r = pro("task", "move", "--tag", "courses", "--to", "travail", "--dry-run", "--format", "plain")
    assert r.code == 0 and "Lait" in r.sortie
    assert titres(pro) == ["Lait"] and titres(pro, "-p", "travail") == [] and pro.sauvegardes() == avant


def test_confirmation_d_un_lot_sans_terminal(pro):
    for i in range(6):
        pro("add", f"T{i}")
    r = pro("task", "move", "--all", "--to", "travail")
    assert r.code == 1 and "-y" in r.texte and len(titres(pro)) == 6
    assert pro("task", "move", "--all", "--to", "travail", "-y").code == 0
    assert titres(pro) == [] and len(titres(pro, "-p", "travail")) == 6


def test_depuis_un_autre_projet_avec_p(pro):
    pro("add", "Pro", "-p", "travail")
    ident = ids(pro, "-p", "travail")["Pro"]
    assert pro("task", "move", ident[:8], "--to", "default", "-p", "travail").code == 0
    assert titres(pro) == ["Pro"] and titres(pro, "-p", "travail") == []


# ------------------------------------------------------------------ refus
def test_cible_inexistante_ou_invalide(pro):
    pro("add", "A")
    i = ids(pro)["A"][:8]
    r = pro("task", "move", i, "--to", "nope")
    assert r.code == 1 and "n'existe pas" in r.texte and "project create nope" in r.texte
    assert pro("task", "move", i, "--to", "Mauvais Nom").code == 1
    assert not (pro.db_dir / "projects" / "nope").exists() and titres(pro) == ["A"]


def test_meme_projet(pro):
    pro("add", "A")
    r = pro("task", "move", ids(pro)["A"][:8], "--to", "default")
    assert r.code == 1 and "déjà dans le projet" in r.texte


def test_to_obligatoire(pro):
    pro("add", "A")
    assert pro("task", "move", ids(pro)["A"][:8]).code == 2


def test_identifiant_inconnu(pro):
    pro("add", "A")
    r = pro("task", "move", "zzzz", "--to", "travail")
    assert r.code == 1 and titres(pro) == ["A"]


def test_un_identifiant_inconnu_n_empeche_pas_les_autres(pro):
    pro("add", "A")
    r = pro("task", "move", ids(pro)["A"][:8], "zzzz", "--to", "travail")
    assert r.code == 1 and titres(pro, "-p", "travail") == ["A"]


def test_refuse_si_la_cible_contient_deja_l_identifiant(pro):
    pro.seed(dict(cle="dup1", titre="Original"))
    pro("add", "Autre")                           # une première sauvegarde, pour que `undo` ait un état antérieur
    pro("task", "move", "dup1", "--to", "travail")
    pro("undo")                                   # `Original` revient dans default tout en restant dans travail
    assert titres(pro) == ["Autre", "Original"]
    r = pro("task", "move", "dup1", "--to", "travail")
    assert r.code == 1 and "contient déjà" in r.texte and titres(pro) == ["Autre", "Original"]


def test_base_vide(pro):
    r = pro("task", "move", "abc", "--to", "travail")
    assert r.code == 1 and "vide" in r.texte


# ------------------------------------------------------------------ dépendances
def test_la_tache_deplacee_n_attend_plus_ce_qui_reste(pro):
    pro.seed(dict(cle="aaa1", titre="Base"), dict(cle="bbb1", titre="Suite", apres=["aaa1"]))
    r = pro("task", "move", "bbb1", "--to", "travail")
    assert r.code == 0 and "'Suite' n'attend plus : Base (restée dans 'default')" in r.sortie
    assert pro("show", "bbb1", "-p", "travail", "--format", "json").json()["apres"] == []


def test_ce_qui_attendait_la_tache_deplacee_est_libere(pro):
    pro.seed(dict(cle="aaa1", titre="Base"), dict(cle="bbb1", titre="Suite", apres=["aaa1"]))
    r = pro("task", "move", "aaa1", "--to", "travail")
    assert r.code == 0 and "'Suite' n'attend plus : Base (déplacée vers 'travail')" in r.sortie
    assert pro("show", "bbb1", "--format", "json").json()["apres"] == []
    assert titres(pro) == ["Suite"] and plain(pro, "report", "blocked") == []


def test_des_taches_deplacees_ensemble_gardent_leurs_liens(pro):
    pro.seed(dict(cle="aaa1", titre="Base"), dict(cle="bbb1", titre="Suite", apres=["aaa1"]), dict(cle="ccc1", titre="Autre"))
    r = pro("task", "move", "aaa1", "bbb1", "--to", "travail")
    assert r.code == 0 and "n'attend plus" not in r.sortie
    assert pro("show", "bbb1", "-p", "travail", "--format", "json").json()["apres"] == ["aaa1"]
    assert [l[2] for l in plain(pro, "report", "blocked", "-p", "travail")] == ["Suite"]


def test_occurrence_suivante_restee_n_est_plus_reliee(pro):
    pro("add", "Poubelles", "--due", jour(0), "--repeat", "weekly")
    ident = ids(pro)["Poubelles"]
    pro("done", ident[:8])                                   # crée l'occurrence suivante ; la terminée pointe vers elle
    assert pro("show", ident[:8], "--format", "json").json()["suivante"]
    pro("task", "move", ident[:8], "--to", "travail")
    assert pro("show", ident[:8], "-p", "travail", "--format", "json").json()["suivante"] is None
    assert pro("task", "undone", ident[:8], "-p", "travail").code == 0         # ne cherche pas une occurrence qui n'est pas là


# ------------------------------------------------------------------ sauvegardes, undo, journal, verrous
def test_chaque_projet_recoit_sa_sauvegarde(pro):
    pro("add", "A")
    avant_source = len(pro.sauvegardes())
    avant_cible = len(list((pro.db_dir / "projects" / "travail" / "backups").iterdir()))
    pro("task", "move", ids(pro)["A"][:8], "--to", "travail")
    assert len(pro.sauvegardes()) == avant_source + 1
    assert len(list((pro.db_dir / "projects" / "travail" / "backups").iterdir())) == avant_cible + 1


def test_undo_dans_la_source_et_avertissement(pro):
    pro("add", "A")
    pro("add", "B")
    r = pro("task", "move", ids(pro)["A"][:8], "--to", "travail")
    assert "undo" in r.sortie and "un projet à la fois" in r.sortie
    assert pro("undo").code == 0
    assert titres(pro) == ["A", "B"] and titres(pro, "-p", "travail") == ["A"]     # limite assumée : la cible n'est pas touchée


def test_undo_dans_la_cible_retire_la_tache_de_la_cible(pro):
    pro("add", "Existe", "-p", "travail")
    pro("add", "A")
    pro("task", "move", ids(pro)["A"][:8], "--to", "travail")
    assert pro("undo", "-p", "travail").code == 0
    assert titres(pro, "-p", "travail") == ["Existe"] and titres(pro) == []


def test_journal(todo):
    env = {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"}
    todo("project", "create", "travail", env=env)
    todo("add", "A", env=env)
    todo("task", "move", ids(todo)["A"][:8], "--to", "travail", env=env)
    ligne = [l for l in todo.journal() if l.startswith("INFO move")]
    assert ligne and "to=travail" in ligne[0]


def test_le_verrou_de_la_cible_est_pris(pro):
    pro("add", "A")
    with open(pro.db_dir / "projects" / "travail" / "todo.lock", "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        r = pro("task", "move", ids(pro)["A"][:8], "--to", "travail", env={"TODO_LOCK_TIMEOUT": "0"})
    assert r.code == 1 and "travail" in r.texte and titres(pro) == ["A"]


def test_deux_deplacements_croises_ne_se_bloquent_pas(pro):
    for i in range(5):
        pro("add", f"P{i}")
        pro("add", f"T{i}", "-p", "travail")
    procs = [subprocess.Popen([sys.executable, "-B", str(SCRIPT), *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, env=pro._env(None), cwd=pro.dossier)
             for args in (("task", "move", "--all", "--to", "travail", "-y"), ("task", "move", "--all", "--to", "default", "-y", "-p", "travail"))]
    assert [p.wait(timeout=60) for p in procs] == [0, 0]
    assert len(titres(pro)) + len(titres(pro, "-p", "travail")) == 10


# ------------------------------------------------------------------ transverse
def test_visible_ensuite_avec_all_projects(pro):
    pro("add", "A")
    pro("task", "move", ids(pro)["A"][:8], "--to", "travail")
    assert [(l[1], l[6]) for l in plain(pro, "list", "--all-projects")] == [("travail", "A")]


def test_aide(pro):
    r = pro("task", "move", "--help").sortie
    assert "--to" in r and "--dry-run" in r and "projet" in r.lower()
    assert "move" in pro("task", "--help").sortie
