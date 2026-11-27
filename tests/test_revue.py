"""Revue hebdomadaire : report review (text, table, plain, json), réglages [review], rappel `reminder`, script cron."""
import os
import shutil
import subprocess
import sys
from datetime import date

import pytest

from outils import AUJOURDHUI, RACINE, jour

JOUR_SEMAINE = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[AUJOURDHUI.weekday()]
AUTRE_JOUR = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[(AUJOURDHUI.weekday() + 3) % 7]


def tache(**champs):
    champs.setdefault("creation", jour(-2) + " 09:00")
    return champs


@pytest.fixture
def garni(todo):
    todo.seed(
        tache(cle="rev00001", titre="Finie hier", statut="TERMINE", terminee=jour(-1) + " 10:00"),
        tache(cle="rev00002", titre="Finie il y a 3 semaines", statut="TERMINE", terminee=jour(-21) + " 10:00"),
        tache(cle="rev00003", titre="En retard", priorite="high", echeance=jour(-3)),
        tache(cle="rev00004", titre="Demain", echeance=jour(1)),
        tache(cle="rev00005", titre="Dans 20 jours", echeance=jour(20)),
        tache(cle="rev00006", titre="Traine", creation=jour(-45) + " 09:00"),
        tache(cle="rev00007", titre="Recente", creation=jour(-1) + " 09:00"),
        tache(cle="rev00008", titre="Bloquee", apres=["rev00006"], echeance=jour(2)),
    )
    return todo


def titres(rubrique):
    return [t["titre"] for t in rubrique["taches"]]


def test_json_structure_et_sections(garni):
    d = garni("report", "review", "--format", "json").json()
    assert d["date"] == jour(0) and d["jours"] == 7 and d["depuis"] == jour(-6)
    assert titres(d["terminees"]) == ["Finie hier"]
    assert titres(d["en_retard"]) == ["En retard"] and d["en_retard"]["taches"][0]["jours_retard"] == 3
    assert titres(d["qui_trainent"]) == ["Traine"] and d["qui_trainent"]["taches"][0]["age_jours"] == 45
    assert titres(d["bloquees"]) == ["Bloquee"] and d["bloquees"]["taches"][0]["attend"][0]["titre"] == "Traine"
    assert [j["date"] for j in d["a_venir"]["jours"]] == [jour(1), jour(2)]
    assert d["a_venir"]["plus_tard"] == 1 and d["a_venir"]["sans_echeance"] == 2
    assert d["bilan"]["terminees"] == 1 and d["bilan"]["en_retard"] == 1 and d["bilan"]["a_faire"] == 6


def test_jours_change_les_deux_fenetres(garni):
    d = garni("report", "review", "--days", "30", "--format", "json").json()
    assert d["depuis"] == jour(-29) and d["a_venir"]["fin"] == jour(29)
    assert "Dans 20 jours" in [t["titre"] for j in d["a_venir"]["jours"] for t in j["taches"]]
    assert titres(d["terminees"]) == ["Finie hier", "Finie il y a 3 semaines"]


def test_older_than_regle_les_taches_qui_trainent(garni):
    d = garni("report", "review", "--older-than", "1d", "--format", "json").json()
    assert set(titres(d["qui_trainent"])) == {"Traine", "Recente"}
    d = garni("report", "review", "--older-than", "90d", "--format", "json").json()
    assert d["qui_trainent"]["total"] == 0


def test_en_cours_compte_les_taches_demarrees(todo):
    todo.seed(tache(cle="rev10001", titre="Active", demarree=jour(-1) + " 09:00"))
    d = todo("report", "review", "--format", "json").json()
    assert titres(d["en_cours"]) == ["Active"] and d["en_cours"]["taches"][0]["ecoule_minutes"] > 0


def test_archivees_comptent_dans_les_terminees(todo):
    todo.seed(tache(cle="rev20001", titre="Finie", statut="TERMINE", terminee=jour(-2) + " 10:00"))
    assert todo("archive", "add", "--older-than", "1d").code == 0
    assert todo("list", "--format", "json").json() == []
    assert titres(todo("report", "review", "--format", "json").json()["terminees"]) == ["Finie"]


def test_texte_contient_les_sections(garni):
    out = garni("report", "review", "--format", "text", "--no-color", "--no-pager").texte
    for morceau in ("REVUE", "TERMINÉES CETTE SEMAINE", "EN RETARD", "EN COURS", "BLOQUÉES", "QUI TRAÎNENT", "SEMAINE À VENIR",
                    "Finie hier", "En retard", "Traine", "Bloquee", "attend : Traine", "Demain"):
        assert morceau in out, morceau


def test_texte_limite_par_section(todo):
    todo.seed(*[tache(cle=f"rev3000{i}", titre=f"Retard {i}", echeance=jour(-1 - i)) for i in range(6)])
    out = todo("report", "review", "--limit", "2", "--format", "text", "--no-color", "--no-pager").texte
    assert "… et 4 autre(s)" in out and "Retard 5" in out and "Retard 0" not in out


def test_plain_une_ligne_par_tache_avec_section(garni):
    lignes = [l.split("\t") for l in garni("report", "review", "--format", "plain").out.splitlines()]
    sections = {(l[0], l[4]) for l in lignes}
    assert ("terminee", "Finie hier") in sections and ("retard", "En retard") in sections
    assert ("traine", "Traine") in sections and ("bloquee", "Bloquee") in sections and ("a_venir", "Demain") in sections
    assert all(len(l) == 5 for l in lignes)


