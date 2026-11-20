"""Dépendances entre tâches (--after) : blocage, next, list, show, done, cycles, export/import."""
import json

import pytest

A, B, C = "aaaa0001-0", "bbbb0002-0", "cccc0003-0"


@pytest.fixture
def chaine(todo):
    """C attend B, B attend A ; A est libre."""
    todo.seed(dict(cle=A, titre="Etape A"), dict(cle=B, titre="Etape B", apres=[A]), dict(cle=C, titre="Etape C", apres=[B]))
    return todo


def noms(r):
    assert r.code == 0, r.texte
    return [t["titre"] for t in r.json()]


# ------------------------------------------------------------------ création et modification
def test_add_after_enregistre_la_dependance(todo):
    todo("add", "Premiere", "--literal")
    pid = todo.id_de("Premiere", longueur=40)
    r = todo("add", "Seconde", "--literal", "--after", pid[:8])
    assert r.code == 0 and "Après" in r.texte
    assert todo.une("Seconde")["apres"] == [pid]


def test_add_after_plusieurs(todo):
    todo("add", "P1", "--literal")
    todo("add", "P2", "--literal")
    ids = [todo.id_de("P1", longueur=40), todo.id_de("P2", longueur=40)]
    todo("add", "Suite", "--literal", "--after", f"{ids[0][:8]},{ids[1][:8]}")
    assert todo.une("Suite")["apres"] == ids


@pytest.mark.parametrize("valeur", ["zzzzzzzz", ""])
def test_add_after_inconnu_ou_vide_echoue(todo, valeur):
    todo("add", "Premiere", "--literal")
    r = todo("add", "Seconde", "--literal", "--after", valeur)
    if valeur:
        assert r.code == 1 and "Aucun identifiant" in r.texte
        assert todo.par_titre("Seconde") == []
    else:
        assert r.code == 0 and todo.une("Seconde")["apres"] == []


def test_edit_after_remplace_puis_supprime(chaine):
    chaine("task", "edit", "cccc", "--after", "aaaa")
    assert chaine.une("Etape C")["apres"] == [A]
    chaine("task", "edit", "cccc", "--after", "none")
    assert chaine.une("Etape C")["apres"] == []
    assert "Aucun changement" in chaine("task", "edit", "cccc", "--after", "").texte


def test_edit_after_est_une_modification_valide(chaine):
    r = chaine("task", "edit", "cccc", "--after", "aaaa")
    assert r.code == 0 and "dépendances" in r.texte


def test_edit_after_inconnu(chaine):
    r = chaine("task", "edit", "cccc", "--after", "zzzz")
    assert r.code == 1 and chaine.une("Etape C")["apres"] == [B]


# ------------------------------------------------------------------ cycles
def test_dependance_sur_soi_meme_refusee(chaine):
    r = chaine("task", "edit", "aaaa", "--after", "aaaa")
    assert r.code == 1 and "circulaire" in r.texte


def test_cycle_direct_et_indirect_refuses(chaine):
    assert chaine("task", "edit", "aaaa", "--after", "bbbb").code == 1       # A après B après A
    assert chaine("task", "edit", "aaaa", "--after", "cccc").code == 1       # A après C après B après A
    assert chaine.une("Etape A")["apres"] == []


def test_pas_de_cycle_en_diamant(chaine):
    """Deux chemins vers la même tâche ne sont pas un cycle."""
    assert chaine("task", "edit", "cccc", "--after", "aaaa,bbbb").code == 0


# ------------------------------------------------------------------ blocage
def test_list_json_indique_les_blocages(chaine):
    t = {x["titre"]: x for x in chaine("list", "--format", "json").json()}
    assert t["Etape A"]["bloquee_par"] == [] and t["Etape B"]["bloquee_par"] == [A] and t["Etape C"]["bloquee_par"] == [B]


def test_next_ne_propose_que_les_taches_libres(chaine):
    assert noms(chaine("next", "--count", "5", "--format", "json")) == ["Etape A"]


def test_next_avance_quand_la_dependance_est_terminee(chaine):
    chaine("done", "aaaa")
    assert noms(chaine("next", "--count", "5", "--format", "json")) == ["Etape B"]
    chaine("done", "bbbb")
    assert noms(chaine("next", "--count", "5", "--format", "json")) == ["Etape C"]


def test_dependance_supprimee_ou_archivee_ne_bloque_plus(chaine):
    chaine("done", "aaaa")
    chaine("archive", "add")
    assert noms(chaine("next", "--format", "json")) == ["Etape B"]
    chaine("task", "remove", "bbbb")
    assert noms(chaine("next", "--format", "json")) == ["Etape C"]       # B n'existe plus : C est libre


def test_reouvrir_une_dependance_rebloque(chaine):
    chaine("done", "aaaa")
    chaine("task", "undone", "aaaa")
    assert noms(chaine("next", "--count", "5", "--format", "json")) == ["Etape A"]


