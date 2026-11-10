import os
import stat

import pytest


@pytest.fixture
def pager(todo, tmp_path):
    """Un « pager » qui laisse une trace avant de recopier son entrée."""
    p = tmp_path / "monpager.sh"
    p.write_text("#!/bin/sh\necho '<<PAGER>>'\ncat\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


@pytest.fixture
def longue(todo):
    todo.seed(*[dict(cle=f"llll{i:04d}-0", titre=f"Tâche {i:02d}", echeance=None) for i in range(40)])
    return todo


def test_pager_utilise_quand_la_liste_depasse_l_ecran(longue, pager):
    r = longue.pty("list", lignes=15, env={"PAGER": pager})
    assert "<<PAGER>>" in r.texte and "Tâche 39" in r.texte


def test_pager_pas_utilise_si_la_liste_tient(todo, pager):
    todo("add", "A")
    r = todo.pty("list", lignes=40, env={"PAGER": pager})
    assert "<<PAGER>>" not in r.texte and "A" in r.texte


def test_no_pager(longue, pager):
    r = longue.pty("list", "--no-pager", lignes=15, env={"PAGER": pager})
    assert "<<PAGER>>" not in r.texte and "Tâche 39" in r.texte


def test_pas_de_pager_dans_un_pipe(longue, pager):
    r = longue("list", env={"PAGER": pager})
    assert "<<PAGER>>" not in r.out and "Tâche 39" in r.out


def test_pas_de_pager_en_json(longue, pager):
    r = longue.pty("list", "--format", "json", lignes=15, env={"PAGER": pager})
    assert "<<PAGER>>" not in r.texte


def test_pager_introuvable_retombe_sur_l_affichage_direct(longue):
    r = longue.pty("list", lignes=15, env={"PAGER": "/nexiste/pas"})
    assert r.code == 0 and "Tâche 39" in r.texte
