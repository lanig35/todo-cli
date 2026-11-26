"""Interface web de todo-cli : pages Jinja + Bootstrap servies par le serveur Flask de `todo serve`.

Comme l'API, l'interface ne touche pas à la base : chaque action lance le CLI (voir serveur.Moteur), avec les mêmes verrous,
hooks, journal et `undo`.

Sécurité : connexion par le jeton du serveur (formulaire) -> cookie de session signé (HttpOnly, SameSite=Lax, 12 h) dont la clé
dérive du jeton (changer le jeton déconnecte tout le monde) ; jeton CSRF sur chaque formulaire POST ; échappement automatique de
Jinja ; en-têtes CSP (aucun script en ligne), X-Frame-Options, Cache-Control: no-store ; redirections `next` limitées au site.
"""
import datetime
import hashlib
import hmac
import re
import secrets
import time
from urllib.parse import quote

from .serveur import PREFIXE, ErreurApi, _RE_ID, etag_de, options_ajout, options_modification

_TRIS = ("alpha", "status", "priority", "due")
_PRIORITES = ("low", "medium", "high")
_ACTIONS = ("done", "undone", "start", "unstart", "postpone", "move")
_MESSAGES = {"done": "Tâche terminée.", "undone": "Tâche rouverte.", "start": "Tâche démarrée.",
             "unstart": "Démarrage annulé.", "postpone": "Échéance reportée.", "move": "Tâche déplacée.",
             "delete": "Tâche supprimée.", "edit": "Tâche modifiée.", "add": "Tâche ajoutée.", "note": "Note ajoutée."}
_CSP = ("default-src 'none'; style-src 'self' https://cdn.jsdelivr.net; script-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; font-src https://cdn.jsdelivr.net; connect-src 'self'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'")
_RE_VUE = re.compile(r"^[\w.-]{1,64}$")


def _csv(texte):
    return [t.strip() for t in (texte or "").split(",") if t.strip()]


def adresse_sure(cible, defaut="/"):
    """`next` n'est suivi que s'il désigne une page de ce site (pas d'URL absolue, ni `//hote`, ni antislash)."""
    if cible and cible.startswith("/") and not cible.startswith("//") and "\\" not in cible and "\n" not in cible:
        return cible
    return defaut


