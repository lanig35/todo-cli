"""Outils partagés par les tests.

La suite pilote `todo.py` de l'extérieur, comme un utilisateur (sous-processus + variable
d'environnement TODO_DB_DIR) : elle n'importe jamais le code du programme. Elle reste donc valable
quelle que soit l'organisation interne du code, et prouve qu'un refactoring ne change rien au
comportement visible.
"""
import calendar
import dbm
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = RACINE / "todo.py"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
AUJOURDHUI = date.today()


def jour(n=0, ref=None):
    """Date au format AAAA-MM-JJ, décalée de n jours par rapport à aujourd'hui (ou `ref`)."""
    return ((ref or AUJOURDHUI) + timedelta(days=n)).strftime("%Y-%m-%d")


def ajouter_mois(d, n):
    """d + n mois, jour ramené au dernier jour valide du mois d'arrivée (31 janv. + 1 mois = 28 févr.)."""
    mois = d.month - 1 + n
    annee = d.year + mois // 12
    mois = mois % 12 + 1
    return d.replace(year=annee, month=mois, day=min(d.day, calendar.monthrange(annee, mois)[1]))


def prochain(jour_semaine):
    """Prochaine occurrence (jamais aujourd'hui) d'un jour de la semaine (0 = lundi)."""
    return AUJOURDHUI + timedelta(days=((jour_semaine - AUJOURDHUI.weekday()) % 7 or 7))


class Resultat:
    """Résultat d'une exécution : code de sortie, stdout, stderr, et versions sans couleurs."""

    def __init__(self, processus):
        self.code = processus.returncode
        self.out = processus.stdout
        self.err = processus.stderr

    @property
    def sortie(self):
        """stdout sans séquences de couleur."""
        return ANSI.sub("", self.out)

    @property
    def texte(self):
        """stdout + stderr sans séquences de couleur."""
        return ANSI.sub("", self.out + self.err)

    def json(self):
        return json.loads(self.out)


class ResultatPty:
    """Résultat d'une exécution dans un pseudo-terminal."""

    def __init__(self, code, brut):
        self.code = code
        self.brut = brut

    @property
    def nb_couleurs(self):
        return len(re.findall(r"\x1b\[[0-9;]*m", self.brut))

    @property
    def texte(self):
        return ANSI.sub("", self.brut).replace("\r", "")


class Todo:
    """Une instance isolée du programme : sa propre base, dans un dossier temporaire."""

    def __init__(self, dossier):
        self.dossier = Path(dossier)
        self.db_dir = self.dossier / "data"
        self.db_dir.mkdir()
        env = os.environ.copy()
        for nom in ("NO_COLOR", "PAGER", "LESS", "COLUMNS", "LINES"):
            env.pop(nom, None)
        env.update(TODO_DB_DIR=str(self.db_dir), PYTHONDONTWRITEBYTECODE="1", TERM="xterm")
        self.env = env

    def _env(self, supplementaire):
        env = {**self.env, **(supplementaire or {})}
        return {k: v for k, v in env.items() if v is not None}  # une valeur None supprime la variable

    # ------------------------------------------------------------------ exécution
    def __call__(self, *args, entree=None, env=None):
        p = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                           input=entree, env=self._env(env), cwd=self.dossier, timeout=60)
        return Resultat(p)

    def pty(self, *args, lignes=24, colonnes=80, env=None, stderr_vers=None, delai=20):
        """Exécute le programme avec un vrai terminal (TTY) comme sortie standard."""
        import fcntl, pty, select, struct, termios, time
        maitre, esclave = pty.openpty()
        fcntl.ioctl(esclave, termios.TIOCSWINSZ, struct.pack("HHHH", lignes, colonnes, 0, 0))
        err = open(stderr_vers, "wb") if stderr_vers else esclave
        p = subprocess.Popen([sys.executable, "-B", str(SCRIPT), *map(str, args)], stdin=esclave, stdout=esclave,
                             stderr=err, env=self._env(env), cwd=self.dossier, start_new_session=True)
        os.close(esclave)
        sortie, debut = b"", time.time()
        while time.time() - debut < delai:
            pret, _, _ = select.select([maitre], [], [], 0.3)
            if pret:
                try:
                    donnees = os.read(maitre, 65536)
                except OSError:
                    break
                if not donnees:
                    break
                sortie += donnees
            if p.poll() is not None and not pret:
                break
        try:
            code = p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            code = "TIMEOUT"
        os.close(maitre)
        if stderr_vers:
            err.close()
        return ResultatPty(code, sortie.decode("utf-8", "replace"))

    # ------------------------------------------------------------------ données
    def seed(self, *taches):
        """Écrit des tâches directement dans la base, avec des clés connues (aucune sauvegarde créée).

        Chaque tâche est un dict : cle, titre, et au choix statut, priorite, echeance, recurrence,
        tags, description, creation, terminee.
        """
        with dbm.open(str(self.db_dir / "todo_db"), "c") as db:
            for t in taches:
                db[t["cle"]] = json.dumps({
                    "titre": t["titre"], "statut": t.get("statut", "A FAIRE"), "priorite": t.get("priorite", "medium"),
                    "description": t.get("description", ""), "date_echeance": t.get("echeance"),
                    "tags": t.get("tags", []), "recurrence": t.get("recurrence"),
                    "date_creation": t.get("creation", "2026-01-01 10:00"), "date_terminee": t.get("terminee"),
                })

    def seed_brut(self, cle, octets):
        """Écrit une valeur brute (par exemple une entrée corrompue)."""
        with dbm.open(str(self.db_dir / "todo_db"), "c") as db:
            db[cle] = octets

    def taches(self):
        """Toutes les tâches (dict id -> tâche), lues via `list --format json`."""
        return {t["id"]: t for t in self("list", "--format", "json").json()}

    def par_titre(self, titre, statut=None):
        return [t for t in self.taches().values() if t["titre"] == titre and (statut is None or t["statut"] == statut)]

    def une(self, titre, statut=None):
        """La seule tâche portant ce titre."""
        trouvees = self.par_titre(titre, statut)
        assert len(trouvees) == 1, f"{len(trouvees)} tâche(s) intitulée(s) {titre!r} : {trouvees}"
        return trouvees[0]

    def id_de(self, titre, statut=None, longueur=8):
        return self.une(titre, statut)["id"][:longueur]

    def echeance(self, titre):
        return self.une(titre)["date_echeance"]

    def sauvegardes(self):
        dossier = self.db_dir / "backups"
        return sorted(os.listdir(dossier)) if dossier.is_dir() else []
