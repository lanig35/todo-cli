"""Pièces jointes : attachment add/list/open/save/remove/gc, corbeille, undo, projets, filtres."""
import json
import os
import stat

import pytest

from outils import jour


@pytest.fixture
def tache(todo):
    todo("add", "Dossier impôts")
    return todo, todo.id_de("Dossier impôts")


@pytest.fixture
def fichiers(todo):
    d = todo.dossier / "src"
    d.mkdir()
    (d / "avis.txt").write_text("avis d'imposition\n")
    (d / "scan.bin").write_bytes(bytes(range(256)) * 20)
    return d


def dossier_pj(todo, ident=None, projet=None):
    base = todo.db_dir / ("projects/" + projet if projet else "") / "attachments"
    return base / ident if ident else base


def pieces(todo, ident):
    return todo("attachment", "list", ident, "--format", "json").json()["pieces_jointes"]


# ------------------------------------------------------------------ ajout
def test_ajoute_des_fichiers_copies(tache, fichiers):
    todo, i = tache
    r = todo("attachment", "add", i, fichiers / "avis.txt", fichiers / "scan.bin", "--comment", "pour 2026")
    assert r.code == 0 and "avis.txt" in r.sortie and "2 au total" in r.sortie
    p = pieces(todo, i)
    assert [x["nom"] for x in p] == ["avis.txt", "scan.bin"]
    assert p[0]["taille"] == len("avis d'imposition\n") and len(p[0]["sha256"]) == 64 and p[0]["commentaire"] == "pour 2026"
    assert all(x["present"] for x in p)
    complet = todo.une("Dossier impôts")["id"]
    assert (dossier_pj(todo, complet) / "avis.txt").read_text() == "avis d'imposition\n"
    (fichiers / "avis.txt").unlink()                       # l'original disparaît : la copie reste
    assert (dossier_pj(todo, complet) / "avis.txt").exists()


