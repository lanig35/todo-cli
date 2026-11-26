"""Interface web (module web, gabarits Jinja) : client de test de Flask, session et CSRF comme un navigateur."""
import html
import os
import re
import sys

import pytest

from outils import RACINE, jour

pytest.importorskip("flask")
sys.path.insert(0, str(RACINE))
from todo_cli import serveur  # noqa: E402

JETON = "jeton-web"


class Navigateur:
    def __init__(self, app, todo):
        self.c = app.test_client()
        self.todo = todo

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def csrf(self, url="/"):
        page = self.c.get(url).text
        m = re.search(r'name="csrf" value="([^"]+)"', page)
        assert m, page[:300]
        return m.group(1)

    def post(self, url, data=None, csrf=True, **kw):
        data = dict(data or {})
        if csrf is True:
            data["csrf"] = self.csrf()
        elif csrf:
            data["csrf"] = csrf
        return self.c.post(url, data=data, **kw)

    def connecter(self):
        r = self.post("/login", {"jeton": JETON}, csrf=self.csrf("/login"))
        assert r.status_code == 302
        return self

    def taches(self, *args):
        return self.todo("list", *args, "--format", "json").json()


@pytest.fixture
def web(todo, monkeypatch):
    for k in [k for k in os.environ if k.startswith("TODO_")]:
        monkeypatch.delenv(k)
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("time.sleep", lambda _: None)           # le délai des mauvais jetons
    return Navigateur(serveur.creer_application(token=JETON), todo).connecter()


def une(web, titre="Tâche", **opts):
    args = [titre]
    for k, v in opts.items():
        args += [f"--{k}", str(v)]
    assert web.todo("add", *args).code == 0
    return [t for t in web.taches() if t["titre"] == titre][0]


# ---------------------------------------------------------------- connexion et garde
def test_pages_protegees_redirigent_vers_la_connexion(todo, monkeypatch):
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    b = Navigateur(serveur.creer_application(token=JETON), todo)
    for url in ("/", "/agenda", "/stats", "/tasks/abcd", "/views/x"):
        r = b.get(url)
        assert r.status_code == 302 and r.headers["Location"].startswith("/login"), url
    assert b.get("/login").status_code == 200


def test_mauvais_jeton(todo, monkeypatch):
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("time.sleep", lambda _: None)
    b = Navigateur(serveur.creer_application(token=JETON), todo)
    r = b.post("/login", {"jeton": "faux"}, csrf=b.csrf("/login"))
    assert r.status_code == 401 and "Jeton invalide" in r.text
    assert b.get("/").status_code == 302


def test_connexion_redirige_vers_next_du_site_seulement(todo, monkeypatch):
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    for suivant, attendu in (("/agenda", "/agenda"), ("//evil.example", "/"), ("https://evil.example", "/"),
                             ("/\\evil", "/"), ("evil", "/")):
        b = Navigateur(serveur.creer_application(token=JETON), todo)
        r = b.post("/login", {"jeton": JETON, "next": suivant}, csrf=b.csrf("/login"))
        assert r.headers["Location"] == attendu, suivant


def test_deconnexion(web):
    assert web.get("/").status_code == 200
    assert web.post("/logout").status_code == 302
    assert web.get("/").status_code == 302


def test_csrf_obligatoire(web):
    n = len(web.taches())
    for csrf in (False, "faux"):
        r = web.post("/tasks", {"titre": "Pirate"}, csrf=csrf)
        assert r.status_code == 400 and "CSRF" in r.text
    assert len(web.taches()) == n
    assert web.post("/logout", csrf=False).status_code == 400


def test_session_et_jeton_api_sont_distincts(web):
    """Le cookie de session n'ouvre pas l'API, et le jeton Bearer n'ouvre pas l'interface."""
    assert web.get("/api/v1/tasks").status_code == 401
    b = web.c.get("/", headers={"Authorization": f"Bearer {JETON}"})
    assert b.status_code == 200                                  # connecté par cookie
    neuf = serveur.creer_application(token=JETON).test_client()
    assert neuf.get("/", headers={"Authorization": f"Bearer {JETON}"}).status_code == 302
    assert neuf.get("/api/v1/health").status_code == 200


def test_en_tetes_de_securite(web):
    r = web.get("/")
    assert "script-src 'self' https://cdn.jsdelivr.net" in r.headers["Content-Security-Policy"]
    assert "unsafe-inline" not in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["Cache-Control"] == "no-store"
    assert "Content-Security-Policy" not in web.get("/api/v1/health").headers
    assert "HttpOnly" in web.get("/login").headers.get("Set-Cookie", "HttpOnly")


