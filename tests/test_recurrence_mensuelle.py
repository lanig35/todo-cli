"""Récurrences : l'échéance se calcule depuis l'origine de la série (pas de dérive après un mois court)."""
import json
from datetime import date

import pytest

from outils import AUJOURDHUI, ajouter_mois


def terminer_et_suivre(todo, titre, fois):
    """Termine l'occurrence ouverte `fois` fois ; retourne la liste des échéances créées."""
    echeances = []
    for _ in range(fois):
        ouverte = todo.une(titre, "A FAIRE")
        todo("done", ouverte["id"][:8])
        echeances.append(todo.une(titre, "A FAIRE")["date_echeance"])
    return echeances


def test_mensuel_fin_de_mois_ne_derive_pas(todo):
    todo("add", "Loyer", "--due", "2030-01-31", "--repeat", "monthly")
    assert terminer_et_suivre(todo, "Loyer", 6) == [
        "2030-02-28", "2030-03-31", "2030-04-30", "2030-05-31", "2030-06-30", "2030-07-31"]


def test_mensuel_annee_bissextile(todo):
    todo("add", "Loyer", "--due", "2031-12-31", "--repeat", "monthly")
    assert terminer_et_suivre(todo, "Loyer", 4) == ["2032-01-31", "2032-02-29", "2032-03-31", "2032-04-30"]


def test_tous_les_deux_mois(todo):
    todo("add", "Bimestre", "--due", "2030-01-31", "--repeat", "2m")
    assert terminer_et_suivre(todo, "Bimestre", 3) == ["2030-03-31", "2030-05-31", "2030-07-31"]


def test_annuel_29_fevrier_retrouve_le_29(todo):
    todo("add", "Anniversaire", "--due", "2032-02-29", "--repeat", "yearly")
    assert terminer_et_suivre(todo, "Anniversaire", 4) == ["2033-02-28", "2034-02-28", "2035-02-28", "2036-02-29"]


def test_hebdomadaire_et_quotidien_inchanges(todo):
    todo("add", "Hebdo", "--due", "2030-01-01", "--repeat", "weekly")
    todo("add", "Jour", "--due", "2030-01-01", "--repeat", "3d")
    assert terminer_et_suivre(todo, "Hebdo", 3) == ["2030-01-08", "2030-01-15", "2030-01-22"]
    assert terminer_et_suivre(todo, "Jour", 3) == ["2030-01-04", "2030-01-07", "2030-01-10"]


def test_terminer_en_avance_va_apres_l_echeance_actuelle(todo):
    todo("add", "Loyer", "--due", "2030-01-31", "--repeat", "monthly")
    assert terminer_et_suivre(todo, "Loyer", 1) == ["2030-02-28"]       # pas « aujourd'hui + 1 mois »


def test_occurrences_manquees_ne_s_accumulent_pas(todo):
    todo("add", "Vieille", "--due", "2020-01-31", "--repeat", "monthly")
    prochaine = terminer_et_suivre(todo, "Vieille", 1)[0]
    k = 1
    while ajouter_mois(date(2020, 1, 31), k) <= AUJOURDHUI:
        k += 1
    assert prochaine == ajouter_mois(date(2020, 1, 31), k).isoformat()   # première occurrence d'origine après aujourd'hui
    assert prochaine > AUJOURDHUI.isoformat()


def test_l_ancre_est_conservee_dans_les_occurrences(todo):
    todo("add", "Loyer", "--due", "2030-01-31", "--repeat", "monthly")
    assert todo.une("Loyer")["ancre"] is None                            # la première tâche n'en a pas besoin
    terminer_et_suivre(todo, "Loyer", 2)
    assert todo.une("Loyer", "A FAIRE")["ancre"] == "2030-01-31"


def test_modifier_l_echeance_repart_de_la_nouvelle_date(todo):
    todo("add", "Loyer", "--due", "2030-01-31", "--repeat", "monthly")
    terminer_et_suivre(todo, "Loyer", 1)                                  # 2030-02-28, ancre 2030-01-31
    todo("task", "edit", todo.id_de("Loyer", "A FAIRE"), "--due", "2030-03-15")
    assert todo.une("Loyer", "A FAIRE")["ancre"] is None
    assert terminer_et_suivre(todo, "Loyer", 2) == ["2030-04-15", "2030-05-15"]


def test_modifier_la_repetition_remet_l_ancre_a_zero(todo):
    todo("add", "Loyer", "--due", "2030-01-31", "--repeat", "monthly")
    terminer_et_suivre(todo, "Loyer", 1)
    todo("task", "edit", todo.id_de("Loyer", "A FAIRE"), "--repeat", "weekly")
    assert terminer_et_suivre(todo, "Loyer", 1) == ["2030-03-07"]


def test_reporter_une_occurrence_decale_la_serie(todo):
    todo("add", "Loyer", "--due", "2030-01-31", "--repeat", "monthly")
    terminer_et_suivre(todo, "Loyer", 1)                                  # 2030-02-28
    todo("task", "postpone", todo.id_de("Loyer", "A FAIRE"), "--to", "2030-03-03")
    assert todo.une("Loyer", "A FAIRE")["ancre"] is None
    assert terminer_et_suivre(todo, "Loyer", 2) == ["2030-04-03", "2030-05-03"]   # « partent de la nouvelle échéance »


def test_anciennes_taches_sans_ancre(todo):
    todo.seed({"cle": "ancien01", "titre": "Ancien", "echeance": "2030-01-31", "recurrence": "1m"})
    assert todo.une("Ancien")["ancre"] is None
    assert terminer_et_suivre(todo, "Ancien", 3) == ["2030-02-28", "2030-03-31", "2030-04-30"]


def test_ancre_exportee_et_importee(todo, tmp_path):
    todo("add", "Loyer", "--due", "2030-01-31", "--repeat", "monthly")
    terminer_et_suivre(todo, "Loyer", 1)
    document = json.loads(todo("data", "export").out)
    assert document["taches"][-1]["ancre"] in ("2030-01-31", None)
    assert any(t["ancre"] == "2030-01-31" for t in document["taches"])
    (tmp_path / "ailleurs").mkdir()
    from outils import Todo
    autre = Todo(tmp_path / "ailleurs")
    assert autre("data", "import", "-", entree=json.dumps(document)).code == 0
    assert terminer_et_suivre(autre, "Loyer", 2) == ["2030-03-31", "2030-04-30"]


def test_import_ancre_invalide(todo):
    r = todo("data", "import", "-", entree=json.dumps([{"titre": "x", "ancre": "pas-une-date"}]))
    assert r.code == 1 and "ancre" in r.texte
