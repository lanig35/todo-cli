"""Complétion du shell (argcomplete) : résultats utiles, et silence total (ni erreur, ni log, ni dossier créé)."""
import re
import shlex
import subprocess
import sys

import pytest

from outils import RACINE

ANCIEN = ("todo remind", "todo edit", "todo note ID", "todo unarchive")


def completer(todo, ligne, env=None):
    """Joue le protocole d'argcomplete : renvoie (propositions, code, stderr, résultat brut)."""
    e = todo._env(env)
    e.update(_ARGCOMPLETE="1", _ARGCOMPLETE_IFS="\x0b", _ARGCOMPLETE_SHELL="bash", COMP_LINE=ligne, COMP_POINT=str(len(ligne)))
    cmd = f"{shlex.quote(sys.executable)} -B {shlex.quote(str(RACINE / 'todo.py'))} 8>&1 9>/dev/null 1>/dev/null"
    p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=e, cwd=todo.dossier)
    return [m for m in p.stdout.split("\x0b") if m], p.returncode, p.stderr, p.stdout


def _argcomplete_fonctionne(dossier):
    """Vrai si argcomplete est installé ET compatible avec cette version de Python (3.1.x ne l'est pas avec 3.13)."""
    try:
        import argcomplete  # noqa: F401
    except ImportError:
        return False
    import os
    script = dossier / "essai.py"
    script.write_text("import argparse, argcomplete\np = argparse.ArgumentParser()\np.add_argument('--zz')\n"
                      "argcomplete.autocomplete(p)\n")
    env = dict(os.environ, _ARGCOMPLETE="1", _ARGCOMPLETE_IFS="\x0b", COMP_LINE="essai --", COMP_POINT="8")
    p = subprocess.run(["bash", "-c", f"{shlex.quote(sys.executable)} {shlex.quote(str(script))} 8>&1 9>/dev/null 1>/dev/null"],
                       capture_output=True, text=True, env=env)
    return "--zz" in p.stdout


@pytest.fixture(scope="module")
def ac_ok(tmp_path_factory):
    return _argcomplete_fonctionne(tmp_path_factory.mktemp("ac"))


@pytest.fixture
def argcomplete_utilisable(ac_ok):
    if not ac_ok:
        pytest.skip("argcomplete absent ou incompatible avec cette version de Python")


# --- ce qui est proposé -----------------------------------------------------------------------------------------------
def test_groupes_et_raccourcis(todo, argcomplete_utilisable):
    propositions = completer(todo, "todo ")[0]
    for attendu in ("task", "note", "archive", "reminder", "report", "admin", "data", "config", "add", "list", "undo"):
        assert attendu in propositions
    assert "remind" not in propositions and "unarchive" not in propositions     # anciennes commandes non proposées


def test_actions_d_un_groupe(todo, argcomplete_utilisable):
    assert {"add", "list", "edit", "done", "undone", "remove", "postpone", "next"} <= set(completer(todo, "todo task ")[0])
    assert {"add", "list", "purge", "restore"} <= set(completer(todo, "todo archive ")[0])
    assert {"check", "enable", "disable", "status"} <= set(completer(todo, "todo reminder ")[0])


def test_cles_de_config(todo, argcomplete_utilisable):
    assert completer(todo, "todo config get li")[0] == ["list.limit", "list.overdue_first"]
    assert "general.color" in completer(todo, "todo config set ")[0]
    assert "log.level" in completer(todo, "todo config get log.")[0]


def test_valeurs_selon_le_reglage(todo, argcomplete_utilisable):
    assert {"auto", "always", "never"} <= set(completer(todo, "todo config set general.color ")[0])
    assert {"true", "false"} <= set(completer(todo, "todo config set general.pager ")[0])
    assert {"low", "medium", "high"} <= set(completer(todo, "todo config set add.priority ")[0])
    assert "auto" not in completer(todo, "todo config set list.limit ")[0]          # entier : rien à proposer
    assert "true" not in completer(todo, "todo config get general.pager ")[0]       # get n'a pas de valeur


