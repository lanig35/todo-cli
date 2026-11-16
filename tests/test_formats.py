"""Formats de sortie : text, table, plain, json, et le choix automatique selon le terminal."""
import re
import subprocess

import pytest

from outils import jour

ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def base(todo):
    todo.seed(
        {"cle": "a" * 8 + "-0", "titre": "Appeler Paul", "echeance": jour(1), "priorite": "high", "tags": ["pro", "tel"]},
        {"cle": "b" * 8 + "-0", "titre": "日本語\tavec tabulation", "description": "ligne 1\nligne 2"},
        {"cle": "c" * 8 + "-0", "titre": "Fini", "statut": "TERMINE", "terminee": jour(-1) + " 10:00"},
    )
    return todo


def champs(sortie):
    return [l.split("\t") for l in sortie.splitlines()]


# --- plain ---------------------------------------------------------------------------------------------------------
def test_list_plain_colonnes_stables(base):
    lignes = champs(base("list", "--format", "plain").out)
    assert len(lignes) == 3 and all(len(l) == 6 for l in lignes)
    paul = next(l for l in lignes if l[5] == "Appeler Paul")
    assert paul == ["a" * 8 + "-0", "todo", "high", jour(1), "pro,tel", "Appeler Paul"]
    assert next(l for l in lignes if l[5] == "Fini")[1] == "done"


def test_list_plain_sans_decor_ni_couleur(base):
    sortie = base("list", "--format", "plain", "--color", "always").out
    assert "─" not in sortie and "\x1b" not in sortie and "tâche(s)" not in sortie


def test_plain_une_tabulation_dans_un_titre_ne_decale_pas_les_colonnes(base):
    assert all(len(l) == 6 for l in champs(base("list", "--format", "plain").out))


def test_plain_vide_n_affiche_rien(todo):
    assert todo("list", "--format", "plain").out == ""
    assert todo("next", "--format", "plain").out == ""
    assert todo("archive", "list", "--format", "plain").out == ""


def test_pipe_avec_grep_et_xargs(base):
    ids = base("list", "--format", "plain").out
    cibles = [l.split("\t")[0] for l in ids.splitlines() if "Appeler" in l]
    assert base("done", *cibles).code == 0
    assert base.une("Appeler Paul")["statut"] == "TERMINE"


def test_show_plain(base):
    d = {l[0]: l[1:] for l in champs(base("show", "b" * 8, "--format", "plain").out)}
    assert d["statut"] == ["todo"] and d["priorite"] == ["medium"]
    assert d["description"] == ["ligne 1 ligne 2"]
    assert "terminee" not in d
    p = champs(base("show", "a" * 8, "--format", "plain").out)
    assert ["tags", "pro,tel"] in p


def test_show_plain_notes(base):
    base("note", "add", "a" * 8, "premiere")
    lignes = champs(base("show", "a" * 8, "--format", "plain").out)
    note = next(l for l in lignes if l[0] == "note")
    assert len(note) == 3 and note[2] == "premiere"


def test_next_et_archive_plain(base):
    assert champs(base("next", "--format", "plain").out)[0][5] == "Appeler Paul"
    base("archive", "add")
    assert [l[5] for l in champs(base("archive", "list", "--format", "plain").out)] == ["Fini"]


def test_agenda_plain(base):
    lignes = champs(base("agenda", "--format", "plain").out)
    assert [jour(1), "a" * 8 + "-0", "high", "Appeler Paul"] in lignes


def test_note_list_plain(base):
    base("note", "add", "a" * 8, "une")
    base("note", "add", "a" * 8, "deux")
    lignes = champs(base("note", "list", "a" * 8, "--format", "plain").out)
    assert [(l[0], l[2]) for l in lignes] == [("1", "une"), ("2", "deux")]


