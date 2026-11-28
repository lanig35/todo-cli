"""Suivi du temps : task start / unstart, --at, filtres, affichage, report active et report cycle."""
import json
import re
from datetime import datetime, timedelta

import pytest

from outils import jour


def instant(jours=0, heure="09:00"):
    return jour(jours) + " " + heure


def plain(todo, *args):
    return [l.split("\t") for l in todo(*args, "--format", "plain").sortie.splitlines()]


@pytest.fixture
def deux(todo):
    todo("add", "Rapport", "--tags", "pro")
    todo("add", "Courses")
    return todo, todo.id_de("Rapport"), todo.id_de("Courses")


def demarree(todo, titre):
    return todo.une(titre)["demarree"]


# ------------------------------------------------------------------ start
def test_start_note_l_instant_present(deux):
    todo, a, b = deux
    avant = datetime.now().replace(second=0, microsecond=0)
    r = todo("task", "start", a)
    assert r.code == 0 and "démarrée" in r.sortie
    d = datetime.strptime(demarree(todo, "Rapport"), "%Y-%m-%d %H:%M")
    assert avant <= d <= datetime.now() + timedelta(minutes=1)
    assert demarree(todo, "Courses") is None


def test_plusieurs_taches_en_cours_en_meme_temps(deux):
    todo, a, b = deux
    assert todo("task", "start", a, b).code == 0
    assert demarree(todo, "Rapport") and demarree(todo, "Courses")
    assert todo("task", "start", a, b).code == 0                          # déjà démarrées : rien à refaire, pas une erreur


@pytest.mark.parametrize("at, attendu", [
    ("hier 9:15", lambda: instant(-1, "09:15")),
    (instant(-2, "16:00"), lambda: instant(-2, "16:00")),
    ("2d 10:00", lambda: instant(-2, "10:00")),
])
def test_start_at_rattrape_un_oubli(deux, at, attendu):
    todo, a, _ = deux
    assert todo("task", "start", a, "--at", at).code == 0
    assert demarree(todo, "Rapport") == attendu()


def test_start_at_heure_du_jour(deux):
    todo, a, _ = deux
    todo("task", "start", a, "--at", "00:00")
    assert demarree(todo, "Rapport") == instant(0, "00:00")


@pytest.mark.parametrize("at", ["demain 10:00", "banane", "25:00", "10h", "hier"])
def test_start_at_invalide(deux, at):
    todo, a, _ = deux
    r = todo("task", "start", a, "--at", at)
    assert r.code == 2 and demarree(todo, "Rapport") is None


def test_start_at_dans_le_futur(deux):
    todo, a, _ = deux
    futur = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 10:00")
    r = todo("task", "start", a, "--at", futur)
    assert r.code == 2 and "futur" in r.texte and demarree(todo, "Rapport") is None


def test_deja_demarree_garde_son_instant(deux):
    todo, a, _ = deux
    todo("task", "start", a, "--at", "hier 9:15")
    r = todo("task", "start", a)
    assert r.code == 0 and "déjà démarrée" in r.sortie and "unstart" in r.sortie
    assert demarree(todo, "Rapport") == instant(-1, "09:15")
    n = len(todo.sauvegardes())
    todo("task", "start", a)
    assert len(todo.sauvegardes()) == n                                   # rien modifié : pas de sauvegarde


def test_corriger_un_demarrage(deux):
    todo, a, _ = deux
    todo("task", "start", a)
    todo("task", "unstart", a)
    todo("task", "start", a, "--at", "hier 8:00")
    assert demarree(todo, "Rapport") == instant(-1, "08:00")


def test_start_tache_terminee_refuse(deux):
    todo, a, _ = deux
    todo("done", a)
    r = todo("task", "start", a)
    assert r.code == 1 and "terminée" in r.sortie and demarree(todo, "Rapport") is None


def test_start_tache_bloquee_avertit_mais_demarre(todo):
    todo("add", "Base")
    todo("add", "Suite", "--after", todo.id_de("Base"))
    r = todo("task", "start", todo.id_de("Suite"))
    assert r.code == 0 and "attend encore" in r.sortie and "Base" in r.sortie
    assert demarree(todo, "Suite")


def test_start_identifiant_inconnu(deux):
    todo, a, _ = deux
    r = todo("task", "start", a, "zzzzzz")
    assert r.code == 1 and demarree(todo, "Rapport")                     # la valide est quand même démarrée


def test_start_avec_note(deux):
    todo, a, _ = deux
    todo("task", "start", a, "-m", "j'attaque")
    notes = todo.une("Rapport")["notes"]
    assert [(n["texte"], n["action"]) for n in notes] == [("j'attaque", "start")]


def test_start_est_annulable_par_undo(deux):
    todo, a, _ = deux
    todo("task", "start", a)
    todo("undo")
    assert demarree(todo, "Rapport") is None


