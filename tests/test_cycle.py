import pytest

from outils import AUJOURDHUI, ajouter_mois, jour


def test_done_enregistre_la_date_de_completion(todo):
    todo("add", "A")
    r = todo("done", todo.id_de("A"))
    assert r.code == 0 and "validée" in r.texte
    t = todo.une("A")
    assert t["statut"] == "TERMINE" and t["date_terminee"].startswith(jour(0))


def test_done_deja_terminee_n_est_pas_une_erreur(todo):
    todo("add", "A")
    i = todo.id_de("A")
    todo("done", i)
    r = todo("done", i)
    assert r.code == 0 and "déjà terminée" in r.texte


def test_undone(todo):
    todo("add", "A")
    i = todo.id_de("A")
    todo("done", i)
    r = todo("undone", i)
    assert r.code == 0 and "rouverte" in r.texte
    t = todo.une("A")
    assert t["statut"] == "A FAIRE" and t["date_terminee"] is None


def test_prefixe_inconnu_et_ambigu(todo):
    todo.seed(dict(cle="abcd1111-0", titre="A"), dict(cle="abcd2222-0", titre="B"))
    r = todo("done", "zzzz")
    assert r.code == 1 and "Aucun identifiant" in r.texte
    r = todo("done", "abcd")
    assert r.code == 1 and "abcd1111" in r.texte and "abcd2222" in r.texte  # ambigu : candidats listés
    assert all(t["statut"] == "A FAIRE" for t in todo.taches().values())
    assert todo("done", "abcd1").code == 0


def test_show(todo):
    todo("add", "Détail", "--prio", "high", "--due", jour(-2), "--tags", "x,y", "--desc", "Longue description")
    r = todo("show", todo.id_de("Détail"))
    assert r.code == 0
    for attendu in ("Détail", "HIGH", jour(-2), "RETARD", "x", "y", "Longue description"):
        assert attendu in r.texte


def test_edit(todo):
    todo("add", "Ancien", "--due", jour(3), "--tags", "a", "--desc", "d")
    i = todo.id_de("Ancien")
    r = todo("edit", i, "--title", "Nouveau", "--prio", "low", "--due", "demain", "--tags", "b,c", "--desc", "e")
    assert r.code == 0 and "modifiée" in r.texte
    t = todo.une("Nouveau")
    assert (t["priorite"], t["date_echeance"], t["tags"], t["description"]) == ("low", jour(1), ["b", "c"], "e")


def test_edit_efface_les_champs(todo):
    todo("add", "T", "--due", jour(3), "--tags", "a", "--desc", "d", "--repeat", "weekly")
    todo("edit", todo.id_de("T"), "--due", "none", "--tags", "", "--desc", "", "--repeat", "none")
    t = todo.une("T")
    assert (t["date_echeance"], t["tags"], t["description"], t["recurrence"]) == (None, [], "", None)


def test_edit_sans_option(todo):
    todo("add", "T")
    r = todo("edit", todo.id_de("T"))
    assert "modifiée" not in r.texte


def test_edit_valeurs_invalides_ne_modifient_rien(todo):
    todo("add", "T", "--due", jour(3))
    i = todo.id_de("T")
    assert todo("edit", i, "--due", "blabla").code == 1
    assert todo("edit", i, "--title", " ").code == 1
    assert todo.echeance("T") == jour(3) and todo.une("T")["titre"] == "T"


def test_remove(todo):
    todo("add", "A")
    r = todo("remove", todo.id_de("A"))
    assert r.code == 0 and "supprimée" in r.texte
    assert todo.taches() == {}


def test_clear_done(todo):
    todo("add", "A"); todo("add", "B")
    todo("done", todo.id_de("A"))
    r = todo("clear-done")
    assert r.code == 0
    assert [t["titre"] for t in todo.taches().values()] == ["B"]
    assert "Aucune tâche terminée" in todo("clear-done").texte


def test_reset_demande_confirmation(todo):
    todo("add", "A")
    assert "annulée" in todo("reset", entree="n\n").texte
    assert len(todo.taches()) == 1
    todo("reset", entree="y\n")
    assert todo.taches() == {}


# ---------------------------------------------------------------- plusieurs identifiants
def test_done_plusieurs(todo):
    for n in "ABC":
        todo("add", n)
    avant = len(todo.sauvegardes())
    r = todo("done", todo.id_de("A"), todo.id_de("B"))
    assert r.code == 0
    st = {t["titre"]: t["statut"] for t in todo.taches().values()}
    assert st == {"A": "TERMINE", "B": "TERMINE", "C": "A FAIRE"}
    assert len(todo.sauvegardes()) == min(5, avant + 1)  # une seule sauvegarde pour le lot


def test_lot_avec_echec_traite_les_autres(todo):
    todo("add", "A"); todo("add", "B")
    r = todo("done", todo.id_de("A"), "zzzz", todo.id_de("B"))
    assert r.code == 1 and "Bilan" in r.texte and "1 échec" in r.texte
    assert all(t["statut"] == "TERMINE" for t in todo.taches().values())