def enregistrer(app, moteur, token):
    from flask import flash, get_flashed_messages, make_response, redirect, render_template, request, session, url_for
    from . import config

    app.secret_key = hmac.new(token.encode(), b"todo-web-session", hashlib.sha256).digest()
    app.config.update(SESSION_COOKIE_NAME="todo_session", SESSION_COOKIE_SAMESITE="Lax",
                      PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=12))
    cache = {}                                           # navigation (projets, vues) : 10 s, vidé à chaque écriture

    # ------------------------------------------------------------------ outils
    def projet_actif():
        nom = session.get("projet")
        return nom if nom and config._MOTIF_PROJET.match(nom) else None

    def navigation():
        cle, maintenant = projet_actif() or "", time.monotonic()
        trouve = cache.get(cle)
        if trouve and maintenant - trouve[0] < 10:
            return trouve[1]
        try:
            projets = moteur.json(["project", "list"])
            vues = moteur.json(["view", "list"], projet_actif()).get("vues", [])
        except ErreurApi:
            projets, vues = {"courant": "", "projets": []}, []
        nav = {"projets": projets.get("projets", []), "courant": projet_actif() or projets.get("courant", ""), "vues": vues}
        cache[cle] = (maintenant, nav)
        return nav

    def jeton_csrf():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        return session["csrf"]

    def identifiant(valeur):
        if not _RE_ID.match(valeur):
            raise ErreurApi(404, "unknown_id", "Tâche introuvable.")
        return valeur

    def page_erreur(statut, message):
        return make_response(render_template("erreur.html", statut=statut, message=message), statut)

    app.extensions["todo_page_erreur"] = page_erreur

    @app.context_processor
    def contexte():
        return {"csrf_token": jeton_csrf, "nav": navigation, "aujourdhui": datetime.date.today().isoformat(),
                "connecte": bool(session.get("ok")), "chemin": request.full_path.rstrip("?"), "version": __import__("todo_cli").__version__}

    def ecrire(mots, options=(), positionnels=(), id_=None, etag=None):
        """Écriture sous le verrou du serveur ; `etag` (champ caché du formulaire) refuse une tâche modifiée entre-temps."""
        with moteur.ecriture:
            if etag and id_:
                if etag_de(moteur.json(["show"], projet_actif(), positionnels=[id_])) != etag:
                    raise ErreurApi(412, "precondition_failed",
                                    "La tâche a été modifiée depuis l'ouverture du formulaire : relisez-la avant de réessayer.")
            resultat = moteur.ecrire(mots, projet_actif(), list(options), list(positionnels))
        cache.clear()
        return resultat

    def retour(defaut):
        return redirect(adresse_sure(request.form.get("next"), defaut))

    def tenter(action, fonction, defaut):
        """Exécute une écriture : message de succès ou d'erreur, puis redirection."""
        try:
            resultat = fonction()
        except ErreurApi as e:
            flash(e.message, "info" if e.code == "nothing_to_edit" else "danger")
            return retour(defaut)
        if isinstance(resultat, dict) and resultat.get("count") == 0:
            flash("Rien à faire (déjà dans cet état ?).", "info")
        else:
            flash(_MESSAGES[action], "success")
        return retour(defaut)

    # ------------------------------------------------------------------ garde, en-têtes
    @app.before_request
    def garde():
        chemin = request.path
        if chemin.startswith(PREFIXE) or chemin.startswith("/static/"):
            return None
        if request.method == "POST":
            voulu, fourni = session.get("csrf", ""), request.form.get("csrf", "")
            if not voulu or not hmac.compare_digest(voulu.encode(), fourni.encode()):
                return page_erreur(400, "Formulaire expiré ou invalide (jeton CSRF) : rechargez la page et recommencez.")
        if chemin == "/login" or session.get("ok"):
            return None
        return redirect(url_for("connexion", next=request.full_path.rstrip("?")))

    @app.after_request
    def entetes(reponse):
        if not request.path.startswith(PREFIXE):
            reponse.headers["Content-Security-Policy"] = _CSP
            reponse.headers["X-Frame-Options"] = "DENY"
            reponse.headers["X-Content-Type-Options"] = "nosniff"
            reponse.headers["Referrer-Policy"] = "same-origin"
            if not request.path.startswith("/static/"):
                reponse.headers["Cache-Control"] = "no-store"
        return reponse

    # ------------------------------------------------------------------ connexion
    @app.route("/login", methods=["GET", "POST"])
    def connexion():
        if request.method == "POST":
            if hmac.compare_digest(request.form.get("jeton", "").encode(), token.encode()):
                suite = adresse_sure(request.form.get("next"))
                session.clear()
                session.permanent = True
                session["ok"] = True
                jeton_csrf()
                return redirect(suite)
            time.sleep(1)                                # ralentit les essais en rafale
            flash("Jeton invalide.", "danger")
            return make_response(render_template("login.html", suivant=request.form.get("next", "")), 401)
        return render_template("login.html", suivant=request.args.get("next", ""))

    @app.post("/logout")
    def deconnexion():
        session.clear()
        return redirect(url_for("connexion"))

    @app.post("/project")
    def changer_projet():
        nom = request.form.get("projet", "")
        if nom and not config._MOTIF_PROJET.match(nom):
            flash("Nom de projet invalide.", "danger")
        elif nom:
            session["projet"] = nom
        else:
            session.pop("projet", None)
        return redirect(url_for("accueil"))

    # ------------------------------------------------------------------ lecture
    @app.get("/")
    def accueil():
        statut = request.args.get("status", "todo")
        tri = request.args.get("sort", "")
        priorite = request.args.get("prio", "")
        options = []
        if statut in ("todo", "done"):
            options.append(f"--status={statut}")
        if request.args.get("q", "").strip():
            options.append(f"--search={request.args['q'].strip()}")
        if request.args.get("tag", "").strip():
            options.append(f"--tag={request.args['tag'].strip()}")
        if tri in _TRIS:
            options.append(f"--sort={tri}")
        if priorite in _PRIORITES:
            options.append(f"--prio={priorite}")
        taches = moteur.json(["list"], projet_actif(), options)
        return render_template("index.html", taches=taches, filtres={"status": statut, "sort": tri, "prio": priorite,
                               "q": request.args.get("q", ""), "tag": request.args.get("tag", "")})

    @app.get("/tasks/<id_>")
    def detail(id_):
        tache = moteur.json(["show"], projet_actif(), positionnels=[identifiant(id_)])
        return render_template("detail.html", t=tache, etag=etag_de(tache))

    @app.get("/agenda")
    def page_agenda():
        jours = request.args.get("days", "7")
        jours = int(jours) if jours.isdigit() and 1 <= int(jours) <= 60 else 7
        return render_template("agenda.html", ag=moteur.json(["agenda"], projet_actif(), [f"--days={jours}"]), jours=jours)

    @app.get("/stats")
    def page_stats():
        brut = moteur.json(["report", "stats"], projet_actif())
        return render_template("stats.html", s={k: v for k, v in brut.items() if not k.startswith("tag.")},
                               tags=sorted(((k[4:], v) for k, v in brut.items() if k.startswith("tag.")), key=lambda x: -x[1]))

    @app.get("/views/<nom>")
    def page_vue(nom):
        if not _RE_VUE.match(nom):
            raise ErreurApi(404, "not_found", "Vue inconnue.")
        resultat = moteur.json(["view", "run"], projet_actif(), fin=[nom, "--format=json"])
        liste = resultat if isinstance(resultat, list) and all(isinstance(x, dict) and "titre" in x for x in resultat) else None
        return render_template("vue.html", nom=nom, taches=liste, brut=None if liste is not None else resultat)

    # ------------------------------------------------------------------ écriture
    @app.post("/tasks")
    def form_ajouter():
        f = request.form
        corps = {"titre": f.get("titre", "")}
        for champ in ("description", "priorite", "date_echeance", "recurrence"):
            if f.get(champ, "").strip():
                corps[champ] = f[champ].strip()
        if _csv(f.get("tags")):
            corps["tags"] = _csv(f["tags"])
        if f.get("saisie_rapide"):
            corps["saisie_rapide"] = True

        def faire():
            titre, options = options_ajout(corps)
            return ecrire(["add"], options, [titre])
        return tenter("add", faire, url_for("accueil"))

    @app.post("/tasks/<id_>/edit")
    def form_modifier(id_):
        id_ = identifiant(id_)
        f = request.form
        corps = {"titre": f.get("titre", ""), "description": f.get("description", ""),
                 "priorite": f.get("priorite", "medium"), "tags": _csv(f.get("tags")),
                 "date_echeance": f.get("date_echeance", "").strip() or None,
                 "recurrence": f.get("recurrence", "").strip() or None}
        return tenter("edit", lambda: ecrire(["task", "edit"], options_modification(corps) + ["-y"], [id_], id_, f.get("etag")),
                      url_for("detail", id_=id_))

    @app.post("/tasks/<id_>/note")
    def noter(id_):
        id_ = identifiant(id_)
        texte = request.form.get("note", "").strip()
        if not texte:
            flash("La note est vide.", "info")
            return retour(url_for("detail", id_=id_))
        return tenter("note", lambda: ecrire(["task", "edit"], options_modification({"note": texte}) + ["-y"], [id_]),
                      url_for("detail", id_=id_))

    @app.post("/tasks/<id_>/delete")
    def form_supprimer(id_):
        id_ = identifiant(id_)
        return tenter("delete", lambda: ecrire(["task", "remove"], ["-y"], [id_], id_, request.form.get("etag")),
                      url_for("accueil"))

    @app.post("/tasks/<id_>/<action>")
    def form_agir(id_, action):
        if action not in _ACTIONS:
            raise ErreurApi(404, "not_found", "Action inconnue.")
        id_ = identifiant(id_)
        f = request.form
        options = ["-y"]
        cible = f.get("to", "").strip()
        if action in ("postpone", "move"):
            if not cible:
                flash("Indiquez une date." if action == "postpone" else "Indiquez le projet cible.", "danger")
                return retour(url_for("detail", id_=id_))
            options.append(f"--to={cible}")
        if f.get("note", "").strip() and action in ("done", "start", "postpone"):
            options.append(f"--note={f['note'].strip()}")
        mots = ["done"] if action == "done" else ["task", action]
        # après un déplacement, la tâche n'est plus dans ce projet : retour à la liste
        defaut = url_for("accueil") if action == "move" else url_for("detail", id_=id_)
        return tenter(action, lambda: ecrire(mots, options, [id_], id_, f.get("etag")), defaut)
