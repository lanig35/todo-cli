"""Notes des tâches : commande note, option -m (done, undone, postpone, edit, remove), affichage, JSON."""
import pytest

from outils import jour

JOURNAL = {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"}


@pytest.fixture
def une_tache(todo):
    todo("add", "Appeler client")
    return todo, todo.id_de("Appeler client")


def notes_de(todo, titre):
    return todo.une(titre)["notes"]


# ------------------------------------------------------------------ commande note
def test_note_ajoute(une_tache):
    todo, i = une_tache
    r = todo("note", "add", i, "premier", "contact")
    assert r.code == 0 and "Note ajoutée" in r.sortie and "1 au total" in r.sortie
    (n,) = notes_de(todo, "Appeler client")
    assert n["texte"] == "premier contact" and n["action"] == "note"
    assert len(n["date"]) == 16  # AAAA-MM-JJ HH:MM


def test_note_s_accumule_dans_l_ordre(une_tache):
    todo, i = une_tache
    todo("note", "add", i, "un")
    todo("note", "add", i, "deux")
    assert [n["texte"] for n in notes_de(todo, "Appeler client")] == ["un", "deux"]


def test_note_liste_sans_texte(une_tache):
    todo, i = une_tache
    assert "Aucune note" in todo("note", "list", i).sortie
    todo("note", "add", i, "un")
    todo("note", "add", i, "deux")
    sortie = todo("note", "list", i).sortie
    assert sortie.index("un") < sortie.index("deux")


def test_note_json(une_tache):
    todo, i = une_tache
    d = todo("note", "add", i, "salut", "--format", "json").json()
    assert d["titre"] == "Appeler client" and d["total"] == 1 and d["note"]["texte"] == "salut"
    d = todo("note", "list", i, "--format", "json").json()
    assert [n["texte"] for n in d["notes"]] == ["salut"]


def test_note_lecture_ne_modifie_rien(une_tache):
    todo, i = une_tache
    todo("note", "add", i, "x")
    avant = todo.sauvegardes()
    todo("note", "list", i)
    assert todo.sauvegardes() == avant


def test_note_sur_tache_terminee(une_tache):
    todo, i = une_tache
    todo("done", i)
    assert todo("note", "add", i, "après coup").code == 0
    assert notes_de(todo, "Appeler client")[0]["texte"] == "après coup"


def test_note_vide_ou_trop_longue(une_tache):
    todo, i = une_tache
    r = todo("note", "add", i, "   ")
    assert r.code == 1 and "vide" in r.texte
    r = todo("note", "add", i, "x" * 501)
    assert r.code == 1 and "trop longue" in r.texte
    assert todo("note", "add", i, "x" * 500).code == 0
    assert len(notes_de(todo, "Appeler client")) == 1


def test_note_retours_a_la_ligne_reduits(une_tache):
    todo, i = une_tache
    todo("note", "add", i, "a\n\n  b")
    assert notes_de(todo, "Appeler client")[0]["texte"] == "a b"


def test_note_id_inconnu(todo):
    todo("add", "x")
    assert todo("note", "add", "zzz", "texte").code == 1


def test_note_cree_une_sauvegarde_et_undo(une_tache):
    todo, i = une_tache
    avant = len(todo.sauvegardes())
    todo("note", "add", i, "à annuler")
    assert len(todo.sauvegardes()) == avant + 1
    todo("undo")
    assert notes_de(todo, "Appeler client") == []


# ------------------------------------------------------------------ -m sur les autres commandes
def test_done_avec_note(une_tache):
    todo, i = une_tache
    r = todo("done", i, "-m", "validé par Paul")
    assert r.code == 0 and "Note ajoutée" in r.sortie
    t = todo.une("Appeler client")
    assert t["statut"] != "A FAIRE" and t["notes"][0]["texte"] == "validé par Paul" and t["notes"][0]["action"] == "done"


def test_done_note_sur_plusieurs_taches(todo):
    todo("add", "A")
    todo("add", "B")
    todo("done", todo.id_de("A"), todo.id_de("B"), "--note", "lot")
    assert notes_de(todo, "A")[0]["texte"] == "lot" and notes_de(todo, "B")[0]["texte"] == "lot"


def test_done_note_vide_refusee_sans_rien_terminer(une_tache):
    todo, i = une_tache
    r = todo("done", i, "-m", " ")
    assert r.code == 1 and todo.une("Appeler client")["statut"] == "A FAIRE"


def test_done_recurrente_la_note_reste_sur_l_occurrence_terminee(todo):
    todo("add", "Rituel", "--repeat", "weekly", "--due", jour(0))
    todo("done", todo.id_de("Rituel"), "-m", "fait")
    taches = todo.par_titre("Rituel")
    assert len(taches) == 2
    terminee = next(t for t in taches if t["statut"] != "A FAIRE")
    suivante = next(t for t in taches if t["statut"] == "A FAIRE")
    assert [n["texte"] for n in terminee["notes"]] == ["fait"] and suivante["notes"] == []


def test_done_deja_terminee_n_ajoute_pas_de_note(une_tache):
    todo, i = une_tache
    todo("done", i)
    todo("done", i, "-m", "bis")
    assert notes_de(todo, "Appeler client") == []


def test_undone_avec_note(une_tache):
    todo, i = une_tache
    todo("done", i)
    r = todo("task", "undone", i, "-m", "oups")
    assert r.code == 0
    t = todo.une("Appeler client")
    assert t["statut"] == "A FAIRE" and t["notes"][0]["action"] == "undone"


def test_postpone_avec_note(une_tache):
    todo, i = une_tache
    todo("task", "postpone", i, "--to", "+3d", "-m", "client absent")
    t = todo.une("Appeler client")
    assert t["date_echeance"] == jour(3) and t["notes"][0] == {**t["notes"][0], "texte": "client absent", "action": "postpone"}


def test_postpone_sans_changement_pas_de_note(todo):
    todo("add", "X", "--due", jour(3))
    todo("task", "postpone", todo.id_de("X"), "--to", jour(3), "-m", "rien")
    assert notes_de(todo, "X") == []


def test_edit_note_seule(une_tache):
    todo, i = une_tache
    r = todo("task", "edit", i, "-m", "juste une note")
    assert r.code == 0 and "note" in r.sortie
    assert notes_de(todo, "Appeler client")[0]["action"] == "edit"


def test_edit_note_avec_autre_modification(une_tache):
    todo, i = une_tache
    r = todo("task", "edit", i, "--prio", "high", "-m", "urgent")
    assert "priorité" in r.sortie and "note" in r.sortie
    t = todo.une("Appeler client")
    assert t["priorite"] == "high" and len(t["notes"]) == 1


def test_edit_sans_rien_cite_note(une_tache):
    todo, i = une_tache
    r = todo("task", "edit", i)
    assert r.code != 0 or "--note" in r.texte


def test_remove_avec_motif_va_au_journal(une_tache):
    todo, i = une_tache
    r = todo("task", "remove", i, "-m", "doublon de #12", env=JOURNAL)
    assert r.code == 0 and "journal" in r.sortie
    assert todo.par_titre("Appeler client") == []
    ligne = next(l for l in todo.journal() if l.startswith("INFO remove"))
    assert "doublon de #12" in ligne and "Appeler client" in ligne


def test_remove_sans_motif_ne_met_pas_le_titre_au_journal(une_tache):
    todo, i = une_tache
    todo("task", "remove", i, env=JOURNAL)
    assert "Appeler client" not in "\n".join(todo.journal())


# ------------------------------------------------------------------ journal
def test_note_au_journal_sans_le_texte_par_defaut(une_tache):
    todo, i = une_tache
    todo("note", "add", i, "secret", env=JOURNAL)
    ligne = next(l for l in todo.journal() if l.startswith("INFO note"))
    assert "note_len=6" in ligne and "secret" not in ligne


def test_note_au_journal_avec_titres_actifs(une_tache):
    todo, i = une_tache
    todo("note", "add", i, "visible", env={**JOURNAL, "TODO_LOG_TITLES": "true"})
    assert "visible" in next(l for l in todo.journal() if l.startswith("INFO note"))


# ------------------------------------------------------------------ affichage et recherche
def test_show_affiche_les_notes(une_tache):
    todo, i = une_tache
    todo("note", "add", i, "première")
    todo("done", i, "-m", "fini")
    sortie = todo("show", i).sortie
    assert "Notes (2)" in sortie and "première" in sortie and "fini (done)" in sortie
    assert sortie.index("première") < sortie.index("fini")


def test_show_sans_note_n_affiche_pas_la_section(une_tache):
    todo, i = une_tache
    assert "Notes" not in todo("show", i).sortie


def test_list_indicateur_de_notes(une_tache):
    todo, i = une_tache
    assert "📝" not in todo("list").sortie
    todo("note", "add", i, "a")
    todo("note", "add", i, "b")
    assert "📝2" in todo("list").sortie


def test_list_search_cherche_dans_les_notes(une_tache):
    todo, i = une_tache
    todo("add", "Autre")
    todo("note", "add", i, "mot-rare-xyz")
    assert [t["titre"] for t in todo("list", "--search", "rare-xyz", "--format", "json").json()] == ["Appeler client"]


def test_json_des_taches_contient_notes(une_tache):
    todo, i = une_tache
    todo("note", "add", i, "n1")
    for cmde in (("list",), ("next",)):
        d = todo(*cmde, "--format", "json").json()
        d = d if isinstance(d, list) else d.get("taches", d)
        assert d[0]["notes"][0]["texte"] == "n1"


def test_anciennes_taches_sans_notes(todo):
    todo.seed({"cle": "a" * 8, "titre": "ancienne"})
    assert todo.une("ancienne")["notes"] == []
    assert todo("note", "add", "aaaa", "ok").code == 0


def test_notes_corrompues_ignorees(todo):
    import dbm
    import json
    with dbm.open(str(todo.db_dir / "todo_db"), "c") as db:
        db["bbbbbbbb"] = json.dumps({"titre": "t", "notes": ["pas un dict", {"texte": ""}, {"texte": "ok", "date": "2026-01-01 10:00"}]})
    assert [n["texte"] for n in notes_de(todo, "t")] == ["ok"]


# ------------------------------------------------------------------ archivage
def test_notes_suivent_l_archivage(une_tache):
    todo, i = une_tache
    todo("note", "add", i, "à garder")
    todo("done", i)
    todo("archive", "add")
    d = todo("archive", "list", "--format", "json").json()
    assert d[0]["notes"][0]["texte"] == "à garder"
    assert todo("archive", "list", "--search", "garder").sortie.count("Appeler client") >= 1
    todo("archive", "restore", d[0]["id"][:8])
    assert notes_de(todo, "Appeler client")[0]["texte"] == "à garder"


# ------------------------------------------------------------------ modifier et supprimer une note
@pytest.fixture
def trois_notes(une_tache):
    todo, i = une_tache
    for texte in ("un", "deux", "trois"):
        todo("note", "add", i, texte)
    return todo, i


def textes(todo):
    return [n["texte"] for n in notes_de(todo, "Appeler client")]


def test_notes_numerotees(trois_notes):
    todo, i = trois_notes
    sortie = todo("note", "list", i).sortie
    assert "1. " in sortie and "3. " in sortie
    assert "1. " in todo("show", i).sortie


def test_note_edit_remplace_le_texte_et_garde_la_date(trois_notes):
    todo, i = trois_notes
    date = notes_de(todo, "Appeler client")[1]["date"]
    r = todo("note", "edit", i, "2", "deux", "corrigé")
    assert r.code == 0 and "n°2 modifiée" in r.sortie
    assert textes(todo) == ["un", "deux corrigé", "trois"]
    n = notes_de(todo, "Appeler client")[1]
    assert n["date"] == date and n["modifiee"] and n["action"] == "note"
    assert "modifiée" in todo("note", "list", i).sortie


def test_note_edit_garde_l_action_d_origine(une_tache):
    todo, i = une_tache
    todo("done", i, "-m", "ok")
    todo("note", "edit", i, "1", "validé")
    assert notes_de(todo, "Appeler client")[0]["action"] == "done"


def test_note_delete(trois_notes):
    todo, i = trois_notes
    r = todo("note", "delete", i, "1")
    assert r.code == 0 and "supprimée" in r.sortie and "2 au total" in r.sortie
    assert textes(todo) == ["deux", "trois"]


def test_note_delete_derniere_puis_liste_vide(une_tache):
    todo, i = une_tache
    todo("note", "add", i, "seule")
    todo("note", "delete", i, "1")
    assert textes(todo) == [] and "Aucune note" in todo("note", "list", i).sortie


def test_note_edit_delete_json(trois_notes):
    todo, i = trois_notes
    d = todo("note", "edit", i, "3", "nouveau", "--format", "json").json()
    assert d["note"]["texte"] == "nouveau" and d["total"] == 3
    d = todo("note", "delete", i, "2", "--format", "json").json()
    assert d["supprimee"]["texte"] == "deux" and d["total"] == 2


@pytest.mark.parametrize("verbe, args", [("delete", ("0",)), ("delete", ("4",)), ("edit", ("4", "x")), ("edit", ("0", "x"))])
def test_note_numero_invalide(trois_notes, verbe, args):
    todo, i = trois_notes
    r = todo("note", verbe, i, *args)
    assert r.code == 1 and "introuvable" in r.texte and textes(todo) == ["un", "deux", "trois"]


def test_note_numero_sur_tache_sans_note(une_tache):
    todo, i = une_tache
    r = todo("note", "delete", i, "1")
    assert r.code == 1 and "aucune note" in r.texte


def test_note_edit_sans_texte_ou_delete_avec_texte(trois_notes):
    todo, i = trois_notes
    assert todo("note", "edit", i, "1").code == 2                       # le texte est obligatoire
    assert todo("note", "delete", i, "1", "texte").code == 2            # `delete` n'en prend pas
    assert textes(todo) == ["un", "deux", "trois"]


def test_note_edit_texte_invalide_refuse(trois_notes):
    todo, i = trois_notes
    assert todo("note", "edit", i, "1", "x" * 501).code == 1
    assert textes(todo)[0] == "un"


def test_note_edit_delete_sauvegarde_et_undo(trois_notes):
    todo, i = trois_notes
    todo("note", "delete", i, "1")
    todo("undo")
    assert textes(todo) == ["un", "deux", "trois"]
    todo("note", "edit", i, "1", "autre")
    todo("undo")
    assert textes(todo)[0] == "un"


def test_note_edit_delete_au_journal(trois_notes):
    todo, i = trois_notes
    todo("note", "edit", i, "2", "secret", env=JOURNAL)
    todo("note", "delete", i, "1", env=JOURNAL)
    lignes = [l for l in todo.journal() if l.startswith("INFO note")]
    assert any("note_edited=2" in l and "secret" not in l for l in lignes)
    assert any("note_deleted=1" in l for l in lignes)
