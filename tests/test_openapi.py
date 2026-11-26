"""Description OpenAPI de l'API (todo_cli/openapi.json) : cohérence avec les routes réelles, exactitude des schémas, mode proxy."""
import copy
import json
import os
import re
import sys

import pytest

from outils import RACINE

pytest.importorskip("flask")
sys.path.insert(0, str(RACINE))
from todo_cli import __version__, serveur  # noqa: E402

CHEMIN = RACINE / "todo_cli" / "openapi.json"
JETON = "jeton-openapi"
ENTETES = {"Authorization": f"Bearer {JETON}"}
METHODES = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def spec():
    return json.loads(CHEMIN.read_text(encoding="utf-8"))


@pytest.fixture
def app(todo, monkeypatch):
    for k in [k for k in os.environ if k.startswith("TODO_")]:
        monkeypatch.delenv(k)
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    return serveur.creer_application(token=JETON, web=False)


def _refs(noeud):
    if isinstance(noeud, dict):
        for k, v in noeud.items():
            if k == "$ref":
                yield v
            else:
                yield from _refs(v)
    elif isinstance(noeud, list):
        for v in noeud:
            yield from _refs(v)


def _resoudre(spec, ref):
    noeud = spec
    for morceau in ref.removeprefix("#/").split("/"):
        noeud = noeud[morceau]
    return noeud


# ---------------------------------------------------------------- forme du document
def test_document_bien_forme(spec):
    assert spec["openapi"].startswith("3.0")
    assert spec["info"]["title"] and spec["paths"]
    for ref in _refs(spec):
        _resoudre(spec, ref)                                 # lève KeyError si une référence est cassée
    ids = [op["operationId"] for chemin in spec["paths"].values() for m, op in chemin.items() if m in METHODES]
    assert len(ids) == len(set(ids)) and all(re.match(r"^[a-zA-Z][a-zA-Z0-9]*$", i) for i in ids)


def test_parametres_de_chemin_declares(spec):
    for chemin, item in spec["paths"].items():
        for methode, op in item.items():
            if methode not in METHODES:
                continue
            declares = {(_resoudre(spec, p["$ref"]) if "$ref" in p else p)["name"] for p in op.get("parameters", [])
                        if (_resoudre(spec, p["$ref"]) if "$ref" in p else p)["in"] == "path"}
            assert declares == set(re.findall(r"\{(\w+)\}", chemin)), (methode, chemin)


def test_securite_sauf_health_et_description(spec):
    publics = {("/health", "get"), ("/openapi.json", "get")}
    for chemin, item in spec["paths"].items():
        for methode, op in item.items():
            if methode in METHODES:
                assert (op.get("security") == []) == ((chemin, methode) in publics), (methode, chemin)
                if (chemin, methode) not in publics:
                    assert op["security"] == [{"bearer": []}]


def test_toutes_les_routes_sont_documentees_et_inversement(spec, app):
    reelles = set()
    for regle in app.url_map.iter_rules():
        if not regle.rule.startswith(serveur.PREFIXE + "/"):
            continue
        chemin = regle.rule.removeprefix(serveur.PREFIXE)
        chemin = chemin.replace("<id_>", "{id}").replace("<nom>", "{nom}")
        for methode in regle.methods - {"HEAD", "OPTIONS"}:
            if "<action>" in chemin:
                reelles |= {(chemin.replace("<action>", a), methode.lower()) for a in serveur._ACTIONS}
            else:
                reelles.add((chemin, methode.lower()))
    documentees = {(c, m) for c, item in spec["paths"].items() for m in item if m in METHODES}
    assert reelles == documentees


def test_parametres_de_filtre_documentes(spec):
    """Les filtres de GET /tasks acceptés par le serveur sont exactement ceux du document."""
    documentes = {p["name"] for p in spec["paths"]["/tasks"]["get"]["parameters"] if "name" in p}
    assert documentes == set(serveur._FILTRES_VALEUR) | set(serveur._FILTRES_BOOLEENS)
    assert {"$ref": "#/components/parameters/project"} in spec["paths"]["/tasks"]["get"]["parameters"]


def test_champs_de_creation_et_modification_documentes(spec):
    s = spec["components"]["schemas"]
    assert set(s["TacheEntree"]["properties"]) == {"titre", "description", "priorite", "date_echeance", "recurrence", "tags", "apres", "saisie_rapide"}
    assert set(s["TacheModification"]["properties"]) == {"titre", "description", "priorite", "date_echeance", "recurrence", "tags", "apres",
                                                         "ajouter_tags", "retirer_tags", "note"}


