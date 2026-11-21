"""Rapports : report tags, blocked, overdue, stale, done (text, table, plain, json)."""
import pytest

from outils import jour


def tache(**champs):
    """Tâche de test, créée hier sauf indication contraire (le défaut du seed date de janvier : trop ancien)."""
    champs.setdefault("creation", jour(-1) + " 09:00")
    return champs


def peupler(todo):
    todo.seed(
        tache(cle="aaa1", titre="Lait", tags=["courses"], echeance=jour(0), creation=jour(-2) + " 09:00"),
        tache(cle="aaa2", titre="Pain", tags=["courses", "midi"], creation=jour(-60) + " 09:00"),
        tache(cle="bbb1", titre="Rapport", echeance=jour(-10), priorite="high", tags=["pro"]),
        tache(cle="bbb2", titre="Facture", echeance=jour(-3), tags=["pro", "compta"]),
        tache(cle="ccc1", titre="Fini hier", statut="TERMINE", terminee=jour(-1) + " 10:00", tags=["courses"]),
        tache(cle="ccc2", titre="Fini il y a 3 semaines", statut="TERMINE", terminee=jour(-21) + " 18:30", tags=["pro"]),
        tache(cle="ddd1", titre="Livraison", apres=["aaa1"]),
        tache(cle="ddd2", titre="Montage", apres=["aaa1", "bbb1"], priorite="high"),
        tache(cle="ddd3", titre="Libre", apres=["ccc1"]),          # sa dépendance est terminée : pas bloquée
    )


def plain(todo, *args):
    return [l.split("\t") for l in todo(*args, "--format", "plain").sortie.splitlines()]


# ------------------------------------------------------------------ tags
def test_tags_plain_trie_par_nombre_puis_nom(todo):
    peupler(todo)
    assert plain(todo, "report", "tags") == [
        ["courses", "2", "1", "3"], ["pro", "2", "1", "3"], ["compta", "1", "0", "1"], ["midi", "1", "0", "1"]]


def test_tags_tri_alphabetique(todo):
    peupler(todo)
    assert [l[0] for l in plain(todo, "report", "tags", "--sort", "alpha")] == ["compta", "courses", "midi", "pro"]


def test_tags_json(todo):
    peupler(todo)
    r = todo("report", "tags", "--format", "json").json()
    assert r["avec_archive"] is False and r["sans_tag"] == {"a_faire": 3, "terminees": 0}
    assert r["tags"][0] == {"tag": "courses", "a_faire": 2, "terminees": 1, "total": 3}


def test_tags_avec_archive(todo):
    peupler(todo)
    todo("archive", "add")
    assert plain(todo, "report", "tags")[0][:3] == ["courses", "2", "0"]
    assert plain(todo, "report", "tags", "--with-archive")[0][:3] == ["courses", "2", "1"]


def test_tags_table_et_text(todo):
    peupler(todo)
    t = todo("report", "tags", "--format", "table").sortie
    assert "TAG" in t and "TERMINÉES" in t and "compta" in t
    x = todo("report", "tags").sortie
    assert "#courses" in x and "4 tag(s)" in x and "sans tag : 3" in x


def test_tags_vide(todo):
    assert todo("report", "tags", "--format", "plain").sortie == ""
    assert "Aucun tag" in todo("report", "tags", "--format", "table").sortie
    assert todo("report", "tags", "--format", "json").json()["tags"] == []


# ------------------------------------------------------------------ blocked
def test_blocked_liste_ce_qui_est_attendu(todo):
    peupler(todo)
    r = todo("report", "blocked").sortie
    assert "Livraison" in r and "Montage" in r and "Libre" not in r
    assert "attend : Lait" in r and "attend : Rapport" in r and "2 tâche(s) bloquée(s)" in r


def test_blocked_plain_donne_les_identifiants_bloquants(todo):
    peupler(todo)
    lignes = {l[2]: l for l in plain(todo, "report", "blocked")}
    assert lignes["Livraison"][3] == "aaa1"
    assert lignes["Montage"][3] == "aaa1,bbb1" and lignes["Montage"][1] == "high"


