import pytest

from outils import jour


def titres(todo):
    return {t["titre"] for t in todo.taches().values()}


def test_rien_a_annuler(todo):
    r = todo("undo")
    assert r.code == 1 and "Rien à annuler" in r.texte
    todo("add", "A")                      # une seule sauvegarde : aucun état antérieur
    r = todo("undo")
    assert r.code == 1 and "Rien à annuler" in r.texte
    assert titres(todo) == {"A"}


def test_annuler_un_ajout(todo):
    todo("add", "A"); todo("add", "B")
    r = todo("undo")
    assert r.code == 0 and "retirer 'B'" in r.texte
    assert titres(todo) == {"A"}


def test_annuler_une_suppression(todo):
    todo("add", "A"); todo("add", "B")
    todo("remove", todo.id_de("B"))
    r = todo("undo")
    assert r.code == 0 and "rétablir 'B'" in r.texte
    assert titres(todo) == {"A", "B"}


def test_annuler_une_modification(todo):
    todo("add", "A", "--prio", "low")
    todo("edit", todo.id_de("A"), "--title", "Nouveau", "--prio", "high")
    r = todo("undo")
    assert "remettre dans leur état précédent 'A'" in r.texte
    t = todo.une("A")
    assert t["priorite"] == "low"


def test_annuler_done(todo):
    todo("add", "A"); todo("add", "B")
    todo("done", todo.id_de("A"))
    todo("undo")
    assert todo.une("A")["statut"] == "A FAIRE" and todo.une("A")["date_terminee"] is None


def test_annuler_done_d_une_recurrente_supprime_l_occurrence(todo):
    todo("add", "R", "--repeat", "daily"); todo("add", "X")
    todo("done", todo.id_de("R"))
    assert len(todo.par_titre("R")) == 2
    r = todo("undo")
    assert "retirer" in r.texte
    assert len(todo.par_titre("R")) == 1 and todo.une("R")["statut"] == "A FAIRE"


def test_un_second_undo_retablit(todo):
    todo("add", "A"); todo("add", "B")
    todo("undo")
    assert titres(todo) == {"A"}
    r = todo("undo")
    assert r.code == 0 and "rétablir 'B'" in r.texte
    assert titres(todo) == {"A", "B"}
    todo("undo")                          # et ainsi de suite : bascule entre les deux états
    assert titres(todo) == {"A"}


def test_undo_annule_aussi_un_restore(todo):
    todo("add", "A"); todo("add", "B"); todo("add", "C")
    todo("restore", "3", "-y")            # retour à {A}
    assert titres(todo) == {"A"}
    todo("undo")
    assert titres(todo) == {"A", "B", "C"}


def test_undo_sans_confirmation_ni_stdin(todo):
    todo("add", "A"); todo("add", "B")
    assert todo("undo", entree="").code == 0


def test_undo_respecte_la_rotation(todo):
    for i in range(8):
        todo("add", f"T{i}")
    for _ in range(4):
        todo("undo")
    assert len(todo.sauvegardes()) <= 5


def test_resume_tronque(todo):
    todo("add", "Base")
    todo.seed(*[dict(cle=f"undo{i:04d}-0", titre=f"Lot{i}") for i in range(8)])
    todo("add", "Dernier")
    todo("reset", entree="y\n")
    r = todo("undo")
    assert "rétablir" in r.texte and "et 5 autre(s)" in r.texte


def test_undo_apres_reset(todo):
    todo("add", "A"); todo("add", "B")
    todo("reset", entree="y\n")
    assert todo.taches() == {}
    r = todo("undo")
    assert r.code == 0 and titres(todo) == {"A", "B"}              # et non {A} : le reset est annulé, pas l'ajout de B
    todo("undo")                                                    # rétablit le reset
    assert todo.taches() == {}


def test_undo_apres_une_modification_hors_programme(todo):
    todo("add", "A"); todo("add", "B")
    todo.seed(dict(cle="hors0001-0", titre="Ajout externe"))        # écrit sans passer par le programme
    r = todo("undo")
    assert r.code == 0 and "retirer 'Ajout externe'" in r.texte
    assert titres(todo) == {"A", "B"}


def test_annuler_un_archivage(todo):
    todo("add", "A"); todo("add", "B")
    todo("done", todo.id_de("A"))
    todo("archive")
    assert titres(todo) == {"B"}
    r = todo("undo")
    assert r.code == 0 and "rétablir 'A'" in r.texte and "(archive)" in r.texte
    assert titres(todo) == {"A", "B"}
    assert todo("archive", "--list", "--format", "json").json() == []


def test_commandes_de_lecture_ne_changent_rien(todo):
    todo("add", "A"); todo("add", "B")
    n = todo.sauvegardes()
    todo("list"); todo("next"); todo("agenda"); todo("stats"); todo("archive", "--list")
    assert todo.sauvegardes() == n
    todo("undo")
    assert titres(todo) == {"A"}


def test_pas_de_couleur_dans_un_pipe(todo):
    todo("add", "A"); todo("add", "B")
    r = todo("undo")
    assert "\x1b" not in r.out
    assert "\x1b[" in todo("undo", "--color", "always").out


def test_dans_l_aide(todo):
    assert "undo" in todo("--help").out and "next" in todo("--help").out
