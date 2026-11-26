"""Client Python de l'API REST de todo-cli (`todo serve`), au-dessus de `requests` (dépendance optionnelle : extra `tui`).

Utilisé par la TUI (`todo tui`) ; utilisable seul :

    from todo_cli.client import Client
    c = Client("http://127.0.0.1:8765", jeton)
    tache, etag = c.ajouter({"titre": "Appeler Paul", "priorite": "high"})
    c.action(tache["id"], "done", etag=etag)
"""
import os

PREFIXE = "/api/v1"


class ErreurClient(Exception):
    """Échec d'un appel : `statut` HTTP (0 = serveur injoignable), `code` de l'API, `message` lisible, `etag` courant (412)."""

    def __init__(self, statut, code, message, etag=None):
        super().__init__(message)
        self.statut, self.code, self.message, self.etag = statut, code, message, etag

    @property
    def conflit(self):
        return self.statut == 412


def importer_requests():
    try:
        import requests
    except ImportError:
        raise RuntimeError("le module « requests » est requis : pip install requests (ou pip install 'todo-cli[tui]')") from None
    return requests


class Client:
    def __init__(self, url, jeton, delai=15, session=None):
        if not jeton:
            raise ValueError("jeton manquant")
        self.requests = importer_requests()
        self.base = url.rstrip("/") + PREFIXE
        self.delai = delai
        self.session = session or self.requests.Session()
        self.session.headers["Authorization"] = f"Bearer {jeton}"
        self.session.headers["Accept"] = "application/json"

    # ------------------------------------------------------------------ bas niveau
    def _appel(self, methode, chemin, projet=None, params=None, corps=None, etag=None):
        """Retourne (JSON, en-têtes) ou lève ErreurClient."""
        parametres = dict(params or {})
        if projet:
            parametres["project"] = projet
        entetes = {"If-Match": etag} if etag else {}
        try:
            r = self.session.request(methode, self.base + chemin, params=parametres, json=corps, headers=entetes,
                                     timeout=self.delai)
        except self.requests.exceptions.Timeout:
            raise ErreurClient(0, "timeout", "le serveur ne répond pas (délai dépassé)") from None
        except self.requests.exceptions.RequestException as e:
            raise ErreurClient(0, "unreachable", f"serveur injoignable : {type(e).__name__}") from None
        try:
            donnees = r.json()
        except ValueError:
            donnees = None
        if r.status_code >= 400:
            erreur = (donnees or {}).get("error", {}) if isinstance(donnees, dict) else {}
            raise ErreurClient(r.status_code, erreur.get("code", "http_error"),
                               erreur.get("message") or f"erreur HTTP {r.status_code}", r.headers.get("ETag"))
        return donnees, r.headers

    # ------------------------------------------------------------------ lecture
    def sante(self):
        return self._appel("GET", "/health")[0]

    def projets(self):
        return self._appel("GET", "/projects")[0]

    def taches(self, projet=None, **filtres):
        return self._appel("GET", "/tasks", projet, {k: v for k, v in filtres.items() if v not in (None, "")})[0]["tasks"]

    def tache(self, id_, projet=None):
        """(tâche, etag)."""
        donnees, h = self._appel("GET", f"/tasks/{id_}", projet)
        return donnees, h.get("ETag")

    def agenda(self, projet=None, jours=7):
        return self._appel("GET", "/agenda", projet, {"days": jours})[0]

    def stats(self, projet=None):
        return self._appel("GET", "/stats", projet)[0]

    def vues(self, projet=None):
        return self._appel("GET", "/views", projet)[0].get("vues", [])

    def vue(self, nom, projet=None):
        return self._appel("GET", f"/views/{nom}", projet)[0]["result"]

    # ------------------------------------------------------------------ écriture : (tâche | None, etag | None)
    @staticmethod
    def _tache_ecrite(donnees, h):
        taches = (donnees or {}).get("tasks") or []
        return (taches[0] if taches else None), h.get("ETag")

    def ajouter(self, champs, projet=None):
        return self._tache_ecrite(*self._appel("POST", "/tasks", projet, corps=champs))

    def modifier(self, id_, champs, projet=None, etag=None):
        return self._tache_ecrite(*self._appel("PATCH", f"/tasks/{id_}", projet, corps=champs, etag=etag))

    def supprimer(self, id_, projet=None, etag=None):
        return self._tache_ecrite(*self._appel("DELETE", f"/tasks/{id_}", projet, etag=etag))

    def action(self, id_, action, corps=None, projet=None, etag=None):
        """done, undone, start, unstart, postpone, move (`corps` : note, at, to)."""
        return self._tache_ecrite(*self._appel("POST", f"/tasks/{id_}/{action}", projet, corps=corps or {}, etag=etag))


def depuis_reglages(url=None):
    """Client configuré par `[client] url`, `[client] token` (à défaut `[server] token`) et `[client] timeout`."""
    from . import reglages
    url = url or reglages.obtenir("client", "url")
    jeton = reglages.obtenir("client", "token") or reglages.obtenir("server", "token") or os.environ.get("TODO_SERVER_TOKEN", "")
    if not jeton:
        raise RuntimeError("aucun jeton : définir TODO_CLIENT_TOKEN (ou TODO_SERVER_TOKEN, ou [client] token)")
    return Client(url, jeton, reglages.obtenir("client", "timeout"))
