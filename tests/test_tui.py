"""Client `requests`, modèle et mise en page de la TUI (sans terminal), puis un essai de `todo tui` dans un pseudo-terminal.

Les appels passent par un vrai serveur HTTP (Werkzeug dans un fil) : API, CLI et base temporaire réels.
"""
import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import threading
import time

import pytest

from outils import RACINE, SCRIPT, jour

pytest.importorskip("flask")
pytest.importorskip("requests")
sys.path.insert(0, str(RACINE))
from werkzeug.serving import make_server  # noqa: E402

from todo_cli import serveur, tui  # noqa: E402
from todo_cli.client import Client, ErreurClient  # noqa: E402
from todo_cli.tui_modele import Etat  # noqa: E402

JETON = "jeton-tui"


class Hote:
    def __init__(self, todo, url):
        self.todo, self.url = todo, url

    def client(self, jeton=JETON, **kw):
        return Client(self.url, jeton, delai=30, **kw)


@pytest.fixture
def hote(todo, monkeypatch):
    for k in [k for k in os.environ if k.startswith("TODO_")]:
        monkeypatch.delenv(k)
    for k, v in todo.env.items():
        monkeypatch.setenv(k, v)
    srv = make_server("127.0.0.1", 0, serveur.creer_application(token=JETON), threaded=True)
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    yield Hote(todo, f"http://127.0.0.1:{srv.server_port}")
    srv.shutdown()
    fil.join(5)


def une(todo, titre, *opts):
    assert todo("add", titre, *opts).code == 0
    return [t for t in todo("list", "--format", "json").json() if t["titre"] == titre][0]


# ---------------------------------------------------------------- client
def test_client_lecture_ecriture(hote):
    c = hote.client()
    assert c.sante()["ok"] and c.projets()["courant"] == "default"
    t, etag = c.ajouter({"titre": "Appeler Paul", "priorite": "high", "date_echeance": "demain", "tags": ["pro"]})
    assert t["titre"] == "Appeler Paul" and etag.startswith('"')
    relue, etag2 = c.tache(t["id"])
    assert relue["id"] == t["id"] and etag2 == etag
    assert [x["titre"] for x in c.taches(status="todo", tag="pro")] == ["Appeler Paul"]
    assert c.taches(tag="autre") == []
    n, etag3 = c.modifier(t["id"], {"priorite": "low"}, etag=etag)
    assert n["priorite"] == "low" and etag3 != etag
    n, _ = c.action(t["id"], "done", {"note": "fini"})
    assert n["statut"] == "TERMINE"
    assert c.agenda()["jours"] is not None and c.stats()["total"] == 1
    c.supprimer(t["id"])
    assert c.taches() == []


def test_client_action_sans_effet(hote):
    c = hote.client()
    t, _ = c.ajouter({"titre": "T"})
    c.action(t["id"], "done")
    tache, _ = c.action(t["id"], "done")
    assert tache is None


def test_client_erreurs(hote):
    c = hote.client()
    with pytest.raises(ErreurClient) as e:
        c.tache("abcdef12")
    assert e.value.statut == 404 and e.value.code == "unknown_id"
    with pytest.raises(ErreurClient) as e:
        hote.client(jeton="faux").projets()
    assert e.value.statut == 401
    with pytest.raises(ErreurClient) as e:
        c.ajouter({"titre": "  "})
    assert e.value.statut == 422
    with pytest.raises(ErreurClient) as e:
        Client("http://127.0.0.1:9", JETON, delai=3).sante()
    assert e.value.statut == 0
    with pytest.raises(ValueError):
        Client(hote.url, "")


def test_client_conflit_etag(hote):
    c = hote.client()
    t, etag = c.ajouter({"titre": "T"})
    hote.todo("task", "edit", t["id"], "--title", "Changée")
    with pytest.raises(ErreurClient) as e:
        c.modifier(t["id"], {"priorite": "high"}, etag=etag)
    assert e.value.conflit and e.value.etag != etag


def test_client_vues(hote):
    une(hote.todo, "Haute", "--prio", "high")
    une(hote.todo, "Basse", "--prio", "low")
    hote.todo("view", "save", "urgent", "list", "--prio", "high")
    c = hote.client()
    assert [v["vue"] for v in c.vues()] == ["urgent"]
    assert [t["titre"] for t in c.vue("urgent")] == ["Haute"]


