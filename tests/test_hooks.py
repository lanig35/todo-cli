"""Hooks : commande lancée après une modification (réglages [hooks])."""
import json
import os
import sys
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


# ------------------------------------------------------------------ régression : tâche supprimée ou déplacée
def test_hook_de_suppression_silencieux(hook):
    """Retrouver une tâche supprimée ne doit ni écrire « Aucun identifiant… » ni noter d'échec dans le journal."""
    hook("add", "À jeter")
    i = hook.une("À jeter")["id"]
    env = avec(hook, on_remove=hook.script, on_change=hook.script) | {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "info"}
    r = hook("task", "remove", i[:8], "-y", env=env)
    assert r.code == 0 and "Aucun identifiant" not in r.texte and "❌" not in r.texte
    assert not any("unknown_id" in l or l.startswith(("WARNING", "ERROR")) for l in hook.journal())
    assert [l.split("|")[2] for l in hook.lignes()] == [i, i]          # identifiant complet, même pour une tâche disparue


# ------------------------------------------------------------------ webhook HTTP
import http.server
import threading
import time


class Serveur:
    def __init__(self, statut=204, pause=0):
        recu = self.recu = []
        self.statut = statut
        serveur = self

        class Gestionnaire(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                corps = self.rfile.read(int(self.headers["Content-Length"]))
                recu.append({"en_tetes": dict(self.headers), "corps": json.loads(corps), "chemin": self.path})
                time.sleep(pause)
                try:
                    self.send_response(serveur.statut)
                    self.end_headers()
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        self.url = f"http://127.0.0.1:{self.http.server_port}/todo"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def fermer(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def serveur():
    s = Serveur()
    yield s
    s.fermer()


def webhook(serveur, **autres):
    return {"TODO_HOOKS_WEBHOOK_URL": serveur.url, **{f"TODO_HOOKS_{k.upper()}": v for k, v in autres.items()}}


def test_webhook_post_json(hook, serveur):
    assert hook("add", "Rapport", "--prio", "high", "--tags", "pro", env=webhook(serveur, webhook_token="s3cret")).code == 0
    (r,) = serveur.recu
    assert r["chemin"] == "/todo" and r["en_tetes"]["Content-Type"] == "application/json"
    assert r["en_tetes"]["X-Todo-Event"] == "add" and r["en_tetes"]["Authorization"] == "Bearer s3cret"
    assert r["en_tetes"]["User-Agent"].startswith("todo-cli/")
    c = r["corps"]
    assert c["event"] == "add" and c["project"] == "default" and c["count"] == 1 and c["version"]
    tache = hook.une("Rapport")
    assert c["ids"] == [tache["id"]] and c["tasks"][0]["id"] == tache["id"]
    assert c["tasks"][0]["titre"] == "Rapport" and c["tasks"][0]["priorite"] == "high" and c["tasks"][0]["tags"] == ["pro"]


def test_webhook_sans_jeton_pas_d_authorization(hook, serveur):
    hook("add", "A", env=webhook(serveur))
    assert "Authorization" not in serveur.recu[0]["en_tetes"]


def test_webhook_une_requete_par_commande(hook, serveur):
    for t in ("A", "B", "C"):
        hook("add", t)
    hook("task", "done", "--all", "-y", env=webhook(serveur))
    (r,) = serveur.recu
    assert r["corps"]["event"] == "done" and r["corps"]["count"] == 3
    assert sorted(t["titre"] for t in r["corps"]["tasks"]) == ["A", "B", "C"]


def test_webhook_gros_lot_sans_detail(hook, serveur):
    hook.seed(*[{"cle": f"k{n:04d}", "titre": f"T{n}"} for n in range(25)])
    hook("task", "done", "--all", "-y", env=webhook(serveur))
    c = serveur.recu[0]["corps"]
    assert c["count"] == 25 and len(c["ids"]) == 25 and "tasks" not in c


def test_webhook_commande_sans_tache(hook, serveur):
    hook("add", "A")
    hook("done", hook.id_de("A"))
    hook("undo", env=webhook(serveur))
    c = serveur.recu[0]["corps"]
    assert c["event"] == "undo" and c["count"] == 0 and c["tasks"] == []


def test_webhook_tache_supprimee(hook, serveur):
    hook("add", "À jeter")
    i = hook.une("À jeter")["id"]
    hook("task", "remove", i, "-y", env=webhook(serveur))
    c = serveur.recu[0]["corps"]
    assert c["event"] == "remove" and c["ids"] == [i] and c["tasks"] == [{"id": i, "titre": "À jeter"}]


def test_webhook_filtre_d_evenements(hook, serveur):
    env = webhook(serveur, webhook_events="done, remove")
    hook("add", "A", env=env)
    assert serveur.recu == []
    hook("done", hook.id_de("A"), env=env)
    assert [r["corps"]["event"] for r in serveur.recu] == ["done"]


def test_webhook_evenement_inconnu_signale(hook, serveur):
    r = hook("add", "A", env=webhook(serveur, webhook_events="done, truc"))
    assert r.code == 0 and "truc" in r.err and serveur.recu == []


def test_webhook_aucun_envoi_sans_modification(hook, serveur):
    hook("add", "A")
    hook("list", env=webhook(serveur))
    hook("show", hook.id_de("A"), env=webhook(serveur))
    hook("add", "B", "--dry-run", env=webhook(serveur))
    hook("done", "zzzzzzzz", env=webhook(serveur))
    assert serveur.recu == []


def test_webhook_desactivation_et_recursion(hook, serveur):
    hook("add", "A", env=webhook(serveur, enabled="0"))
    hook("add", "B", env=webhook(serveur) | {"TODO_IN_HOOK": "1"})
    assert serveur.recu == []


def test_webhook_et_hook_commande_ensemble(hook, serveur):
    hook("add", "A", env=webhook(serveur) | avec(hook, on_add=hook.script))
    assert len(serveur.recu) == 1 and len(hook.lignes()) == 1


def test_webhook_pas_pour_les_vues(hook, serveur):
    hook("view", "save", "x", "--overdue", env=webhook(serveur))
    assert serveur.recu == []


@pytest.mark.parametrize("url,attendu", [("ftp://exemple.org/x", "URL invalide"), ("pas une url", "URL invalide"),
                                         ("http://", "URL invalide")])
def test_webhook_url_invalide(hook, url, attendu):
    r = hook("add", "A", env={"TODO_HOOKS_WEBHOOK_URL": url})
    assert r.code == 0 and attendu in r.err and hook.une("A")


def test_webhook_connexion_refusee(hook):
    s = Serveur()
    s.fermer()
    r = hook("add", "A", env=webhook(s))
    assert r.code == 0 and "envoi impossible" in r.err


@pytest.mark.parametrize("statut", [400, 500])
def test_webhook_erreur_http(hook, statut):
    s = Serveur(statut=statut)
    try:
        r = hook("add", "A", env=webhook(s) | {"TODO_LOG_TARGET": "file", "TODO_LOG_LEVEL": "warning"})
        assert r.code == 0 and f"a répondu {statut}" in r.err
        assert any("WARNING" in l and "hook=webhook_url" in l for l in hook.journal())
    finally:
        s.fermer()


def test_webhook_delai_depasse(hook):
    s = Serveur(pause=3)
    try:
        debut = time.time()
        r = hook("add", "A", env=webhook(s, timeout="1"))
        assert r.code == 0 and "envoi impossible" in r.err and time.time() - debut < 3
    finally:
        s.fermer()


def test_webhook_via_fichier_de_configuration(hook, serveur):
    hook.config(f"[hooks]\nwebhook_url = {serveur.url}\nwebhook_events = add\n")
    hook("add", "A")
    hook("done", hook.id_de("A"))
    assert [r["corps"]["event"] for r in serveur.recu] == ["add"]


# ------------------------------------------------------------------ exemple Redis (faux serveur RESP)
import socket
import sys
from pathlib import Path

REDIS_HOOK = Path(__file__).resolve().parent.parent / "examples" / "hooks" / "redis_hook.py"


class FauxRedis:
    """Comprend juste assez de RESP pour enregistrer les commandes reçues."""

    def __init__(self, mot_de_passe=None):
        self.commandes = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._boucle, daemon=True).start()

    def _boucle(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(c,), daemon=True).start()

    def _client(self, c):
        f = c.makefile("rb")
        while True:
            ligne = f.readline()
            if not ligne:
                return
            mots = []
            for _ in range(int(ligne[1:])):
                n = int(f.readline()[1:])
                mots.append(f.read(n + 2)[:-2].decode())
            self.commandes.append(mots)
            c.sendall({"XADD": b"$3\r\n1-0\r\n", "HSET": b":1\r\n", "HDEL": b":1\r\n"}.get(mots[0], b"+OK\r\n"))

    def fermer(self):
        self.sock.close()


@pytest.fixture
def redis():
    r = FauxRedis()
    yield r
    r.fermer()


def env_redis(redis, **autres):
    return {"TODO_HOOKS_ON_CHANGE": f"{sys.executable} {REDIS_HOOK}", "REDIS_PORT": str(redis.port), **autres}


def test_exemple_redis_ajout_puis_suppression(hook, redis):
    env = env_redis(redis)
    assert hook("add", "Écrire", "--tags", "pro", env=env).code == 0
    tache = hook.une("Écrire")
    xadd = next(c for c in redis.commandes if c[0] == "XADD")
    champs = dict(zip(xadd[6::2], xadd[7::2]))
    assert xadd[1] == "todo:events" and champs["event"] == "add" and champs["id"] == tache["id"] and champs["title"] == "Écrire"
    assert json.loads(champs["task"])["tags"] == ["pro"]
    hset = next(c for c in redis.commandes if c[0] == "HSET")
    assert hset[1:3] == ["todo:tasks:default", tache["id"]] and json.loads(hset[3])["titre"] == "Écrire"
    redis.commandes.clear()
    hook("task", "remove", tache["id"], "-y", env=env)
    assert ["HDEL", "todo:tasks:default", tache["id"]] in redis.commandes


def test_exemple_redis_mot_de_passe_et_flux(hook, redis):
    hook("add", "A", env=env_redis(redis, REDIS_PASSWORD="pw", REDIS_STREAM="mes:evts"))
    assert redis.commandes[0] == ["AUTH", "pw"] and any(c[:2] == ["XADD", "mes:evts"] for c in redis.commandes)


def test_exemple_redis_indisponible_ne_change_rien(hook):
    res = hook("add", "A", env={"TODO_HOOKS_ON_CHANGE": f"{sys.executable} {REDIS_HOOK}", "REDIS_PORT": "1"})
    assert res.code == 0 and "Hook on_change" in res.err and hook.une("A")


# ------------------------------------------------------------------ un hook « après » peut appeler todo (verrou libéré)
def test_hook_apres_peut_appeler_todo(hook, tmp_path):
    """Régression : le verrou de la base était tenu pendant les hooks, un `todo` lancé par le hook attendait 10 s puis échouait."""
    from outils import SCRIPT
    sortie = tmp_path / "liste.log"
    appel = script_appelant = tmp_path / "appelle_todo.sh"
    appel.write_text(f'#!/bin/sh\n"{sys.executable}" -B "{SCRIPT}" list --format plain > {sortie}\n"{sys.executable}" -B "{SCRIPT}" add "Creee par le hook" >> {sortie}\n')
    appel.chmod(appel.stat().st_mode | stat.S_IEXEC)
    debut = time.time()
    r = hook("add", "A", env=avec(hook, on_add=str(appel), timeout="20"))
    assert r.code == 0 and time.time() - debut < 8 and "interrompue" not in r.err
    assert "A" in sortie.read_text().splitlines()[0]
    assert sorted(t["titre"] for t in hook.taches().values()) == ["A", "Creee par le hook"]     # TODO_IN_HOOK : pas de hook en cascade
