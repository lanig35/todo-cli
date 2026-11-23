"""Hooks « avant » (before_add, before_done) : un code de sortie non nul refuse l'action."""
import json
import stat
import sys

import pytest

from test_hooks import hook, Serveur, webhook  # noqa: F401  (fixtures et aides)


def script(tmp_path, nom, corps):
    f = tmp_path / nom
    f.write_text(corps)
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return str(f)


@pytest.fixture
def v(hook, tmp_path):
    hook.trace = tmp_path / "trace.log"
    hook.espion = script(tmp_path, "espion.sh",
                         '#!/bin/sh\nprintf "%s|%s|%s|%s|%s|%s|%s|%s\\n" "$TODO_HOOK" "$TODO_PHASE" "$TODO_EVENT" "$TODO_ID" "$TODO_TITLE" '
                         f'"$TODO_COUNT" "$TODO_PROJECT" "$TODO_IN_HOOK" >> {hook.trace}\ncat >> {hook.trace}; echo >> {hook.trace}\n')
    hook.refus = script(tmp_path, "refus.sh", '#!/bin/sh\necho "Le hook dit non."\nexit 3\n')
    hook.exige_tag = script(tmp_path, "exige_tag.py", f'#!{sys.executable}\nimport json, sys\n'
                            't = json.load(sys.stdin)\n'
                            'if not t.get("tags"):\n    print("Ajoutez au moins un tag.")\n    sys.exit(1)\n')
    hook.refuse_titre = script(tmp_path, "refuse_titre.sh", '#!/bin/sh\n[ "$TODO_TITLE" = "Bloquee" ] && { echo "Bloquee refusee"; exit 1; }\nexit 0\n')
    return hook


def avant(**reglages):
    return {f"TODO_HOOKS_{k.upper()}": v for k, v in reglages.items()}


def lignes(v):
    return v.trace.read_text().splitlines() if v.trace.exists() else []


# ------------------------------------------------------------------ add
def test_add_accepte_recoit_la_tache_a_creer(v):
    r = v("add", "Rapport #pro !high", env=avant(before_add=v.espion))
    assert r.code == 0 and v.une("Rapport")
    nom, phase, evt, id_, titre, nb, projet, garde = lignes(v)[0].split("|")
    assert (nom, phase, evt, titre, nb, projet, garde) == ("before_add", "before", "add", "Rapport", "1", "default", "1")
    assert id_ == v.une("Rapport")["id"]                                       # l'identifiant que la tâche va recevoir
    donnees = json.loads(lignes(v)[1])
    assert donnees["titre"] == "Rapport" and donnees["tags"] == ["pro"] and donnees["priorite"] == "high" and donnees["id"] == id_
    assert donnees["statut"] == "A FAIRE"


def test_add_refuse(v):
    avant_sauvegardes = len(v.sauvegardes())
    r = v("add", "Sans tag", env=avant(before_add=v.refus))
    assert r.code == 1 and "Le hook dit non." in r.err and "Refusé par le hook before_add" in r.err and "code 3" in r.err
    assert v.taches() == {} and len(v.sauvegardes()) == avant_sauvegardes
    assert "Tâche ajoutée" not in r.texte


def test_add_decision_selon_la_tache(v):
    env = avant(before_add=v.exige_tag)
    r = v("add", "Sans tag", env=env)
    assert r.code == 1 and "Ajoutez au moins un tag." in r.err and v.taches() == {}
    assert v("add", "Avec tag", "--tags", "pro", env=env).code == 0
    assert v("add", "Aussi #pro", env=env).code == 0
    assert sorted(t["titre"] for t in v.taches().values()) == ["Aussi", "Avec tag"]


def test_add_refuse_json(v):
    r = v("add", "X", "--format", "json", env=avant(before_add=v.refus))
    o = json.loads(r.out)
    assert r.code == 1 and o["ok"] is False and o["errors"] == ["hook_refused"] and o["tasks"] == [] and "Le hook dit non." not in r.out


def test_add_refuse_journal(v):
    v("add", "X", env=avant(before_add=v.refus) | {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "warning"})
    assert any("WARNING" in l and "hook_refused" in l and "hook=before_add" in l and "code=3" in l for l in v.journal())


def test_add_refuse_ni_hook_apres_ni_webhook(v):
    s = Serveur()
    try:
        env = avant(before_add=v.refus, on_add=v.espion, on_change=v.espion) | webhook(s)
        v("add", "X", env=env)
        assert lignes(v) == [] and s.recu == []                                   # rien de modifié : aucun hook « après »
    finally:
        s.fermer()


def test_add_accepte_puis_hook_apres(v):
    v("add", "X", env=avant(before_add=v.espion, on_add=v.espion))
    assert [l.split("|")[0] for l in lignes(v) if l.startswith(("before_add", "on_add"))] == ["before_add", "on_add"]


