"""Export et import JSON."""
import json
import shutil
import subprocess

import pytest

from outils import Todo, jour

JOURNAL = {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"}


@pytest.fixture
def source(todo):
    """Une instance avec des tâches variées : récurrente, notes, terminée, archivée."""
    todo.seed(
        {"cle": "aaaaaaaa-1", "titre": "Alpha", "priorite": "high", "echeance": jour(2), "tags": ["pro", "dev"],
         "recurrence": "1w", "description": "à faire", "creation": "2026-01-01 10:00"},
        {"cle": "bbbbbbbb-2", "titre": "Beta", "creation": "2026-01-02 10:00"},
        {"cle": "cccccccc-3", "titre": "Gamma", "statut": "TERMINE", "terminee": "2026-02-01 09:00", "creation": "2026-01-03 10:00"},
    )
    todo("note", "add", "aaaaaaaa", "une note")
    todo("done", "cccccccc")
    todo("archive", "add")
    return todo


@pytest.fixture
def destination(tmp_path):
    (tmp_path / "dest").mkdir()
    return Todo(tmp_path / "dest")


def export(todo, *args):
    return todo("data", "export", *args)


# ------------------------------------------------------------------ export
def test_export_stdout_est_du_json_valide(source):
    r = export(source)
    assert r.code == 0
    d = r.json()
    assert d["format"] == "todo-cli" and d["version"] == 1
    assert d["compteurs"] == {"taches": 2, "archive": 1}
    assert [t["titre"] for t in d["taches"]] == ["Alpha", "Beta"]   # triées par date de création
    assert d["archive"][0]["titre"] == "Gamma" and d["archive"][0]["date_archivage"]


def test_export_contient_tous_les_champs(source):
    alpha = export(source).json()["taches"][0]
    assert alpha["id"].startswith("aaaaaaaa") and alpha["priorite"] == "high"
    assert alpha["tags"] == ["pro", "dev"] and alpha["recurrence"] == "1w" and alpha["description"] == "à faire"
    assert alpha["notes"][0]["texte"] == "une note"


def test_export_vers_un_fichier(source, tmp_path):
    cible = tmp_path / "sortie.json"
    r = export(source, str(cible))
    assert r.code == 0 and "2 tâche(s) et 1 archivée(s)" in r.sortie and r.out.count("{") == 0
    assert json.loads(cible.read_text(encoding="utf-8"))["compteurs"] == {"taches": 2, "archive": 1}
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".todo-export-")]   # pas de fichier temporaire


def test_export_refuse_d_ecraser_sans_force(source, tmp_path):
    cible = tmp_path / "sortie.json"
    cible.write_text("précieux")
    r = export(source, str(cible))
    assert r.code == 1 and "--force" in r.texte and cible.read_text() == "précieux"
    assert export(source, str(cible), "--force").code == 0 and "format" in cible.read_text()


def test_export_dossier_inexistant(source, tmp_path):
    r = export(source, str(tmp_path / "absent" / "x.json"))
    assert r.code == 1 and "Impossible d'écrire" in r.texte


def test_export_sans_archive(source):
    d = export(source, "--no-archive").json()
    assert d["archive"] == [] and d["compteurs"]["archive"] == 0


def test_export_base_vide(todo):
    d = export(todo).json()
    assert d["taches"] == [] and d["archive"] == []


def test_export_ne_modifie_rien(source):
    avant = source.sauvegardes()
    export(source)
    assert source.sauvegardes() == avant


def test_export_tiret_est_la_sortie_standard(source):
    assert export(source, "-").json()["compteurs"]["taches"] == 2


