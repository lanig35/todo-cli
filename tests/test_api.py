"""API REST (`todo serve`, module serveur) : requêtes via le client de test de Flask (ignoré sans Flask) et un essai du vrai serveur.

Le serveur lance le CLI en sous-processus : chaque requête passe donc par le vrai programme et sa base temporaire.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from outils import RACINE, SCRIPT, jour

pytest.importorskip("flask")
sys.path.insert(0, str(RACINE))
from todo_cli import serveur  # noqa: E402

P = serveur.PREFIXE
JETON = "jeton-de-test"
EN_TETE = {"Authorization": f"Bearer {JETON}"}


class Client:
    """Petit enrobage du client de test : JSON en entrée, (statut, JSON, en-têtes) en sortie."""

    def __init__(self, app):
        self.c = app.test_client()

    def appeler(self, methode, chemin, corps=None, entetes=None, brut=None):
        h = {**EN_TETE, **(entetes or {})}
        if corps is not None:
            r = self.c.open(P + chemin, method=methode, json=corps, headers=h)
        else:
            r = self.c.open(P + chemin, method=methode, headers=h, data=brut)
        return r.status_code, r.get_json(silent=True), r.headers

    def get(self, chemin, **kw):
        return self.appeler("GET", chemin, **kw)

    def post(self, chemin, corps=None, **kw):
        return self.appeler("POST", chemin, corps, **kw)

    def patch(self, chemin, corps, **kw):
        return self.appeler("PATCH", chemin, corps, **kw)

    def delete(self, chemin, **kw):
        return self.appeler("DELETE", chemin, **kw)


@pytest.fixture
def api(todo, monkeypatch):
    """Client de l'API sur la base temporaire de `todo` ; `api.todo` pilote le CLI sur la même base."""
    for k in [k for k in os.environ if k.startswith("TODO_")]:
        monkeypatch.delenv(k)
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    client = Client(serveur.creer_application(token=JETON, delai=30))
    client.todo = todo
    return client


def ajouter(api, titre="Tâche", **champs):
    statut, corps, _ = api.post("/tasks", {"titre": titre, **champs})
    assert statut == 201, corps
    return corps["tasks"][0]


# ---------------------------------------------------------------- authentification
def test_sante_sans_jeton(api):
    r = api.c.get(P + "/health")
    assert r.status_code == 200 and r.get_json()["ok"] is True


@pytest.mark.parametrize("entetes", [{}, {"Authorization": "Bearer faux"}, {"Authorization": "Basic " + JETON},
                                     {"Authorization": JETON}])
def test_jeton_obligatoire(api, entetes):
    r = api.c.get(P + "/tasks", headers=entetes)
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "unauthorized"
    assert "Bearer" in r.headers["WWW-Authenticate"]


def test_ecriture_sans_jeton_refusee(api):
    r = api.c.post(P + "/tasks", json={"titre": "x"})
    assert r.status_code == 401
    assert api.todo("list", "--format", "json").json() == []


def test_serveur_refuse_de_demarrer_sans_jeton():
    with pytest.raises(RuntimeError, match="jeton"):
        serveur.creer_application(token="")


# ---------------------------------------------------------------- ajout
def test_ajout(api):
    statut, corps, h = api.post("/tasks", {"titre": "Appeler Paul", "priorite": "high", "date_echeance": "demain",
                                           "tags": ["pro", "tel"], "description": "vite"})
    assert statut == 201 and corps["ok"] and corps["count"] == 1
    t = corps["tasks"][0]
    assert (t["titre"], t["priorite"], t["date_echeance"], t["tags"], t["description"]) == \
           ("Appeler Paul", "high", jour(1), ["pro", "tel"], "vite")
    assert h["Location"] == f"{P}/tasks/{t['id']}" and h["ETag"].startswith('"')
    assert api.get(f"/tasks/{t['id']}")[1]["titre"] == "Appeler Paul"


def test_ajout_titre_litteral_par_defaut(api):
    t = ajouter(api, "Appeler Paul !high #pro demain")
    assert t["titre"] == "Appeler Paul !high #pro demain" and t["priorite"] == "medium" and t["tags"] == []


