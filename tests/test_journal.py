import os
import re
import socket
import subprocess
import sys

import pytest

from outils import RACINE, jour

FICHIER = {"TODO_LOG_TARGET": "file"}


@pytest.fixture
def jr(todo):
    """La fixture `todo`, avec le journal dirigé vers un fichier ; `jr.lignes()` relit ce fichier."""
    class Journalise:
        def __call__(self, *args, env=None, **kw):
            return todo(*args, env={**FICHIER, **(env or {})}, **kw)

        def __getattr__(self, nom):
            return getattr(todo, nom)

        def lignes(self):
            return todo.journal()

        def derniere(self):
            return todo.journal()[-1]

    return Journalise()


def court(todo, titre):
    return todo.id_de(titre)


# ---------------------------------------------------------------- actions
def test_add(jr):
    jr("add", "Appeler Paul")
    [ligne] = jr.lignes()
    assert re.fullmatch(r"INFO add ids=[0-9a-f]{8} exit=0", ligne)


def test_pas_de_titre_par_defaut(jr):
    jr("add", "SECRET-TITRE", "--desc", "SECRET-DESC", "--tags", "SECRET-TAG")
    i = court(jr, "SECRET-TITRE")
    jr("edit", i, "--title", "SECRET-AUTRE")
    jr("done", i)
    jr("archive")
    jr("unarchive", i)
    jr("remove", i)
    tout = jr.fichier_log.read_text()
    assert tout and not re.search(r"SECRET", tout)


def test_titres_si_demande(jr):
    jr("add", "Appeler Paul", env={"TODO_LOG_TITLES": "1"})
    assert 'titres=["Appeler Paul"]' in jr.derniere()
    jr.config("[log]\ntitles = true\n")
    jr("add", "Autre")
    assert 'titres=["Autre"]' in jr.derniere()


def test_done_plusieurs_avec_echec(jr):
    jr("add", "A"); jr("add", "B")
    a, b = court(jr, "A"), court(jr, "B")
    r = jr("done", a, "zzzz", b)
    assert r.code == 1
    assert jr.lignes()[-2:] == ["WARNING done refus reason=unknown_id prefix=zzzz",
                                f"WARNING done ids={a},{b} total=3 failed=1 exit=1"]


def test_done_recurrente_et_undone(jr):
    jr("add", "R", "--repeat", "daily")
    i = court(jr, "R")
    jr("done", i)
    assert jr.derniere().startswith(f"INFO done ids={i}")
    jr("undone", i)
    assert jr.derniere() == f"INFO undone ids={i} exit=0"


def test_edit_nomme_les_champs_sans_les_valeurs(jr):
    jr("add", "A")
    i = court(jr, "A")
    jr("edit", i, "--title", "Nouveau", "--prio", "high", "--tags", "x")
    assert jr.derniere() == f"INFO edit ids={i} fields=titre,priorité,tags exit=0"


def test_remove_postpone_archive(jr):
    jr.seed(dict(cle="jrnl0001-0", titre="T", echeance=jour(1)), dict(cle="jrnl0002-0", titre="U", statut="TERMINE"))
    jr("postpone", "jrnl0001")
    assert jr.derniere() == "INFO postpone ids=jrnl0001 total=1 failed=0 exit=0"
    jr("archive")
    assert jr.derniere() == "INFO archive ids=jrnl0002 total=1 failed=0 exit=0".replace(" total=1 failed=0", "")
    jr("unarchive", "jrnl0002")
    assert jr.derniere() == "INFO unarchive ids=jrnl0002 total=1 failed=0 exit=0"
    jr("remove", "jrnl0001")
    assert jr.derniere() == "INFO remove ids=jrnl0001 total=1 failed=0 exit=0"


