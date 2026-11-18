"""Verrou de la base (flock sur todo.lock) : exclusion des écritures, lectures partagées, délai d'attente."""
import fcntl
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

COURT = {"TODO_LOCK_TIMEOUT": "1"}


@pytest.fixture
def verrou(todo):
    """Prise du verrou par le test lui-même : `verrou(mode)` le prend, `verrou.relacher()` le rend."""
    ouverts = []

    class Prise:
        def __call__(self, mode):
            f = open(todo.db_dir / "todo.lock", "w")
            fcntl.flock(f, fcntl.LOCK_EX if mode == "exclusif" else fcntl.LOCK_SH)
            ouverts.append(f)

        def relacher(self):
            while ouverts:
                ouverts.pop().close()

    prise = Prise()
    yield prise
    prise.relacher()


def test_le_fichier_de_verrou_est_cree(todo):
    todo("add", "Une tache")
    assert (todo.db_dir / "todo.lock").exists()


def test_ecriture_refusee_quand_un_autre_ecrit(todo, verrou):
    todo("add", "Existante")
    verrou("exclusif")
    debut = time.monotonic()
    r = todo("add", "Nouvelle", env=COURT)
    assert r.code == 1 and "utilisée par une autre instance" in r.texte and "lock_timeout" in r.texte
    assert 0.9 <= time.monotonic() - debut < 8
    verrou.relacher()
    assert [t["titre"] for t in todo.taches().values()] == ["Existante"]


def test_lecture_refusee_pendant_une_ecriture(todo, verrou):
    todo("add", "Existante")
    verrou("exclusif")
    assert todo("list", env=COURT).code == 1


def test_lectures_simultanees_autorisees(todo, verrou):
    todo("add", "Existante")
    verrou("partage")
    assert "Existante" in todo("list", env=COURT).sortie
    assert todo("show", todo.id_de("Existante"), env=COURT).code == 0


def test_ecriture_attend_la_fin_des_lectures(todo, verrou):
    todo("add", "Existante")
    verrou("partage")
    assert todo("add", "Nouvelle", env=COURT).code == 1


def test_attente_puis_succes_quand_le_verrou_se_libere(todo):
    todo("add", "Existante")
    f = open(todo.db_dir / "todo.lock", "w")
    fcntl.flock(f, fcntl.LOCK_EX)
    threading.Timer(1.0, f.close).start()
    r = todo("add", "Nouvelle", env={"TODO_LOCK_TIMEOUT": "10"})
    assert r.code == 0
    assert {t["titre"] for t in todo.taches().values()} == {"Existante", "Nouvelle"}


def test_delai_zero_echoue_tout_de_suite(todo, verrou):
    todo("add", "Existante")
    verrou("exclusif")
    debut = time.monotonic()
    assert todo("add", "Nouvelle", env={"TODO_LOCK_TIMEOUT": "0"}).code == 1
    assert time.monotonic() - debut < 5


def test_config_ne_prend_pas_de_verrou(todo, verrou):
    verrou("exclusif")
    assert todo("config", "show", env=COURT).code == 0


def test_verrou_libere_quand_le_processus_meurt(todo):
    """Un plantage ne laisse pas de verrou périmé."""
    p = subprocess.Popen([sys.executable, "-c",
                          "import fcntl,sys,time\n"
                          f"f=open({str(todo.db_dir / 'todo.lock')!r},'w');fcntl.flock(f,fcntl.LOCK_EX);print('ok',flush=True);time.sleep(60)"],
                         stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "ok"
    assert todo("add", "Bloquee", env={"TODO_LOCK_TIMEOUT": "0"}).code == 1
    p.kill()
    p.wait()
    assert todo("add", "Libre", env=COURT).code == 0


def test_lock_timeout_invalide_est_signale(todo):
    r = todo("add", "x", env={"TODO_LOCK_TIMEOUT": "-3"})
    assert "TODO_LOCK_TIMEOUT" in r.texte and r.code == 0


def test_lock_timeout_dans_le_reglage_config(todo):
    assert todo("config", "set", "general.lock_timeout", "3").code == 0
    assert todo("config", "get", "general.lock_timeout").sortie.strip() == "3"


def test_ecritures_concurrentes_ne_perdent_rien(todo):
    """Dix `add` lancés ensemble : toutes les tâches sont là et la base est intacte."""
    todo("add", "Amorce")
    n = 10
    with ThreadPoolExecutor(n) as pool:
        codes = list(pool.map(lambda i: todo("add", f"Concurrente {i}", "--literal", env={"TODO_LOCK_TIMEOUT": "30"}).code, range(n)))
    assert codes == [0] * n
    titres = {t["titre"] for t in todo.taches().values()}
    assert titres == {"Amorce", *(f"Concurrente {i}" for i in range(n))}