def test_ajout_saisie_rapide_sur_demande(api):
    t = ajouter(api, "Appeler Paul !high #pro", saisie_rapide=True)
    assert t["titre"] == "Appeler Paul" and t["priorite"] == "high" and t["tags"] == ["pro"]


@pytest.mark.parametrize("titre", ["--help", "-p autre", "--format=text", "--all"])
def test_un_titre_ne_passe_jamais_pour_une_option(api, titre):
    assert ajouter(api, titre)["titre"] == titre


def test_ajout_recurrence_et_dependance(api):
    a = ajouter(api, "A")
    b = ajouter(api, "B", apres=[a["id"]], date_echeance="demain", recurrence="weekly")
    assert b["bloquee_par"] == [a["id"]] and b["recurrence"] == "1w"


@pytest.mark.parametrize("corps,statut,code", [
    ({}, 422, "empty_title"), ({"titre": "  "}, 422, "empty_title"), ({"titre": 5}, 422, "empty_title"),
    ({"titre": "x", "couleur": "bleu"}, 400, "invalid_body"),
    ({"titre": "x", "tags": 3}, 400, "invalid_body"),
    ({"titre": "x", "date_echeance": "blabla"}, 422, "invalid_date"),
    ({"titre": "x", "priorite": "urgent"}, 400, None),
    ({"titre": "x", "apres": ["abc"]}, 404, "unknown_id"),
])
def test_ajout_invalide(api, corps, statut, code):
    s, c, _ = api.post("/tasks", corps)
    assert s == statut
    if code:
        assert c["error"]["code"] == code
    assert api.todo("list", "--format", "json").json() == []


def test_corps_non_json(api):
    r = api.c.post(P + "/tasks", data="pas du json", headers={**EN_TETE, "Content-Type": "application/json"})
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "invalid_body"
    r = api.c.post(P + "/tasks", headers=EN_TETE)
    assert r.status_code == 400


def test_corps_trop_gros(api):
    s, c, _ = api.post("/tasks", {"titre": "x" * 200000})
    assert s == 413 and c["error"]["code"] == "too_large"


# ---------------------------------------------------------------- lecture
def test_liste_et_filtres(api):
    ajouter(api, "Un", priorite="high", tags=["pro"])
    ajouter(api, "Deux", tags=["perso"])
    t3 = ajouter(api, "Trois", date_echeance="demain")
    api.post(f"/tasks/{t3['id']}/done")
    titres = lambda q: sorted(t["titre"] for t in api.get("/tasks" + q)[1]["tasks"])
    assert titres("") == ["Deux", "Trois", "Un"]               # comme `todo list` : tout, terminées comprises
    assert titres("?status=todo") == ["Deux", "Un"]
    assert titres("?status=done") == ["Trois"]
    assert titres("?tag=pro") == ["Un"]
    assert titres("?prio=high") == ["Un"]
    assert titres("?search=deux") == ["Deux"]
    assert titres("?status=todo&limit=1") in (["Deux"], ["Un"])
    assert titres("?no_tag=true&status=todo") == []
    assert titres("?has_notes=false&status=todo") == ["Deux", "Un"]


@pytest.mark.parametrize("q", ["?bogus=1", "?limit=abc", "?limit=-1", "?overdue=peut-etre", "?sort=--help"])
def test_liste_parametre_invalide(api, q):
    s, c, _ = api.get("/tasks" + q)
    assert s == 400, c


def test_afficher_inconnu_ou_invalide(api):
    assert api.get("/tasks/abcdef")[0] == 404
    assert api.get("/tasks/pas-un-id!")[0] == 404
    assert api.get("/tasks/--help")[0] == 404


def test_afficher_par_prefixe(api):
    t = ajouter(api, "Préfixe")
    s, c, _ = api.get(f"/tasks/{t['id'][:8]}")
    assert s == 200 and c["id"] == t["id"]


def test_projets_prochaines_agenda_stats(api):
    ajouter(api, "Demain", date_echeance="demain")
    assert api.get("/projects")[1]["courant"] == "default"
    assert [t["titre"] for t in api.get("/next")[1]["tasks"]] == ["Demain"]
    assert api.get("/next?n=1&prio=high")[1]["tasks"] == []
    ag = api.get("/agenda?days=3")[1]
    assert "jours" in ag and "en_retard" in ag
    assert api.get("/stats")[1]["total"] == 1
    assert api.get("/next?n=x")[0] == 400
    assert api.get("/stats?x=1")[0] == 400


