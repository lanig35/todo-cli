"""Emplacement du stockage résolu à l'exécution : le dossier vient des réglages, rien n'est figé à l'import."""
import re
from pathlib import Path

PAQUET = Path(__file__).resolve().parent.parent / "todo_cli"
CHEMINS = ("DB_DIR", "DB_NAME", "ARCHIVE_NAME", "BACKUP_DIR", "NB_BACKUPS_MAX", "REMIND_OFF", "REMIND_LAST",
           "REMIND_STATUS", "ARCHIVE_AUTO_LAST", "LOCK_FILE")


def test_aucun_module_ne_fige_un_chemin_a_l_import():
    """`from .config import DB_NAME` copierait la valeur à l'import : seul `config.DB_NAME` reste dynamique."""
    fautifs = []
    for fichier in sorted(PAQUET.glob("*.py")):
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"\s*from \.config import (.+)", ligne)
            if m and any(n.strip() in CHEMINS for n in m.group(1).split(",")):
                fautifs.append(f"{fichier.name}:{numero}")
    assert not fautifs, f"chemins du stockage importés par valeur : {fautifs}"


def test_le_dossier_vient_de_la_variable_d_environnement(todo, tmp_path):
    autre = tmp_path / "ailleurs"
    todo("add", "Ici", env={"TODO_DB_DIR": str(autre)})
    assert list(autre.glob("todo_db*"))
    assert (autre / "backups").is_dir()
    assert (autre / "todo.lock").exists()
    assert todo("list", env={"TODO_DB_DIR": str(autre)}).out.count("Ici") == 1


def test_le_dossier_vient_de_l_option_config(todo, tmp_path):
    """--config est lue avant que le dossier de stockage ne soit résolu : il peut donc en désigner un autre."""
    autre = tmp_path / "essai-todo"
    ini = tmp_path / "essai.ini"
    ini.write_text(f"[general]\ndb_dir = {autre}\n", encoding="utf-8")
    env = {"TODO_DB_DIR": None}
    assert todo("--config", str(ini), "add", "Dans l'essai", env=env).code == 0
    assert list(autre.glob("todo_db*"))
    assert "Dans l'essai" not in todo("list").out          # la base par défaut n'a rien reçu


def test_les_dossiers_sont_crees_au_premier_usage(todo, tmp_path):
    neuf = tmp_path / "a" / "b" / "c"
    assert not neuf.exists()
    assert todo("list", env={"TODO_DB_DIR": str(neuf)}).code == 0
    assert (neuf / "backups").is_dir()


def test_les_fichiers_d_etat_suivent_le_dossier(todo, tmp_path):
    autre = tmp_path / "etat"
    env = {"TODO_DB_DIR": str(autre)}
    todo("reminder", "disable", env=env)
    assert (autre / "remind_off").exists()
    assert not (todo.db_dir / "remind_off").exists()
