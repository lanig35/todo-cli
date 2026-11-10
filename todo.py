#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
# La ligne ci-dessus permet à l'utilitaire argcomplete de détecter le script.

"""Lanceur de todo-cli : toute la logique est dans le paquet `todo_cli/`.

Ce fichier reste à la racine pour que `./todo.py` et un lien symbolique (`ln -s todo.py ~/.local/bin/todo`)
continuent de fonctionner ; la ligne `PYTHON_ARGCOMPLETE_OK` doit rester dans le script exécuté.
"""
import os
import sys

# Fonctionne aussi via un lien symbolique : on cherche le paquet à côté du vrai fichier.
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from todo_cli.cli import executer  # noqa: E402

if __name__ == "__main__":
    executer()
