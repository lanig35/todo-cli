import pytest

from outils import jour


@pytest.fixture
def garni(todo):
    todo.seed(dict(cle="cccc0001-0", titre="Retard", priorite="high", echeance=jour(-2), tags=["x"]),
              dict(cle="cccc0002-0", titre="Fini", statut="TERMINE", terminee=jour(0) + " 08:00"))
    return todo


def test_aucune_couleur_dans_un_pipe(garni):
    for cmd in (["list"], ["stats"], ["show", "cccc0001"], ["restore"], ["list", "--format", "json"]):
        r = garni(*cmd)
        assert "\x1b" not in r.out and "\x1b" not in r.err, cmd


@pytest.mark.parametrize("args", [["list", "--color", "always"], ["--color", "always", "list"]])
def test_always_force(garni, args):
    assert "\x1b[" in garni(*args).out


@pytest.mark.parametrize("args", [["list", "--color", "never"], ["list", "--no-color"], ["--no-color", "list"]])
def test_never(garni, args):
    assert "\x1b" not in garni(*args).out


def test_la_derniere_option_gagne(garni):
    assert "\x1b[" in garni("list", "--no-color", "--color", "always").out
    assert "\x1b" not in garni("list", "--color", "always", "--no-color").out


def test_choix_explicite_l_emporte_sur_no_color(garni):
    assert "\x1b[" in garni("list", "--color", "always", env={"NO_COLOR": "1"}).out


def test_json_jamais_colore(garni):
    r = garni("list", "--format", "json", "--color", "always")
    assert "\x1b" not in r.out and r.json()


def test_pty_colore_par_defaut(garni):
    r = garni.pty("list")
    assert r.code == 0 and r.nb_couleurs > 0 and "Retard" in r.texte


def test_pty_no_color_env(garni):
    r = garni.pty("list", env={"NO_COLOR": "1"})
    assert r.nb_couleurs == 0 and "Retard" in r.texte


def test_pty_no_color_vide_est_ignore(garni):
    assert garni.pty("list", env={"NO_COLOR": ""}).nb_couleurs > 0


def test_pty_term_dumb(garni):
    assert garni.pty("list", env={"TERM": "dumb"}).nb_couleurs == 0


def test_pty_option_no_color(garni):
    assert garni.pty("list", "--no-color").nb_couleurs == 0


def test_avertissement_stderr_colore_selon_stderr(todo, tmp_path):
    todo.seed(dict(cle="cccc0001-0", titre="Ok"))
    todo.seed_brut("cccc0009-0", b"pas du json")
    # stdout = terminal, stderr redirigé vers un fichier : pas de couleur dans le fichier
    journal = tmp_path / "erreurs.log"
    todo.pty("list", stderr_vers=str(journal))
    contenu = journal.read_text()
    assert "cccc0009" in contenu and "\x1b" not in contenu
