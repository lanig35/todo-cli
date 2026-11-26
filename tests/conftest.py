import pytest

from outils import Todo


@pytest.fixture
def todo(tmp_path):
    """Une instance du programme avec sa propre base vide, détruite à la fin du test."""
    return Todo(tmp_path)


# ---------------------------------------------------------------- sous-ensemble de non-régression : pytest -m smoke
# La suite complète dépasse 15 minutes ; `pytest -m smoke` (environ 1 minute) en prend un échantillon qui touche toutes les
# fonctions : les fichiers courts en entier, et les premiers tests (cas nominaux) de chacun des autres, plus quelques tests
# bout en bout nommés ci-dessous. La suite complète tourne en intégration continue (`pytest -n auto`).
SMOKE_FICHIERS_COMPLETS = {
    "test_version.py", "test_stats.py", "test_stockage_dynamique.py", "test_robustesse.py", "test_pager.py", "test_postpone.py",
    "test_next.py", "test_agenda.py", "test_json.py", "test_couleurs.py", "test_liste.py", "test_ajout.py", "test_sauvegardes.py",
}
SMOKE_PREMIERS_PAR_FICHIER = 3
SMOKE_EN_PLUS = {"test_tui_dans_un_pseudo_terminal", "test_todo_serve_de_bout_en_bout", "test_hook_avant_refuse_via_api",
                 "test_undo_annule_une_ecriture_de_l_api", "test_modifier_conflit_etag", "test_echappement_xss"}


def pytest_collection_modifyitems(items):
    vus = {}
    for item in items:
        fichier = item.path.name
        vus[fichier] = vus.get(fichier, 0) + 1
        if (fichier in SMOKE_FICHIERS_COMPLETS or vus[fichier] <= SMOKE_PREMIERS_PAR_FICHIER
                or getattr(item, "originalname", item.name) in SMOKE_EN_PLUS):
            item.add_marker(pytest.mark.smoke)
