"""`todo admin doctor` : diagnostic (lecture seule), codes de sortie, formats, réparations `--fix`."""
import dbm
import json
import os
import stat

import pytest


def brut(todo, cle, **champs):
    todo.seed_brut(cle, json.dumps(champs).encode("utf-8"))


def archiver_brut(todo, cle, **champs):
    with dbm.open(str(todo.db_dir / "todo_archive"), "c") as db:
        db[cle] = json.dumps(champs)


def diagnostic(todo, *args, env=None):
    r = todo("admin", "doctor", "--format", "json", *args, env=env)
    return r, (r.json() if r.out.strip() else None)


def codes(d, niveau=None, sauf=("no_backup",)):
    """Codes des constats (sans `no_backup`, normal quand la base est garnie directement, sauf demande contraire)."""
    return sorted(c["code"] for c in d["constats"] if (niveau is None or c["niveau"] == niveau) and c["code"] not in sauf)


def contenu_base(todo):
    with dbm.open(str(todo.db_dir / "todo_db"), "r") as db:
        return {k: db[k] for k in db.keys()}


# ------------------------------------------------------------------ base saine
def test_base_saine(todo):
    todo("add", "Alpha", "--due", "demain")
    r, d = diagnostic(todo)
    assert r.code == 0 and d["ok"] is True
    assert d["constats"] == [] and d["bilan"] == {"erreurs": 0, "avertissements": 0, "infos": 0, "reparables": 0}
    assert d["projets"][0]["projet"] == "default" and d["projets"][0]["taches"] == 1


def test_base_absente(todo):
    r, d = diagnostic(todo)
    assert r.code == 0 and d["projets"][0]["taches"] == 0


def test_pas_de_raccourci_hors_du_groupe_admin(todo):
    assert todo("doctor").code == 2
    assert todo("admin", "doctor", "--format", "json").code == 0


def test_lecture_seule(todo):
    brut(todo, "aaaa1111", titre="X", priorite="urgent", apres=["zzzz9999"])
    todo("list")                                            # crée le verrou et les dossiers que toute commande crée
    avant = contenu_base(todo)
    fichiers = sorted(os.listdir(todo.db_dir))
    diagnostic(todo)
    assert contenu_base(todo) == avant and sorted(os.listdir(todo.db_dir)) == fichiers


# ------------------------------------------------------------------ constats sur les tâches
@pytest.mark.parametrize("champs, code, niveau, reparable", [
    ({"priorite": "urgent"}, "invalid_priority", "avertissement", True),
    ({"demarree": "hier"}, "invalid_started", "avertissement", True),
    ({"date_terminee": "2026-01-01 10:00"}, "todo_with_done_date", "avertissement", True),
    ({"tags": ["a", 3]}, "invalid_tags", "avertissement", True),
    ({"apres": "pas-une-liste"}, "invalid_dependencies", "avertissement", True),
    ({"apres": ["introuvable9"]}, "missing_dependency", "info", True),
    ({"titre": "  "}, "missing_title", "avertissement", False),
    ({"statut": "BOF"}, "invalid_status", "erreur", False),
    ({"date_echeance": "demain"}, "invalid_due", "avertissement", False),
    ({"date_echeance": "2026-02-31"}, "invalid_due", "avertissement", False),
    ({"recurrence": "xx", "date_echeance": "2026-12-01"}, "invalid_recurrence", "avertissement", False),
    ({"recurrence": "1w"}, "recurrence_without_due", "avertissement", False),
    ({"date_creation": "hier"}, "invalid_dates", "avertissement", False),
    ({"statut": "TERMINE"}, "done_without_date", "info", False),
    ({"suivante": "disparue1"}, "missing_next", "info", False),
])
def test_constats_de_tache(todo, champs, code, niveau, reparable):
    brut(todo, "aaaa1111", **{"titre": "T", "statut": "A FAIRE", **champs})
    r, d = diagnostic(todo)
    trouves = [c for c in d["constats"] if c["code"] == code]
    assert len(trouves) == 1, d["constats"]
    c = trouves[0]
    assert c["niveau"] == niveau and c["reparable"] is reparable and c["id"] == "aaaa1111" and c["projet"] == "default"
    assert r.code == (1 if niveau == "erreur" else 0)


def test_entree_illisible(todo):
    todo.seed_brut("bbbb2222", b"{pas du json")
    todo.seed_brut("cccc3333", b"[1, 2]")
    r, d = diagnostic(todo)
    assert codes(d, "erreur") == ["unreadable_entry", "unreadable_entry"] and r.code == 1


def test_dependance_vers_l_archive_est_normale(todo):
    archiver_brut(todo, "arch0001", titre="Faite", statut="TERMINE", date_terminee="2026-01-01 10:00")
    brut(todo, "aaaa1111", titre="T", apres=["arch0001"])
    assert "missing_dependency" not in codes(diagnostic(todo)[1])