def test_clear_done_reset_restore_undo(jr):
    jr("add", "A"); jr("add", "B")
    jr("done", court(jr, "A"))
    jr("clear-done")
    assert jr.derniere() == "INFO clear-done count=1 exit=0"
    jr("restore", "2", "-y")
    assert re.fullmatch(r"INFO restore backup=\d{8}_\d{6}_\d+ exit=0", jr.derniere())
    jr("undo")
    assert re.fullmatch(r"INFO undo backup=\d{8}_\d{6}_\d+ exit=0", jr.derniere())
    jr("reset", entree="y\n")
    assert jr.derniere() == "INFO reset exit=0"


def test_reset_annule_ne_journalise_pas(jr):
    jr("add", "A")
    avant = jr.lignes()
    jr("reset", entree="n\n")
    assert jr.lignes() == avant


def test_config_init_et_remind(jr, tmp_path):
    cible = tmp_path / "c" / "config.ini"
    jr("config", "init", env={"TODO_CONFIG": str(cible)})
    assert jr.derniere() == f"INFO config file={cible} exit=0"
    jr("remind", "--disable")
    assert jr.derniere() == "INFO remind state=disabled exit=0"
    jr("remind", "--enable")
    assert jr.derniere() == "INFO remind state=enabled exit=0"


def test_seed_resume_les_identifiants(jr):
    pytest.importorskip("faker")
    jr("seed", "30")
    [ligne] = jr.lignes()
    assert "count=30" in ligne and ligne.count(",") == 19           # 20 identifiants au plus, le total est donné


def test_lectures_silencieuses(jr):
    jr("add", "A", "--due", "aujourd'hui")
    jr("done", "zzzz")
    avant = jr.lignes()
    i = court(jr, "A")
    for cmd in (["list"], ["show", i], ["stats"], ["agenda"], ["next"], ["remind"], ["archive", "--list"], ["config", "show"],
                ["restore"], ["config", "path"]):
        assert jr(*cmd).code == 0
    assert jr.lignes() == avant


# ---------------------------------------------------------------- niveaux
def test_niveau_debug_ajoute_les_lectures(jr):
    jr("list", "--log-level", "debug")
    assert jr.derniere() == "DEBUG list exit=0"
    jr("--log-level", "debug", "remind")
    assert jr.derniere() == "DEBUG remind exit=0"


def test_niveaux(jr):
    def sortie(niveau):
        jr.fichier_log.write_text("")
        jr("add", "A", "--log-level", niveau)
        jr("add", "", "--log-level", niveau)
        return [l.split()[0] for l in jr.lignes()]
    assert sortie("info") == ["INFO", "WARNING"]
    assert sortie("warning") == ["WARNING"]
    assert sortie("error") == []
    assert sortie("off") == []
    assert sortie("debug") == ["INFO", "WARNING"]


def test_precedence_du_niveau(jr):
    jr.config("[log]\nlevel = off\n")
    jr("add", "A")
    assert jr.lignes() == []                                                    # fichier
    jr("add", "B", env={"TODO_LOG_LEVEL": "info"})
    assert len(jr.lignes()) == 1                                                # variable > fichier
    jr("add", "C", "--log-level", "off", env={"TODO_LOG_LEVEL": "info"})
    assert len(jr.lignes()) == 1                                                # option > variable


# ---------------------------------------------------------------- refus et erreurs
@pytest.mark.parametrize("args, raison", [
    (["add", " "], "empty_title"),
    (["add", "X", "--due", "blabla"], "invalid_date"),
    (["add", "X", "--repeat", "foo"], "invalid_repeat"),
    (["list", "--due-before", "blabla"], "invalid_date"),
    (["done", "zzzz"], "unknown_id"),
    (["restore", "99", "-y"], "invalid_backup_number"),
    (["archive", "abcd", "--older-than", "1d"], "invalid_combination"),
    (["archive", "--older-than", "xyz"], "invalid_duration"),
    (["agenda", "--days", "400"], "days_limit"),
])
def test_refus(jr, args, raison):
    jr("add", "Base")
    r = jr(*args)
    assert f"refus reason={raison}" in jr.derniere() or any(f"refus reason={raison}" in l for l in jr.lignes()[1:])
    assert all(l.startswith(("INFO", "WARNING")) for l in jr.lignes())


