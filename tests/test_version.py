"""Numéro de version : option --version, CHANGELOG et export concordent."""
import re

import pytest

from outils import RACINE

SEMVER = r"\d+\.\d+\.\d+"


def version_du_code():
    """Lue dans le fichier, sans importer le programme (la suite ne dépend que de son comportement visible)."""
    source = (RACINE / "todo_cli" / "__init__.py").read_text(encoding="utf-8")
    return re.search(rf'^__version__ = "({SEMVER})"$', source, re.MULTILINE).group(1)


def test_option_version(todo):
    r = todo("--version")
    assert r.code == 0 and r.sortie.strip() == f"todo {version_du_code()}"
    assert re.fullmatch(rf"todo {SEMVER}", r.sortie.strip())


def test_version_sans_toucher_a_la_base(todo):
    todo("--version")
    assert todo.sauvegardes() == [] and not list(todo.db_dir.glob("todo_*"))   # aucune base créée


def test_changelog_decrit_la_version_courante():
    changelog = (RACINE / "CHANGELOG.md").read_text(encoding="utf-8")
    premiere = re.search(rf"^## \[({SEMVER})\] - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.MULTILINE)
    assert premiere and premiere.group(1) == version_du_code()
    assert f"[{version_du_code()}]: https://github.com/lanig35/todo-cli/releases/tag/v{version_du_code()}" in changelog


def test_readme_cite_le_changelog_et_la_version():
    readme = (RACINE / "README.md").read_text(encoding="utf-8")
    assert "CHANGELOG.md" in readme and "todo --version" in readme


def test_export_indique_la_version_du_programme(todo):
    assert todo("data", "export").json()["genere_par"] == f"todo {version_du_code()}"


def test_import_accepte_un_export_d_une_autre_version(todo):
    import json
    document = {"format": "todo-cli", "version": 1, "genere_par": "todo 0.9.0", "taches": [{"titre": "ancienne"}]}
    assert todo("data", "import", "-", entree=json.dumps(document)).code == 0 and todo.une("ancienne")
