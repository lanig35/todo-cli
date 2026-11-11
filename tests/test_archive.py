import os

import pytest

from outils import jour


@pytest.fixture
def garni(todo):
    todo.seed(
        dict(cle="arch0001-0", titre="Vieille", statut="TERMINE", terminee=jour(-40) + " 10:00", tags=["pro"],
             description="vieux dossier"),
        dict(cle="arch0002-0", titre="Moyenne", statut="TERMINE", terminee=jour(-10) + " 10:00"),
        dict(cle="arch0003-0", titre="Recente", statut="TERMINE", terminee=jour(0) + " 08:00"),
        dict(cle="arch0004-0", titre="Sans-date", statut="TERMINE", terminee=None),
        dict(cle="arch0005-0", titre="Active", echeance=jour(2)),
    )
    return todo


def titres(todo):
    return {t["titre"] for t in todo.taches().values()}


def archives(todo):
    return {t["titre"]: t for t in todo("archive", "--list", "--format", "json").json()}


def test_archiver_tout_ce_qui_est_termine(garni):
    r = garni("archive")
    assert r.code == 0 and "4 tâche(s) archivée(s)" in r.texte
    assert titres(garni) == {"Active"}
    assert set(archives(garni)) == {"Vieille", "Moyenne", "Recente", "Sans-date"}


def test_archives_invisibles_ailleurs(garni):
    garni("archive")
    assert "Vieille" not in garni("list").texte
    assert "Vieille" not in garni("agenda", "--days", "60").texte
    assert "1 tâche(s) au total" in garni("stats").texte


@pytest.mark.parametrize("duree, attendus", [
    ("30d", {"Vieille"}),
    ("1w", {"Vieille", "Moyenne"}),
    ("1m", {"Vieille"}),
    ("1y", set()),
    ("0d", None),
])
def test_older_than(garni, duree, attendus):
    r = garni("archive", "--older-than", duree)
    if attendus is None:
        assert r.code == 1 and "Durée non reconnue" in r.texte
        return
    assert r.code == 0
    assert set(archives(garni)) == attendus
    assert "Sans-date" in titres(garni)                       # âge inconnu : jamais archivée par ancienneté
    if attendus:
        assert "sans date de complétion" in r.texte


def test_older_than_borne_incluse(todo):
    todo.seed(dict(cle="arch0001-0", titre="Pile", statut="TERMINE", terminee=jour(-30) + " 23:59"),
              dict(cle="arch0002-0", titre="Presque", statut="TERMINE", terminee=jour(-29) + " 00:01"))
    todo("archive", "--older-than", "30d")
    assert set(archives(todo)) == {"Pile"}


@pytest.mark.parametrize("duree", ["abc", "30", "d", "1.5w", "3x", ""])
def test_older_than_invalide(garni, duree):
    r = garni("archive", "--older-than", duree)
    assert r.code == 1 and "Durée non reconnue" in r.texte
    assert len(titres(garni)) == 5


def test_older_than_negatif_invalide(garni):
    r = garni("archive", "--older-than=-5d")
    assert r.code == 1 and "Durée non reconnue" in r.texte


def test_rien_a_archiver(todo):
    todo("add", "A")
    r = todo("archive")
    assert r.code == 0 and "Aucune tâche terminée" in r.texte
    assert todo("archive", "--older-than", "1d").code == 0


def test_base_vide(todo):
    r = todo("archive")
    assert r.code == 0 and "rien à archiver" in r.texte


def test_archiver_par_identifiant(garni):
    r = garni("archive", "arch0001", "arch0002")
    assert r.code == 0 and "Bilan : 2 tâche(s) archivée(s)" in r.texte
    assert set(archives(garni)) == {"Vieille", "Moyenne"}
    assert titres(garni) == {"Recente", "Sans-date", "Active"}


def test_tache_non_terminee_refusee(garni):
    r = garni("archive", "arch0005", "arch0003")
    assert r.code == 1 and "n'est pas terminée" in r.texte and "1 échec" in r.texte
    assert "Active" in titres(garni)                          # reste dans la liste
    assert set(archives(garni)) == {"Recente"}                # l'autre est archivée quand même


def test_identifiant_inconnu(garni):
    r = garni("archive", "zzzz")
    assert r.code == 1 and "Aucun identifiant" in r.texte
    assert archives(garni) == {}