def test_unset_propose_les_cles_du_fichier(todo, argcomplete_utilisable):
    todo.config("[list]\nlimit = 3\n[remind]\nsoon = 2\n")
    assert set(completer(todo, "todo config unset ")[0]) >= {"list.limit", "remind.soon"}
    assert "general.color" not in completer(todo, "todo config unset ")[0]


def test_formats(todo, argcomplete_utilisable):
    assert completer(todo, "todo list --format ")[0] == ["auto", "text", "table", "plain", "json"]


def test_options_des_groupes_completables(todo, argcomplete_utilisable):
    assert "--disable" in completer(todo, "todo reminder check --")[0] or "disable" in completer(todo, "todo reminder ")[0]
    assert "purge" in completer(todo, "todo archive ")[0]
    assert "add" in completer(todo, "todo archive ")[0]


def test_fichier_de_config_choisi_par_option(todo, tmp_path, argcomplete_utilisable):
    autre = tmp_path / "a.ini"
    autre.write_text("[agenda]\ndays = 3\n")
    todo.config("[list]\nlimit = 3\n")                         # le fichier par défaut, lui, ne doit pas être lu
    propositions = completer(todo, f"todo --config {autre} config unset ")[0]
    assert "agenda.days" in propositions and "list.limit" not in propositions


# --- silence ---------------------------------------------------------------------------------------------------------
LIGNES = ["todo ", "todo con", "todo config get li", "todo config set general.color ", "todo remind --",
          "todo add \"titre non ferme", "todo --config /inexistant/x.ini config get "]


@pytest.mark.parametrize("ligne", LIGNES)
def test_complétion_silencieuse(todo, ligne):
    """Quel que soit l'état d'argcomplete : code 0, rien sur stderr, rien dans le journal, aucun dossier créé."""
    todo.config("[list]\nclef_inconnue = 3\nlimit = abc\n")           # un fichier fautif ne doit rien afficher non plus
    _, code, err, _ = completer(todo, ligne, env={"TODO_LOG_TARGET": "file"})
    assert code == 0 and err == ""
    assert not todo.fichier_log.exists()


def test_complétion_ne_cree_pas_le_stockage(tmp_path, todo):
    neuf = tmp_path / "pas-encore" / "base"
    _, code, err, _ = completer(todo, "todo ", env={"TODO_DB_DIR": str(neuf), "TODO_LOG_TARGET": "file"})
    assert code == 0 and err == "" and not neuf.exists() and not (tmp_path / "pas-encore").exists()


def test_complétion_cassee_est_avalee(todo):
    """Une exception pendant la complétion (argcomplete défaillant, environnement inattendu) reste muette."""
    _, code, err, _ = completer(todo, "todo ", env={"COMP_POINT": "pas-un-nombre", "TODO_LOG_TARGET": "file"})
    assert code == 0 and err == "" and not todo.fichier_log.exists()


def test_arc_debug_montre_la_trace(todo, ac_ok):
    """Quand argcomplete est défaillant (ou absent), `_ARC_DEBUG=1` permet de voir pourquoi ; sinon rien à voir."""
    if ac_ok:
        pytest.skip("argcomplete fonctionne : aucune exception à montrer")
    _, code, err, _ = completer(todo, "todo ", env={"_ARC_DEBUG": "1"})
    assert code == 0 and "Traceback" in err


# --- messages d'aide : plus aucune ancienne syntaxe -------------------------------------------------------------------
INTERDIT = [re.compile(p) for p in (
    r"\btodo (remind|edit|undone|remove|postpone|stats|reset|restore|seed|export|import|unarchive)\b",
    r"\btodo note (?!add\b|list\b|edit\b|delete\b)\S",
    r"\btodo archive (--|<)",
)]


def test_aucun_message_ne_cite_l_ancienne_syntaxe():
    import ast
    fautes = []
    for fichier in sorted((RACINE / "todo_cli").glob("*.py")):
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                for motif in INTERDIT:
                    if motif.search(noeud.value):
                        fautes.append(f"{fichier.name}:{noeud.lineno}: {motif.search(noeud.value).group(0)}")
    assert fautes == []


@pytest.mark.parametrize("commande, attendu", [
    (("reminder", "disable"), "todo reminder enable"),
])
def test_rappels_desactives_indiquent_la_nouvelle_commande(todo, commande, attendu):
    assert attendu in todo(*commande).sortie
    todo.seed({"cle": "a" * 8, "titre": "t", "echeance": "2000-01-01"})
    assert attendu in todo("config", "show").sortie


