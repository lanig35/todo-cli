"""Sorties JSON (compatibles jq) des commandes remind et config."""
import shutil
import subprocess

import pytest

from outils import jour


@pytest.fixture
def taches(todo):
    todo.seed(
        {"cle": "a" * 8, "titre": "retard", "echeance": jour(-3), "priorite": "high"},
        {"cle": "b" * 8, "titre": "ajd", "echeance": jour(0)},
        {"cle": "c" * 8, "titre": "bientot", "echeance": jour(2)},
        {"cle": "d" * 8, "titre": "loin", "echeance": jour(30)},
        {"cle": "e" * 8, "titre": "fait", "echeance": jour(-1), "statut": "TERMINÉE", "terminee": "2026-01-02 10:00"},
    )
    return todo


def test_remind_json_structure(taches):
    r = taches("remind", "--format", "json")
    assert r.code == 0
    d = r.json()
    assert d["actif"] is True and d["desactive_par"] == []
    assert d["compteurs"] == {"retards": 1, "aujourdhui": 1, "a_venir": 0, "total": 2}
    assert [t["titre"] for t in d["retards"]] == ["retard"]
    assert d["retards"][0]["jours_restants"] == -3
    assert [t["titre"] for t in d["aujourdhui"]] == ["ajd"]
    assert d["a_venir"] == []


def test_remind_json_soon(taches):
    d = taches("remind", "--format", "json", "--soon", "3").json()
    assert d["bientot_jours"] == 3
    assert [t["titre"] for t in d["a_venir"]] == ["bientot"]


def test_remind_json_sans_limite(todo):
    todo.seed(*[{"cle": f"{i:08d}", "titre": f"t{i}", "echeance": jour(-1)} for i in range(8)])
    d = todo("remind", "--format", "json", "--limit", "2").json()
    assert d["compteurs"]["retards"] == 8 and len(d["retards"]) == 8


def test_remind_json_toujours_un_document(todo):
    d = todo("remind", "--format", "json").json()
    assert d["compteurs"]["total"] == 0 and d["retards"] == []
    assert todo("remind").out == ""  # le texte reste muet


def test_remind_json_desactive(taches):
    taches("remind", "--disable")
    d = taches("remind", "--format", "json").json()
    assert d["actif"] is False and d["compteurs"]["total"] == 0
    assert d["desactive_par"] == ["commande remind --disable"]


def test_remind_json_desactive_par_variable(taches):
    d = taches("remind", "--format", "json", env={"TODO_NO_REMIND": "1"}).json()
    assert d["actif"] is False and d["compteurs"]["total"] == 0


def test_remind_etat_json(todo):
    assert todo("remind", "--status", "--format", "json").json()["actif"] is True
    d = todo("remind", "--disable", "--format", "json").json()
    assert d["actif"] is False and d["desactive_par"]
    assert todo("remind", "--status", "--format", "json").json()["actif"] is False
    d = todo("remind", "--enable", "--format", "json").json()
    assert d["actif"] is True and d["desactive_par"] == []


@pytest.mark.parametrize("option", ["--once-a-day", "--write-status"])
def test_remind_json_incompatible_options(todo, option):
    r = todo("remind", "--format", "json", option)
    assert r.code == 1 and "{" not in r.out
    assert "--format json" in r.texte


def test_config_path_json(todo):
    assert todo("config", "path", "--format", "json").json() == {"fichier": str(todo.fichier_config), "existe": False}
    todo.config("")
    assert todo("config", "path", "--format", "json").json()["existe"] is True
    assert todo("config", "path").sortie.strip() == str(todo.fichier_config)  # texte inchangé


def test_config_init_json(todo):
    d = todo("config", "init", "--format", "json").json()
    assert d == {"fichier": str(todo.fichier_config), "cree": True, "ecrase": False}
    assert todo.fichier_config.exists()


def test_config_init_json_existe_deja(todo):
    todo.config("[general]\n")
    r = todo("config", "init", "--format", "json")
    assert r.code == 1
    d = r.json()
    assert d["cree"] is False and d["erreur"] == "existe_deja"
    assert todo.fichier_config.read_text() == "[general]\n"


def test_config_init_json_force(todo):
    todo.config("[general]\n")
    r = todo("config", "init", "--force", "--format", "json")
    assert r.code == 0 and r.json()["ecrase"] is True


def test_config_init_json_ecriture_impossible(todo):
    fichier = todo.dossier / "pas_un_dossier"
    fichier.write_text("x")
    r = todo("config", "init", "--format", "json", env={"TODO_CONFIG": str(fichier / "config.ini")})
    assert r.code == 1
    d = r.json()
    assert d["cree"] is False and d["erreur"] == "ecriture_impossible" and d["detail"]


def test_config_show_json_inchange(todo):
    d = todo("config", "show", "--format", "json").json()
    assert "reglages" in d and "fichier" in d


@pytest.mark.skipif(not shutil.which("jq"), reason="jq absent")
def test_jq_consomme_les_sorties(taches):
    sortie = taches("remind", "--format", "json", "--soon", "3").out
    r = subprocess.run(["jq", "-r", ".retards[].titre"], input=sortie, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.split() == ["retard"]
    sortie = taches("config", "path", "--format", "json").out
    r = subprocess.run(["jq", "-r", ".fichier"], input=sortie, capture_output=True, text=True)
    assert r.stdout.strip() == str(taches.fichier_config)
