"""Hooks : commande lancée après une modification (réglages [hooks])."""
import json
import os
import stat

import pytest


@pytest.fixture
def hook(todo, tmp_path):
    """Script qui ajoute une ligne `événement|id|titre|nb|projet|IN_HOOK` puis l'entrée standard à un fichier."""
    sortie = tmp_path / "hook.log"
    script = tmp_path / "hook.sh"
    script.write_text(
        '#!/bin/sh\n'
        f'printf "%s|%s|%s|%s|%s|%s|%s\\n" "$TODO_HOOK" "$TODO_EVENT" "$TODO_ID" "$TODO_TITLE" "$TODO_COUNT" '
        f'"$TODO_PROJECT" "$TODO_IN_HOOK" >> {sortie}\n'
        f'cat >> {sortie}; echo >> {sortie}\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    def lignes():
        if not sortie.exists():
            return []
        return [l for l in sortie.read_text().splitlines() if "|" in l and l.split("|")[0].startswith("on_")]

    todo.script = str(script)
    todo.lignes = lignes
    todo.brut = lambda: sortie.read_text() if sortie.exists() else ""
    return todo


def avec(hook, **hooks):
    return {f"TODO_HOOKS_{k.upper()}": v for k, v in hooks.items()}


def test_on_add_recoit_la_tache(hook):
    env = avec(hook, on_add=hook.script)
    assert hook("add", "Écrire le rapport", "--tags", "pro", env=env).code == 0
    (l,) = hook.lignes()
    nom, evt, id_, titre, nb, projet, garde = l.split("|")
    assert (nom, evt, titre, nb, projet, garde) == ("on_add", "add", "Écrire le rapport", "1", "default", "1")
    assert id_ == hook.une("Écrire le rapport")["id"]
    donnees = json.loads(hook.brut().splitlines()[1])
    assert donnees["titre"] == "Écrire le rapport" and donnees["tags"] == ["pro"]


def test_aucun_hook_sans_reglage_ni_sur_lecture(hook):
    hook("add", "A")
    hook("list", env=avec(hook, on_change=hook.script))
    hook("show", hook.id_de("A"), env=avec(hook, on_change=hook.script))
    assert hook.lignes() == []


@pytest.mark.parametrize("commande,evenement", [
    (("task", "done"), "done"), (("done",), "done"),
])
def test_done(hook, commande, evenement):
    hook("add", "A")
    hook(*commande, hook.id_de("A"), env=avec(hook, on_done=hook.script))
    assert [l.split("|")[:2] for l in hook.lignes()] == [["on_done", evenement]]


def test_evenements_specifiques(hook):
    env = avec(hook, on_undone=hook.script, on_start=hook.script, on_unstart=hook.script, on_edit=hook.script,
               on_postpone=hook.script, on_remove=hook.script, on_done=hook.script)
    hook("add", "A", "--due", "demain")
    i = hook.id_de("A")
    hook("task", "start", i, env=env)
    hook("task", "unstart", i, env=env)
    hook("task", "edit", i, "--title", "B", env=env)
    hook("task", "postpone", i, "--to", "+2d", env=env)
    hook("task", "done", i, env=env)
    hook("task", "undone", i, env=env)
    hook("task", "remove", i, "-y", env=env)
    evts = [l.split("|")[1] for l in hook.lignes()]
    assert evts == ["start", "unstart", "edit", "postpone", "done", "undone", "remove"]


def test_tache_supprimee_utilise_le_journal(hook):
    hook("add", "À jeter")
    i = hook.une("À jeter")["id"]
    hook("task", "remove", i[:8], "-y", env=avec(hook, on_remove=hook.script))
    (l,) = hook.lignes()
    assert l.split("|")[3] == "À jeter" and l.split("|")[2].startswith(i[:8])
    assert json.loads(hook.brut().splitlines()[1])["titre"] == "À jeter"


def test_on_change_en_plus_du_hook_specifique(hook):
    hook("add", "A")
    hook("done", hook.id_de("A"), env=avec(hook, on_done=hook.script, on_change=hook.script))
    assert [l.split("|")[0] for l in hook.lignes()] == ["on_done", "on_change"]


def test_on_change_sans_tache_une_seule_fois(hook, tmp_path):
    hook("add", "A")
    hook("done", hook.id_de("A"))
    r = hook("undo", env=avec(hook, on_change=hook.script))
    assert r.code == 0
    lignes = hook.lignes()
    assert len(lignes) == 1 and lignes[0].split("|")[0] == "on_change"


def test_lot_une_execution_par_tache(hook):
    for t in ("A", "B", "C"):
        hook("add", t)
    hook("task", "done", "--all", env=avec(hook, on_done=hook.script))
    lignes = [l.split("|") for l in hook.lignes()]
    assert sorted(l[3] for l in lignes) == ["A", "B", "C"] and {l[4] for l in lignes} == {"3"}


def test_lot_trop_grand_une_seule_execution(hook):
    hook.seed(*[{"cle": f"k{n:04d}", "titre": f"T{n}"} for n in range(25)])
    hook("task", "done", "--all", "-y", env=avec(hook, on_done=hook.script))
    (l,) = hook.lignes()
    assert l.split("|")[4] == "25" and l.split("|")[2] == ""
    assert len(json.loads(hook.brut().splitlines()[1])["ids"]) == 25


def test_projet_transmis(hook):
    hook("add", "Perso")
    assert hook("project", "create", "pro").code == 0
    hook("add", "A", "-p", "pro", env=avec(hook, on_add=hook.script))
    assert hook.lignes()[0].split("|")[5] == "pro"


def test_pas_d_injection(hook, tmp_path):
    piege = tmp_path / "PWNED"
    hook("add", f'x"; touch {piege}; $(touch {piege})', env=avec(hook, on_add=hook.script))
    assert not piege.exists() and len(hook.lignes()) == 1


def test_echec_du_hook_ne_change_pas_le_code(hook):
    r = hook("add", "A", env=avec(hook, on_add="false"))
    assert r.code == 0 and "Hook on_add" in r.err and "code 1" in r.err
    assert hook.une("A")


def test_commande_introuvable(hook):
    r = hook("add", "A", env=avec(hook, on_add="/nexiste/pas"))
    assert r.code == 0 and "impossible de lancer" in r.err


def test_commande_mal_formee(hook):
    r = hook("add", "A", env=avec(hook, on_add="echo 'ouvert"))
    assert r.code == 0 and "commande invalide" in r.err


def test_timeout(hook):
    r = hook("add", "A", env=avec(hook, on_add="sleep 5", timeout="1"))
    assert r.code == 0 and "interrompue après 1 s" in r.err


def test_sortie_du_hook_sur_stderr(hook):
    r = hook("add", "A", env=avec(hook, on_add="echo bonjour"))
    assert "bonjour" not in r.sortie and "bonjour" in r.err


def test_desactivation(hook):
    hook("add", "A", env=avec(hook, on_add=hook.script, enabled="0"))
    assert hook.lignes() == []


def test_pas_de_recursion(hook):
    hook("add", "A", env=avec(hook, on_add=hook.script) | {"TODO_IN_HOOK": "1"})
    assert hook.lignes() == []


def test_dry_run_ne_declenche_rien(hook):
    hook("add", "A", "--dry-run", env=avec(hook, on_add=hook.script))
    assert hook.lignes() == []


def test_echec_de_commande_sans_modification(hook):
    r = hook("done", "zzzzzzzz", env=avec(hook, on_done=hook.script, on_change=hook.script))
    assert r.code != 0 and hook.lignes() == []


def test_avertissement_journalise(hook):
    hook("add", "A", env=avec(hook, on_add="false", ) | {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "warning"})
    assert any("WARNING" in l and " hook " in l and "hook=on_add" in l for l in hook.journal())


def test_reglage_dans_le_fichier_de_configuration(hook):
    hook.config(f"[hooks]\non_add = {hook.script}\n")
    hook("add", "A")
    assert len(hook.lignes()) == 1