def test_start_par_filtre(deux):
    todo, a, b = deux
    todo("add", "Autre", "--tags", "pro")
    r = todo("task", "start", "--tag", "pro", "--dry-run", "--format", "plain")
    assert r.code == 0 and {l.split("\t")[5] for l in r.sortie.splitlines()} == {"Rapport", "Autre"}
    assert demarree(todo, "Rapport") is None                              # simulation : rien n'est modifié
    assert todo("task", "start", "--tag", "pro").code == 0
    assert demarree(todo, "Rapport") and demarree(todo, "Autre") and demarree(todo, "Courses") is None
    assert todo("task", "start", "--tag", "pro", "--not-started").sortie.count("Aucune tâche") == 1


def test_start_sans_cible(deux):
    todo, _, _ = deux
    assert todo("task", "start").code == 2


def test_raccourci_absent_et_aide(todo):
    assert todo("start", "x").code == 2                                   # `start` n'est pas un raccourci de premier niveau
    assert "--at" in todo("task", "start", "--help").sortie
    assert todo("task", "start", "x", "--at", "demain 10:00").code == 2


# ------------------------------------------------------------------ unstart
def test_unstart(deux):
    todo, a, b = deux
    todo("task", "start", a, b)
    r = todo("task", "unstart", a)
    assert r.code == 0 and "annulé" in r.sortie
    assert demarree(todo, "Rapport") is None and demarree(todo, "Courses")
    r = todo("task", "unstart", a)
    assert r.code == 0 and "n'est pas démarrée" in r.sortie


def test_unstart_garde_le_statut_d_une_tache_terminee(deux):
    todo, a, _ = deux
    todo("task", "start", a, "--at", "hier 9:00")
    todo("done", a)
    assert todo("task", "unstart", a).code == 0
    t = todo("show", a, "--format", "json").json()
    assert t["demarree"] is None and t["statut"] == "TERMINE"


def test_unstart_par_filtre_et_note(deux):
    todo, a, b = deux
    todo("task", "start", a, b)
    todo("task", "unstart", "--all", "-y", "-m", "annulé")
    assert demarree(todo, "Rapport") is None and demarree(todo, "Courses") is None
    assert todo.une("Rapport")["notes"][0]["action"] == "unstart"


# ------------------------------------------------------------------ done / undone / récurrence
def test_done_garde_l_instant_de_demarrage(deux):
    todo, a, _ = deux
    todo("task", "start", a, "--at", "hier 9:00")
    todo("done", a)
    t = todo("show", a, "--format", "json").json()
    assert t["statut"] == "TERMINE" and t["demarree"] == instant(-1, "09:00") and t["date_terminee"]


def test_done_sans_demarrage_reste_possible(deux):
    todo, a, _ = deux
    assert todo("done", a).code == 0
    assert todo("show", a, "--format", "json").json()["demarree"] is None
    assert "Délai" not in todo("show", a, "--format", "text").texte


def test_undone_efface_le_demarrage(deux):
    todo, a, _ = deux
    todo("task", "start", a, "--at", "hier 9:00")
    todo("done", a)
    todo("task", "undone", a)
    assert demarree(todo, "Rapport") is None
    assert todo("show", a, "--format", "plain").sortie.count("demarree") == 0


def test_occurrence_suivante_repart_sans_demarrage(todo):
    todo("add", "Arroser", "--repeat", "daily")
    ident = todo.id_de("Arroser")
    todo("task", "start", ident)
    todo("done", ident)
    ouvertes = [t for t in todo.taches().values() if t["titre"] == "Arroser" and t["statut"] == "A FAIRE"]
    assert len(ouvertes) == 1 and ouvertes[0]["demarree"] is None
    assert todo("show", ident, "--format", "json").json()["demarree"]


# ------------------------------------------------------------------ filtres, colonnes, affichage
def test_filtres_started(deux):
    todo, a, b = deux
    todo("task", "start", a)
    assert [l[5] for l in plain(todo, "list", "--started")] == ["Rapport"]
    assert [l[5] for l in plain(todo, "list", "--not-started")] == ["Courses"]
    assert todo("list", "--started", "--not-started").code == 2
    todo("done", a)
    assert [l[5] for l in plain(todo, "list", "--started", "--status", "done")] == ["Rapport"]
    assert plain(todo, "list", "--started", "--status", "todo") == []     # « en cours » = démarrée et à faire


def test_colonne_started(deux):
    todo, a, b = deux
    todo("task", "start", a, "--at", "hier 9:15")
    lignes = {l[1]: l[2] for l in plain(todo, "list", "--columns", "id,title,started")}
    assert lignes == {"Rapport": instant(-1, "09:15"), "Courses": ""}
    assert "DÉMARRÉE" in todo("list", "--columns", "id,started", "--format", "table").sortie