def test_cycles_et_auto_dependance(todo):
    brut(todo, "aaaa1111", titre="A", apres=["bbbb2222"])
    brut(todo, "bbbb2222", titre="B", apres=["cccc3333"])
    brut(todo, "cccc3333", titre="C", apres=["aaaa1111"])
    brut(todo, "dddd4444", titre="D", apres=["dddd4444"])
    brut(todo, "eeee5555", titre="E", apres=["aaaa1111"])        # attend le cycle sans en faire partie
    r, d = diagnostic(todo)
    assert codes(d, "erreur") == ["dependency_cycle", "self_dependency"] and r.code == 1
    assert [c["id"] for c in d["constats"] if c["code"] == "self_dependency"] == ["dddd4444"]


def test_archive(todo):
    archiver_brut(todo, "arch0001", titre="Pas finie", statut="A FAIRE")
    archiver_brut(todo, "arch0002", titre="Doublon", statut="TERMINE", date_terminee="2026-01-01 10:00")
    brut(todo, "arch0002", titre="Doublon", statut="TERMINE", date_terminee="2026-01-01 10:00")
    d = diagnostic(todo)[1]
    assert codes(d) == ["archived_not_done", "duplicate_in_archive"]
    assert d["projets"][0]["archive"] == 2


# ------------------------------------------------------------------ pièces jointes
def test_pieces_jointes(todo):
    brut(todo, "aaaa1111", titre="T", pieces_jointes=[{"nom": "absent.txt", "date": "2026-01-01 10:00", "taille": 3, "sha256": "x"}])
    r, d = diagnostic(todo)
    assert codes(d, "erreur") == ["attachment_missing"] and r.code == 1
    r, d = diagnostic(todo, "--no-attachments")
    assert codes(d) == [] and r.code == 0


def test_piece_orpheline(todo):
    brut(todo, "aaaa1111", titre="T")
    dossier = todo.db_dir / "attachments" / "aaaa1111"
    dossier.mkdir(parents=True)
    (dossier / "reste.txt").write_text("x")
    d = diagnostic(todo)[1]
    assert codes(d) == ["attachment_orphan"]


# ------------------------------------------------------------------ codes de sortie et formats
def test_strict_compte_les_avertissements(todo):
    brut(todo, "aaaa1111", titre="T", priorite="urgent")
    assert todo("admin", "doctor", "--format", "json").code == 0
    r = todo("admin", "doctor", "--strict", "--format", "json")
    assert r.code == 1 and r.json()["ok"] is False


def test_formats(todo):
    brut(todo, "aaaa1111", titre="Titre", priorite="urgent")
    brut(todo, "bbbb2222", titre="B", statut="BOF")
    plain = todo("admin", "doctor", "--format", "plain").out.splitlines()
    assert plain[0].split("\t")[:4] == ["avertissement", "invalid_priority", "default", "aaaa1111"]
    assert any(l.startswith("erreur\tinvalid_status\t") for l in plain)
    table = todo("admin", "doctor", "--format", "table").texte
    assert "NIVEAU" in table and "invalid_status" in table
    texte = todo("admin", "doctor", "--format", "text", "--no-color").texte
    assert "Diagnostic de todo-cli" in texte and "invalid_priority" in texte and "1 erreur(s)" in texte
    assert "todo admin doctor --fix" in texte


def test_texte_base_saine(todo):
    todo("add", "Alpha")
    assert "Aucun problème" in todo("admin", "doctor", "--format", "text", "--no-color").texte


# ------------------------------------------------------------------ projets
def test_tous_les_projets(todo):
    todo("project", "create", "travail")
    todo("-p", "travail", "add", "Dossier")
    brut(todo, "aaaa1111", titre="T", priorite="urgent")
    d = todo("admin", "doctor", "--all-projects", "--format", "json").json()
    assert sorted(p["projet"] for p in d["projets"]) == ["default", "travail"]
    assert [c["projet"] for c in d["constats"] if c["code"] == "invalid_priority"] == ["default"]


def test_projet_choisi(todo):
    todo("project", "create", "travail")
    brut(todo, "aaaa1111", titre="T", priorite="urgent")
    assert todo("-p", "travail", "admin", "doctor", "--format", "json").json()["constats"] == []


def test_dossier_de_projet_invalide(todo):
    (todo.db_dir / "projects" / "Mauvais Nom").mkdir(parents=True)
    d = diagnostic(todo)[1]
    assert codes(d) == ["invalid_project_dir"]


# ------------------------------------------------------------------ environnement
def test_variable_inconnue_avec_suggestion(todo):
    d = diagnostic(todo, env={"TODO_REMIND_ENABLE": "1"})[1]
    c = [c for c in d["constats"] if c["code"] == "unknown_env_var"]
    assert len(c) == 1 and "TODO_REMIND_ENABLED" in c[0]["message"] and c[0]["portee"] == "environnement"


def test_configuration_invalide(todo):
    todo.config("[list]\nlimit = abc\n[inconnue]\nx = 1\n")
    d = diagnostic(todo)[1]
    assert codes(d).count("config_warning") == 2


def test_hook_introuvable_et_url_invalide(todo):
    d = diagnostic(todo, env={"TODO_HOOKS_ON_ADD": "/nexiste/pas --x", "TODO_HOOKS_ON_DONE": "sh -c true",
                              "TODO_HOOKS_WEBHOOK_URL": "ftp://example.org/x"})[1]
    assert codes(d) == ["hook_command_not_found", "invalid_webhook_url"]


