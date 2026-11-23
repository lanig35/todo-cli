"""Webhook : file d'attente, nouvelles tentatives, signature HMAC, `todo hooks queue|flush|clear`."""
import hashlib
import hmac
import json
import time

import pytest

from test_hooks import Serveur, hook, webhook  # noqa: F401  (fixtures et aides)


def file_(todo, projet=None):
    base = todo.db_dir if projet is None else todo.db_dir / "projects" / projet
    return base / "webhook_queue.json"


def etat(todo):
    r = todo("hooks", "queue", "--format", "json")
    assert r.code == 0
    return r.json()


def rendre_exigible(todo):
    """Simule l'attente écoulée : la prochaine commande peut renvoyer la file."""
    f = file_(todo)
    d = json.loads(f.read_text())
    d["next_retry"] = 0
    f.write_text(json.dumps(d))


@pytest.fixture
def serveur():
    s = Serveur()
    yield s
    s.fermer()


@pytest.fixture
def arrete():
    """URL d'un serveur qui n'écoute pas."""
    s = Serveur()
    s.fermer()
    return s


def test_echec_passager_mis_en_file(hook, arrete):
    r = hook("add", "A", env=webhook(arrete))
    assert r.code == 0 and "mis en file d'attente" in r.err and "Connection refused" in r.err
    e = etat(hook)
    assert e["pending"] == 1 and e["entries"][0]["event"] == "add" and e["entries"][0]["attempts"] == 1
    assert e["consecutive_failures"] == 1 and e["next_retry"]
    assert hook.une("A")                                                     # la commande a réussi


def test_pas_de_nouvel_essai_avant_l_echeance(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete))
    r = hook("add", "B", env=webhook(serveur))                               # serveur revenu, mais attente en cours
    assert serveur.recu == [] and etat(hook)["pending"] == 2 and "mis en file" not in r.err


def test_renvoi_dans_l_ordre_puis_evenement_courant(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete))
    hook("add", "B", env=webhook(arrete))
    rendre_exigible(hook)
    assert hook("add", "C", env=webhook(serveur)).code == 0
    assert [r["corps"]["tasks"][0]["titre"] for r in serveur.recu] == ["A", "B", "C"]
    assert not file_(hook).exists()                                          # file vide : fichier supprimé
    assert [r["en_tetes"]["X-Todo-Attempt"] for r in serveur.recu] == ["2", "1", "1"]


def test_meme_identifiant_de_livraison_a_chaque_essai(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete))
    delivery = etat(hook)["entries"][0]["delivery"]
    rendre_exigible(hook)
    hook("add", "B", env=webhook(serveur))
    premier = serveur.recu[0]
    assert premier["corps"]["delivery"] == delivery == premier["en_tetes"]["X-Todo-Delivery"]
    assert serveur.recu[1]["corps"]["delivery"] != delivery


def test_attente_croissante(hook, arrete):
    hook("add", "A", env=webhook(arrete))
    t1 = json.loads(file_(hook).read_text())["next_retry"]
    rendre_exigible(hook)
    hook("add", "B", env=webhook(arrete))
    d = json.loads(file_(hook).read_text())
    assert d["fails"] == 2 and d["next_retry"] - time.time() > 40 and 20 < t1 - time.time() <= 31


def test_flush_ignore_l_attente(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete))
    hook("add", "B", env=webhook(arrete))
    r = hook("hooks", "flush", "--format", "text", env=webhook(serveur))
    assert r.code == 0 and "2 événement(s) envoyé(s)" in r.out and len(serveur.recu) == 2
    assert etat(hook)["pending"] == 0


def test_flush_echec_code_1_et_file_gardee(hook, arrete):
    hook("add", "A", env=webhook(arrete))
    r = hook("hooks", "flush", "--format", "text", env=webhook(arrete))
    assert r.code == 1 and "1 en attente" in r.out and etat(hook)["pending"] == 1
    assert hook("hooks", "flush", "--format", "json", env=webhook(arrete)).json() == {"ok": False, "sent": 0, "dropped": 0, "pending": 1}


