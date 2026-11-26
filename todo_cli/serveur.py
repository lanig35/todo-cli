"""API REST de todo-cli (Flask) : `todo serve`.

Le serveur ne touche pas à la base : chaque requête lance le CLI dans un sous-processus avec `--format json` et en
renvoie le résultat. Les verrous, les hooks (y compris « avant »), la journalisation, l'archivage automatique, `undo`
et les sauvegardes se comportent donc exactement comme en ligne de commande.

Flask est une dépendance optionnelle (`pip install flask`, ou `pip install 'todo-cli[server]'`) : le reste du programme
n'en a pas besoin, ce module n'est importé que par `todo serve`.

Sécurité : un jeton est obligatoire (`[server] token` ou TODO_SERVER_TOKEN), envoyé dans `Authorization: Bearer …` ;
seul `GET /api/v1/health` en est dispensé. Aucune requête n'est interprétée par un shell : le sous-processus reçoit une
liste d'arguments, les valeurs prennent la forme `--option=valeur` (une valeur ne peut jamais passer pour une option) et
les identifiants et noms de projet sont validés.
"""
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import threading

from . import __version__, config

PREFIXE = "/api/v1"
_RE_ID = re.compile(r"^[0-9a-fA-F-]{1,36}$")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_PROGRAMME = "from todo_cli.cli import executer; executer()"

# Paramètres de filtre de GET /tasks (et de /next, /agenda pour ceux qui y existent) -> option du CLI
_FILTRES_VALEUR = ("status", "search", "search_in", "tag", "any_tag", "not_tag", "prio", "not_prio", "created_after",
                   "created_before", "done_after", "done_before", "due_before", "due_after", "sort", "limit", "start")
_FILTRES_BOOLEENS = ("no_tag", "overdue", "today", "no_due", "blocked", "ready", "started", "not_started", "recurring",
                     "no_recurring", "has_notes", "no_notes", "has_files", "no_files", "all_projects")
_ENTIERS = ("limit", "start", "days", "n")

# Champs d'une tâche acceptés en entrée (mêmes noms qu'en sortie) -> option de `add` / `task edit`
_CHAMPS_AJOUT = {"description": "desc", "priorite": "prio", "date_echeance": "due", "recurrence": "repeat"}
_CHAMPS_MODIF = {"titre": "title", "description": "desc", "priorite": "prio", "date_echeance": "due",
                 "recurrence": "repeat"}
_ACTIONS = ("done", "undone", "start", "unstart", "postpone", "move")

# Raison technique du journal -> statut HTTP (les raisons absentes valent 400)
_STATUT_ERREUR = {"unknown_id": 404, "unknown_project": 404, "invalid_target_project": 404, "ambiguous_id": 409, "duplicate_id": 409,
                  "db_locked": 503, "dependency_cycle": 409, "hook_refused": 409, "hook_timeout": 409,
                  "hook_unavailable": 409, "hook_invalid": 409, "hook_error": 409, "not_done": 409,
                  "next_occurrence_done": 409, "postpone_done_task": 409, "start_done_task": 409}
_STATUT_422 = ("invalid_date", "invalid_priority", "invalid_repeat", "invalid_duration", "empty_title", "empty_note",
               "note_too_long", "recurrence_needs_due", "date_out_of_range", "invalid_combination",
               "nothing_to_edit", "empty_id", "invalid_project_name")


class ErreurApi(Exception):
    """Erreur renvoyée telle quelle au client : {"error": {"code", "message"}}."""

    def __init__(self, statut, code, message, **extra):
        super().__init__(message)
        self.statut, self.code, self.message, self.extra = statut, code, message, extra


def nettoyer(texte):
    """Message du CLI sans couleurs ni pictogrammes de tête."""
    texte = _ANSI.sub("", texte or "").strip()
    return re.sub(r"^[^\w'\"`(]+", "", texte.splitlines()[0] if texte else "").strip() or "erreur"


def classer_echec(code, stderr):
    """(statut HTTP, raison) d'une commande de lecture qui a échoué (sans JSON d'erreur)."""
    texte = nettoyer(stderr)
    if code == 2:
        return 400, "usage"
    if "Aucun identifiant" in texte or "liste est vide" in texte:
        return 404, "unknown_id"
    if "n'existe pas" in texte or "introuvable" in texte:
        return 404, "not_found"
    if "verrou" in texte.lower():
        return 503, "db_locked"
    return 400, "bad_request"