def test_identifiant_ambigu_et_doublon(todo):
    todo.seed(dict(cle="abcd1111-0", titre="A", statut="TERMINE"), dict(cle="abcd2222-0", titre="B", statut="TERMINE"))
    assert todo("archive", "abcd").code == 1
    assert titres(todo) == {"A", "B"}
    r = todo("archive", "abcd1", "abcd1111")
    assert r.code == 0 and set(archives(todo)) == {"A"}


def test_ids_et_older_than_incompatibles(garni):
    r = garni("archive", "arch0001", "--older-than", "1d")
    assert r.code == 1 and "pas les deux" in r.texte
    assert len(titres(garni)) == 5


def test_date_archivage_enregistree(garni):
    garni("archive", "arch0001")
    t = archives(garni)["Vieille"]
    assert t["date_archivage"].startswith(jour(0))
    assert t["date_terminee"].startswith(jour(-40)) and t["tags"] == ["pro"]


# ---------------------------------------------------------------- consulter
def test_archive_vide(todo):
    assert "L'archive est vide" in todo("archive", "--list").texte
    assert todo("archive", "--list", "--format", "json").json() == []


def test_lister_archive(garni):
    garni("archive")
    r = garni("archive", "--list").texte
    assert "ARCHIVE" in r and "4 tâche(s) archivée(s)" in r and "(id: arch0001)" in r
    assert f"terminée le {jour(-40)}" in r and f"archivée le {jour(0)}" in r and "#pro" in r
    assert "Active" not in r
    # plus récemment terminée d'abord, sans date en dernier
    assert r.index("Recente") < r.index("Moyenne") < r.index("Vieille") < r.index("Sans-date")


@pytest.mark.parametrize("texte, attendus", [
    ("vieux", {"Vieille"}), ("PRO", {"Vieille"}), ("moyenne", {"Moyenne"}), ("e", {"Vieille", "Moyenne", "Recente", "Sans-date"}),
    ("introuvable", set()),
])
def test_rechercher_dans_l_archive(garni, texte, attendus):
    garni("archive")
    r = garni("archive", "--search", texte, "--format", "json")
    assert {t["titre"] for t in r.json()} == attendus


def test_search_implique_list(garni):
    garni("archive", "arch0001")
    assert "Vieille" in garni("archive", "--search", "vieille").texte
    assert titres(garni) == {"Moyenne", "Recente", "Sans-date", "Active"}   # rien n'a été archivé de plus


def test_list_incompatible_avec_ids(garni):
    assert garni("archive", "--list", "arch0001").code == 1
    assert garni("archive", "--list", "--older-than", "1d").code == 1


def test_lister_ne_cree_pas_de_sauvegarde(garni):
    garni("archive", "arch0001")
    avant = garni.sauvegardes()
    garni("archive", "--list")
    assert garni.sauvegardes() == avant


# ---------------------------------------------------------------- récupérer
def test_unarchive(garni):
    garni("archive")
    r = garni("unarchive", "arch0001")
    assert r.code == 0 and "Tâche récupérée" in r.texte
    t = garni.une("Vieille")
    assert t["statut"] == "TERMINE" and t["date_terminee"].startswith(jour(-40))
    assert "date_archivage" not in t
    assert "Vieille" not in archives(garni)


def test_unarchive_plusieurs_et_echec(garni):
    garni("archive")
    r = garni("unarchive", "arch0001", "zzzz", "arch0002")
    assert r.code == 1 and "Bilan" in r.texte and "1 échec" in r.texte
    assert {"Vieille", "Moyenne"} <= titres(garni)


def test_unarchive_sans_archive(todo):
    r = todo("unarchive", "abcd")
    assert r.code == 1 and "archive est vide" in r.texte


def test_unarchive_id_d_une_tache_non_archivee(garni):
    garni("archive", "arch0001")
    r = garni("unarchive", "arch0005")
    assert r.code == 1 and "Aucun identifiant" in r.texte


def test_unarchive_refuse_un_doublon(garni):
    garni("archive", "arch0001")
    garni.seed(dict(cle="arch0001-0", titre="Doublon"))      # même identifiant réapparu dans la liste
    r = garni("unarchive", "arch0001")
    assert r.code == 1 and "déjà cet identifiant" in r.texte
    assert "Vieille" in archives(garni)                      # elle reste archivée