def test_stats_plain_et_json(base):
    mesures = dict(champs(base("stats", "--format", "plain").out))
    assert mesures["total"] == "3" and mesures["terminees"] == "1" and mesures["priorite_high"] == "1"
    d = base("stats", "--format", "json").json()
    assert d["total"] == 3 and d["tag.pro"] == 1


# --- table ---------------------------------------------------------------------------------------------------------
def test_list_table(base):
    sortie = base("list", "--format", "table", "--color", "always").out
    lignes = sortie.splitlines()
    assert lignes[0].startswith("┌") and lignes[-1].startswith("└") and "\x1b" not in sortie
    assert "TITRE" in lignes[1] and "Appeler Paul" in sortie and "aaaaaaaa" in sortie
    assert "aaaaaaaa-0" not in sortie                   # préfixe de 8 caractères


def test_table_alignee_meme_avec_idéogrammes(base):
    assert len({len(l) for l in base("list", "--format", "table").out.splitlines() if "日本語" not in l}) == 1


def test_table_vide_garde_le_message(todo):
    assert "vide" in todo("list", "--format", "table").sortie


def test_show_stats_note_table(base):
    assert "CHAMP" in base("show", "a" * 8, "--format", "table").out
    assert "INDICATEUR" in base("stats", "--format", "table").out
    base("note", "add", "a" * 8, "x")
    assert "NOTE" in base("note", "list", "a" * 8, "--format", "table").out


def test_table_tronquee_a_la_largeur_du_terminal(base):
    base("add", "T" * 200)
    r = base.pty("list", "--format", "table", colonnes=60)
    lignes = [l for l in r.texte.splitlines() if l.startswith(("│", "┌", "└"))]
    assert lignes and all(len(l) <= 60 for l in lignes) and "…" in r.texte


# --- text et json inchangés ------------------------------------------------------------------------------------------
def test_text_est_l_affichage_decore(base):
    sortie = base("list", "--format", "text").sortie
    assert "MA TO-DO LIST" in sortie and "3 tâche(s)" in sortie


def test_json_inchange(base):
    assert len(base("list", "--format", "json").json()) == 3


def test_format_inconnu_refuse(base):
    r = base("list", "--format", "xml")
    assert r.code == 2 and "xml" in r.err


# --- choix automatique -------------------------------------------------------------------------------------------------
AUTO = {"TODO_FORMAT": None}


def test_auto_plain_dans_un_pipe(base):
    r = base("list", env=AUTO)
    assert champs(r.out)[0][1] in ("todo", "done") and "MA TO-DO LIST" not in r.out


def test_auto_text_dans_un_terminal(base):
    r = base.pty("list", env=AUTO)
    assert "MA TO-DO LIST" in r.texte


def test_option_prioritaire_sur_auto(base):
    assert "MA TO-DO LIST" in base("list", "--format", "text", env=AUTO).sortie


def test_variable_et_fichier(base):
    assert "MA TO-DO LIST" in base("list", env={"TODO_FORMAT": "text"}).sortie
    base.config("[general]\nformat = table\n")
    assert base("list", env=AUTO).out.startswith("┌")
    assert base("list", env={"TODO_FORMAT": "plain"}).out.count("\t") > 0        # variable > fichier
    assert base("list", "--format", "text", env=AUTO).sortie.count("┌") == 0      # option > fichier


def test_format_du_fichier_invalide_est_signale(base):
    base.config("[general]\nformat = json\n")
    r = base("list", env=AUTO)
    assert r.code == 0 and "format" in r.err


def test_commandes_sans_rendu_tabulaire_restent_en_text(base):
    assert "Rappels" in base("reminder", "status", "--format", "plain").sortie
    r = base("config", "path", env=AUTO)
    assert r.out.strip() == str(base.fichier_config)
    assert base("add", "Zed", env=AUTO).code == 0


def test_stdout_pipe_reel(base):
    sortie = base("list", env=AUTO).out
    n = subprocess.run(["wc", "-l"], input=sortie, capture_output=True, text=True).stdout.strip()
    assert n == "3"