def test_pas_de_script_ni_style_en_ligne(web):
    une(web, "Une tâche")
    for url in ("/", "/agenda", "/stats", "/login"):
        page = web.get(url).text
        assert not re.search(r"<script(?![^>]*\bsrc=)", page), url
        assert not re.search(r"\sstyle=|\son[a-z]+=", page), url


def test_page_erreur_html(web):
    r = web.get("/rien")
    assert r.status_code == 404 and "<html" in r.text and "Page introuvable" in r.text
    assert web.get("/api/v1/rien", headers={"Authorization": f"Bearer {JETON}"}).get_json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------- lecture
def test_liste_et_filtres(web):
    une(web, "Zeta", prio="high")
    une(web, "Courses", tags="maison")
    web.todo("done", une(web, "Finie")["id"])
    page = web.get("/").text
    assert "Zeta" in page and "Courses" in page and "Finie" not in page
    assert "Finie" in web.get("/?status=done").text
    assert "Finie" in web.get("/?status=all").text
    assert "Courses" not in web.get("/?prio=high").text
    assert "Courses" in web.get("/?tag=maison").text and "Zeta" not in web.get("/?tag=maison").text
    assert "Courses" in web.get("/?q=cour").text and "Zeta" not in web.get("/?q=cour").text
    assert web.get("/?sort=--help&prio=zzz").status_code == 200       # valeurs hors liste ignorées


def test_echappement_xss(web):
    web.post("/tasks", {"titre": "<script>alert(1)</script>", "description": "<img src=x onerror=alert(1)>", "tags": "<b>"})
    t = web.taches()[0]
    for url in ("/", f"/tasks/{t['id']}", "/stats"):
        page = web.get(url).text
        assert "<script>alert" not in page and "<img src=x" not in page and "<b>" not in page, url
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in web.get("/").text


def test_detail_agenda_stats(web):
    t = une(web, "Demain", due="demain")
    web.todo("task", "edit", t["id"], "--note", "ma note")
    page = web.get(f"/tasks/{t['id']}").text
    assert "Demain" in page and "ma note" in page and jour(1) in page
    assert "Demain" in web.get("/agenda").text and "Demain" in web.get("/agenda?days=3").text
    assert web.get("/agenda?days=abc").status_code == 200
    assert "Total" in web.get("/stats").text


def test_detail_inconnu(web):
    assert web.get("/tasks/abcdef12").status_code == 404
    assert web.get("/tasks/pas-un-id!").status_code == 404


def test_vues(web):
    une(web, "Zeta", prio="high")
    une(web, "Omega", prio="low")
    web.todo("view", "save", "urgent", "list", "--prio", "high")
    assert "urgent" in web.get("/").text                          # dans le menu
    page = web.get("/views/urgent").text
    assert "Zeta" in page and "Omega" not in page
    assert web.get("/views/inconnue").status_code == 404
    assert web.get("/views/a b").status_code == 404


# ---------------------------------------------------------------- écriture
def test_ajouter(web):
    r = web.post("/tasks", {"titre": "Appeler Paul", "priorite": "high", "date_echeance": "demain", "tags": "pro, tel",
                            "description": "vite"})
    assert r.status_code == 302
    t = web.taches()[0]
    assert (t["titre"], t["priorite"], t["date_echeance"], t["tags"], t["description"]) == \
           ("Appeler Paul", "high", jour(1), ["pro", "tel"], "vite")
    assert "Tâche ajoutée" in web.get("/").text


def test_ajouter_titre_litteral_ou_saisie_rapide(web):
    web.post("/tasks", {"titre": "Littéral !high #x"})
    web.post("/tasks", {"titre": "Rapide !high #x", "saisie_rapide": "1"})
    par_titre = {t["titre"]: t for t in web.taches()}
    assert par_titre["Littéral !high #x"]["priorite"] == "medium"
    assert par_titre["Rapide"]["priorite"] == "high" and par_titre["Rapide"]["tags"] == ["x"]


def test_ajouter_invalide(web):
    web.post("/tasks", {"titre": "  "})
    assert "titre" in web.get("/").text.lower() and web.taches() == []
    web.post("/tasks", {"titre": "X", "date_echeance": "blabla"})
    assert web.taches() == []


def test_modifier(web):
    t = une(web, "Avant", tags="a", due="demain")
    etag = _etag(web, t)
    web.post(f"/tasks/{t['id']}/edit", {"titre": "Après", "priorite": "high", "date_echeance": "", "tags": "b, c",
                                        "recurrence": "", "description": "d", "etag": etag})
    n = web.taches()[0]
    assert (n["titre"], n["priorite"], n["date_echeance"], n["tags"], n["description"]) == ("Après", "high", None, ["b", "c"], "d")
    assert "Tâche modifiée" in web.get(f"/tasks/{t['id']}").text