def test_projet_en_parametre(api):
    api.todo("project", "create", "pro")
    api.todo("add", "Dans pro", "-p", "pro")
    assert api.get("/tasks")[1]["tasks"] == []
    assert [t["titre"] for t in api.get("/tasks?project=pro")[1]["tasks"]] == ["Dans pro"]
    t = ajouter_dans(api, "pro", "Autre")
    assert api.get(f"/tasks/{t['id']}?project=pro")[0] == 200
    assert api.get(f"/tasks/{t['id']}")[0] == 404
    assert api.get("/tasks?project=inconnu")[0] == 404
    assert api.get("/tasks?project=a/b")[0] == 422
    assert api.get("/tasks?project=--help")[0] == 422


def ajouter_dans(api, projet, titre):
    s, c, _ = api.post(f"/tasks?project={projet}", {"titre": titre})
    assert s == 201, c
    return c["tasks"][0]


def test_vues(api):
    ajouter(api, "Haute", priorite="high")
    ajouter(api, "Basse", priorite="low")
    assert api.todo("view", "save", "urgent", "list", "--prio", "high").code == 0
    assert [v["vue"] for v in api.get("/views")[1]["vues"]] == ["urgent"]
    s, c, _ = api.get("/views/urgent")
    assert s == 200 and c["view"] == "urgent" and [t["titre"] for t in c["result"]] == ["Haute"]
    assert api.get("/views/inconnue")[0] == 404
    assert api.get("/views/a b")[0] == 404


# ---------------------------------------------------------------- modification
def test_modifier(api):
    t = ajouter(api, "Avant", tags=["a"], date_echeance="demain", recurrence="weekly")
    s, c, h = api.patch(f"/tasks/{t['id']}", {"titre": "Après", "priorite": "high", "ajouter_tags": ["b"], "note": "ok"})
    assert s == 200
    n = c["tasks"][0]
    assert (n["titre"], n["priorite"], n["tags"]) == ("Après", "high", ["a", "b"]) and n["notes"][-1]["texte"] == "ok"
    assert h["ETag"] != api.get(f"/tasks/{t['id']}")[2].get("X") and h["ETag"] == api.get(f"/tasks/{t['id']}")[2]["ETag"]


def test_modifier_effacer_avec_null(api):
    t = ajouter(api, "T", tags=["a"], date_echeance="demain", recurrence="weekly", description="d")
    s, c, _ = api.patch(f"/tasks/{t['id']}", {"date_echeance": None, "recurrence": None, "tags": [], "description": ""})
    assert s == 200, c
    n = c["tasks"][0]
    assert (n["date_echeance"], n["recurrence"], n["tags"], n["description"]) == (None, None, [], "")


@pytest.mark.parametrize("corps,statut", [({}, 422), ({"inconnu": 1}, 400), ({"titre": None}, 400),
                                          ({"date_echeance": "xx"}, 422), ({"priorite": "zz"}, 400), ({"titre": 4}, 400)])
def test_modifier_invalide(api, corps, statut):
    t = ajouter(api, "T")
    assert api.patch(f"/tasks/{t['id']}", corps)[0] == statut
    assert api.get(f"/tasks/{t['id']}")[1]["titre"] == "T"


def test_modifier_inconnu(api):
    s, c, _ = api.patch("/tasks/abcdef12", {"titre": "x"})
    assert s == 404 and c["error"]["code"] == "unknown_id"


# ---------------------------------------------------------------- ETag / If-Match
def test_etag_stable_puis_change(api):
    t = ajouter(api, "E")
    e1 = api.get(f"/tasks/{t['id']}")[2]["ETag"]
    assert api.get(f"/tasks/{t['id']}")[2]["ETag"] == e1
    api.patch(f"/tasks/{t['id']}", {"titre": "E2"})
    assert api.get(f"/tasks/{t['id']}")[2]["ETag"] != e1