def test_identifiant_ambigu(jr):
    jr.seed(dict(cle="abcd1111-0", titre="A"), dict(cle="abcd2222-0", titre="B"))
    jr("done", "abcd")
    assert jr.derniere() == "WARNING done refus reason=ambiguous_id prefix=abcd"


def test_entree_corrompue(jr):
    jr.seed(dict(cle="jrnl0001-0", titre="A"))
    jr.seed_brut("jrnl0002-0", b"pas du json")
    r = jr("list")
    assert r.code == 0 and "jrnl0002" in r.err                                  # toujours sur stderr
    assert jr.derniere() == "WARNING list refus reason=unreadable_entry id=jrnl0002"


@pytest.mark.parametrize("args, detail", [
    (["add", "X", "--prio", "urgent"], "invalid choice"),
    (["list", "--limit", "0"], "--limit"),
    (["done"], "required"),
    (["--inconnue"], "unrecognized"),
])
def test_erreurs_d_usage(jr, args, detail):
    r = jr(*args)
    assert r.code == 2 and r.err
    assert "refus reason=usage" in jr.derniere() and detail in jr.derniere()


def test_commande_inconnue_dans_le_journal(jr):
    jr("list", "--bogus")
    assert jr.derniere().startswith("WARNING list refus reason=usage")


def test_sortie_en_erreur_sans_detail(jr):
    jr("add", "A")
    r = jr("undo")                                                              # rien à annuler : exit 1, pas de refus
    assert r.code == 1
    assert jr.derniere() == "WARNING undo sortie exit=1"


def test_exception_inattendue(jr, tmp_path):
    code = ("import sys\nsys.path.insert(0, sys.argv[1])\nfrom todo_cli import cli\n"
            "cli.nettoyer_terminees = lambda: 1 / 0\nsys.argv = ['todo', 'clear-done']\ncli.executer()\n")
    p = subprocess.run([sys.executable, "-B", "-c", code, str(RACINE)], capture_output=True, text=True, cwd=tmp_path,
                       env={**jr.env, **FICHIER})
    assert p.returncode == 1 and "ZeroDivisionError" in p.stderr               # la trace reste visible sur stderr
    lignes = jr.lignes()
    assert lignes[0] == "CRITICAL clear-done exception type=ZeroDivisionError"
    assert any("ZeroDivisionError: division by zero" in l for l in lignes)      # trace complète dans le journal
    assert any(l.startswith("WARNING clear-done sortie exit=1") for l in lignes)


def test_avertissements_de_configuration_journalises_une_fois(jr):
    jr.config("[list]\nlimite = 3\n")
    r = jr("add", "A")
    assert "clé inconnue" in r.err
    configs = [l for l in jr.lignes() if " config " in l]
    assert len(configs) == 1 and configs[0].startswith("WARNING add config detail=") and "limite" in configs[0]


# ---------------------------------------------------------------- destinations
def test_aucune_sortie_parasite(jr):
    r = jr("add", "A")
    assert r.err == "" and "\x1b" not in jr.fichier_log.read_text()


def test_cible_off(todo):
    todo("add", "A", env={"TODO_LOG_TARGET": "off"})
    assert not todo.fichier_log.exists()


def test_fichier_par_defaut_xdg(todo, tmp_path):
    etat = tmp_path / "etat"
    todo("add", "A", env={"TODO_LOG_TARGET": "file", "TODO_LOG_FILE": None, "XDG_STATE_HOME": str(etat)})
    assert (etat / "todo" / "todo.log").is_file()


