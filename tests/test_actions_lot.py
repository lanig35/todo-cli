"""Actions en lot par filtre : done / undone / postpone / remove / edit visent des tâches choisies par les filtres de `list`."""
import json

from outils import jour


def peupler(todo):
    todo.seed(
        dict(cle="aaa1", titre="Lait", tags=["courses"], echeance=jour(0)),
        dict(cle="aaa2", titre="Pain", tags=["courses", "midi"]),
        dict(cle="bbb1", titre="Rapport", echeance=jour(-10), priorite="high", tags=["pro"]),
        dict(cle="bbb2", titre="Facture", echeance=jour(-3), tags=["pro", "compta"]),
        dict(cle="ccc1", titre="Archivable", statut="TERMINE", terminee=jour(-1) + " 10:00", tags=["courses"]),
    )


def echeances(todo):
    return {t["titre"]: t["date_echeance"] for t in todo.taches().values()}


def statuts(todo):
    return {t["titre"]: t["statut"] for t in todo.taches().values()}


# ------------------------------------------------------------------ done
def test_done_par_tag_ne_prend_que_les_taches_a_faire(todo):
    peupler(todo)
    r = todo("done", "--tag", "courses")
    assert r.code == 0 and "Bilan : 2 tâche(s) validée(s)" in r.sortie
    s = statuts(todo)
    assert s["Lait"] == s["Pain"] == "TERMINE" and s["Rapport"] == "A FAIRE"


def test_done_sans_correspondance_n_est_pas_une_erreur(todo):
    peupler(todo)
    r = todo("done", "--tag", "inconnu")
    assert r.code == 0 and "Aucune tâche ne correspond" in r.sortie
    assert todo.sauvegardes() == []


def test_done_tags_combines_en_et(todo):
    peupler(todo)
    todo("done", "--tag", "pro", "--tag", "compta")
    s = statuts(todo)
    assert s["Facture"] == "TERMINE" and s["Rapport"] == "A FAIRE"


def test_done_filtre_retard_et_priorite(todo):
    peupler(todo)
    todo("done", "--overdue", "--prio", "high")
    s = statuts(todo)
    assert s["Rapport"] == "TERMINE" and s["Facture"] == "A FAIRE"


def test_done_recurrente_cree_une_occurrence_par_tache(todo):
    todo.seed(dict(cle="r1", titre="Releve A", recurrence="weekly", echeance=jour(0), tags=["cpt"]),
              dict(cle="r2", titre="Releve B", recurrence="weekly", echeance=jour(0), tags=["cpt"]))
    r = todo("done", "--tag", "cpt")
    assert r.code == 0 and r.sortie.count("Prochaine occurrence") == 2
    assert len(todo.taches()) == 4


# ------------------------------------------------------------------ postpone
def test_postpone_overdue_vers_demain(todo):
    peupler(todo)
    r = todo("postpone", "--overdue", "--to", "demain")
    assert r.code == 0 and "Bilan : 2 tâche(s) reportée(s)" in r.sortie
    e = echeances(todo)
    assert e["Rapport"] == e["Facture"] == jour(1)
    assert e["Lait"] == jour(0)                      # pas en retard : intacte


def test_postpone_ignore_les_taches_terminees(todo):
    peupler(todo)
    todo("postpone", "--tag", "courses", "--to", "+2d")
    assert echeances(todo)["Archivable"] is None


# ------------------------------------------------------------------ undone / remove / edit
def test_undone_cible_les_taches_terminees(todo):
    peupler(todo)
    r = todo("undone", "--tag", "courses")
    assert r.code == 0 and "Bilan" not in r.sortie and "Archivable" in r.sortie     # une seule tâche : pas de bilan
    assert statuts(todo)["Archivable"] == "A FAIRE"


def test_remove_par_filtre_avec_statut(todo):
    peupler(todo)
    r = todo("remove", "--status", "done")
    assert r.code == 0
    assert "Archivable" not in statuts(todo) and len(todo.taches()) == 4


def test_remove_tout_apres_confirmation_automatique(todo):
    peupler(todo)
    r = todo("remove", "--all", "-y")
    assert r.code == 0 and "Bilan : 5 tâche(s) supprimée(s)" in r.sortie
    assert todo.taches() == {}


def test_edit_ajoute_et_retire_des_tags_en_lot(todo):
    peupler(todo)
    r = todo("task", "edit", "--tag", "pro", "--add-tag", "urgent", "--remove-tag", "compta")
    assert r.code == 0 and "Bilan : 2 tâche(s) modifiée(s)" in r.sortie
    t = {x["titre"]: x["tags"] for x in todo.taches().values()}
    assert t["Rapport"] == ["pro", "urgent"] and t["Facture"] == ["pro", "urgent"]
    assert t["Lait"] == ["courses"]


def test_edit_priorite_en_lot_avec_filtre_not_prio(todo):
    peupler(todo)
    todo("task", "edit", "--tag", "pro", "--prio", "low", "--not-prio", "medium")      # --prio = nouvelle valeur
    p = {x["titre"]: x["priorite"] for x in todo.taches().values()}
    assert p["Rapport"] == "low" and p["Facture"] == "medium"