def test_list_marque_les_taches_en_cours(deux):
    todo, a, _ = deux
    todo("task", "start", a, "--at", "hier 9:00")
    texte = todo("list", "--format", "text").texte
    assert re.search(r"Rapport.*▶ 1 j", texte) or re.search(r"Rapport.*▶ \d+ h", texte)
    assert "▶" not in [l for l in texte.splitlines() if "Courses" in l][0]


def test_show_affiche_depart_et_delai(deux):
    todo, a, _ = deux
    todo("task", "start", a, "--at", "2d 00:00")                         # minuit : « 2 j » quelle que soit l'heure du test
    texte = todo("show", a, "--format", "text").texte
    assert f"Démarrée le : {instant(-2, '00:00')}" in texte and "depuis 2 j" in texte
    todo("done", a)
    texte = todo("show", a, "--format", "text").texte
    assert "Délai" in texte and "durée calendaire" in texte and "depuis" not in texte
    ligne = [l.split("\t") for l in todo("show", a, "--format", "plain").sortie.splitlines()]
    assert ["demarree", instant(-2, "00:00")] in ligne


def test_json_de_list_porte_demarree(deux):
    todo, a, _ = deux
    assert all("demarree" in t for t in todo("list", "--format", "json").json())


def test_demarrage_invalide_dans_la_base_est_ignore(todo):
    todo.seed_brut(b"abc", json.dumps({"titre": "X", "statut": "A FAIRE", "priorite": "medium", "demarree": "hier"}).encode())
    assert todo("show", "abc", "--format", "json").json()["demarree"] is None


def test_archivage_et_deplacement_gardent_demarree(deux):
    todo, a, _ = deux
    todo("project", "create", "autre")
    todo("task", "start", a, "--at", "hier 9:15")
    todo("task", "move", a, "--to", "autre")
    assert todo("show", a, "--format", "json", "-p", "autre").json()["demarree"] == instant(-1, "09:15")
    todo("done", a, "-p", "autre")
    todo("archive", "add", "-p", "autre")
    assert todo("archive", "list", "--format", "json", "-p", "autre").json()[0]["demarree"] == instant(-1, "09:15")


def test_export_import_conservent_demarree(deux, tmp_path):
    todo, a, _ = deux
    todo("task", "start", a, "--at", "hier 9:15")
    export = tmp_path / "e.json"
    export.write_text(todo("data", "export").sortie)
    assert json.loads(export.read_text())["taches"][0].get("demarree") or json.loads(export.read_text())["taches"][1].get("demarree")
    todo("admin", "reset", "-y")
    assert todo("data", "import", export).code == 0
    assert demarree(todo, "Rapport") == instant(-1, "09:15")


def test_import_refuse_une_demarree_invalide(todo, tmp_path):
    f = tmp_path / "i.json"
    f.write_text(json.dumps({"format": "todo-cli", "version": 1, "taches": [{"titre": "X", "demarree": "hier"}], "archive": []}))
    r = todo("data", "import", f)
    assert r.code == 1 and "demarree" in r.texte


# ------------------------------------------------------------------ report active
def test_report_active(deux):
    todo, a, b = deux
    todo("add", "Fini")
    todo("task", "start", a, "--at", "hier 9:00")
    todo("task", "start", b, "--at", "2d 00:00")        # minuit : « 2 j » quelle que soit l'heure du test
    todo("task", "start", todo.id_de("Fini"))
    todo("done", todo.id_de("Fini"))
    lignes = plain(todo, "report", "active")
    assert [l[4] for l in lignes] == ["Courses", "Rapport"]               # le plus ancien d'abord ; la tâche terminée est absente
    assert int(lignes[0][1]) > int(lignes[1][1]) > 0 and lignes[1][2] == instant(-1, "09:00")
    j = todo("report", "active", "--format", "json").json()
    assert j["total"] == 2 and j["taches"][0]["titre"] == "Courses" and j["taches"][0]["ecoule_minutes"] > 0
    texte = todo("report", "active", "--format", "text").texte
    assert "TÂCHES EN COURS" in texte and "▶ 2 j" in texte
    assert "Courses" in todo("report", "active", "--format", "table").sortie


def test_report_active_vide(todo):
    todo("add", "A")
    assert plain(todo, "report", "active") == []
    assert todo("report", "active", "--format", "json").json() == {**todo("report", "active", "--format", "json").json(), "total": 0, "taches": []}
    assert "Aucune tâche en cours" in todo("report", "active", "--format", "text").texte