def test_blocked_json(todo):
    peupler(todo)
    r = todo("report", "blocked", "--format", "json").json()
    assert r["total"] == 2
    montage = next(t for t in r["taches"] if t["titre"] == "Montage")
    assert montage["bloquee_par"] == ["aaa1", "bbb1"]
    assert [a["titre"] for a in montage["attend"]] == ["Lait", "Rapport"]


def test_blocked_table_titres_des_bloquants(todo):
    peupler(todo)
    t = todo("report", "blocked", "--format", "table").sortie
    assert "ATTEND" in t and "Lait, Rapport" in t


def test_blocked_vide(todo):
    todo("add", "Seule")
    assert "Aucune tâche bloquée" in todo("report", "blocked").sortie
    assert todo("report", "blocked", "--format", "plain").sortie == ""


def test_blocked_dependance_terminee_libere(todo):
    peupler(todo)
    todo("done", "aaa1")
    assert [l[2] for l in plain(todo, "report", "blocked")] == ["Montage"]


# ------------------------------------------------------------------ overdue
def test_overdue_les_plus_en_retard_d_abord(todo):
    peupler(todo)
    lignes = plain(todo, "report", "overdue")
    assert [(l[1], l[4]) for l in lignes] == [("10", "Rapport"), ("3", "Facture")]
    assert lignes[0][2] == "high" and lignes[0][3] == jour(-10)


def test_overdue_ignore_aujourd_hui_et_les_terminees(todo):
    peupler(todo)
    todo.seed(dict(cle="eee1", titre="Terminée en retard", statut="TERMINE", echeance=jour(-5)))
    titres = [l[4] for l in plain(todo, "report", "overdue")]
    assert "Lait" not in titres and "Terminée en retard" not in titres


def test_overdue_json(todo):
    peupler(todo)
    r = todo("report", "overdue", "--format", "json").json()
    assert r["total"] == 2 and r["date"] == jour(0)
    assert [(t["titre"], t["jours_retard"]) for t in r["taches"]] == [("Rapport", 10), ("Facture", 3)]


def test_overdue_text_et_table(todo):
    peupler(todo)
    x = todo("report", "overdue").sortie
    assert "[10 j.]" in x and "2 tâche(s) en retard" in x
    t = todo("report", "overdue", "--format", "table").sortie
    assert "RETARD (J)" in t and "Rapport" in t


def test_overdue_vide(todo):
    todo("add", "Rien")
    assert "Aucune tâche en retard" in todo("report", "overdue").sortie


# ------------------------------------------------------------------ stale
def test_stale_sans_echeance_et_anciennes(todo):
    peupler(todo)
    lignes = plain(todo, "report", "stale")                       # défaut : 30 jours
    assert [(l[1], l[3]) for l in lignes] == [("60", "Pain")]


def test_stale_duree_reglable(todo):
    peupler(todo)
    titres = [l[3] for l in plain(todo, "report", "stale", "--older-than", "1w")]
    assert titres[0] == "Pain" and "Lait" not in titres           # Lait a une échéance ; Pain seul est assez ancien


def test_stale_ignore_les_taches_avec_echeance_et_terminees(todo):
    todo.seed(dict(cle="s1", titre="Avec échéance", echeance=jour(5), creation=jour(-90) + " 08:00"),
              dict(cle="s2", titre="Terminée", statut="TERMINE", creation=jour(-90) + " 08:00"))
    assert plain(todo, "report", "stale") == []


def test_stale_json(todo):
    peupler(todo)
    r = todo("report", "stale", "--format", "json").json()
    assert r["avant"] == jour(-30) and r["total"] == 1 and r["taches"][0]["age_jours"] == 60


def test_stale_duree_invalide(todo):
    r = todo("report", "stale", "--older-than", "bientôt")
    assert r.code == 1 and "--older-than" in r.texte


def test_stale_refuse_une_date_future(todo):
    assert todo("report", "stale", "--older-than", "demain").code == 1


def test_stale_text(todo):
    peupler(todo)
    x = todo("report", "stale").sortie
    assert "Pain" in x and "créée il y a 60 j." in x