def test_document_servi_sans_jeton(app, spec):
    c = app.test_client()
    r = c.get(serveur.PREFIXE + "/openapi.json")
    assert r.status_code == 200
    servi = r.get_json()
    assert servi["info"]["version"] == __version__
    servi["info"]["version"] = spec["info"]["version"]
    assert servi == spec


def test_validateur_externe(spec):
    validateur = pytest.importorskip("openapi_spec_validator")
    validateur.validate(spec)


# ---------------------------------------------------------------- les réponses respectent les schémas
def _validateur(spec, nom):
    jsonschema = pytest.importorskip("jsonschema")
    composants = copy.deepcopy(spec["components"])

    def convertir(n):
        if isinstance(n, dict):
            if n.get("nullable") and isinstance(n.get("type"), str):
                n["type"] = [n["type"], "null"]
            n.pop("nullable", None)
            for v in n.values():
                convertir(v)
        elif isinstance(n, list):
            for v in n:
                convertir(v)
    convertir(composants)
    return jsonschema.Draft7Validator({"$ref": f"#/components/schemas/{nom}", "components": composants})


def verifier(spec, nom, donnees):
    erreurs = list(_validateur(spec, nom).iter_errors(donnees))
    assert not erreurs, [e.message for e in erreurs[:3]]


def test_reponses_conformes_aux_schemas(spec, app, todo):
    c = app.test_client()
    appeler = lambda m, u, **kw: c.open(serveur.PREFIXE + u, method=m, headers=ENTETES, **kw)
    r = appeler("POST", "/tasks", json={"titre": "T", "priorite": "high", "date_echeance": "demain", "tags": ["a"], "recurrence": "weekly"})
    assert r.status_code == 201
    verifier(spec, "Ecriture", r.get_json())
    t = r.get_json()["tasks"][0]
    verifier(spec, "Tache", appeler("GET", f"/tasks/{t['id']}").get_json())
    for tache in appeler("GET", "/tasks").get_json()["tasks"]:
        verifier(spec, "Tache", tache)
    verifier(spec, "Ecriture", appeler("PATCH", f"/tasks/{t['id']}", json={"note": "n", "priorite": "low", "tags": []}).get_json())
    verifier(spec, "Ecriture", appeler("POST", f"/tasks/{t['id']}/start").get_json())
    verifier(spec, "Ecriture", appeler("POST", f"/tasks/{t['id']}/done", json={"note": "ok"}).get_json())
    verifier(spec, "Projets", appeler("GET", "/projects").get_json())
    verifier(spec, "Agenda", appeler("GET", "/agenda").get_json())
    verifier(spec, "Stats", appeler("GET", "/stats").get_json())
    todo("view", "save", "tout", "list")
    verifier(spec, "Vues", appeler("GET", "/views").get_json())
    for erreur in (appeler("GET", "/tasks/abcdef12"), appeler("POST", "/tasks", json={"titre": " "}), appeler("GET", "/tasks?x=1"),
                   c.get(serveur.PREFIXE + "/tasks")):
        assert erreur.status_code >= 400
        verifier(spec, "Erreur", erreur.get_json())
    verifier(spec, "Erreur", appeler("POST", f"/tasks/{t['id']}/move", json={"to": "fantome"}).get_json())


# ---------------------------------------------------------------- mode proxy
def test_cookie_secure_derriere_un_proxy(todo, monkeypatch):
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    res = lambda: serveur.creer_application(token=JETON).test_client().get("/login", headers={"X-Forwarded-Proto": "https"})
    assert "Secure" not in res().headers.get("Set-Cookie", "")
    monkeypatch.setenv("TODO_SERVER_PROXY", "1")
    assert "Secure" in res().headers["Set-Cookie"]


def test_en_tetes_x_forwarded_pris_en_compte_seulement_avec_proxy(todo, monkeypatch):
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    from flask import request
    for proxy, attendu in (("0", "http"), ("1", "https")):
        monkeypatch.setenv("TODO_SERVER_PROXY", proxy)
        app = serveur.creer_application(token=JETON, web=False)

        @app.get("/schema-vu")
        def schema_vu():
            return request.scheme
        assert app.test_client().get("/schema-vu", headers={"X-Forwarded-Proto": "https"}).get_data(as_text=True) == attendu