def test_fichier_illisible_ne_bloque_pas(todo, tmp_path):
    os.mkdir(tmp_path / "dossier-pas-fichier")
    r = todo("add", "A", env={"TODO_LOG_TARGET": "file", "TODO_LOG_FILE": str(tmp_path / "dossier-pas-fichier")})
    assert r.code == 0 and r.err == "" and "Traceback" not in r.err
    assert todo.une("A")


def test_auto_sans_journal_systeme_retombe_sur_le_fichier(todo, tmp_path):
    r = todo("add", "A", env={"TODO_LOG_TARGET": "auto", "TODO_LOG_SOCKET": str(tmp_path / "absent.sock")})
    assert r.code == 0 and r.err == ""
    if not _python_systemd():
        assert todo.journal() and todo.journal()[0].startswith("INFO add")


def test_journal_explicite_sans_journal_systeme_previent_et_retombe_sur_le_fichier(todo, tmp_path):
    if _python_systemd():
        pytest.skip("python3-systemd présent : le journal est toujours joignable")
    r = todo("add", "A", env={"TODO_LOG_TARGET": "journal", "TODO_LOG_SOCKET": str(tmp_path / "absent.sock")})
    assert r.code == 0 and "repli sur le fichier de log" in r.err
    assert todo.journal()[0].startswith("INFO add")


def _python_systemd():
    p = subprocess.run([sys.executable, "-c", "import systemd.journal"], capture_output=True)
    return p.returncode == 0


@pytest.fixture
def faux_syslog(tmp_path):
    """Un serveur de socket Unix datagramme qui joue le rôle de /dev/log (journald)."""
    chemin = str(tmp_path / "log.sock")
    serveur = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    serveur.bind(chemin)
    serveur.settimeout(0.5)

    def lire():
        recus = []
        try:
            while True:
                recus.append(serveur.recv(65536).decode("utf-8"))
        except socket.timeout:
            return recus

    yield chemin, lire
    serveur.close()


@pytest.mark.skipif(_python_systemd(), reason="python3-systemd présent : le journal passe par JournalHandler")
def test_envoi_au_socket_syslog(todo, faux_syslog):
    chemin, lire = faux_syslog
    env = {"TODO_LOG_TARGET": "journal", "TODO_LOG_SOCKET": chemin}
    todo("add", "A", env=env)
    todo("add", "", env=env)                                    # refus : WARNING
    todo("--log-level", "debug", "list", env=env)
    recus = lire()
    assert len(recus) == 3
    # <PRI> = facilité USER (1 * 8) + gravité : info 6, warning 4, debug 7
    assert re.fullmatch(r"<14>todo\[\d+\]: add ids=[0-9a-f]{8} exit=0\x00", recus[0]), recus[0]
    assert re.fullmatch(r"<12>todo\[\d+\]: add refus reason=empty_title\x00", recus[1]), recus[1]
    assert re.fullmatch(r"<15>todo\[\d+\]: list exit=0\x00", recus[2]), recus[2]
    assert not todo.fichier_log.exists()                        # pas de double écriture


@pytest.mark.skipif(_python_systemd(), reason="python3-systemd présent : le journal passe par JournalHandler")
def test_auto_prefere_le_socket_syslog_au_fichier(todo, faux_syslog):
    chemin, lire = faux_syslog
    todo("add", "A", env={"TODO_LOG_TARGET": "auto", "TODO_LOG_SOCKET": chemin})
    assert len(lire()) == 1 and not todo.fichier_log.exists()


def test_reglages_dans_config_show(todo):
    d = {r["cle"]: r for r in todo("config", "show", "--format", "json").json()["reglages"]}
    for cle in ("log.level", "log.target", "log.file", "log.socket", "log.titles"):
        assert cle in d
    assert d["log.level"]["valeur"] == "info" and d["log.level"]["origine"] == "défaut"
    assert d["log.titles"]["valeur"] is False and d["log.socket"]["valeur"] == "/dev/log"


def test_aide(todo):
    assert "--log-level" in todo("list", "--help").out and "--log-level" in todo("--help").out