def _etag(web, t):
    return html.unescape(re.search(r'name="etag" value="([^"]+)"', web.get(f"/tasks/{t['id']}").text).group(1))


def test_modifier_conflit_etag(web):
    t = une(web, "Avant")
    etag = _etag(web, t)
    web.todo("task", "edit", t["id"], "--title", "Changée ailleurs")
    web.post(f"/tasks/{t['id']}/edit", {"titre": "Mon écrasement", "priorite": "medium", "etag": etag})
    assert web.taches()[0]["titre"] == "Changée ailleurs"
    assert "modifiée depuis" in web.get(f"/tasks/{t['id']}").text


def test_modifier_sans_changement(web):
    t = une(web, "Stable")
    web.post(f"/tasks/{t['id']}/edit", {"titre": "Stable", "priorite": "medium", "etag": _etag(web, t)})
    assert web.taches()[0]["titre"] == "Stable"


def test_actions(web):
    t = une(web, "Cycle", due="demain")
    i = t["id"]
    web.post(f"/tasks/{i}/start")
    assert web.taches()[0]["demarree"]
    web.post(f"/tasks/{i}/unstart")
    assert not web.taches()[0]["demarree"]
    web.post(f"/tasks/{i}/postpone", {"to": "+3d"})
    assert web.taches()[0]["date_echeance"] == jour(4)
    web.post(f"/tasks/{i}/done", {"note": "fini"})
    assert web.taches()[0]["statut"] == "TERMINE"
    web.post(f"/tasks/{i}/done")
    assert "Rien à faire" in web.get("/").text
    web.post(f"/tasks/{i}/undone")
    assert web.taches()[0]["statut"] == "A FAIRE"


def test_actions_invalides(web):
    t = une(web, "T")
    assert web.post(f"/tasks/{t['id']}/exploser").status_code == 404
    web.post(f"/tasks/{t['id']}/postpone", {"to": ""})
    web.post(f"/tasks/{t['id']}/postpone", {"to": "nimporte"})
    assert web.taches()[0]["date_echeance"] is None
    assert web.post("/tasks/abcdef12/done").status_code == 302          # introuvable : message, pas de plantage


def test_retour_vers_la_page_d_origine(web):
    t = une(web, "T")
    r = web.post(f"/tasks/{t['id']}/done", {"next": "/?status=all"})
    assert r.headers["Location"] == "/?status=all"
    r = web.post(f"/tasks/{t['id']}/undone", {"next": "https://evil.example/"})
    assert "evil" not in r.headers["Location"]


def test_note(web):
    t = une(web, "T")
    web.post(f"/tasks/{t['id']}/note", {"note": "Une note <b>x</b>"})
    page = web.get(f"/tasks/{t['id']}").text
    assert "Une note &lt;b&gt;x&lt;/b&gt;" in page
    web.post(f"/tasks/{t['id']}/note", {"note": "  "})
    assert "La note est vide" in web.get(f"/tasks/{t['id']}").text


def test_supprimer(web):
    t = une(web, "À supprimer")
    web.post(f"/tasks/{t['id']}/delete", {"etag": _etag(web, t)})
    assert web.taches() == []
    assert web.todo("undo").code == 0 and len(web.taches()) == 1


def test_projets_et_deplacement(web):
    web.todo("project", "create", "perso")
    t = une(web, "Voyageuse")
    assert "perso" in web.get(f"/tasks/{t['id']}").text           # proposé comme cible
    web.post("/project", {"projet": "perso"})
    assert "Voyageuse" not in web.get("/").text
    web.post("/project", {"projet": "default"})
    web.post(f"/tasks/{t['id']}/move", {"to": "perso"})
    assert web.taches() == [] and [x["titre"] for x in web.taches("-p", "perso")] == ["Voyageuse"]
    web.post("/project", {"projet": "../x"})
    assert "invalide" in web.get("/").text


def test_hook_avant_refuse_via_le_web(web):
    web.todo.config("[hooks]\nbefore_add = false\n")
    web.post("/tasks", {"titre": "Refusée"})
    assert web.taches() == []
    assert "alert-danger" in web.get("/").text


def test_web_desactive(todo, monkeypatch):
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    app = serveur.creer_application(token=JETON, web=False)
    c = app.test_client()
    assert c.get("/").status_code == 404 and c.get("/api/v1/health").status_code == 200