def test_stockage_modifiable_par_les_autres(todo):
    os.chmod(todo.db_dir, 0o777)
    d = diagnostic(todo)[1]
    assert "storage_group_writable" in codes(d)
    os.chmod(todo.db_dir, 0o700)
    assert "storage_group_writable" not in codes(diagnostic(todo)[1])


def test_fichier_des_vues_illisible(todo):
    (todo.db_dir / "views.json").write_text("{pas du json")
    r, d = diagnostic(todo)
    assert codes(d, "erreur") == ["views_file_invalid"] and r.code == 1


def test_file_du_webhook(todo):
    (todo.db_dir / "webhook_queue.json").write_text("{pas du json")
    assert codes(diagnostic(todo)[1]) == ["webhook_queue_unreadable"]
    assert (todo.db_dir / "webhook_queue.json").exists()          # lue sans être mise de côté
    (todo.db_dir / "webhook_queue.json").write_text(json.dumps({"entries": [{"body": {}, "delivery": "d"}]}))
    assert codes(diagnostic(todo)[1]) == ["webhook_queue_pending"]


def test_sans_sauvegarde(todo):
    brut(todo, "aaaa1111", titre="T")
    assert "no_backup" in codes(diagnostic(todo)[1], sauf=())
    todo("add", "Autre")
    assert "no_backup" not in codes(diagnostic(todo)[1], sauf=())


# ------------------------------------------------------------------ --fix
@pytest.fixture
def abimee(todo):
    todo("add", "Saine")
    brut(todo, "aaaa1111", titre="Prio", priorite="urgent", statut="A FAIRE", tags=["x", 3], apres=["zzzz9999"], demarree="hier",
         date_terminee="2026-01-01 10:00", champ_inconnu="reste", notes=[{"date": "2026-01-01 10:00", "texte": "n", "action": "note"}])
    todo.seed_brut("bbbb2222", b"{pas du json")
    return todo


def test_fix_simulation_ne_modifie_rien(abimee):
    avant = contenu_base(abimee)
    r = abimee("admin", "doctor", "--fix", "--dry-run", "--format", "json")
    d = r.json()
    assert d["reparations"]["simulation"] is True and [t["id"] for t in d["reparations"]["taches"]] == ["aaaa1111"]
    assert contenu_base(abimee) == avant


def test_fix_demande_confirmation(abimee):
    avant = contenu_base(abimee)
    r = abimee("admin", "doctor", "--fix", "--format", "text", "--no-color", entree="n\n")
    assert "annulée" in r.texte and contenu_base(abimee) == avant
    r = abimee("admin", "doctor", "--fix", "--format", "json")                 # pas de terminal ni de --yes : refusé
    assert r.code == 1 and contenu_base(abimee) == avant


def test_fix_repare_sans_rien_perdre(abimee):
    r = abimee("admin", "doctor", "--fix", "--yes", "--format", "json")
    d = r.json()
    assert [t["id"] for t in d["reparations"]["taches"]] == ["aaaa1111"] and d["reparations"]["simulation"] is False
    assert codes(d) == ["unreadable_entry"] and r.code == 1                       # reste ce qui ne se répare pas
    t = json.loads(contenu_base(abimee)["aaaa1111".encode()])
    assert t["priorite"] == "medium" and t["tags"] == ["x"] and t["apres"] == [] and t["demarree"] is None and t["date_terminee"] is None
    assert t["champ_inconnu"] == "reste" and t["titre"] == "Prio" and t["notes"][0]["texte"] == "n"
    assert contenu_base(abimee)[b"bbbb2222"] == b"{pas du json"                  # une entrée illisible n'est jamais touchée
    assert diagnostic(abimee)[1]["bilan"]["reparables"] == 0


def test_fix_est_annulable_par_undo(abimee):
    avant = json.loads(contenu_base(abimee)[b"aaaa1111"])
    abimee("admin", "doctor", "--fix", "--yes")
    assert abimee("undo").code == 0
    assert json.loads(contenu_base(abimee)[b"aaaa1111"]) == avant


def test_fix_repare_aussi_l_archive(todo):
    archiver_brut(todo, "arch0001", titre="Faite", statut="TERMINE", date_terminee="2026-01-01 10:00", priorite="urgent")
    todo("admin", "doctor", "--fix", "--yes")
    with dbm.open(str(todo.db_dir / "todo_archive"), "r") as db:
        assert json.loads(db["arch0001"])["priorite"] == "medium"


def test_fix_sans_rien_a_reparer(todo):
    todo("add", "Alpha")
    avant = contenu_base(todo)
    r = todo("admin", "doctor", "--fix", "--yes", "--format", "json")
    assert r.code == 0 and contenu_base(todo) == avant and r.json()["reparations"]["taches"] == []


def test_options_incompatibles(todo):
    assert todo("admin", "doctor", "--fix", "--all-projects", "--yes").code == 1
    assert todo("admin", "doctor", "--dry-run").code == 1
    assert todo("admin", "doctor", "--yes").code == 1