def test_next_message_quand_tout_est_bloque(todo):
    todo.seed(dict(cle=A, titre="Etape A", statut="TERMINE", terminee="2026-01-02 10:00"), dict(cle=B, titre="Etape B", apres=[A]))
    todo.seed(dict(cle=C, titre="Etape C", apres=[B]))
    todo.seed(dict(cle="dddd0004-0", titre="Etape D", apres=[C]))
    assert "Etape B" in todo("next", "--format", "text").sortie
    todo.seed(dict(cle=B, titre="Etape B", statut="TERMINE", terminee="2026-01-02 10:00", apres=[A]))
    todo("done", "cccc")
    todo("done", "dddd")
    todo.seed(dict(cle="eeee0005-0", titre="Etape E", apres=["ffff0006-0"]), dict(cle="ffff0006-0", titre="Etape F", apres=["eeee0005-0"]))
    r = todo("next", "--format", "text")
    assert "attente d'une dépendance" in r.sortie     # cycle importé à la main : rien n'est proposé


def test_done_sur_tache_bloquee_avertit_mais_aboutit(chaine):
    r = chaine("done", "bbbb")
    assert r.code == 0 and "attendait encore" in r.texte and "Etape A" in r.texte
    assert chaine.une("Etape B")["statut"] == "TERMINE"


def test_done_sur_tache_libre_sans_avertissement(chaine):
    assert "attendait" not in chaine("done", "aaaa").texte


def test_occurrence_suivante_n_herite_pas_des_dependances(todo):
    todo.seed(dict(cle=A, titre="Pre"), dict(cle=B, titre="Hebdo", echeance="2026-06-01", recurrence="1w", apres=[A]))
    todo("done", "bbbb")
    suivante = [t for t in todo("list", "--format", "json").json() if t["titre"] == "Hebdo" and t["statut"] != "TERMINE"]
    assert len(suivante) == 1 and suivante[0]["apres"] == []


# ------------------------------------------------------------------ filtres, colonnes, show
def test_filtres_blocked_et_ready(chaine):
    assert set(noms(chaine("list", "--blocked", "--format", "json"))) == {"Etape B", "Etape C"}
    assert noms(chaine("list", "--ready", "--format", "json")) == ["Etape A"]
    assert chaine("list", "--blocked", "--ready").code == 2


def test_ready_exclut_les_terminees(chaine):
    chaine("done", "aaaa")
    assert noms(chaine("list", "--ready", "--format", "json")) == ["Etape B"]


def test_colonnes_after_et_blocked(chaine):
    lignes = {l.split("\t")[1]: l.split("\t") for l in
              chaine("list", "--format", "plain", "--columns", "id,title,after,blocked").out.splitlines()}
    assert lignes["Etape B"][2:] == [A, "yes"] and lignes["Etape A"][2:] == ["", "no"]
    table = chaine("list", "--format", "table", "--columns", "title,after,blocked").out
    assert "aaaa0001" in table and "aaaa0001-0" not in table and "BLOQUÉE" in table


def test_list_texte_marque_les_taches_bloquees(chaine):
    sortie = chaine("list", "--format", "text").sortie
    ligne = next(l for l in sortie.splitlines() if "Etape B" in l)
    assert "🔒" in ligne and "aaaa0001" in ligne
    assert "🔒" not in next(l for l in sortie.splitlines() if "Etape A" in l)


def test_show_text_json_et_plain(chaine):
    assert "Après" in chaine("show", "bbbb", "--format", "text").sortie and "Etape A" in chaine("show", "bbbb", "--format", "text").sortie
    assert chaine("show", "bbbb", "--format", "json").json()["apres"] == [A]
    lignes = [l.split("\t") for l in chaine("show", "bbbb", "--format", "plain").out.splitlines()]
    assert ["apres", A] in lignes
    assert not any(l[0] == "apres" for l in (m.split("\t") for m in chaine("show", "aaaa", "--format", "plain").out.splitlines()))


# ------------------------------------------------------------------ export / import
def test_export_import_conserve_les_dependances(chaine, tmp_path):
    f = tmp_path / "x.json"
    assert chaine("data", "export", str(f)).code == 0
    doc = json.loads(f.read_text())
    assert {t["titre"]: t["apres"] for t in doc["taches"]}["Etape B"] == [A]
    chaine("admin", "reset", "-y")
    assert chaine("data", "import", str(f), "-y").code == 0
    assert chaine.une("Etape B")["apres"] == [A] and noms(chaine("next", "--count", "5", "--format", "json")) == ["Etape A"]


def test_import_ancien_fichier_sans_apres(todo, tmp_path):
    f = tmp_path / "ancien.json"
    f.write_text(json.dumps({"format": "todo-cli", "version": 1, "taches": [{"titre": "Vieille"}]}))
    assert todo("data", "import", str(f), "-y").code == 0
    assert todo.une("Vieille")["apres"] == []


def test_import_apres_invalide_refuse(todo, tmp_path):
    f = tmp_path / "mauvais.json"
    f.write_text(json.dumps({"format": "todo-cli", "version": 1, "taches": [{"titre": "X", "apres": "pas une liste"}]}))
    r = todo("data", "import", str(f), "-y")
    assert "apres" in r.texte


def test_ancienne_syntaxe(todo):
    todo("add", "Premiere", "--literal")
    todo("add", "Seconde", "--literal", "--after", todo.id_de("Premiere"))
    assert todo.une("Seconde")["apres"] == [todo.une("Premiere")["id"]]