def test_messages_d_aide_utilisent_les_groupes(todo):
    todo("add", "Tâche")
    todo("archive", "add")
    todo.seed({"cle": "c" * 8, "titre": "fini", "statut": "TERMINE", "terminee": "2026-01-02 10:00"})
    todo("archive", "add")
    assert "todo archive restore" in todo("archive", "list").sortie
    assert "todo admin restore" in todo("admin", "restore").sortie
    todo.seed({"cle": "d" * 8, "titre": "x"})
    assert 'todo note add dddddddd "texte"' in todo("note", "list", "d" * 8).sortie


# --- projets -------------------------------------------------------------------------------------------------------------
def test_groupe_project_dans_les_groupes(todo, argcomplete_utilisable):
    assert "project" in completer(todo, "todo ")[0]
    assert {"current", "list", "create", "use", "rename", "delete"} <= set(completer(todo, "todo project ")[0])


def test_noms_de_projets_proposes_sans_rien_creer(todo, argcomplete_utilisable):
    todo("project", "create", "travail")
    todo("project", "create", "perso")
    for ligne in ("todo project use ", "todo list --project ", "todo -p ", "todo project delete "):
        propositions, code, err, _ = completer(todo, ligne)
        assert {"default", "travail", "perso"} <= set(propositions), ligne
        assert err == ""
    assert completer(todo, "todo project use tr")[0] == ["travail "]
    assert sorted(p.name for p in (todo.db_dir / "projects").iterdir()) == ["perso", "travail"]


def test_completion_avec_un_projet_inexistant_ne_cree_rien(todo, argcomplete_utilisable):
    propositions, code, err, _ = completer(todo, "todo -p fantome list --", env=None)
    assert err == "" and not (todo.db_dir / "projects").exists()


# --- vues ----------------------------------------------------------------------------------------------------------------
def test_vues_proposees(todo, argcomplete_utilisable):
    assert "view" in completer(todo, "todo ")[0]
    assert {"save", "run", "list", "show", "rename", "remove"} <= set(completer(todo, "todo view ")[0])
    todo("view", "save", "retards", "--overdue")
    todo("project", "create", "pro")
    todo("view", "save", "-p", "pro", "urgent", "--prio", "high")
    for ligne in ("todo view run ", "todo view show ", "todo view remove ", "todo view rename "):
        propositions, _, err, _ = completer(todo, ligne)
        assert "retards" in propositions and "urgent" not in propositions and err == "", ligne
    assert "urgent" in completer(todo, "todo view run -p pro ")[0]


def test_completion_des_vues_ne_cree_rien(todo, argcomplete_utilisable):
    _, code, err, _ = completer(todo, "todo view run ")
    assert err == "" and not (todo.db_dir / "views.json").exists()


# --- pièces jointes ------------------------------------------------------------------------------------------------------
def test_groupe_attachment_et_options(todo, argcomplete_utilisable):
    assert "attachment" in completer(todo, "todo ")[0]
    assert {"add", "list", "open", "save", "remove", "gc"} <= set(completer(todo, "todo attachment ")[0])
    assert "--has-files" in completer(todo, "todo list --has-")[0]
    assert "--older-than" in completer(todo, "todo attachment gc --")[0]


# --- suivi du temps ------------------------------------------------------------------------------------------------------
def test_start_unstart_et_rapports_completables(todo, argcomplete_utilisable):
    assert {"start", "unstart"} <= set(completer(todo, "todo task ")[0])
    assert {"active", "cycle"} <= set(completer(todo, "todo report ")[0])
    assert "--at" in completer(todo, "todo task start --a")[0]
    assert "--started" in completer(todo, "todo list --star")[0]
    assert "--by" in [c.strip() for c in completer(todo, "todo report cycle --b")[0]]


def test_attachment_check_et_link_completables(todo, argcomplete_utilisable):
    assert "check" in completer(todo, "todo attachment ")[0]
    assert "--link" in [c.strip() for c in completer(todo, "todo attachment add --li")[0]]
