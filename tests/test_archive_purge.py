"""archive --purge : suppression définitive de tâches archivées (remplace l'ancien clear-done)."""
import pytest

from outils import jour

JOURNAL = {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"}


@pytest.fixture
def archive3(todo):
    """Active + trois tâches archivées (terminées il y a 100, 40 et 2 jours) + une archivée sans date de complétion."""
    todo.seed(
        {"cle": "act-0001", "titre": "Active"},
        {"cle": "vieille1", "titre": "Vieille", "statut": "TERMINE", "terminee": jour(-100) + " 10:00"},
        {"cle": "moyenne1", "titre": "Moyenne", "statut": "TERMINE", "terminee": jour(-40) + " 10:00"},
        {"cle": "recente1", "titre": "Récente", "statut": "TERMINE", "terminee": jour(-2) + " 10:00"},
        {"cle": "sansdate", "titre": "SansDate", "statut": "TERMINE"},
    )
    todo("archive", "sansdate")
    todo("archive")
    return todo


def titres_archive(todo):
    return sorted(t["titre"] for t in todo("archive", "--list", "--format", "json").json())


def test_purge_tout_apres_confirmation(archive3):
    r = archive3("archive", "--purge", entree="y\n")
    assert r.code == 0 and "4 tâche(s) supprimée(s)" in r.sortie
    assert titres_archive(archive3) == [] and "Active" in {t["titre"] for t in archive3.taches().values()}


def test_purge_demande_confirmation_et_montre_les_titres(archive3):
    r = archive3("archive", "--purge", entree="n\n")
    assert r.code == 0 and "annulée" in r.texte and "DANGER" in r.texte and "4 tâche(s)" in r.texte
    assert len(titres_archive(archive3)) == 4


def test_purge_sans_reponse_ne_fait_rien(archive3):
    archive3("archive", "--purge")
    assert len(titres_archive(archive3)) == 4


def test_purge_yes_sans_confirmation(archive3):
    r = archive3("archive", "--purge", "-y")
    assert r.code == 0 and titres_archive(archive3) == []


def test_purge_older_than(archive3):
    r = archive3("archive", "--purge", "--older-than", "30d", "-y")
    assert "2 tâche(s) supprimée(s)" in r.sortie
    assert titres_archive(archive3) == ["Récente", "SansDate"]


def test_purge_older_than_signale_les_sans_date(archive3):
    r = archive3("archive", "--purge", "--older-than", "1d", "-y")
    assert "1 tâche(s) sans date de complétion ignorée(s)" in r.sortie
    assert "SansDate" in titres_archive(archive3)


def test_purge_older_than_rien_a_purger(archive3):
    r = archive3("archive", "--purge", "--older-than", "5y", "-y")
    assert r.code == 0 and "Aucune tâche archivée" in r.sortie and len(titres_archive(archive3)) == 4


def test_purge_par_identifiant(archive3):
    r = archive3("archive", "--purge", "vieille1", "recente1", "-y")
    assert r.code == 0 and "2 tâche(s) supprimée(s)" in r.sortie and "Bilan" in r.sortie
    assert titres_archive(archive3) == ["Moyenne", "SansDate"]


def test_purge_identifiant_inconnu(archive3):
    r = archive3("archive", "--purge", "zzzz", "-y")
    assert r.code == 1 and len(titres_archive(archive3)) == 4


def test_purge_identifiant_de_la_liste_n_est_pas_dans_l_archive(archive3):
    r = archive3("archive", "--purge", "act-0001", "-y")
    assert r.code == 1 and "Active" in {t["titre"] for t in archive3.taches().values()}


def test_purge_ids_et_older_than_incompatibles(archive3):
    r = archive3("archive", "--purge", "vieille1", "--older-than", "30d", "-y")
    assert r.code == 1 and len(titres_archive(archive3)) == 4


def test_purge_durée_invalide(archive3):
    r = archive3("archive", "--purge", "--older-than", "bientôt", "-y")
    assert r.code == 1 and "Durée non reconnue" in r.texte


@pytest.mark.parametrize("option", ["--list", "--search"])
def test_purge_incompatible_avec_list_et_search(archive3, option):
    args = ("archive", "--purge", option) + (("x",) if option == "--search" else ())
    r = archive3(*args, "-y")
    assert r.code == 1 and "--purge" in r.texte and len(titres_archive(archive3)) == 4


def test_purge_archive_vide(todo):
    r = todo("archive", "--purge", "-y")
    assert r.code == 0 and "vide" in r.sortie
    todo("add", "x")
    todo("done", todo.id_de("x"))
    todo("archive")
    todo("archive", "--purge", "-y")
    r = todo("archive", "--purge", "-y")
    assert r.code == 0 and "Aucune tâche archivée" in r.sortie


def test_purge_sauvegarde_puis_undo_retablit(archive3):
    archive3("archive", "--purge", "-y")
    assert titres_archive(archive3) == []
    archive3("undo")
    assert len(titres_archive(archive3)) == 4


def test_purge_ne_touche_pas_a_la_liste(archive3):
    avant = archive3.taches()
    archive3("archive", "--purge", "-y")
    assert archive3.taches() == avant


def test_purge_entree_corrompue_supprimable_par_id(todo):
    import dbm
    with dbm.open(str(todo.db_dir / "todo_archive"), "c") as db:
        db["corrompu1"] = b"\xff pas du json"
    r = todo("archive", "--purge", "corrompu1", "-y")
    assert r.code == 0
    with dbm.open(str(todo.db_dir / "todo_archive"), "r") as db:
        assert len(db) == 0


def test_purge_au_journal(archive3):
    archive3("archive", "--purge", "vieille1", "-y", env=JOURNAL)
    ligne = next(l for l in archive3.journal() if l.startswith("INFO archive"))
    assert "purged=1" in ligne and "ids=vieille1" in ligne and "Vieille" not in ligne


def test_clear_done_n_existe_plus(todo):
    r = todo("clear-done")
    assert r.code == 2 and "invalid choice" in r.texte