def test_cycle_complet_et_recurrence(todo):
    todo("add", "R", "--repeat", "daily")
    todo("done", todo.id_de("R"))
    todo("archive")
    assert todo.par_titre("R", "A FAIRE") != []              # l'occurrence suivante reste active
    assert todo.par_titre("R", "TERMINE") == []
    todo("unarchive", [t["id"][:8] for t in todo("archive", "--list", "--format", "json").json()][0])
    assert len(todo.par_titre("R", "TERMINE")) == 1


# ---------------------------------------------------------------- stats
def test_stats_avec_archive(garni):
    garni("archive")
    sans = garni("stats").texte
    avec = garni("stats", "--with-archive").texte
    assert "1 tâche(s) au total" in sans and "dont" not in sans
    assert "5 tâche(s) au total" in avec and "dont 4 archivée(s)" in avec and "80% terminées (4/5)" in avec
    assert "1 terminée(s) aujourd'hui" in avec


def test_stats_avec_archive_base_principale_vide(todo):
    todo.seed(dict(cle="arch0001-0", titre="A", statut="TERMINE", terminee=jour(0) + " 08:00"))
    todo("archive")
    assert todo("stats").texte.count("Aucune statistique") == 1
    assert "1 tâche(s) au total" in todo("stats", "--with-archive").texte


# ---------------------------------------------------------------- sauvegardes
def fichiers_archive(dossier):
    return [f for f in os.listdir(dossier) if f.startswith("todo_archive")]


def test_la_sauvegarde_contient_l_archive(garni):
    garni("archive")
    derniere = garni.db_dir / "backups" / garni.sauvegardes()[-1]
    assert fichiers_archive(derniere)


def test_restore_ramene_aussi_l_archive(garni):
    avant = garni.sauvegardes()
    garni("archive", "arch0001")                    # sauvegarde S1 : état après archivage
    garni("unarchive", "arch0001")                  # S2 : tâche revenue dans la liste, archive vide
    garni("archive", "arch0002")                    # S3 : Moyenne archivée
    assert set(archives(garni)) == {"Moyenne"}
    # n°1 = S3 (état actuel), n°2 = S2, n°3 = S1
    r = garni("restore", "3", "-y")
    assert r.code == 0
    assert set(archives(garni)) == {"Vieille"}
    assert "Vieille" not in titres(garni) and "Moyenne" in titres(garni)
    assert not (set(titres(garni)) & set(archives(garni)))   # jamais dans les deux à la fois


def test_restore_ancienne_sauvegarde_sans_archive(todo):
    todo.seed(dict(cle="arch0001-0", titre="A", statut="TERMINE"))
    todo("add", "B")                                # S1 : aucune archive
    todo("archive")
    assert set(archives(todo)) == {"A"}
    # la sauvegarde n°2 (avant archivage) n'a pas de fichier d'archive : l'archive redevient vide
    todo("restore", "2", "-y")
    assert archives(todo) == {} and "A" in titres(todo)


def test_restore_est_reversible_avec_l_archive(garni):
    garni("add", "Z")                               # S1 : avant archivage (pas d'archive)
    garni("archive")                                # S2
    garni("restore", "2", "-y")                     # retour à S1 ; l'état S2 est mis de côté
    assert archives(garni) == {} and len(titres(garni)) == 6
    garni("restore", "2", "-y")                     # on annule la restauration
    assert len(archives(garni)) == 4 and titres(garni) == {"Active", "Z"}


def test_reset_conserve_l_archive(garni):
    garni("archive")
    garni("reset", entree="y\n")
    assert garni.taches() == {} and len(archives(garni)) == 4


def test_pager_archive(garni, tmp_path):
    import stat
    garni("archive")
    p = tmp_path / "pg.sh"
    p.write_text("#!/bin/sh\necho '<<PAGER>>'\ncat\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    garni.seed(*[dict(cle=f"zzzz{i:04d}-0", titre=f"X{i}", statut="TERMINE") for i in range(30)])
    garni("archive")
    assert "<<PAGER>>" in garni.pty("archive", "--list", lignes=15, env={"PAGER": str(p)}).texte
    assert "<<PAGER>>" not in garni.pty("archive", "--list", "--no-pager", lignes=15, env={"PAGER": str(p)}).texte
    assert "<<PAGER>>" not in garni.pty("archive", "--list", "--format", "json", lignes=15, env={"PAGER": str(p)}).texte


def test_commandes_dans_l_aide(todo):
    sortie = todo("--help").out
    assert "archive" in sortie and "unarchive" in sortie