# ------------------------------------------------------------------ done
def test_done_par_defaut_sept_jours(todo):
    peupler(todo)
    lignes = plain(todo, "report", "done")
    assert [(l[0][:10], l[3]) for l in lignes] == [(jour(-1), "Fini hier")]


def test_done_since_et_ordre_recent_d_abord(todo):
    peupler(todo)
    lignes = plain(todo, "report", "done", "--since", "1m")
    assert [l[3] for l in lignes] == ["Fini hier", "Fini il y a 3 semaines"]


def test_done_until(todo):
    peupler(todo)
    lignes = plain(todo, "report", "done", "--since", "1m", "--until", "2w")
    assert [l[3] for l in lignes] == ["Fini il y a 3 semaines"]


def test_done_plage_vide(todo):
    r = todo("report", "done", "--since", "1d", "--until", "1w")
    assert r.code == 1 and "Plage vide" in r.texte


def test_done_date_invalide_ou_future(todo):
    assert todo("report", "done", "--since", "demain").code == 1
    assert todo("report", "done", "--since", "n'importe quoi").code == 1


def test_done_avec_archive(todo):
    peupler(todo)
    todo("archive", "add")
    assert plain(todo, "report", "done") == []
    assert [l[3] for l in plain(todo, "report", "done", "--with-archive")] == ["Fini hier"]


def test_done_json(todo):
    peupler(todo)
    r = todo("report", "done", "--since", "30d", "--format", "json").json()
    assert r["total"] == 2 and r["depuis"] == jour(-30) and r["jusqu_a"] == jour(0)
    assert [j["date"] for j in r["jours"]] == [jour(-1), jour(-21)]
    assert r["jours"][0]["taches"][0]["titre"] == "Fini hier"


def test_done_text_regroupe_par_jour(todo):
    peupler(todo)
    x = todo("report", "done", "--since", "1m").sortie
    assert "Fini hier" in x and "Fini il y a 3 semaines" in x
    assert "2 tâche(s) terminée(s)" in x and "2 jour(s) actif(s)" in x


def test_done_table_et_vide(todo):
    peupler(todo)
    assert "TERMINÉE" in todo("report", "done", "--format", "table").sortie
    todo("report", "done", "--since", "aujourd'hui")
    assert "Aucune tâche terminée" in todo("report", "done", "--since", "aujourd'hui").sortie


# ------------------------------------------------------------------ transverse
@pytest.mark.parametrize("rapport", ["tags", "blocked", "overdue", "stale", "done"])
def test_les_rapports_ne_modifient_rien(todo, rapport):
    peupler(todo)
    avant = todo("list", "--format", "json").out
    for fmt in ("text", "table", "plain", "json"):
        assert todo("report", rapport, "--format", fmt).code == 0
    assert todo("list", "--format", "json").out == avant and todo.sauvegardes() == []


@pytest.mark.parametrize("rapport", ["tags", "blocked", "overdue", "stale", "done"])
def test_les_rapports_sont_vides_sur_une_base_neuve(todo, rapport):
    assert todo("report", rapport, "--format", "plain").sortie == ""
    assert todo("report", rapport).code == 0


def test_les_rapports_respectent_le_pager_et_la_couleur(todo):
    peupler(todo)
    r = todo("report", "overdue", "--no-pager", "--color", "always")
    assert r.code == 0 and "\x1b[" in r.out
    assert "\x1b[" not in todo("report", "overdue", "--color", "never").out


def test_rapports_listes_dans_l_aide(todo):
    r = todo("report", "--help").sortie
    for nom in ("tags", "blocked", "overdue", "stale", "done"):
        assert nom in r


def test_les_rapports_prennent_un_verrou_partage(todo):
    """Deux rapports peuvent tourner en même temps : ils ne s'excluent pas."""
    peupler(todo)
    import subprocess, sys
    from outils import SCRIPT
    procs = [subprocess.Popen([sys.executable, "-B", str(SCRIPT), "report", "overdue", "--format", "plain"],
                              stdout=subprocess.PIPE, text=True, env=todo._env(None), cwd=todo.dossier) for _ in range(3)]
    assert [p.wait(timeout=30) for p in procs] == [0, 0, 0]