# ------------------------------------------------------------------ aller-retour
def test_aller_retour_complet(source, destination, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    r = destination("data", "import", str(cible))
    assert r.code == 0 and "3 ajoutée(s)" in r.sortie
    assert destination.taches() == source.taches()
    assert destination("archive", "list", "--format", "json").json() == source("archive", "list", "--format", "json").json()


def test_reexport_identique(source, destination, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    destination("data", "import", str(cible))
    a, b = export(source).json(), export(destination).json()
    a.pop("exporte_le"), b.pop("exporte_le")
    assert a == b


def test_import_depuis_l_entree_standard(source, destination):
    r = destination("data", "import", "-", entree=export(source).out)
    assert r.code == 0 and len(destination.taches()) == 2


def test_import_sortie_de_list_json(source, destination):
    r = destination("data", "import", "-", entree=source("list", "--format", "json").out)
    assert r.code == 0 and "2 ajoutée(s)" in r.sortie
    assert {t["titre"] for t in destination.taches().values()} == {"Alpha", "Beta"}


# ------------------------------------------------------------------ modes
def test_import_ignore_les_identifiants_existants(source, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    source("task", "edit", "aaaaaaaa", "--title", "Modifié localement")
    r = source("data", "import", str(cible))
    assert r.code == 0 and "0 ajoutée(s)" in r.sortie and "3 ignorée(s)" in r.sortie
    assert source.une("Modifié localement")


def test_import_update_remplace_par_la_version_du_fichier(source, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    source("task", "edit", "aaaaaaaa", "--title", "Modifié localement")
    r = source("data", "import", str(cible), "--update")
    assert r.code == 0 and "3 mise(s) à jour" in r.sortie
    assert source.une("Alpha") and not source.par_titre("Modifié localement")


def test_import_update_deplace_entre_liste_et_archive(source, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    source("archive", "restore", "cccccccc")               # Gamma revient dans la liste ; le fichier la veut archivée
    source("data", "import", str(cible), "--update")
    assert not source.par_titre("Gamma")
    assert [t["titre"] for t in source("archive", "list", "--format", "json").json()] == ["Gamma"]


def test_import_ne_cree_pas_de_doublon_liste_archive(source, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    source("archive", "restore", "cccccccc")
    source("data", "import", str(cible))                   # Gamma existe (dans la liste) : ignorée, pas dupliquée
    assert source("archive", "list", "--format", "json").json() == []


def test_import_replace(source, destination, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    destination("add", "À écraser")
    r = destination("data", "import", str(cible), "--replace", "-y")
    assert r.code == 0 and "supprimée(s) avant import" in r.sortie
    assert not destination.par_titre("À écraser") and len(destination.taches()) == 2


def test_import_replace_demande_confirmation(source, destination, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    destination("add", "Garder")
    r = destination("data", "import", str(cible), "--replace", entree="n\n")
    assert "annulée" in r.sortie and destination.par_titre("Garder")
    r = destination("data", "import", str(cible), "--replace", entree="y\n")
    assert not destination.par_titre("Garder") and len(destination.taches()) == 2


def test_import_replace_avec_stdin_exige_y(source, destination):
    r = destination("data", "import", "-", "--replace", entree=export(source).out)
    assert r.code == 1 and "-y" in r.texte


def test_update_et_replace_exclusifs(source, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    assert source("data", "import", str(cible), "--update", "--replace").code != 0


def test_import_dry_run(source, destination, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    r = destination("data", "import", str(cible), "--dry-run")
    assert r.code == 0 and "Simulation" in r.sortie and "3 ajoutée(s)" in r.sortie
    assert destination.taches() == {} and destination.sauvegardes() == []


# ------------------------------------------------------------------ validation
def test_import_fichier_inexistant(todo, tmp_path):
    r = todo("data", "import", str(tmp_path / "absent.json"))
    assert r.code == 1 and "Impossible de lire" in r.texte


@pytest.mark.parametrize("contenu, attendu", [
    ("pas du json", "JSON valide"),
    ('"texte"', "objet"),
    ('{"format": "autre", "taches": []}', "Format inconnu"),
    ('{"format": "todo-cli", "version": 99, "taches": []}', "Version"),
    ('{"format": "todo-cli", "version": 1}', "Aucune tâche"),
    ('{"taches": {"a": 1}}', "listes"),
])
def test_import_fichier_inutilisable(todo, tmp_path, contenu, attendu):
    cible = tmp_path / "x.json"
    cible.write_text(contenu, encoding="utf-8")
    r = todo("data", "import", str(cible))
    assert r.code == 1 and attendu in r.texte and todo.taches() == {}


@pytest.mark.parametrize("entree, raison", [
    ({"priorite": "high"}, "titre"),
    ({"titre": "  "}, "titre"),
    ({"titre": "x", "priorite": "urgent"}, "priorité"),
    ({"titre": "x", "statut": "FINI"}, "statut"),
    ({"titre": "x", "date_echeance": "demain"}, "échéance"),
    ({"titre": "x", "date_echeance": "2026-13"}, "échéance"),
    ({"titre": "x", "tags": "a,b"}, "tags"),
    ({"titre": "x", "recurrence": "souvent"}, "récurrence"),
    ({"titre": "x", "description": 5}, "description"),
    ("une chaîne", "objet"),
])
def test_import_entree_invalide(todo, tmp_path, entree, raison):
    cible = tmp_path / "x.json"
    cible.write_text(json.dumps([{"titre": "bonne"}, entree]), encoding="utf-8")
    r = todo("data", "import", str(cible))
    assert r.code == 1 and raison in r.texte and "taches[1]" in r.texte
    assert "1 ajoutée(s)" in r.sortie and "1 invalide(s)" in r.sortie
    assert [t["titre"] for t in todo.taches().values()] == ["bonne"]     # les entrées valides passent quand même


def test_import_identifiant_en_double_dans_le_fichier(todo):
    entree = json.dumps([{"id": "zz", "titre": "a"}, {"id": "zz", "titre": "b"}])
    r = todo("data", "import", "-", entree=entree)
    assert r.code == 1 and "double" in r.texte and [t["titre"] for t in todo.taches().values()] == ["a"]


def test_import_sans_identifiant_en_genere_un(todo):
    todo("data", "import", "-", entree=json.dumps([{"titre": "a"}, {"titre": "a"}]))
    assert len(todo.par_titre("a")) == 2


def test_import_valeurs_par_defaut_et_normalisation(todo):
    todo("data", "import", "-", entree=json.dumps([{"titre": " Sobre ", "priorite": "HIGH", "tags": [" A ", ""], "recurrence": "weekly"}]))
    t = todo.une("Sobre")
    assert t["priorite"] == "high" and t["tags"] == ["a"] and t["recurrence"] == "1w"
    assert t["statut"] == "A FAIRE" and t["notes"] == [] and t["date_creation"]


def test_import_notes_invalides_ignorees(todo):
    todo("data", "import", "-", entree=json.dumps([{"titre": "t", "notes": ["x", {"texte": ""}, {"texte": "ok", "date": "2026-01-01 10:00"}]}]))
    assert [n["texte"] for n in todo.une("t")["notes"]] == ["ok"]


def test_import_bilan_json(source, destination):
    d = destination("data", "import", "-", "--format", "json", entree=export(source).out).json()
    assert d["ajoutees"] == 3 and d["ignorees"] == 0 and d["invalides"] == [] and d["simulation"] is False
    d = destination("data", "import", "-", "--format", "json", entree=json.dumps([{"titre": ""}])).json()
    assert d["invalides"][0]["position"] == "taches[0]"


# ------------------------------------------------------------------ sauvegarde, undo, journal
def test_import_cree_une_sauvegarde_et_undo_l_annule(source, destination):
    destination("add", "Existante")
    avant = len(destination.sauvegardes())
    destination("data", "import", "-", entree=export(source).out)
    assert len(destination.sauvegardes()) == avant + 1 and len(destination.taches()) == 3
    destination("undo")
    assert [t["titre"] for t in destination.taches().values()] == ["Existante"]


def test_import_sans_changement_ne_sauvegarde_pas(source, tmp_path):
    cible = tmp_path / "x.json"
    export(source, str(cible))
    avant = source.sauvegardes()
    source("data", "import", str(cible))
    assert source.sauvegardes() == avant


def test_import_au_journal_et_export_en_lecture_seule(source, destination, tmp_path):
    cible = tmp_path / "x.json"
    source("data", "export", str(cible), env=JOURNAL)
    assert source.journal() == []                    # l'export ne modifie rien : rien à tracer en INFO
    destination("data", "import", str(cible), env=JOURNAL)
    ligne = next(l for l in destination.journal() if l.startswith("INFO import"))
    assert "imported=3" in ligne and "Alpha" not in ligne


@pytest.mark.skipif(not shutil.which("jq"), reason="jq absent")
def test_jq_lit_l_export(source):
    sortie = export(source).out
    r = subprocess.run(["jq", "-r", ".taches[].titre"], input=sortie, capture_output=True, text=True)
    assert r.stdout.split() == ["Alpha", "Beta"]