# ---------------------------------------------------------------- modèle
def test_modele_liste_filtres_projets(hote):
    for t, o in (("Zeta", ("--prio", "high")), ("Alpha", ()), ("Courses", ("--tags", "maison"))):
        une(hote.todo, t, *o)
    hote.todo("done", une(hote.todo, "Finie")["id"])
    e = Etat(hote.client())
    assert e.charger() and sorted(t["titre"] for t in e.taches) == ["Alpha", "Courses", "Zeta"]
    assert e.nom_projet() == "default" and e.projets
    e.cycler_statut()
    assert [t["titre"] for t in e.taches] == ["Finie"]
    e.cycler_statut()
    assert len(e.taches) == 4
    e.cycler_statut()                                   # retour à « à faire »
    e.cycler_prio()
    assert e.prio == "low" or [t["titre"] for t in e.taches] == []
    e.reinitialiser_filtres()
    e.definir_recherche("cour")
    assert [t["titre"] for t in e.taches] == ["Courses"]
    e.definir_recherche("")
    e.definir_tag("#maison")
    assert [t["titre"] for t in e.taches] == ["Courses"] and e.tag == "maison"
    e.reinitialiser_filtres()
    e.cycler_tri()
    assert e.tri == "due" and "tri échéance" in e.libelle_filtres()


def test_modele_selection_conservee_apres_rechargement(hote):
    for t in ("A", "B", "C"):
        une(hote.todo, t)
    e = Etat(hote.client())
    e.charger()
    e.aller(True)
    id_ = e.courante()["id"]
    une(hote.todo, "D")
    e.charger()
    assert e.courante()["id"] == id_
    e.bouger(-99)
    assert e.sel == 0
    e.bouger(99)
    assert e.sel == len(e.taches) - 1


def test_modele_actions(hote):
    e = Etat(hote.client())
    e.charger()
    assert e.ajouter("Appeler Paul !high #pro") and e.message[0] == "ok"
    assert e.courante()["titre"] == "Appeler Paul" and e.courante()["priorite"] == "high"
    assert e.basculer_demarrage() and e.courante()["demarree"]
    assert e.basculer_demarrage() and not e.courante()["demarree"]
    assert e.action("postpone", {"to": "+2d"})
    assert e.changer_priorite()
    assert e.courante()["priorite"] == "low"
    assert e.noter("une note") and e.message == ("ok", "Note ajoutée.")
    assert e.basculer_termine()
    assert e.taches == []                                 # filtre « à faire » : elle disparaît
    e.cycler_statut()
    assert e.courante()["statut"] == "TERMINE"
    assert e.basculer_termine() is True


def test_modele_ajout_litteral_et_titre_vide(hote):
    e = Etat(hote.client())
    assert not e.ajouter("   ") and e.message[0] == "info"
    assert e.ajouter("Brut !high", rapide=False)
    assert e.courante()["titre"] == "Brut !high" and e.courante()["priorite"] == "medium"


def test_modele_fiche_et_conflit(hote):
    t = une(hote.todo, "Avant")
    e = Etat(hote.client())
    e.charger()
    assert e.ouvrir_fiche() and e.fiche["id"] == t["id"] and e.etag
    assert e.modifier({"titre": "Mon titre"}) and e.fiche["titre"] == "Mon titre"
    hote.todo("task", "edit", t["id"], "--title", "Changée ailleurs")
    assert not e.modifier({"titre": "Écrasement"})
    assert e.message[0] == "erreur" and "ailleurs" in e.message[1]
    assert e.fiche["titre"] == "Changée ailleurs"           # relue
    assert e.modifier({"titre": "Recommencé"})
    assert hote.todo("list", "--format", "json").json()[0]["titre"] == "Recommencé"


def test_modele_fiche_effacer_echeance_et_tags(hote):
    une(hote.todo, "T", "--due", "demain", "--tags", "a,b")
    e = Etat(hote.client())
    e.charger()
    e.ouvrir_fiche()
    assert e.modifier({"date_echeance": None, "tags": []})
    assert e.fiche["date_echeance"] is None and e.fiche["tags"] == []