def test_table_a_les_colonnes(garni):
    out = garni("report", "review", "--format", "table").texte
    assert "SECTION" in out and "TITRE" in out and "Finie hier" in out


def test_base_vide(todo):
    assert "Rien à signaler" in todo("report", "review", "--format", "text", "--no-color", "--no-pager").texte
    d = todo("report", "review", "--format", "json").json()
    assert d["bilan"] == {k: 0 for k in d["bilan"]}


def test_lecture_seule(garni):
    avant = garni("list", "--all", "--format", "json").out
    garni("report", "review", "--format", "json")
    assert garni("list", "--all", "--format", "json").out == avant


def test_reglages_review(garni):
    garni.config("[review]\ndays = 30\nlimit = 3\nstale = 90d\n")
    d = garni("report", "review", "--format", "json").json()
    assert d["jours"] == 30 and d["qui_trainent"]["total"] == 0
    d = garni("report", "review", "--days", "3", "--format", "json").json()
    assert d["jours"] == 3


def test_durees_invalides_refusees(garni):
    assert garni("report", "review", "--older-than", "n'importe quoi").code == 1
    assert garni("report", "review", "--days", "0").code != 0
    assert garni("report", "review", "--days", "91").code == 1


def test_vue_enregistrable(garni):
    assert garni("view", "save", "revue", "report", "review", "--days", "14").code == 0
    assert "REVUE" in garni("view", "run", "revue", "--no-color", "--no-pager", "--format", "text").texte


# ------------------------------------------------------------------ rappel
def test_rappel_signale_le_jour_de_revue(todo):
    env = {"TODO_REVIEW_DAY": JOUR_SEMAINE}
    assert "revue hebdomadaire" in todo("reminder", "check", "--no-color", env=env).texte
    d = todo("reminder", "check", "--format", "json", env=env).json()
    assert d["revue"] == {"jour": JOUR_SEMAINE, "aujourdhui": True}


def test_rappel_muet_les_autres_jours_ou_sans_reglage(todo):
    assert todo("reminder", "check", env={"TODO_REVIEW_DAY": AUTRE_JOUR}).out == ""
    assert todo("reminder", "check").out == ""
    d = todo("reminder", "check", "--format", "json").json()
    assert d["revue"] == {"jour": None, "aujourdhui": False}


def test_rappel_revue_avec_taches_en_retard(garni):
    out = garni("reminder", "check", "--no-color", env={"TODO_REVIEW_DAY": JOUR_SEMAINE}).texte
    assert "en retard" in out and "todo report review" in out


def test_rappel_revue_une_fois_par_jour(todo):
    env = {"TODO_REVIEW_DAY": JOUR_SEMAINE}
    assert todo("reminder", "check", "--once-a-day", env=env).out != ""
    assert todo("reminder", "check", "--once-a-day", env=env).out == ""


def test_statut_une_ligne_mentionne_la_revue(todo):
    todo("reminder", "check", "--write-status", env={"TODO_REVIEW_DAY": JOUR_SEMAINE})
    assert "revue" in (todo.db_dir / "remind_status").read_text(encoding="utf-8")
    todo("reminder", "check", "--write-status", env={"TODO_REVIEW_DAY": AUTRE_JOUR})
    assert (todo.db_dir / "remind_status").read_text(encoding="utf-8") == ""


def test_rappels_desactives_pas_de_rappel_de_revue(todo):
    todo("reminder", "disable")
    assert todo("reminder", "check", env={"TODO_REVIEW_DAY": JOUR_SEMAINE}).out == ""


def test_jour_de_revue_invalide_refuse(todo):
    assert todo("config", "set", "review.day", "lundi").code != 0


# ------------------------------------------------------------------ script cron
SCRIPT = RACINE / "examples" / "cron" / "revue-hebdomadaire.sh"


@pytest.fixture
def commande(tmp_path, todo):
    """Un exécutable `todo` qui relance todo.py avec l'environnement de test."""
    exe = tmp_path / "todo-test"
    exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{RACINE / "todo.py"}" "$@"\n')
    exe.chmod(0o755)
    return exe


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh requis")
def test_script_cron_ecrit_le_rapport_sans_couleur(garni, commande, monkeypatch, tmp_path):
    env = {**os.environ, **garni.env, "TODO_BIN": str(commande), "PATH": f"{tmp_path / 'vide'}:/usr/bin:/bin"}
    r = subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "REVUE" in r.stdout and "\x1b[" not in r.stdout


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh requis")
def test_script_cron_passe_par_mail_quand_disponible(garni, commande, tmp_path):
    faux = tmp_path / "bin"
    faux.mkdir()
    sortie = tmp_path / "courriel.txt"
    mail = faux / "mail"
    mail.write_text(f'#!/bin/sh\n{{ echo "ARGS: $*"; cat; }} > "{sortie}"\n')
    mail.chmod(0o755)
    env = {**os.environ, **garni.env, "TODO_BIN": str(commande), "PATH": f"{faux}:{os.environ['PATH']}",
           "REVUE_DEST": "moi@example.org", "REVUE_SUJET": "Ma revue", "REVUE_OPTIONS": "--days 14"}
    r = subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    courriel = sortie.read_text(encoding="utf-8")
    assert "ARGS: -s Ma revue moi@example.org" in courriel and "REVUE" in courriel