def etag_de(tache):
    """Empreinte d'une tâche (valeur de l'en-tête ETag, guillemets compris)."""
    contenu = json.dumps(tache, sort_keys=True, ensure_ascii=False).encode()
    return '"' + hashlib.sha256(contenu).hexdigest()[:16] + '"'


class Moteur:
    """Lance le CLI dans un sous-processus ; les écritures sont sérialisées (un seul verrou, côté serveur)."""

    def __init__(self, delai=30):
        self.delai = delai
        self.ecriture = threading.Lock()
        racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.env = {k: v for k, v in os.environ.items() if k not in ("TODO_SERVER_TOKEN", "TODO_FORMAT", "TODO_PROJECT")}
        self.programme = f"import sys; sys.path.insert(0, {racine!r}); sys.argv[0] = 'todo'; {_PROGRAMME}"
        self.env["NO_COLOR"] = "1"

    def lancer(self, mots, projet=None, options=(), positionnels=(), fin=()):
        """Exécute `todo <mots> [--project=P] [options] -- positionnels` ; retourne (code, stdout, stderr).

        `fin` : arguments laissés tels quels après tout le reste (nom de vue et son `--format=json`).
        """
        argv = [*mots, "--color=never"]
        if not fin:
            argv.append("--format=json")
        if projet:
            argv.append(f"--project={projet}")
        argv += list(options)
        if positionnels:
            argv += ["--", *positionnels]
        argv += list(fin)
        try:
            r = subprocess.run([sys.executable, "-c", self.programme, *argv], capture_output=True, text=True,
                               timeout=self.delai, env=self.env, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise ErreurApi(504, "timeout", f"la commande a dépassé {self.delai} s") from None
        return r.returncode, r.stdout, r.stderr

    def json(self, mots, projet=None, options=(), positionnels=(), fin=()):
        """Lecture : le JSON de la commande, ou ErreurApi."""
        code, sortie, erreur = self.lancer(mots, projet, options, positionnels, fin)
        if code != 0:
            erreur = erreur or sortie                  # certains messages (liste vide) partent sur stdout
            statut, raison = classer_echec(code, erreur)
            raise ErreurApi(statut, raison, nettoyer(erreur))
        try:
            return json.loads(sortie)
        except ValueError:
            raise ErreurApi(500, "bad_output", "sortie du CLI illisible") from None

    def ecrire(self, mots, projet=None, options=(), positionnels=()):
        """Écriture : (JSON d'écriture du CLI) ou ErreurApi ; à appeler sous `self.ecriture`."""
        code, sortie, erreur = self.lancer(mots, projet, options, positionnels)
        try:
            resultat = json.loads(sortie)
        except ValueError:
            resultat = None
        if code == 0 and isinstance(resultat, dict):
            return resultat
        if isinstance(resultat, dict) and resultat.get("errors"):
            raison = resultat["errors"][0]
            statut = _STATUT_ERREUR.get(raison, 422 if raison in _STATUT_422 else 400)
            raise ErreurApi(statut, raison, nettoyer(erreur), result=resultat)
        erreur = erreur or sortie
        statut, raison = classer_echec(code, erreur)
        raise ErreurApi(statut, raison, nettoyer(erreur))


def _liste(valeur, nom):
    """Liste de chaînes (ou chaîne séparée par des virgules) -> 'a,b'."""
    if isinstance(valeur, str):
        valeur = [v for v in valeur.split(",") if v.strip()]
    if not isinstance(valeur, list) or not all(isinstance(v, str) for v in valeur):
        raise ErreurApi(400, "invalid_body", f"« {nom} » doit être une liste de chaînes")
    return ",".join(v.strip() for v in valeur)


def _texte(valeur, nom):
    if not isinstance(valeur, str):
        raise ErreurApi(400, "invalid_body", f"« {nom} » doit être une chaîne")
    return valeur


def options_ajout(corps):
    """(titre, options) de `add` d'après le corps JSON."""
    inconnus = set(corps) - {"titre", "description", "priorite", "date_echeance", "recurrence", "tags", "apres", "saisie_rapide"}
    if inconnus:
        raise ErreurApi(400, "invalid_body", f"champs inconnus : {', '.join(sorted(inconnus))}")
    titre = corps.get("titre")
    if not isinstance(titre, str) or not titre.strip():
        raise ErreurApi(422, "empty_title", "« titre » est obligatoire")
    options = [] if corps.get("saisie_rapide") else ["--literal"]
    for champ, option in _CHAMPS_AJOUT.items():
        if corps.get(champ) is not None:
            options.append(f"--{option}={_texte(corps[champ], champ)}")
    for champ, option in (("tags", "tags"), ("apres", "after")):
        if corps.get(champ):
            options.append(f"--{option}={_liste(corps[champ], champ)}")
    return titre, options


def options_modification(corps):
    """Options de `task edit` d'après le corps JSON (null = supprimer, quand le CLI le permet)."""
    inconnus = set(corps) - set(_CHAMPS_MODIF) - {"tags", "apres", "ajouter_tags", "retirer_tags", "note"}
    if inconnus:
        raise ErreurApi(400, "invalid_body", f"champs inconnus : {', '.join(sorted(inconnus))}")
    options = []
    for champ, option in _CHAMPS_MODIF.items():
        if champ in corps:
            valeur = corps[champ]
            if valeur is None and champ in ("date_echeance", "recurrence"):
                valeur = "none"
            elif valeur is None:
                raise ErreurApi(400, "invalid_body", f"« {champ} » ne peut pas être null")
            options.append(f"--{option}={_texte(valeur, champ)}")
    if "tags" in corps:
        options.append(f"--tags={_liste(corps['tags'] or [], 'tags')}")
    if "apres" in corps:
        options.append(f"--after={_liste(corps['apres'] or [], 'apres') or 'none'}")
    for champ, option in (("ajouter_tags", "add-tag"), ("retirer_tags", "remove-tag")):
        if corps.get(champ):
            options.append(f"--{option}={_liste(corps[champ], champ)}")
    if corps.get("note"):
        options.append(f"--note={_texte(corps['note'], 'note')}")
    return options


def options_requete(args, valeurs, booleens, extras=()):
    """Options du CLI d'après la chaîne de requête ; un paramètre inconnu est refusé (400)."""
    connus = set(valeurs) | set(booleens) | set(extras) | {"project"}
    inconnus = set(args) - connus
    if inconnus:
        raise ErreurApi(400, "unknown_parameter", f"paramètre(s) inconnu(s) : {', '.join(sorted(inconnus))}")
    options = []
    for nom in valeurs:
        if nom in args:
            valeur = args[nom]
            if nom in _ENTIERS and not valeur.isdigit():
                raise ErreurApi(400, "invalid_parameter", f"« {nom} » doit être un entier")
            options.append(f"--{nom.replace('_', '-')}={valeur}")
    for nom in booleens:
        if args.get(nom, "").lower() in ("1", "true", "yes", "oui", "on", ""):
            if nom in args:
                options.append(f"--{nom.replace('_', '-')}")
        elif args.get(nom, "").lower() not in ("0", "false", "no", "non", "off"):
            raise ErreurApi(400, "invalid_parameter", f"« {nom} » doit valoir true ou false")
    return options


def creer_application(token=None, delai=None, taille_max=None, web=None):
    """Application Flask. Sans argument, lit les réglages `[server]` (utilisable par gunicorn : `todo_cli.serveur:creer_application()`)."""
    try:
        from flask import Flask, jsonify, make_response, request
    except ImportError:
        raise RuntimeError("Flask n'est pas installé : pip install flask (ou pip install 'todo-cli[server]')") from None
    from . import reglages
    token = token if token is not None else reglages.obtenir("server", "token")
    if not token:
        raise RuntimeError("aucun jeton : définir [server] token (todo config set server.token …) ou TODO_SERVER_TOKEN")
    delai = delai or reglages.obtenir("server", "timeout")
    taille_max = taille_max or reglages.obtenir("server", "max_body")
    web = reglages.obtenir("server", "web") if web is None else web

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.config["MAX_CONTENT_LENGTH"] = taille_max
    moteur = Moteur(delai)
    app.extensions["todo_moteur"] = moteur

    def repondre(donnees, statut=200, etag=None, **entetes):
        r = make_response(jsonify(donnees), statut)
        if etag:
            r.headers["ETag"] = etag
        for k, v in entetes.items():
            r.headers[k.replace("_", "-")] = v
        return r

    def projet_demande():
        nom = request.args.get("project")
        if nom is None:
            return None
        if not config._MOTIF_PROJET.match(nom):
            raise ErreurApi(422, "invalid_project_name", f"nom de projet invalide : {nom!r}")
        return nom

    def identifiant(valeur):
        if not _RE_ID.match(valeur):
            raise ErreurApi(404, "unknown_id", "identifiant invalide")
        return valeur

    def corps_json(obligatoire=True):
        if not request.get_data():
            if obligatoire:
                raise ErreurApi(400, "invalid_body", "corps JSON attendu")
            return {}
        corps = request.get_json(silent=True)
        if not isinstance(corps, dict):
            raise ErreurApi(400, "invalid_body", "le corps doit être un objet JSON (Content-Type: application/json)")
        return corps

    def verifier_etag(id_, projet):
        """Si-Match : refuse (412) quand la tâche a changé depuis la lecture. Sous le verrou d'écriture."""
        voulu = request.headers.get("If-Match")
        if not voulu or voulu.strip() == "*":
            return
        tache = moteur.json(["show", id_], projet)
        if etag_de(tache) not in [v.strip().removeprefix("W/") for v in voulu.split(",")]:
            raise ErreurApi(412, "precondition_failed", "la tâche a été modifiée depuis votre lecture", etag=etag_de(tache))

    def resultat_ecriture(resultat, statut=200, **entetes):
        taches = resultat.get("tasks") or []
        etag = etag_de({k: v for k, v in taches[0].items()}) if len(taches) == 1 and "titre" in taches[0] else None
        return repondre(resultat, statut, etag, **entetes)

    @app.before_request
    def authentifier():
        if not request.path.startswith(PREFIXE + "/") or request.path == PREFIXE + "/health":
            return None                      # l'interface web a sa propre garde (session) : voir web.py
        fourni = request.headers.get("Authorization", "")
        schema, _, valeur = fourni.partition(" ")
        if schema.lower() != "bearer" or not hmac.compare_digest(valeur.strip().encode(), token.encode()):
            r = repondre({"error": {"code": "unauthorized", "message": "jeton manquant ou invalide"}}, 401)
            r.headers["WWW-Authenticate"] = 'Bearer realm="todo"'
            return r
        return None

    def page_html(statut, message):
        """Page d'erreur de l'interface web (None pour l'API, qui répond en JSON)."""
        if request.path.startswith(PREFIXE) or "todo_page_erreur" not in app.extensions:
            return None
        return app.extensions["todo_page_erreur"](statut, message)

    @app.errorhandler(ErreurApi)
    def erreur_api(e):
        page = page_html(e.statut, e.message)
        if page is not None:
            return page
        corps = {"error": {"code": e.code, "message": e.message}}
        corps.update(e.extra.get("result") and {"result": e.extra["result"]} or {})
        return repondre(corps, e.statut, e.extra.get("etag"))

    @app.errorhandler(404)
    def non_trouve(_):
        page = page_html(404, "Page introuvable.")
        if page is not None:
            return page
        return repondre({"error": {"code": "not_found", "message": "ressource inconnue"}}, 404)

    @app.errorhandler(405)
    def methode(_):
        page = page_html(405, "Méthode non autorisée.")
        if page is not None:
            return page
        return repondre({"error": {"code": "method_not_allowed", "message": "méthode non autorisée"}}, 405)

    @app.errorhandler(413)
    def trop_gros(_):
        page = page_html(413, "Formulaire trop volumineux.")
        if page is not None:
            return page
        return repondre({"error": {"code": "too_large", "message": "corps trop volumineux"}}, 413)

    @app.errorhandler(Exception)
    def inattendue(e):
        app.logger.exception("erreur inattendue")
        page = page_html(500, "Erreur interne.")
        if page is not None:
            return page
        return repondre({"error": {"code": "internal", "message": "erreur interne"}}, 500)

    # ---- lecture ----
    @app.get(PREFIXE + "/health")
    def sante():
        return repondre({"ok": True, "version": __version__})

    @app.get(PREFIXE + "/projects")
    def projets():
        return repondre(moteur.json(["project", "list"]))

    @app.get(PREFIXE + "/tasks")
    def lister():
        options = options_requete(request.args, _FILTRES_VALEUR, _FILTRES_BOOLEENS)
        return repondre({"tasks": moteur.json(["list"], projet_demande(), options)})

    @app.get(PREFIXE + "/tasks/<id_>")
    def afficher(id_):
        tache = moteur.json(["show"], projet_demande(), positionnels=[identifiant(id_)])
        return repondre(tache, etag=etag_de(tache))

    @app.get(PREFIXE + "/next")
    def prochaines():
        options = options_requete(request.args, ("tag", "prio"), ("all_projects",), extras=("n",))
        if "n" in request.args:
            if not request.args["n"].isdigit():
                raise ErreurApi(400, "invalid_parameter", "« n » doit être un entier")
            options += ["-n", request.args["n"]]
        return repondre({"tasks": moteur.json(["next"], projet_demande(), options)})

    @app.get(PREFIXE + "/agenda")
    def agenda():
        options = options_requete(request.args, ("days", "from"), ("all_projects",))
        return repondre(moteur.json(["agenda"], projet_demande(), options))

    @app.get(PREFIXE + "/stats")
    def stats():
        options_requete(request.args, (), ())
        return repondre(moteur.json(["report", "stats"], projet_demande()))

    @app.get(PREFIXE + "/views")
    def vues():
        return repondre(moteur.json(["view", "list"], projet_demande()))

    @app.get(PREFIXE + "/views/<nom>")
    def vue(nom):
        if not re.match(r"^[\w.-]{1,64}$", nom):
            raise ErreurApi(404, "not_found", "vue inconnue")
        return repondre({"view": nom, "result": moteur.json(["view", "run"], projet_demande(), fin=[nom, "--format=json"])})

    # ---- écriture ----
    @app.post(PREFIXE + "/tasks")
    def ajouter():
        titre, options = options_ajout(corps_json())
        with moteur.ecriture:
            resultat = moteur.ecrire(["add"], projet_demande(), options, [titre])
        taches = resultat.get("tasks") or []
        lieu = f"{PREFIXE}/tasks/{taches[0]['id']}" if taches else None
        return resultat_ecriture(resultat, 201, **({"Location": lieu} if lieu else {}))

    @app.patch(PREFIXE + "/tasks/<id_>")
    def modifier(id_):
        id_ = identifiant(id_)
        options = options_modification(corps_json()) + ["-y"]
        projet = projet_demande()
        with moteur.ecriture:
            verifier_etag(id_, projet)
            resultat = moteur.ecrire(["task", "edit"], projet, options, [id_])
        return resultat_ecriture(resultat)

    @app.delete(PREFIXE + "/tasks/<id_>")
    def supprimer(id_):
        id_ = identifiant(id_)
        projet = projet_demande()
        with moteur.ecriture:
            verifier_etag(id_, projet)
            resultat = moteur.ecrire(["task", "remove"], projet, ["-y"], [id_])
        return resultat_ecriture(resultat)

    @app.post(PREFIXE + "/tasks/<id_>/<action>")
    def agir(id_, action):
        if action not in _ACTIONS:
            raise ErreurApi(404, "not_found", f"action inconnue : {action}")
        id_ = identifiant(id_)
        corps = corps_json(obligatoire=False)
        autorises = {"note"} | {"done": set(), "undone": set(), "start": {"at"}, "unstart": set(),
                                "postpone": {"to"}, "move": {"to"}}[action]
        if set(corps) - autorises:
            raise ErreurApi(400, "invalid_body", f"champs inconnus : {', '.join(sorted(set(corps) - autorises))}")
        options = ["-y"]
        if action == "move":
            options.append(f"--to={_texte(corps.get('to', ''), 'to')}")
            if not corps.get("to"):
                raise ErreurApi(422, "invalid_combination", "« to » (projet cible) est obligatoire")
        elif corps.get("to"):
            options.append(f"--to={_texte(corps['to'], 'to')}")
        if corps.get("at"):
            options.append(f"--at={_texte(corps['at'], 'at')}")
        if corps.get("note") and action in ("done", "start", "postpone"):
            options.append(f"--note={_texte(corps['note'], 'note')}")
        elif corps.get("note"):
            raise ErreurApi(400, "invalid_body", f"« note » n'existe pas pour {action}")
        mots = ["done"] if action == "done" else ["task", action]
        projet = projet_demande()
        with moteur.ecriture:
            verifier_etag(id_, projet)
            resultat = moteur.ecrire(mots, projet, options, [id_])
        return resultat_ecriture(resultat)

    if web:
        from . import web as interface
        interface.enregistrer(app, moteur, token)
    return app


def servir(hote=None, port=None):
    """Lance le serveur (Werkzeug, multi-threads) : `todo serve`. Retourne un code de sortie."""
    from . import reglages
    hote = hote or reglages.obtenir("server", "host")
    port = port or reglages.obtenir("server", "port")
    try:
        app = creer_application()
    except RuntimeError as e:
        print(f" ❌ Erreur : {e}", file=sys.stderr)
        return 1
    if hote not in ("127.0.0.1", "localhost", "::1"):
        print(f" ⚠️  Le serveur écoute sur {hote} sans chiffrement : placez-le derrière un proxy HTTPS (le jeton circule en clair).",
              file=sys.stderr)
    print(f" 🌐 todo-cli {__version__} : interface web http://{hote}:{port}/  ·  API http://{hote}:{port}{PREFIXE}/  (Ctrl-C pour arrêter)")
    app.run(host=hote, port=port, threaded=True, use_reloader=False)
    return 0