def test_edit_add_tag_sur_un_identifiant(todo):
    peupler(todo)
    assert todo("task", "edit", "aaa1", "--add-tag", "Maison, urgent").code == 0
    assert todo.une("Lait")["tags"] == ["courses", "maison", "urgent"]
    assert todo("task", "edit", "aaa1", "--remove-tag", "courses").code == 0
    assert todo.une("Lait")["tags"] == ["maison", "urgent"]


def test_edit_tags_et_add_tag_incompatibles(todo):
    peupler(todo)
    r = todo("task", "edit", "aaa1", "--tags", "x", "--add-tag", "y")
    assert r.code == 1 and "ne se combine pas" in r.texte


def test_edit_titre_refuse_en_lot(todo):
    peupler(todo)
    r = todo("task", "edit", "--tag", "pro", "--title", "X")
    assert r.code == 1 and "--title ne s'applique qu'à une seule tâche" in r.texte
    assert todo("task", "edit", "aaa1", "bbb1", "--title", "X").code == 1


def test_edit_sans_modification_demandee_n_interroge_pas(todo):
    peupler(todo)
    r = todo("task", "edit", "--tag", "pro")
    assert r.code == 1 and "Rien à modifier" in r.texte


def test_edit_plusieurs_identifiants(todo):
    peupler(todo)
    r = todo("task", "edit", "aaa1", "bbb1", "--prio", "low")
    assert r.code == 0 and "Bilan : 2 tâche(s) modifiée(s)" in r.sortie


# ------------------------------------------------------------------ garde-fous
def test_sans_identifiant_ni_filtre_la_commande_refuse(todo):
    peupler(todo)
    for commande in ("done", "undone", "postpone", "remove"):
        r = todo(commande)
        assert r.code == 2 and "Indiquez au moins un identifiant, ou un filtre" in r.texte, commande
    assert len(todo.taches()) == 5


def test_identifiants_et_filtres_ne_se_melangent_pas(todo):
    peupler(todo)
    r = todo("done", "aaa1", "--tag", "courses")
    assert r.code == 1 and "pas les deux" in r.texte and statuts(todo)["Lait"] == "A FAIRE"


def test_all_ne_se_combine_pas_avec_un_filtre(todo):
    peupler(todo)
    r = todo("done", "--all", "--tag", "courses")
    assert r.code == 1 and "--all ne se combine pas" in r.texte


def test_all_vise_toutes_les_taches_concernees(todo):
    peupler(todo)
    todo("done", "--all")
    assert set(statuts(todo).values()) == {"TERMINE"}


def test_dry_run_sans_filtre_est_refuse(todo):
    peupler(todo)
    assert todo("done", "aaa1", "--dry-run").code == 1


def test_search_in_exige_search(todo):
    peupler(todo)
    assert todo("done", "--search-in", "notes").code == 1


def test_no_due_et_bornes_incompatibles(todo):
    peupler(todo)
    assert todo("postpone", "--no-due", "--due-before", "demain").code == 1


# ------------------------------------------------------------------ simulation
def test_dry_run_ne_modifie_rien(todo):
    peupler(todo)
    r = todo("postpone", "--overdue", "--dry-run")
    assert r.code == 0 and "2 tâche(s) seraient reportées" in r.sortie
    assert "Rapport" in r.sortie and "Facture" in r.sortie and "Lait" not in r.sortie
    assert echeances(todo)["Rapport"] == jour(-10) and todo.sauvegardes() == []


def test_dry_run_json(todo):
    peupler(todo)
    cibles = todo("done", "--tag", "pro", "--dry-run", "--format", "json").json()
    assert sorted(t["titre"] for t in cibles) == ["Facture", "Rapport"]


def test_dry_run_plain_et_colonnes(todo):
    peupler(todo)
    r = todo("done", "--tag", "pro", "--dry-run", "--format", "plain", "--columns", "id,title")
    lignes = [l.split("\t") for l in r.sortie.splitlines()]
    assert sorted(l[1] for l in lignes) == ["Facture", "Rapport"]


def test_dry_run_vide_dit_qu_il_n_y_a_rien(todo):
    peupler(todo)
    r = todo("done", "--tag", "nada", "--dry-run")
    assert r.code == 0 and "Aucune tâche ne correspond" in r.sortie


def test_dry_run_ne_prend_pas_le_verrou_exclusif_et_ne_declenche_pas_l_archivage(todo):
    peupler(todo)
    todo.config("[archive]\nauto_days = 1\n")
    todo("done", "--tag", "pro", "--dry-run")
    assert todo.sauvegardes() == []


# ------------------------------------------------------------------ confirmation
def seed_six(todo):
    todo.seed(*[dict(cle=f"k{i}", titre=f"T{i}", tags=["lot"]) for i in range(6)])