def test_if_match_refuse_si_modifiee(api):
    t = ajouter(api, "E")
    etag = api.get(f"/tasks/{t['id']}")[2]["ETag"]
    api.todo("task", "edit", t["id"], "--title", "Changée ailleurs")
    s, c, h = api.patch(f"/tasks/{t['id']}", {"priorite": "high"}, entetes={"If-Match": etag})
    assert s == 412 and c["error"]["code"] == "precondition_failed"
    assert h["ETag"] != etag
    assert api.get(f"/tasks/{t['id']}")[1]["priorite"] == "medium"        # rien n'a été écrit
    # avec l'étiquette à jour, ça passe
    assert api.patch(f"/tasks/{t['id']}", {"priorite": "high"}, entetes={"If-Match": h["ETag"]})[0] == 200


@pytest.mark.parametrize("methode,chemin,corps", [("DELETE", "", None), ("POST", "/done", None), ("POST", "/start", None)])
def test_if_match_vaut_pour_toutes_les_ecritures(api, methode, chemin, corps):
    t = ajouter(api, "E")
    s, _, _ = api.appeler(methode, f"/tasks/{t['id']}{chemin}", corps, entetes={"If-Match": '"autre"'})
    assert s == 412
    assert api.get(f"/tasks/{t['id']}")[1]["statut"] == "A FAIRE"


def test_if_match_etoile_et_absent(api):
    t = ajouter(api, "E")
    assert api.patch(f"/tasks/{t['id']}", {"priorite": "low"}, entetes={"If-Match": "*"})[0] == 200
    assert api.patch(f"/tasks/{t['id']}", {"priorite": "high"})[0] == 200


# ---------------------------------------------------------------- actions
def test_done_undone(api):
    t = ajouter(api, "D")
    s, c, _ = api.post(f"/tasks/{t['id']}/done", {"note": "fini"})
    assert s == 200 and c["tasks"][0]["statut"] == "TERMINE" and c["tasks"][0]["notes"][-1]["texte"] == "fini"
    s, c, _ = api.post(f"/tasks/{t['id']}/done")                  # déjà terminée : rien à faire, pas une erreur
    assert s == 200 and c["count"] == 0
    s, c, _ = api.post(f"/tasks/{t['id']}/undone")
    assert s == 200 and c["tasks"][0]["statut"] == "A FAIRE"


def test_done_recurrente_donne_la_suivante(api):
    t = ajouter(api, "R", date_echeance="demain", recurrence="daily")
    c = api.post(f"/tasks/{t['id']}/done")[1]
    assert c["tasks"][0]["suivante"]


def test_start_unstart(api):
    t = ajouter(api, "S")
    c = api.post(f"/tasks/{t['id']}/start", {"at": "hier 9:15"})[1]
    assert c["tasks"][0]["demarree"].endswith("09:15")
    c = api.post(f"/tasks/{t['id']}/unstart")[1]
    assert c["tasks"][0]["demarree"] is None


def test_postpone(api):
    t = ajouter(api, "P", date_echeance="demain")
    c = api.post(f"/tasks/{t['id']}/postpone", {"to": "+3d"})[1]
    assert c["tasks"][0]["date_echeance"] == jour(4)        # +3d à partir de l'échéance
    s, c, _ = api.post(f"/tasks/{t['id']}/postpone", {"to": "nimporte"})
    assert s == 422 and c["error"]["code"] == "invalid_date"


def test_move(api):
    api.todo("project", "create", "autre")
    t = ajouter(api, "M")
    s, c, _ = api.post(f"/tasks/{t['id']}/move", {"to": "autre"})
    assert s == 200 and c["to"] == "autre"
    assert api.get("/tasks")[1]["tasks"] == []
    assert [x["titre"] for x in api.get("/tasks?project=autre")[1]["tasks"]] == ["M"]
    assert api.post(f"/tasks/{t['id']}/move", {})[0] == 422
    assert api.post(f"/tasks/{t['id']}/move?project=autre", {"to": "fantome"})[0] == 404


def test_action_inconnue_ou_champ_inconnu(api):
    t = ajouter(api, "A")
    assert api.post(f"/tasks/{t['id']}/exploser")[0] == 404
    assert api.post(f"/tasks/{t['id']}/done", {"x": 1})[0] == 400
    assert api.post(f"/tasks/{t['id']}/undone", {"note": "n"})[0] == 400
    assert api.post("/tasks/abcdef12/done")[0] == 404