def test_report_active_tous_les_projets(todo):
    todo("project", "create", "perso")
    todo("add", "A")
    todo("add", "B", "-p", "perso")
    todo("task", "start", todo.id_de("A"))
    todo("task", "start", todo("list", "-p", "perso", "--format", "json").json()[0]["id"][:8], "-p", "perso")
    assert len(plain(todo, "report", "active")) == 1
    assert len(plain(todo, "report", "active", "--all-projects")) == 2


# ------------------------------------------------------------------ report cycle
def tache(**champs):
    champs.setdefault("creation", jour(-30) + " 09:00")
    return champs


@pytest.fixture
def mesures(todo):
    todo.seed(
        tache(cle="a1", titre="Court", statut="TERMINE", demarree=instant(-3, "09:00"), terminee=instant(-3, "10:30"), tags=["pro"], priorite="high"),
        tache(cle="a2", titre="Long", statut="TERMINE", demarree=instant(-6, "09:00"), terminee=instant(-4, "09:00"), tags=["pro", "x"], priorite="low"),
        tache(cle="a3", titre="Moyen", statut="TERMINE", demarree=instant(-2, "09:00"), terminee=instant(-1, "09:00"), priorite="high"),
        tache(cle="a4", titre="Sans demarrage", statut="TERMINE", terminee=instant(-1, "12:00")),
        tache(cle="a5", titre="Ancienne", statut="TERMINE", demarree=instant(-100, "09:00"), terminee=instant(-90, "09:00")),
        tache(cle="a6", titre="En cours", demarree=instant(-1, "09:00")),
    )
    return todo


def test_cycle_global(mesures):
    j = mesures("report", "cycle", "--format", "json").json()
    assert j["mesurees"] == 3 and j["sans_demarrage"] == 1 and j["unite"] == "minutes" and j["par"] is None
    g = j["groupes"][0]
    assert g["nom"] == "tout" and g["nombre"] == 3 and g["min"] == 90 and g["max"] == 2 * 1440 and g["mediane"] == 1440
    assert g["moyenne"] == round((90 + 2880 + 1440) / 3)
    assert {t["titre"]: t["delai_minutes"] for t in j["taches"]} == {"Court": 90, "Long": 2880, "Moyen": 1440}


def test_cycle_plain_et_table(mesures):
    assert plain(mesures, "report", "cycle") == [["tout", "3", "1470", "1440", "90", "2880"]]
    assert "MOYENNE (MIN)" in mesures("report", "cycle", "--format", "table").sortie


def test_cycle_texte_donne_des_durees_lisibles(mesures):
    texte = mesures("report", "cycle", "--format", "text").texte
    assert "DÉLAIS DE TRAITEMENT" in texte and "médiane 1 j" in texte and "plus court 1 h 30" in texte and "plus long 2 j" in texte
    assert "1 terminée(s) sans démarrage" in texte


def test_cycle_par_tag(mesures):
    lignes = {l[0]: l[1:] for l in plain(mesures, "report", "cycle", "--by", "tag")}
    assert lignes["pro"] == ["2", "1485", "1485", "90", "2880"]            # Court et Long
    assert lignes["x"] == ["1", "2880", "2880", "2880", "2880"] and lignes["(sans tag)"][0] == "1"
    assert [l[0] for l in plain(mesures, "report", "cycle", "--by", "tag")][0] == "pro"   # le plus fourni d'abord


def test_cycle_par_priorite(mesures):
    lignes = plain(mesures, "report", "cycle", "--by", "prio")
    assert [l[0] for l in lignes] == ["high", "low"] and lignes[0][1] == "2"


def test_cycle_periode_et_archive(mesures):
    assert plain(mesures, "report", "cycle", "--since", "1y")[0][1] == "4"          # inclut « Ancienne »
    assert plain(mesures, "report", "cycle", "--since", "5d", "--until", "3d")[0][1] == "2"
    assert plain(mesures, "report", "cycle", "--since", "20d", "--until", "10d") == []
    assert mesures("report", "cycle", "--since", "5d", "--until", "10d").code == 1       # plage vide
    mesures("archive", "add")
    assert plain(mesures, "report", "cycle") == []                                    # archivées : exclues par défaut
    assert plain(mesures, "report", "cycle", "--with-archive")[0][1] == "3"


def test_cycle_vide(todo):
    assert plain(todo, "report", "cycle") == []
    assert "Aucune tâche terminée et démarrée" in todo("report", "cycle", "--format", "text").texte
    assert todo("report", "cycle", "--format", "json").json()["groupes"] == []


# ------------------------------------------------------------------ journal, complétion
def test_journal_vocabulaire(deux):
    todo, a, _ = deux
    todo.config("[log]\ntarget = file\nlevel = info\n")
    todo("task", "start", a, env={"TODO_LOG_TARGET": "file"})
    todo("task", "unstart", a, env={"TODO_LOG_TARGET": "file"})
    contenu = todo.fichier_log.read_text()
    assert "start" in contenu and "unstart" in contenu