def test_lot_de_cinq_taches_ou_plus_demande_y_sans_terminal(todo):
    seed_six(todo)
    r = todo("done", "--tag", "lot")
    assert r.code == 1 and "ajoutez -y" in r.texte
    assert set(statuts(todo).values()) == {"A FAIRE"}


def test_option_y_confirme_le_lot(todo):
    seed_six(todo)
    r = todo("done", "--tag", "lot", "-y")
    assert r.code == 0 and "Bilan : 6 tâche(s) validée(s)" in r.sortie


def test_sous_le_seuil_aucune_confirmation(todo):
    todo.seed(*[dict(cle=f"k{i}", titre=f"T{i}", tags=["lot"]) for i in range(4)])
    assert todo("done", "--tag", "lot").code == 0


def test_seuil_reglable(todo):
    seed_six(todo)
    assert todo("done", "--tag", "lot", env={"TODO_BATCH_CONFIRM": "7"}).code == 0


def test_seuil_zero_ne_demande_jamais(todo):
    seed_six(todo)
    assert todo("done", "--tag", "lot", env={"TODO_BATCH_CONFIRM": "0"}).code == 0


def test_reponse_oui_dans_un_terminal(todo):
    seed_six(todo)
    import fcntl, os, pty, subprocess, sys, time
    from outils import SCRIPT
    maitre, esclave = pty.openpty()
    p = subprocess.Popen([sys.executable, "-B", str(SCRIPT), "done", "--tag", "lot"], stdin=esclave, stdout=esclave,
                         stderr=esclave, env=todo._env(None), cwd=todo.dossier, start_new_session=True)
    os.close(esclave)
    time.sleep(1.5)
    os.write(maitre, b"y\n")
    assert p.wait(timeout=20) == 0
    os.close(maitre)
    assert set(statuts(todo).values()) == {"TERMINE"}


def test_reponse_non_dans_un_terminal(todo):
    seed_six(todo)
    import os, pty, subprocess, sys, time
    from outils import SCRIPT
    maitre, esclave = pty.openpty()
    p = subprocess.Popen([sys.executable, "-B", str(SCRIPT), "done", "--tag", "lot"], stdin=esclave, stdout=esclave,
                         stderr=esclave, env=todo._env(None), cwd=todo.dossier, start_new_session=True)
    os.close(esclave)
    time.sleep(1.5)
    os.write(maitre, b"n\n")
    assert p.wait(timeout=20) == 0
    os.close(maitre)
    assert set(statuts(todo).values()) == {"A FAIRE"}


def test_la_confirmation_ne_concerne_pas_les_identifiants_explicites(todo):
    seed_six(todo)
    assert todo("done", *[f"k{i}" for i in range(6)]).code == 0


# ------------------------------------------------------------------ cohérence
def test_un_seul_undo_pour_tout_le_lot(todo):
    peupler(todo)
    todo("add", "Initiale")                       # une première modification : sinon `undo` n'a pas d'état antérieur
    todo("postpone", "--overdue", "--to", "+5d")
    assert len(todo.sauvegardes()) == 2
    assert todo("undo").code == 0
    e = echeances(todo)
    assert e["Rapport"] == jour(-10) and e["Facture"] == jour(-3)


def test_le_lot_est_journalise_avec_le_nombre_de_taches(todo):
    peupler(todo)
    todo("done", "--tag", "courses", env={"TODO_LOG_TARGET": "file"})
    assert any("selection=filter" in l and "count=2" in l for l in todo.journal())


def test_syntaxe_ancienne_et_nouvelle_equivalentes(todo):
    peupler(todo)
    assert todo("task", "done", "--tag", "pro").code == 0
    assert todo("done", "--tag", "courses").code == 0


def test_json_du_bilan_inchange_pour_un_identifiant(todo):
    peupler(todo)
    r = todo("done", "aaa1")
    assert r.code == 0 and "Bilan" not in r.sortie


def test_la_selection_est_figee_avant_toute_modification(todo):
    """done sur un lot récurrent ne doit pas rattraper les occurrences qu'il crée lui-même."""
    todo.seed(dict(cle="r1", titre="Releve", recurrence="daily", echeance=jour(-2), tags=["cpt"]))
    todo("done", "--tag", "cpt")
    t = todo.taches()
    assert len(t) == 2 and sorted(x["statut"] for x in t.values()) == ["A FAIRE", "TERMINE"]


def test_filtre_bloque_et_pret(todo):
    todo.seed(dict(cle="p1", titre="Parent"), dict(cle="e1", titre="Enfant", apres=["p1"]))
    r = todo("postpone", "--blocked", "--dry-run", "--format", "json").json()
    assert [t["titre"] for t in r] == ["Enfant"]
    r = todo("postpone", "--ready", "--dry-run", "--format", "json").json()
    assert [t["titre"] for t in r] == ["Parent"]


def test_recherche_texte_en_lot(todo):
    peupler(todo)
    todo("remove", "--search", "FACTURE")                   # sans accent ni casse
    assert "Facture" not in statuts(todo)
