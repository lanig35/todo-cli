import pytest

from outils import Todo


@pytest.fixture
def todo(tmp_path):
    """Une instance du programme avec sa propre base vide, détruite à la fin du test."""
    return Todo(tmp_path)