def test_modele_supprimer_et_deplacer(hote):
    hote.todo("project", "create", "perso")
    une(hote.todo, "A déplacer")
    une(hote.todo, "A supprimer")
    e = Etat(hote.client())
    e.charger()
    e.ouvrir_fiche()
    titre = e.fiche["titre"]
    assert e.action("move", {"to": "perso"}) and e.fiche is None
    assert [t["titre"] for t in hote.todo("list", "-p", "perso", "--format", "json").json()] == [titre]
    assert e.supprimer() and len(e.taches) == 0
    assert hote.todo("undo").code == 0
    assert e.changer_projet("perso") and e.nom_projet() == "perso" and [t["titre"] for t in e.taches] == [titre]
    assert not e.changer_projet("inconnu") and e.nom_projet() == "perso"


def test_modele_sans_tache(hote):
    e = Etat(hote.client())
    e.charger()
    assert not e.basculer_termine() and e.message[0] == "info"
    assert not e.supprimer() and not e.ouvrir_fiche()
    assert e.agenda()["jours"] is not None and e.stats()["total"] == 0


def test_modele_serveur_hs(hote):
    e = Etat(Client("http://127.0.0.1:9", JETON, delai=3))
    assert not e.charger() and e.message[0] == "erreur" and "injoignable" in e.message[1]


# ---------------------------------------------------------------- mise en page
@pytest.mark.parametrize("texte,larg", [("abc", 3), ("éàç", 3), ("日本語", 6), ("é", 1), ("", 0)])
def test_largeur(texte, larg):
    assert tui.largeur(texte) == larg


@pytest.mark.parametrize("texte,n,attendu", [("abcdef", 6, "abcdef"), ("abcdef", 4, "abc…"), ("日本語", 5, "日本…"),
                                             ("a\nb", 9, "a b"), ("abc", 0, "")])
def test_tronquer(texte, n, attendu):
    assert tui.tronquer(texte, n) == attendu


def test_ligne_tache_largeur_exacte():
    t = {"id": "0123456789abcdef", "titre": "Une tâche très très longue " * 3, "statut": "A FAIRE", "priorite": "high",
         "date_echeance": "2026-01-01", "tags": ["pro", "maison"], "demarree": None, "bloquee_par": []}
    for n in (40, 60, 80, 120, 200):
        segs = tui.ligne_tache(t, n, "2026-06-01")
        assert sum(tui.largeur(s) for s, _ in segs) <= n
    styles = dict((s.strip(), st) for s, st in tui.ligne_tache(t, 100, "2026-06-01"))
    assert styles["2026-01-01"] == "rouge"                                # en retard
    t["date_echeance"] = "2026-06-01"
    assert dict((s.strip(), st) for s, st in tui.ligne_tache(t, 100, "2026-06-01"))["2026-06-01"] == "jaune"
    t["statut"] = "TERMINE"
    assert tui.ligne_tache(t, 100, "2026-06-01")[0][0].startswith("✓")


def test_ligne_tache_etroite_ne_plante_pas():
    t = {"id": "abc", "titre": "T", "statut": "A FAIRE", "priorite": "low", "tags": [], "demarree": "x", "bloquee_par": ["b"]}
    for n in (0, 5, 24, 30):
        tui.ligne_tache(t, n, "2026-01-01")


def test_lignes_fiche_agenda_stats():
    t = {"id": "i" * 36, "titre": "Titre", "description": "ligne 1\nligne 2", "priorite": "high", "statut": "A FAIRE",
         "date_creation": "2026-11-25 10:00", "date_echeance": "2026-11-26", "tags": ["a"], "recurrence": "1w",
         "demarree": "2026-11-25 11:00", "bloquee_par": ["b" * 36], "notes": [{"date": "d", "texte": "une note", "action": "note"}],
         "pieces_jointes": [], "date_terminee": None, "suivante": None}
    texte = "\n".join(x for x, _ in tui.lignes_fiche(t, 60))
    for attendu in ("Titre", "ligne 2", "une note", "#a", "Récurrence  1w", "Bloquée par bbbbbbbb", "Notes (1)", "en cours depuis"):
        assert attendu in texte
    ag = {"debut": "2026-11-25", "fin": "2026-11-27", "en_retard": [{"titre": "Vieille", "date_echeance": "2026-11-01"}],
          "jours": [{"date": "2026-11-26", "taches": [{"titre": "Demain", "priorite": "medium"}]}], "plus_tard": 2, "sans_echeance": 3}
    texte = "\n".join(x for x, _ in tui.lignes_agenda(ag, 60))
    assert "Vieille" in texte and "Demain" in texte and "2 plus tard · 3 sans" in texte
    assert "Rien de prévu" in "\n".join(x for x, _ in tui.lignes_agenda({**ag, "en_retard": [], "jours": []}, 60))
    st = "\n".join(x for x, _ in tui.lignes_stats({"total": 4, "terminees": 1, "tag.pro": 2}, 60))
    assert "Total" in st and "#pro" in st