def test_flush_sans_webhook_configure(hook):
    r = hook("hooks", "flush")
    assert r.code == 1 and "aucun webhook" in r.err


def test_clear(hook, arrete):
    hook("add", "A", env=webhook(arrete))
    hook("add", "B", env=webhook(arrete))
    r = hook("hooks", "clear", "--format", "text")
    assert r.code == 0 and "2 événement(s) supprimé(s)" in r.out and not file_(hook).exists()
    assert etat(hook)["pending"] == 0


def test_queue_formats(hook, arrete):
    assert "Aucun événement" in hook("hooks", "queue", "--format", "text").out
    hook("add", "A", env=webhook(arrete))
    t = hook("hooks", "queue", "--format", "text").out
    assert "FILE DU WEBHOOK" in t and "add" in t and "Connection refused" in t
    assert "LIVRAISON" in hook("hooks", "queue", "--format", "table").out
    ligne = hook("hooks", "queue", "--format", "plain").sortie.splitlines()[0].split("\t")
    assert ligne[1] == "add" and ligne[3] == "1"


@pytest.mark.parametrize("statut", [500, 502, 503, 408, 429, 401, 403, 404])
def test_statuts_a_reessayer(hook, statut):
    s = Serveur(statut=statut)
    try:
        hook("add", "A", env=webhook(s))
        assert etat(hook)["pending"] == 1 and f"a répondu {statut}" in etat(hook)["entries"][0]["last_error"]
    finally:
        s.fermer()


@pytest.mark.parametrize("statut", [400, 413, 422])
def test_refus_definitif_abandonne(hook, statut):
    s = Serveur(statut=statut)
    try:
        r = hook("add", "A", env=webhook(s))
        assert r.code == 0 and "abandonné (refus définitif)" in r.err and etat(hook)["pending"] == 0
    finally:
        s.fermer()


def test_refus_definitif_en_tete_de_file_ne_bloque_pas_la_suite(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete))
    serveur.statut = 400
    rendre_exigible(hook)
    r = hook("add", "B", env=webhook(serveur))
    assert "abandonné" in r.err
    serveur.statut = 204
    hook("add", "C", env=webhook(serveur))
    assert [x["corps"]["tasks"][0]["titre"] for x in serveur.recu][-1] == "C" and etat(hook)["pending"] == 0


def test_serveur_revenu_en_erreur_puis_ok(hook, serveur):
    serveur.statut = 503
    hook("add", "A", env=webhook(serveur))
    assert etat(hook)["pending"] == 1
    serveur.statut = 204
    rendre_exigible(hook)
    hook("done", hook.id_de("A"), env=webhook(serveur))
    assert etat(hook)["pending"] == 0 and [r["corps"]["event"] for r in serveur.recu][-2:] == ["add", "done"]


def test_sans_file_comme_avant(hook, arrete):
    r = hook("add", "A", env=webhook(arrete, webhook_retry="0"))
    assert r.code == 0 and "envoi impossible" in r.err and "file d'attente" not in r.err and not file_(hook).exists()


def test_signature_hmac(hook, serveur):
    hook("add", "A", env=webhook(serveur, webhook_secret="mon-secret"))
    r = serveur.recu[0]
    corps = json.dumps(r["corps"], ensure_ascii=False).encode("utf-8")
    attendu = "sha256=" + hmac.new(b"mon-secret", corps, hashlib.sha256).hexdigest()
    assert r["en_tetes"]["X-Todo-Signature"] == attendu


def test_sans_secret_pas_de_signature(hook, serveur):
    hook("add", "A", env=webhook(serveur))
    assert "X-Todo-Signature" not in serveur.recu[0]["en_tetes"]


def test_signature_aussi_au_renvoi(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete, webhook_secret="s"))
    rendre_exigible(hook)
    hook("add", "B", env=webhook(serveur, webhook_secret="s"))
    assert all("X-Todo-Signature" in r["en_tetes"] for r in serveur.recu)