def test_remove_plusieurs_avec_doublon(todo):
    for n in "ABC":
        todo("add", n)
    a = todo.id_de("A")
    r = todo("remove", a, a[:6], todo.id_de("B"))
    assert r.code == 0
    assert [t["titre"] for t in todo.taches().values()] == ["C"]


def test_doublon_ne_cree_qu_une_occurrence(todo):
    todo("add", "R", "--repeat", "daily")
    i = todo.id_de("R")
    todo("done", i, i)
    assert len(todo.par_titre("R", "A FAIRE")) == 1


def test_lot_ambigu_ne_modifie_rien_pour_cet_id(todo):
    todo.seed(dict(cle="abcd1111-0", titre="A"), dict(cle="abcd2222-0", titre="B"), dict(cle="ffff0000-0", titre="C"))
    r = todo("remove", "abcd", "ffff")
    assert r.code == 1
    assert {t["titre"] for t in todo.taches().values()} == {"A", "B"}


# ---------------------------------------------------------------- récurrence
def prochaine(due, pas_mois=None, pas_jours=None):
    """Occurrence suivante : au moins un pas après l'échéance d'origine, et strictement après aujourd'hui."""
    from datetime import timedelta, date
    origine = date.fromisoformat(due)
    k = 1
    while True:
        d = ajouter_mois(origine, k * pas_mois) if pas_mois else origine + timedelta(days=k * pas_jours)
        if d > AUJOURDHUI:
            return d.strftime("%Y-%m-%d")
        k += 1


@pytest.mark.parametrize("regle, due, attendu", [
    ("1d", jour(-3), prochaine(jour(-3), pas_jours=1)),
    ("1w", jour(-10), prochaine(jour(-10), pas_jours=7)),
    ("2w", jour(-1), prochaine(jour(-1), pas_jours=14)),
    ("3d", jour(5), prochaine(jour(5), pas_jours=3)),
    ("1d", jour(0), jour(1)),
    ("1d", jour(1), jour(2)),   # terminée avant l'échéance : on saute à l'occurrence suivante
    ("1m", AUJOURDHUI.replace(day=15).strftime("%Y-%m-%d"), None),
])
def test_prochaine_occurrence(todo, regle, due, attendu):
    todo.seed(dict(cle="rrrr0001-0", titre="R", echeance=due, recurrence=regle, priorite="high", tags=["t"],
                   description="desc"))
    r = todo("done", "rrrr0001")
    assert r.code == 0 and "Prochaine occurrence" in r.texte
    nouvelle = todo.une("R", "A FAIRE")
    if attendu:
        assert nouvelle["date_echeance"] == attendu
    assert nouvelle["date_echeance"] > jour(0)
    assert (nouvelle["priorite"], nouvelle["tags"], nouvelle["description"], nouvelle["recurrence"]) == \
        ("high", ["t"], "desc", regle)
    assert todo.une("R", "TERMINE")["suivante"] == nouvelle["id"]


def test_recurrence_mensuelle_et_annuelle(todo):
    todo.seed(dict(cle="rrrr0001-0", titre="M", echeance="2026-01-15", recurrence="1m"),
              dict(cle="rrrr0002-0", titre="Y", echeance="2024-03-10", recurrence="1y"))
    todo("done", "rrrr0001", "rrrr0002")
    assert todo.par_titre("M", "A FAIRE")[0]["date_echeance"] == prochaine("2026-01-15", pas_mois=1)
    assert todo.par_titre("Y", "A FAIRE")[0]["date_echeance"] == prochaine("2024-03-10", pas_mois=12)


def test_undone_supprime_l_occurrence_creee(todo):
    todo("add", "R", "--repeat", "daily")
    todo("done", todo.id_de("R"))
    assert len(todo.taches()) == 2
    todo("undone", todo.id_de("R", "TERMINE"))
    taches = list(todo.taches().values())
    assert len(taches) == 1 and taches[0]["statut"] == "A FAIRE"


def test_undone_refuse_si_la_suivante_est_terminee(todo):
    todo.seed(dict(cle="rrrr0001-0", titre="R", echeance=jour(0), recurrence="1d"))
    todo("done", "rrrr0001")
    suivante = todo.une("R", "A FAIRE")["id"][:8]
    todo("done", suivante)
    nb = len(todo.taches())
    r = todo("undone", "rrrr0001")
    assert len(todo.taches()) == nb
    assert todo.taches()["rrrr0001-0"]["statut"] == "TERMINE"
    assert "rouverte" not in r.texte


def test_remove_n_arrete_pas_la_serie(todo):
    todo("add", "R", "--repeat", "daily")
    todo("done", todo.id_de("R"))
    todo("remove", todo.id_de("R", "A FAIRE"))
    assert todo.par_titre("R", "A FAIRE") == []