# ---------------------------------------------------------------- commande et pseudo-terminal
def test_tui_sans_jeton(todo):
    r = todo("tui", env={"TODO_SERVER_TOKEN": None, "TODO_CLIENT_TOKEN": None})
    assert r.code == 1 and "jeton" in r.texte


def test_tui_serveur_injoignable(todo):
    r = todo("tui", "--url", "http://127.0.0.1:9", env={"TODO_CLIENT_TOKEN": "x"})
    assert r.code == 1 and "injoignable" in r.texte


def test_tui_jeton_refuse(hote):
    r = hote.todo("tui", "--url", hote.url, env={"TODO_CLIENT_TOKEN": "faux"})
    assert r.code == 1 and "jeton" in r.texte


def test_tui_sans_terminal(hote):
    r = hote.todo("tui", "--url", hote.url, env={"TODO_CLIENT_TOKEN": JETON})
    assert r.code == 1 and "terminal" in r.texte


class Terminal:
    """Lance `todo tui` dans un pseudo-terminal 30x100 ; `envoyer` écrit des touches, `attendre` guette du texte à l'écran."""

    def __init__(self, env, url):
        self.sortie = b""
        self.fd, esclave = pty.openpty()
        fcntl.ioctl(esclave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        self.proc = subprocess.Popen([sys.executable, str(SCRIPT), "tui", "--url", url], stdin=esclave, stdout=esclave,
                                     stderr=esclave, start_new_session=True,
                                     env={**env, "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
        os.close(esclave)

    def attendre(self, texte, delai=20):
        fin = time.time() + delai
        while time.time() < fin and texte.encode() not in self.sortie:
            if select.select([self.fd], [], [], 0.2)[0]:
                try:
                    self.sortie += os.read(self.fd, 65536)
                except OSError:
                    break
        return texte.encode() in self.sortie

    def envoyer(self, touches):
        os.write(self.fd, touches.encode())

    def code_de_sortie(self, delai=10):
        fin = time.time() + delai
        while time.time() < fin:
            if select.select([self.fd], [], [], 0.1)[0]:
                try:
                    os.read(self.fd, 65536)
                except OSError:
                    pass
            if self.proc.poll() is not None:
                return self.proc.returncode
        return None

    def fermer(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        os.close(self.fd)


def test_tui_dans_un_pseudo_terminal(hote):
    une(hote.todo, "Alpha tâche")
    une(hote.todo, "Beta tâche", "--prio", "high")
    env = {**hote.todo.env, "TODO_CLIENT_TOKEN": JETON}
    t = Terminal(env, hote.url)
    try:
        assert t.attendre("Alpha tâche") and t.attendre("2 tâche(s)")
        # ajout : « a », saisie, Entrée
        t.envoyer("a")
        assert t.attendre("Nouvelle tâche :")
        t.envoyer("Depuis la TUI !high\r")
        assert t.attendre("Tâche ajoutée.")
        nouvelles = [x for x in hote.todo("list", "--format", "json").json() if x["titre"] == "Depuis la TUI"]
        assert nouvelles and nouvelles[0]["priorite"] == "high"
        # terminer la tâche sélectionnée
        t.envoyer("d")
        assert t.attendre("Tâche terminée")
        assert sum(1 for x in hote.todo("list", "--format", "json").json() if x["statut"] == "TERMINE") == 1
        # fiche puis retour, agenda, aide
        t.envoyer("\r")
        assert t.attendre("Identifiant")
        t.envoyer("\x1b")
        t.envoyer("?")
        assert t.attendre("ajouter (saisie rapide")
        t.envoyer("q")                                      # quitte l'aide, puis la TUI
        t.envoyer("q")
        assert t.code_de_sortie() == 0
    finally:
        t.fermer()
