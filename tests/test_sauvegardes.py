def test_rotation_garde_cinq_sauvegardes(todo):
    for i in range(8):
        todo("add", f"T{i}")
    assert len(todo.sauvegardes()) == 5


def test_liste_des_sauvegardes(todo):
    todo("add", "A"); todo("add", "B")
    r = todo("restore")
    assert r.code == 0
    assert "1." in r.texte and "2." in r.texte and "2 tâche(s)" in r.texte and "1 tâche(s)" in r.texte
    assert "Restaurer : todo restore" in r.texte


def test_restore_sans_sauvegarde(todo):
    r = todo("restore")
    assert r.code == 0 and "Aucune sauvegarde" in r.texte


def test_restore_avec_confirmation(todo):
    todo("add", "A"); todo("add", "B")
    todo("restore", "2", entree="n\n")
    assert len(todo.taches()) == 2
    r = todo("restore", "2", "-y")
    assert r.code == 0 and "restaurée" in r.texte
    assert [t["titre"] for t in todo.taches().values()] == ["A"]


def test_restore_est_annulable(todo):
    todo("add", "A"); todo("add", "B")
    todo("restore", "2", "-y")                 # retour à {A} ; l'état {A, B} est sauvegardé en n°2
    assert len(todo.taches()) == 1
    todo("restore", "2", "-y")
    assert {t["titre"] for t in todo.taches().values()} == {"A", "B"}


def test_restore_numero_invalide(todo):
    todo("add", "A")
    for n in ("99", "0"):
        assert "invalide" in todo("restore", n, "-y").texte
    assert len(todo.taches()) == 1


def test_reset_sauvegarde_avant_de_vider(todo):
    todo("add", "A")
    todo("reset", entree="y\n")
    assert todo.taches() == {}
    todo("restore", "1", "-y")
    assert [t["titre"] for t in todo.taches().values()] == ["A"]


def test_pas_de_sauvegarde_sans_modification(todo):
    todo("add", "A")
    n = todo.sauvegardes()
    todo("list"); todo("stats"); todo("show", todo.id_de("A"))
    assert todo.sauvegardes() == n