def test_done_d_une_tache_bloquee_est_permis(api):
    """Comme en ligne de commande : un simple avertissement, la tâche est terminée."""
    a = ajouter(api, "A")
    b = ajouter(api, "B", apres=[a["id"]])
    assert api.get(f"/tasks/{b['id']}")[1]["bloquee_par"] == [a["id"]]
    s, c, _ = api.post(f"/tasks/{b['id']}/done")
    assert s == 200 and c["tasks"][0]["statut"] == "TERMINE"


def test_supprimer(api):
    t = ajouter(api, "X")
    s, c, _ = api.delete(f"/tasks/{t['id']}")
    assert s == 200 and c["tasks"][0]["id"] == t["id"]
    assert api.get(f"/tasks/{t['id']}")[0] == 404
    assert api.delete(f"/tasks/{t['id']}")[0] == 404


def test_methode_ou_route_inconnue(api):
    assert api.appeler("PUT", "/tasks")[0] == 405
    assert api.get("/rien")[0] == 404


# ---------------------------------------------------------------- hooks et cohérence avec le CLI
def test_hook_avant_refuse_via_api(api):
    api.todo.config("[hooks]\nbefore_add = false\n")
    s, c, _ = api.post("/tasks", {"titre": "Refusée"})
    assert s == 409 and c["error"]["code"] == "hook_refused"
    assert api.todo("list", "--format", "json").json() == []


def test_hook_apres_declenche_via_api(api, tmp_path):
    trace = tmp_path / "trace.txt"
    api.todo.config(f"[hooks]\non_add = sh -c 'echo $TODO_TITLE >> {trace}'\n")
    ajouter(api, "Tracée")
    assert trace.read_text().strip() == "Tracée"


def test_undo_annule_une_ecriture_de_l_api(api):
    ajouter(api, "Base")
    ajouter(api, "Éphémère")
    assert api.todo("undo").code == 0
    assert [t["titre"] for t in api.todo("list", "--format", "json").json()] == ["Base"]


def test_ecritures_simultanees(api):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as pool:
        codes = list(pool.map(lambda i: api.post("/tasks", {"titre": f"T{i}"})[0], range(8)))
    assert codes == [201] * 8
    assert len(api.get("/tasks")[1]["tasks"]) == 8


# ---------------------------------------------------------------- vrai serveur
def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_todo_serve_sans_jeton(todo):
    r = todo("serve", "--port", _port_libre(), env={"TODO_SERVER_TOKEN": None})
    assert r.code == 1 and "jeton" in r.texte


def test_todo_serve_de_bout_en_bout(todo):
    port = _port_libre()
    env = {**todo._env({"TODO_SERVER_TOKEN": JETON}), "PYTHONUNBUFFERED": "1"}
    p = subprocess.Popen([sys.executable, "-B", str(SCRIPT), "serve", "--port", str(port)], env=env, cwd=todo.dossier,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    base = f"http://127.0.0.1:{port}{P}"

    def requete(methode, chemin, corps=None, jeton=JETON):
        r = urllib.request.Request(base + chemin, method=methode, data=json.dumps(corps).encode() if corps else None,
                                   headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {jeton}"} if jeton else {})})
        try:
            with urllib.request.urlopen(r, timeout=30) as rep:
                return rep.status, json.loads(rep.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        for _ in range(100):
            try:
                assert requete("GET", "/health", jeton=None)[0] == 200
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        else:
            pytest.fail("le serveur ne répond pas")
        assert requete("GET", "/tasks", jeton=None)[0] == 401
        s, c = requete("POST", "/tasks", {"titre": "Via HTTP"})
        assert s == 201
        s, c = requete("GET", "/tasks")
        assert [t["titre"] for t in c["tasks"]] == ["Via HTTP"]
        assert todo("list", "--format", "json").json()[0]["titre"] == "Via HTTP"
    finally:
        p.terminate()
        p.wait(timeout=10)


def test_config_show_masque_le_jeton(todo):
    r = todo("config", "show", env={"TODO_SERVER_TOKEN": "tres-secret"})
    assert "tres-secret" not in r.texte and "masqué" in r.texte
    assert "tres-secret" not in todo("config", "show", "--format", "json", env={"TODO_SERVER_TOKEN": "tres-secret"}).texte
    assert todo("config", "get", "server.token", env={"TODO_SERVER_TOKEN": "tres-secret"}).sortie.strip() == "tres-secret"