def test_droits_restrictifs(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    complet = todo.une("Dossier impôts")["id"]
    assert stat.S_IMODE(os.stat(dossier_pj(todo, complet) / "avis.txt").st_mode) == 0o600
    assert stat.S_IMODE(os.stat(dossier_pj(todo, complet)).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(dossier_pj(todo)).st_mode) == 0o700


def test_nom_deja_pris_recoit_un_suffixe(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    todo("attachment", "add", i, fichiers / "avis.txt")
    todo("attachment", "add", i, fichiers / "avis.txt")
    assert [x["nom"] for x in pieces(todo, i)] == ["avis.txt", "avis-2.txt", "avis-3.txt"]


def test_ajout_atomique_si_un_fichier_est_invalide(tache, fichiers):
    todo, i = tache
    r = todo("attachment", "add", i, fichiers / "avis.txt", fichiers / "absent.pdf")
    assert r.code == 1 and "introuvable" in r.sortie
    assert pieces(todo, i) == [] and not dossier_pj(todo).exists()
    assert todo("attachment", "add", i, fichiers).code == 1             # un dossier n'est pas joignable


def test_taille_maximale(tache, fichiers):
    todo, i = tache
    todo.config("[attachments]\nmax_size = 1\n")
    (fichiers / "gros.bin").write_bytes(b"x" * (1024 * 1024 + 1))
    r = todo("attachment", "add", i, fichiers / "gros.bin")
    assert r.code == 1 and "trop gros" in r.sortie and "max_size" in r.sortie
    assert pieces(todo, i) == []
    assert todo("attachment", "add", i, fichiers / "gros.bin", env={"TODO_ATTACHMENTS_MAX_SIZE": "0"}).code == 0


def test_commentaire_trop_long(tache, fichiers):
    todo, i = tache
    assert todo("attachment", "add", i, fichiers / "avis.txt", "--comment", "x" * 201).code == 1


def test_tache_introuvable(todo, fichiers):
    todo("add", "A")
    assert todo("attachment", "add", "zzzz", fichiers / "avis.txt").code == 1


def test_nom_assaini(tache, fichiers):
    todo, i = tache
    (fichiers / ".cache").write_text("x")
    todo("attachment", "add", i, fichiers / ".cache")
    assert [x["nom"] for x in pieces(todo, i)] == ["_cache"]


def test_ajout_sur_la_sortie_json(tache, fichiers):
    todo, i = tache
    d = todo("attachment", "add", i, fichiers / "avis.txt", "--format", "json").json()
    assert d["total"] == 1 and d["ajoutees"][0]["nom"] == "avis.txt"


def test_ajout_cree_une_sauvegarde_et_undo_le_defait(tache, fichiers):
    todo, i = tache
    avant = len(todo.sauvegardes())
    todo("attachment", "add", i, fichiers / "avis.txt")
    assert len(todo.sauvegardes()) == avant + 1
    todo("undo")
    assert pieces(todo, i) == []
    todo("attachment", "add", i, fichiers / "avis.txt")                  # le fichier orphelin est réutilisé, pas suffixé
    assert [x["nom"] for x in pieces(todo, i)] == ["avis.txt"]


# ------------------------------------------------------------------ affichage
def test_list_formats(tache, fichiers):
    todo, i = tache
    assert "Aucune pièce jointe" in todo("attachment", "list", i).sortie
    todo("attachment", "add", i, fichiers / "avis.txt", "--comment", "c")
    assert "avis.txt" in todo("attachment", "list", i).sortie
    ligne = todo("attachment", "list", "--format", "plain").sortie.splitlines()[0].split("\t")
    assert ligne[1:3] == ["1", "avis.txt"] and ligne[3] == str(len("avis d'imposition\n")) and ligne[6] == "c"
    assert "avis.txt" in todo("attachment", "list", "--format", "table").sortie
    tout = todo("attachment", "list", "--format", "json").json()
    assert [t["titre"] for t in tout] == ["Dossier impôts"] and tout[0]["pieces_jointes"][0]["numero"] == 1


def test_list_sans_identifiant_ignore_les_taches_sans_piece(tache, fichiers):
    todo, i = tache
    todo("add", "Autre")
    todo("attachment", "add", i, fichiers / "avis.txt")
    assert [t["titre"] for t in todo("attachment", "list", "--format", "json").json()] == ["Dossier impôts"]


def test_show_affiche_les_pieces(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    assert "Pièces jointes (1)" in todo("show", i).sortie and "avis.txt" in todo("show", i).sortie
    assert ["piece", "avis.txt", str(len("avis d'imposition\n"))] in [l.split("\t") for l in todo("show", i, "--format", "plain").sortie.splitlines()]
    assert todo("show", i, "--format", "json").json()["pieces_jointes"][0]["nom"] == "avis.txt"


def test_show_signale_un_fichier_manquant(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    (dossier_pj(todo, todo.une("Dossier impôts")["id"]) / "avis.txt").unlink()
    assert "fichier manquant" in todo("show", i).sortie
    assert todo("attachment", "open", i, "1").code == 1


def test_colonne_files_et_filtres(tache, fichiers):
    todo, i = tache
    todo("add", "Sans")
    todo("attachment", "add", i, fichiers / "avis.txt", fichiers / "scan.bin")
    lignes = [l.split("\t") for l in todo("list", "--columns", "id,title,files", "--format", "plain").sortie.splitlines()]
    assert {l[1]: l[2] for l in lignes} == {"Dossier impôts": "2", "Sans": "0"}
    assert [t["titre"] for t in todo("list", "--has-files", "--format", "json").json()] == ["Dossier impôts"]
    assert [t["titre"] for t in todo("list", "--no-files", "--format", "json").json()] == ["Sans"]
    assert todo("list", "--has-files", "--no-files").code == 2
    assert "📎2" in todo("list").sortie


# ------------------------------------------------------------------ open / save
def test_open_sans_outil_affiche_le_chemin(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    env = {"DISPLAY": None, "WAYLAND_DISPLAY": None}
    r = todo("attachment", "open", i, "1", env=env)
    assert r.code == 0 and str(dossier_pj(todo, todo.une("Dossier impôts")["id"]) / "avis.txt") in r.sortie
    assert todo("attachment", "open", i, "1", "--format", "plain", env=env).sortie.strip().endswith("avis.txt")
    assert todo("attachment", "open", i, "1", "--format", "json", env=env).json()["ouvert"] is False


def test_open_avec_l_outil_configure(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    r = todo("attachment", "open", i, "1", env={"TODO_ATTACHMENTS_OPENER": "cat"})
    assert r.code == 0 and "avis d'imposition" in r.sortie
    assert todo("attachment", "open", i, "1", env={"TODO_ATTACHMENTS_OPENER": "false"}).code == 1
    r = todo("attachment", "open", i, "1", env={"TODO_ATTACHMENTS_OPENER": "outil-inexistant-xyz"})
    assert r.code == 1 and "outil-inexistant-xyz" in r.sortie


def test_save_copie_vers_un_dossier(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "scan.bin")
    sortie = todo.dossier / "sortie"
    sortie.mkdir()
    assert todo("attachment", "save", i, "1", "--to", sortie).code == 0
    assert (sortie / "scan.bin").read_bytes() == (fichiers / "scan.bin").read_bytes()
    r = todo("attachment", "save", i, "1", "--to", sortie)
    assert r.code == 1 and "existe déjà" in r.sortie
    (sortie / "scan.bin").write_bytes(b"autre")
    assert todo("attachment", "save", i, "1", "--to", sortie, "--force").code == 0
    assert (sortie / "scan.bin").read_bytes() == (fichiers / "scan.bin").read_bytes()
    assert todo("attachment", "save", i, "1", "--to", todo.dossier / "nulle-part").code == 1


def test_save_dans_le_dossier_courant(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    assert todo("attachment", "save", i, "1").code == 0
    assert (todo.dossier / "avis.txt").exists()                   # le programme tourne dans todo.dossier


@pytest.mark.parametrize("verbe", ["open", "save", "remove"])
@pytest.mark.parametrize("numero", ["0", "2", "-1"])
def test_numero_invalide(tache, fichiers, verbe, numero):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    r = todo("attachment", verbe, i, numero)
    assert r.code in (1, 2)
    assert len(pieces(todo, i)) == 1


# ------------------------------------------------------------------ suppression, corbeille, undo
def test_remove_met_le_fichier_en_corbeille(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt", fichiers / "scan.bin")
    complet = todo.une("Dossier impôts")["id"]
    r = todo("attachment", "remove", i, "1")
    assert r.code == 0 and "détachée" in r.sortie
    assert [x["nom"] for x in pieces(todo, i)] == ["scan.bin"]
    assert not (dossier_pj(todo, complet) / "avis.txt").exists()
    assert list((dossier_pj(todo) / ".trash" / complet).glob("*/avis.txt"))


def test_undo_apres_remove_retrouve_le_fichier(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    complet = todo.une("Dossier impôts")["id"]
    todo("attachment", "remove", i, "1")
    todo("undo")
    assert todo("attachment", "open", i, "1", env={"TODO_ATTACHMENTS_OPENER": "cat"}).sortie.count("avis d'imposition") == 1
    assert (dossier_pj(todo, complet) / "avis.txt").exists()
    assert not (dossier_pj(todo) / ".trash").exists()


def test_task_remove_puis_undo(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    complet = todo.une("Dossier impôts")["id"]
    assert todo("task", "remove", i).code == 0
    assert not (dossier_pj(todo, complet)).exists() and list((dossier_pj(todo) / ".trash" / complet).glob("*/avis.txt"))
    todo("undo")
    assert all(x["present"] for x in pieces(todo, i))
    todo("attachment", "save", i, "1", "--to", todo.dossier)
    assert (todo.dossier / "avis.txt").read_text() == "avis d'imposition\n"


def test_archivage_laisse_les_fichiers_en_place(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    complet = todo.une("Dossier impôts")["id"]
    todo("done", i)
    todo("archive", "add")
    assert (dossier_pj(todo, complet) / "avis.txt").exists()
    todo("archive", "restore", i)
    assert all(x["present"] for x in pieces(todo, i))


def test_purge_de_l_archive_met_en_corbeille(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    complet = todo.une("Dossier impôts")["id"]
    todo("done", i)
    todo("archive", "add")
    todo("archive", "purge", "-y")
    assert not (dossier_pj(todo, complet)).exists() and list((dossier_pj(todo) / ".trash" / complet).glob("*/avis.txt"))
    todo("undo")                                                     # la purge est annulée : la tâche et son fichier reviennent
    todo("archive", "restore", i)
    assert all(x["present"] for x in pieces(todo, i))


# ------------------------------------------------------------------ gc
def test_gc_vide_la_corbeille(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    todo("attachment", "remove", i, "1")
    r = todo("attachment", "gc", entree="n\n")
    assert r.code == 0 and "annulée" in r.sortie and (dossier_pj(todo) / ".trash").exists()
    assert todo("attachment", "gc", entree="").code == 0 and (dossier_pj(todo) / ".trash").exists()     # sans terminal : non
    r = todo("attachment", "gc", "-y")
    assert r.code == 0 and "1 fichier(s) supprimé(s)" in r.sortie
    assert not (dossier_pj(todo) / ".trash").exists()
    assert "est vide" in todo("attachment", "gc", "-y").sortie


def test_gc_json(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    todo("attachment", "remove", i, "1")
    assert todo("attachment", "gc", "-y", "--format", "json").json() == {"supprimes": 1, "octets": len("avis d'imposition\n")}


def test_gc_older_than(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    complet = todo.une("Dossier impôts")["id"]
    todo("attachment", "remove", i, "1")                              # en corbeille depuis aujourd'hui
    ancien = dossier_pj(todo) / ".trash" / complet / "20200101-120000"
    ancien.mkdir(parents=True)
    (ancien / "vieux.txt").write_text("v")
    r = todo("attachment", "gc", "--older-than", "30d", "-y")
    assert r.code == 0 and "1 fichier(s) supprimé(s)" in r.sortie
    assert not ancien.exists() and list((dossier_pj(todo) / ".trash" / complet).glob("*/avis.txt"))
    assert todo("attachment", "gc", "--older-than", "bientôt", "-y").code == 1


# ------------------------------------------------------------------ projets
def test_move_emmene_les_fichiers(tache, fichiers):
    todo, i = tache
    todo("project", "create", "travail")
    todo("attachment", "add", i, fichiers / "avis.txt")
    complet = todo.une("Dossier impôts")["id"]
    assert todo("task", "move", i, "--to", "travail").code == 0
    assert not (dossier_pj(todo, complet)).exists()
    assert (dossier_pj(todo, complet, "travail") / "avis.txt").read_text() == "avis d'imposition\n"
    assert todo("attachment", "open", i, "1", "-p", "travail", env={"TODO_ATTACHMENTS_OPENER": "cat"}).sortie.count("avis") >= 1


def test_chaque_projet_a_ses_pieces(todo, fichiers):
    todo("project", "create", "travail")
    todo("add", "A")
    todo("add", "B", "-p", "travail")
    a, b = todo.id_de("A"), todo("list", "-p", "travail", "--format", "json").json()[0]["id"][:8]
    todo("attachment", "add", a, fichiers / "avis.txt")
    todo("attachment", "add", b, fichiers / "scan.bin", "-p", "travail")
    assert [x["nom"] for x in pieces(todo, a)] == ["avis.txt"]
    assert todo("attachment", "list", b, "--format", "json", "-p", "travail").json()["pieces_jointes"][0]["nom"] == "scan.bin"
    assert dossier_pj(todo).exists() and dossier_pj(todo, projet="travail").exists()


# ------------------------------------------------------------------ cohérence avec le reste
def test_import_update_garde_les_pieces(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    export = todo.dossier / "export.json"
    export.write_text(todo("data", "export").sortie)
    d = json.loads(export.read_text())
    d["taches"][0]["titre"] = "Renommée"
    export.write_text(json.dumps(d))
    assert todo("data", "import", export, "--update").code == 0
    assert todo.une("Renommée")["pieces_jointes"][0]["nom"] == "avis.txt"


def test_les_sauvegardes_ne_contiennent_pas_les_fichiers(tache, fichiers):
    todo, i = tache
    todo("attachment", "add", i, fichiers / "avis.txt")
    for s in todo.sauvegardes():
        assert not any(f.startswith("avis") for f in os.listdir(todo.db_dir / "backups" / s))


def test_ancienne_tache_sans_pieces(todo):
    todo.seed({"cle": b"abc", "titre": "Vieille"})
    assert todo("show", "abc", "--format", "json").json()["pieces_jointes"] == []
    assert "Aucune pièce jointe" in todo("attachment", "list", "abc").sortie


def test_entree_pieces_corrompue_ignoree(todo):
    todo.seed_brut(b"abc", json.dumps({"titre": "X", "statut": "A FAIRE", "priorite": "medium",
                                       "pieces_jointes": [{"nom": "../evil"}, {"nom": "ok.txt", "taille": "grand"}, 5, {"nom": ".cache"}]}).encode())
    p = todo("show", "abc", "--format", "json").json()["pieces_jointes"]
    assert [x["nom"] for x in p] == ["ok.txt"] and p[0]["taille"] == 0


def test_reglages_attachments(todo):
    assert "[attachments]" in todo("config", "show").sortie or "max_size" in todo("config", "show").sortie
    assert todo("config", "get", "attachments.max_size").sortie.strip().startswith("10")