# ------------------------------------------------------------------ done
def test_done_recoit_la_tache_avant_modification(v):
    v("add", "A")
    i = v.une("A")["id"]
    assert v("done", i, env=avant(before_done=v.espion)).code == 0
    nom, phase, evt, id_, titre, nb, projet, garde = lignes(v)[0].split("|")
    assert (nom, phase, evt, id_, titre, nb) == ("before_done", "before", "done", i, "A", "1")
    assert json.loads(lignes(v)[1])["statut"] == "A FAIRE" and json.loads(lignes(v)[1])["id"] == i   # état d'avant
    assert v.une("A")["statut"] == "TERMINE"


def test_done_refuse(v):
    v("add", "A")
    r = v("done", v.id_de("A"), env=avant(before_done=v.refus))
    assert r.code == 1 and "Refusé par le hook before_done" in r.err and v.une("A")["statut"] == "A FAIRE"
    assert "validée" not in r.texte


def test_done_lot_refus_partiel(v):
    for t in ("Ok1", "Bloquee", "Ok2"):
        v("add", t)
    r = v("done", "--all", "-y", env=avant(before_done=v.refuse_titre))
    assert r.code == 1 and "Bloquee refusee" in r.err
    assert {t["titre"]: t["statut"] for t in v.taches().values()} == {"Ok1": "TERMINE", "Bloquee": "A FAIRE", "Ok2": "TERMINE"}


def test_done_lot_json(v):
    for t in ("Ok1", "Bloquee"):
        v("add", t)
    r = v("done", "--all", "-y", "--format", "json", env=avant(before_done=v.refuse_titre))
    o = json.loads(r.out)
    assert r.code == 1 and o["ok"] is False and o["count"] == 1 and o["tasks"][0]["titre"] == "Ok1" and o["errors"] == ["hook_refused"]
    assert o["failed"] == 1


def test_done_lot_un_appel_par_tache(v):
    for t in ("A", "B", "C"):
        v("add", t)
    v("done", "--all", "-y", env=avant(before_done=v.espion))
    appels = [l.split("|") for l in lignes(v) if l.startswith("before_done")]
    assert sorted(a[4] for a in appels) == ["A", "B", "C"] and {a[5] for a in appels} == {"3"}


def test_done_tache_deja_terminee_sans_hook(v):
    v("add", "A")
    v("done", v.id_de("A"))
    v("done", v.id_de("A"), env=avant(before_done=v.refus))
    assert "Refusé" not in v("done", v.id_de("A"), env=avant(before_done=v.refus)).err


def test_done_refuse_pas_de_hook_apres(v):
    v("add", "A")
    v("done", v.id_de("A"), env=avant(before_done=v.refus, on_done=v.espion, on_change=v.espion))
    assert lignes(v) == []


def test_done_dry_run_sans_hook(v):
    v("add", "A")
    v("done", "--all", "--dry-run", env=avant(before_done=v.espion))
    assert lignes(v) == []


def test_done_recurrente_n_appelle_pas_before_add(v):
    v("add", "Arroser", "--repeat", "daily")
    v("done", v.id_de("Arroser"), env=avant(before_done=v.espion, before_add=v.refus))
    assert len(v.taches()) == 2 and sorted(t["statut"] for t in v.taches().values()) == ["A FAIRE", "TERMINE"]


# ------------------------------------------------------------------ garde-fous
def test_hook_introuvable_refuse_par_precaution(v):
    r = v("add", "A", env=avant(before_add="/nexiste/pas"))
    assert r.code == 1 and "impossible de lancer" in r.err and "TODO_HOOKS_ENABLED=0" in r.err and v.taches() == {}


def test_hook_mal_forme_refuse(v):
    r = v("add", "A", env=avant(before_add="echo 'ouvert"))
    assert r.code == 1 and "commande invalide" in r.err and v.taches() == {}


def test_hook_trop_lent_refuse(v):
    r = v("add", "A", env=avant(before_add="sleep 5", timeout="1"))
    assert r.code == 1 and "interrompue après 1 s" in r.err and v.taches() == {}


def test_contournement_par_hooks_enabled(v):
    assert v("add", "A", env=avant(before_add=v.refus, enabled="0")).code == 0 and v.une("A")


def test_pas_de_recursion(v):
    assert v("add", "A", env=avant(before_add=v.refus) | {"TODO_IN_HOOK": "1"}).code == 0


def test_sans_reglage_rien_ne_change(v):
    assert v("add", "A").code == 0 and v("done", v.id_de("A")).code == 0


def test_sortie_du_hook_sur_stderr(v):
    r = v("add", "A", "--format", "json", env=avant(before_add="echo bonjour-avant"))
    assert r.code == 0 and "bonjour-avant" not in r.out and "bonjour-avant" in r.err and json.loads(r.out)["ok"]


def test_dans_le_fichier_de_configuration(v):
    v.config(f"[hooks]\nbefore_add = {v.refus}\n")
    assert v("add", "A").code == 1 and v.taches() == {}


def test_projet_transmis(v):
    v("project", "create", "pro")
    v("add", "A", "-p", "pro", env=avant(before_add=v.espion))
    assert lignes(v)[0].split("|")[6] == "pro"


def test_seed_ne_declenche_pas_before_add(v):
    r = v("admin", "seed", "3", env=avant(before_add=v.refus))
    assert r.code == 0 and len(v.taches()) == 3