def test_file_limitee_en_taille(hook, arrete):
    for t in "ABCDE":
        hook("add", t, env=webhook(arrete, webhook_queue_max="3"))
    e = etat(hook)
    assert e["pending"] <= 4                                                 # purge à chaque commande, avant l'ajout
    hook("add", "F", env=webhook(arrete, webhook_queue_max="3"))
    assert etat(hook)["pending"] <= 4


def test_retention(hook, arrete):
    hook("add", "A", env=webhook(arrete))
    d = json.loads(file_(hook).read_text())
    d["entries"][0]["created"] = time.time() - 8 * 86400
    file_(hook).write_text(json.dumps(d))
    r = hook("add", "B", env=webhook(arrete))
    assert "abandonné(s) de la file" in r.err and "trop ancien" in r.err
    assert [e["event"] for e in etat(hook)["entries"]] == ["add"] and etat(hook)["pending"] == 1


def test_file_corrompue_mise_de_cote(hook, serveur):
    file_(hook).write_text("{ pas du json")
    r = hook("add", "A", env=webhook(serveur))
    assert r.code == 0 and "illisible" in r.err and len(serveur.recu) == 1
    assert (hook.db_dir / "webhook_queue.json.corrompu").exists()


def test_evenement_filtre_vide_quand_meme_la_file(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete))
    rendre_exigible(hook)
    hook("add", "B", env=webhook(serveur, webhook_events="done"))            # add non voulu : rien d'ajouté, la file se vide
    assert [r["corps"]["tasks"][0]["titre"] for r in serveur.recu] == ["A"] and etat(hook)["pending"] == 0


def test_ordre_conserve_si_file_non_vide(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete))
    rendre_exigible(hook)
    serveur.statut = 503
    hook("add", "B", env=webhook(serveur))                                    # A échoue de nouveau, B derrière lui, jamais devant
    assert [e["event"] for e in etat(hook)["entries"]] == ["add", "add"] and len(serveur.recu) == 1
    serveur.statut = 204
    rendre_exigible(hook)
    hook("add", "C", env=webhook(serveur))
    assert [r["corps"]["tasks"][0]["titre"] for r in serveur.recu[1:]] == ["A", "B", "C"]


def test_vidage_automatique_borne(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete))
    d = json.loads(file_(hook).read_text())
    d["entries"] = [dict(d["entries"][0], delivery=f"{n:032x}") for n in range(60)]
    d["next_retry"] = 0
    file_(hook).write_text(json.dumps(d))
    hook("add", "B", env=webhook(serveur))
    assert len(serveur.recu) == 50 and etat(hook)["pending"] == 11             # 10 restants + B derrière eux
    hook("hooks", "flush", env=webhook(serveur))
    assert etat(hook)["pending"] == 0 and len(serveur.recu) == 61


def test_files_separees_par_projet(hook, arrete):
    hook("project", "create", "pro")
    hook("add", "A", env=webhook(arrete))
    hook("add", "B", "-p", "pro", env=webhook(arrete))
    assert file_(hook).exists() and file_(hook, "pro").exists()
    assert hook("hooks", "clear", "-p", "pro").code == 0
    assert file_(hook).exists() and not file_(hook, "pro").exists()


def test_la_file_ne_change_pas_le_code_de_sortie(hook, arrete):
    for _ in range(3):
        assert hook("add", "X", env=webhook(arrete)).code == 0


def test_hooks_ne_declenchent_rien(hook, arrete, serveur):
    hook("add", "A", env=webhook(arrete))
    hook("hooks", "queue", env=webhook(serveur))
    hook("hooks", "clear", env=webhook(serveur))
    assert serveur.recu == []


def test_options_dans_le_fichier_de_configuration(hook, arrete):
    hook.config(f"[hooks]\nwebhook_url = {arrete.url}\nwebhook_retry = false\n")
    r = hook("add", "A")
    assert "file d'attente" not in r.err and not file_(hook).exists()
