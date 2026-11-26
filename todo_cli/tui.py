"""TUI (curses) de todo-cli : `todo tui` — un client de l'API REST (`todo serve`), utilisable en SSH.

Séparation : `tui_modele.Etat` porte la logique (testée sans terminal) ; ce module ne contient que la mise en page (fonctions
pures `ligne_tache`, `lignes_fiche`, `lignes_agenda`, `lignes_stats`, elles aussi testées) et la boucle curses. Les appels
réseau tournent dans un fil : l'écran reste vivant (indicateur d'attente, redimensionnement) pendant que le serveur répond.
"""
import curses
import datetime
import locale
import sys
import textwrap
import threading
import unicodedata

from .client import ErreurClient, depuis_reglages
from .tui_modele import Etat

AIDE_LISTE = ("j/k ↑↓ naviguer · Entrée fiche · a ajouter · d terminer · s démarrer · p reporter · m déplacer · x supprimer · "
              "/ chercher · P projet · ? aide · q quitter")
AIDE_FICHE = "j/k défiler · e titre · D description · w échéance · t tags · ! priorité · n note · d s p m x · Esc retour"
TEXTE_AIDE = [
    ("Liste", ""),
    ("  j k ↑ ↓ PgUp PgDn Home End", "naviguer"),
    ("  Entrée / l", "ouvrir la fiche"),
    ("  a", "ajouter (saisie rapide : « Appeler Paul demain !high #pro »)"),
    ("  d", "terminer / rouvrir"),
    ("  s", "démarrer / arrêter"),
    ("  p", "reporter (date : +3d, lundi, 2026-12-01…)"),
    ("  m", "déplacer vers un autre projet"),
    ("  e  n  !", "modifier le titre · ajouter une note · changer la priorité"),
    ("  x", "supprimer (annulable : todo undo)"),
    ("Filtres", ""),
    ("  /  t", "rechercher · filtrer par tag"),
    ("  f  F  o  c", "statut · priorité · tri · réinitialiser"),
    ("  P", "changer de projet"),
    ("Autres", ""),
    ("  g  S", "agenda · statistiques"),
    ("  r", "recharger"),
    ("  q", "quitter"),
    ("Fiche", ""),
    ("  e D w t ! n", "titre · description · échéance · tags · priorité · note"),
    ("  d s p m x", "comme dans la liste"),
    ("  Esc / q / h", "retour à la liste"),
]


# ---------------------------------------------------------------------- mise en page (fonctions pures)
def largeur(texte):
    """Largeur d'affichage en cellules (accents et caractères combinants gérés, CJK sur deux cellules)."""
    total = 0
    for c in texte:
        if unicodedata.combining(c):
            continue
        total += 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
    return total


def tronquer(texte, n):
    """Coupe à `n` cellules (… si trop long) ; chaînes sans retour à la ligne."""
    texte = " ".join(texte.split("\n"))
    if n <= 0:
        return ""
    if largeur(texte) <= n:
        return texte
    sortie, w = "", 0
    for c in texte:
        cw = largeur(c)
        if w + cw > n - 1:
            break
        sortie, w = sortie + c, w + cw
    return sortie + "…"


def ajuster(texte, n):
    """Tronque ou complète par des espaces pour occuper exactement `n` cellules."""
    texte = tronquer(texte, n)
    return texte + " " * (n - largeur(texte))


def ligne_tache(t, n, aujourdhui):
    """Segments (texte, style) d'une ligne de la liste, sur `n` cellules."""
    fait = t["statut"] != "A FAIRE"
    marque = "✓" if fait else "▶" if t.get("demarree") else "!" if t.get("bloquee_par") else " "
    prio = {"high": "H", "medium": "M", "low": "L"}.get(t["priorite"], "?")
    echeance = t.get("date_echeance") or ""
    if fait:
        style_ech = "vert"
    elif echeance and echeance < aujourdhui:
        style_ech = "rouge"
    elif echeance == aujourdhui:
        style_ech = "jaune"
    else:
        style_ech = "normal"
    tags = " ".join("#" + x for x in t.get("tags", []))
    fixe = 2 + 2 + 9 + 11                                         # marque, priorité, id, échéance
    reste = max(n - fixe, 0)
    largeur_tags = min(largeur(tags), reste // 3) if tags else 0
    largeur_titre = max(reste - largeur_tags - (1 if largeur_tags else 0), 0)
    segments = [(marque + " ", "vert" if fait else "cyan" if marque == "▶" else "jaune" if marque == "!" else "normal"),
                (prio + " ", "rouge" if prio == "H" and not fait else "dim" if prio == "L" else "normal"),
                (ajuster(t["id"][:8], 8) + " ", "dim"), (ajuster(echeance, 10) + " ", style_ech),
                (ajuster(t["titre"], largeur_titre), "dim" if fait else "normal")]
    if largeur_tags:
        segments.append((" " + ajuster(tags, largeur_tags), "cyan"))
    return segments


def _paragraphe(texte, n, prefixe=""):
    sortie = []
    for ligne in str(texte).splitlines() or [""]:
        sortie += textwrap.wrap(ligne, max(n - len(prefixe), 10), initial_indent=prefixe, subsequent_indent=prefixe) or [prefixe.rstrip()]
    return sortie


def lignes_fiche(t, n):
    """[(texte, style)] de la fiche d'une tâche."""
    L = [(x, "gras") for x in _paragraphe(t["titre"], n)] + [("", "normal")]
    fait = t["statut"] != "A FAIRE"
    L.append((f"Statut      {'terminée' if fait else 'à faire'}" + (" · en cours depuis " + t["demarree"] if t.get("demarree") and not fait else ""),
              "vert" if fait else "normal"))
    L.append((f"Priorité    {t['priorite']}", "rouge" if t["priorite"] == "high" else "normal"))
    L.append((f"Échéance    {t.get('date_echeance') or '—'}", "normal"))
    if t.get("recurrence"):
        L.append((f"Récurrence  {t['recurrence']}", "normal"))
    L.append((f"Créée       {t.get('date_creation') or '—'}", "dim"))
    if t.get("date_terminee"):
        L.append((f"Terminée    {t['date_terminee']}", "dim"))
    if t.get("tags"):
        L.append(("Tags        " + " ".join("#" + x for x in t["tags"]), "cyan"))
    if t.get("bloquee_par"):
        L.append(("Bloquée par " + ", ".join(b[:8] for b in t["bloquee_par"]), "jaune"))
    if t.get("suivante"):
        L.append((f"Suivante    {t['suivante'][:8]}", "dim"))
    L.append((f"Identifiant {t['id']}", "dim"))
    if t.get("description"):
        L += [("", "normal"), ("Description", "gras")] + [(x, "normal") for x in _paragraphe(t["description"], n, "  ")]
    if t.get("notes"):
        L += [("", "normal"), (f"Notes ({len(t['notes'])})", "gras")]
        for note in t["notes"]:
            L.append((f"  {note.get('date', '')}" + (f" · {note['action']}" if note.get("action") not in (None, "note") else ""), "dim"))
            L += [(x, "normal") for x in _paragraphe(note.get("texte", ""), n, "    ")]
    if t.get("pieces_jointes"):
        L += [("", "normal"), ("Pièces jointes", "gras")] + [("  " + str(p.get("nom", p) if isinstance(p, dict) else p), "normal") for p in t["pieces_jointes"]]
    return L


def lignes_agenda(ag, n, aujourdhui=""):
    L = [(f"Agenda {ag['debut']} → {ag['fin']}", "gras"), ("", "normal")]
    if ag.get("en_retard"):
        L.append((f"En retard ({len(ag['en_retard'])})", "rouge"))
        L += [("  " + tronquer(f"{t['date_echeance']}  {t['titre']}", n - 2), "rouge") for t in ag["en_retard"]]
        L.append(("", "normal"))
    for jour in ag.get("jours", []):
        if jour["taches"]:
            L.append((jour["date"] + ("  (aujourd'hui)" if jour["date"] == aujourdhui else ""), "jaune" if jour["date"] == aujourdhui else "gras"))
            L += [("  " + tronquer(f"{t['priorite'][0].upper()} {t['titre']}", n - 2), "normal") for t in jour["taches"]]
    if len(L) == 2:
        L.append(("Rien de prévu sur cette période.", "dim"))
    L += [("", "normal"), (f"{ag.get('plus_tard', 0)} plus tard · {ag.get('sans_echeance', 0)} sans échéance", "dim")]
    return L


def lignes_stats(s, n):
    L = [("Statistiques", "gras"), ("", "normal")]
    for libelle, cle in (("Total", "total"), ("Terminées", "terminees"), ("Avancement %", "pourcentage_termine"), ("En retard", "en_retard"),
                         ("Pour aujourd'hui", "pour_aujourdhui"), ("Terminées aujourd'hui", "terminees_aujourdhui"),
                         ("Terminées sur 7 jours", "terminees_7_jours"), ("Priorité haute", "priorite_high"),
                         ("Priorité moyenne", "priorite_medium"), ("Priorité basse", "priorite_low")):
        L.append((f"  {libelle:<24}{s.get(cle, 0)}", "rouge" if cle == "en_retard" and s.get(cle) else "normal"))
    tags = sorted(((k[4:], v) for k, v in s.items() if k.startswith("tag.")), key=lambda x: -x[1])
    if tags:
        L += [("", "normal"), ("Tags", "gras")] + [(f"  #{k:<22}{v}", "cyan") for k, v in tags]
    return L


# ---------------------------------------------------------------------- écran curses
class Ecran:
    def __init__(self, scr, etat):
        self.scr, self.etat = scr, etat
        self.mode = "liste"                                  # liste | fiche | page | aide
        self.defilement = 0                                  # fiche et pages
        self.page = []                                       # lignes (texte, style) d'une page agenda / stats / aide
        self.titre_page = ""
        self.attente = ""
        self.styles = {}
        self.demarrer_curses()

    def demarrer_curses(self):
        curses.curs_set(0)
        self.scr.keypad(True)
        base = {"normal": 0, "gras": curses.A_BOLD, "dim": curses.A_DIM}
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
                fond = -1
            except curses.error:
                fond = curses.COLOR_BLACK
            for i, c in enumerate((curses.COLOR_RED, curses.COLOR_YELLOW, curses.COLOR_GREEN, curses.COLOR_CYAN), 1):
                curses.init_pair(i, c, fond)
            base.update({"rouge": curses.color_pair(1), "jaune": curses.color_pair(2), "vert": curses.color_pair(3),
                         "cyan": curses.color_pair(4)})
        else:
            base.update({"rouge": curses.A_BOLD, "jaune": curses.A_BOLD, "vert": 0, "cyan": 0})
        self.styles = base

    # ------------------------------------------------------------------ primitives
    def ecrire(self, y, x, texte, attr=0):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        texte = tronquer(texte, w - x - (1 if y == h - 1 else 0)) if largeur(texte) > w - x else texte
        try:
            self.scr.addstr(y, x, texte, attr)
        except curses.error:
            pass

    def segments(self, y, x, segments, extra=0):
        for texte, style in segments:
            self.ecrire(y, x, texte, self.styles.get(style, 0) | extra)
            x += largeur(texte)

    def attendre(self, fonction):
        """Exécute `fonction` dans un fil ; l'écran continue de tourner (indicateur) jusqu'à la réponse du serveur."""
        resultat = {}

        def travail():
            try:
                resultat["valeur"] = fonction()
            except BaseException as e:                       # noqa: BLE001 : remonté dans le fil principal
                resultat["erreur"] = e
        fil = threading.Thread(target=travail, daemon=True)
        fil.start()
        self.scr.timeout(80)
        tour = 0
        try:
            while fil.is_alive():
                self.attente = "Patientez " + "|/-\\"[tour % 4]
                self.dessiner()
                tour += 1
                self.scr.getch()                             # consomme (et ignore) les touches pendant l'attente
        finally:
            self.scr.timeout(-1)
            self.attente = ""
            curses.flushinp()
        if "erreur" in resultat:
            raise resultat["erreur"]
        return resultat.get("valeur")

    # ------------------------------------------------------------------ dessin
    def dessiner(self):
        s, e = self.scr, self.etat
        s.erase()
        h, w = s.getmaxyx()
        if h < 6 or w < 30:
            self.ecrire(0, 0, "Terminal trop petit")
            s.refresh()
            return
        titre = {"liste": f" todo · {e.nom_projet()} · {e.libelle_filtres()} · {len(e.taches)} tâche(s)",
                 "fiche": f" todo · {e.nom_projet()} · fiche", "page": f" todo · {self.titre_page}",
                 "aide": " todo · aide"}[self.mode]
        s.attron(curses.A_REVERSE)
        self.ecrire(0, 0, ajuster(titre, w))
        s.attroff(curses.A_REVERSE)
        if self.mode == "liste":
            self.dessiner_liste(h, w)
        else:
            lignes = lignes_fiche(e.fiche, w - 2) if self.mode == "fiche" and e.fiche else self.page
            visibles = h - 3
            self.defilement = max(0, min(self.defilement, max(len(lignes) - visibles, 0)))
            for i, (texte, style) in enumerate(lignes[self.defilement:self.defilement + visibles]):
                self.ecrire(1 + i, 1, texte, self.styles.get(style, 0))
        niveau, texte = e.message
        if self.attente:
            niveau, texte = "info", self.attente
        style = {"erreur": "rouge", "ok": "vert", "info": "jaune"}.get(niveau, "normal")
        self.ecrire(h - 2, 0, ajuster(" " + texte, w), self.styles[style])
        aide = {"liste": AIDE_LISTE, "fiche": AIDE_FICHE, "page": " j/k défiler · q retour", "aide": " j/k défiler · q retour"}[self.mode]
        self.ecrire(h - 1, 0, tronquer(" " + aide, w - 1), self.styles["dim"])
        s.refresh()

    def dessiner_liste(self, h, w):
        e = self.etat
        visibles = h - 3
        if not e.taches:
            self.ecrire(2, 2, "Aucune tâche (a : ajouter · c : réinitialiser les filtres).", self.styles["dim"])
            return
        haut = max(0, min(e.sel - visibles // 2, len(e.taches) - visibles))
        aujourdhui = datetime.date.today().isoformat()
        for i, t in enumerate(e.taches[haut:haut + visibles]):
            y = 1 + i
            choisi = haut + i == e.sel
            if choisi:
                self.ecrire(y, 0, " " * (w - 1), curses.A_REVERSE)
            self.segments(y, 1, ligne_tache(t, w - 2, aujourdhui), curses.A_REVERSE if choisi else 0)

    # ------------------------------------------------------------------ saisie
    def saisir(self, invite, initial=""):
        """Ligne de saisie en bas de l'écran (édition au curseur, Entrée valide, Échap annule) -> texte | None."""
        texte, pos = list(initial), len(initial)
        curses.curs_set(1)
        try:
            while True:
                h, w = self.scr.getmaxyx()
                place = max(w - largeur(invite) - 3, 5)
                debut = max(0, pos - place + 1)
                self.dessiner()
                self.ecrire(h - 2, 0, ajuster(" " + invite + "".join(texte)[debut:debut + place], w), curses.A_BOLD)
                self.scr.move(h - 2, min(1 + largeur(invite) + largeur("".join(texte[debut:pos])), w - 1))
                self.scr.refresh()
                try:
                    c = self.scr.get_wch()
                except KeyboardInterrupt:
                    return None
                if c in ("\n", "\r", curses.KEY_ENTER):
                    return "".join(texte)
                if c == "\x1b":
                    return None
                if c in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    if pos:
                        del texte[pos - 1]
                        pos -= 1
                elif c == curses.KEY_DC:
                    if pos < len(texte):
                        del texte[pos]
                elif c == curses.KEY_LEFT:
                    pos = max(0, pos - 1)
                elif c == curses.KEY_RIGHT:
                    pos = min(len(texte), pos + 1)
                elif c in (curses.KEY_HOME, "\x01"):
                    pos = 0
                elif c in (curses.KEY_END, "\x05"):
                    pos = len(texte)
                elif c == "\x15":                              # Ctrl-U
                    texte, pos = [], 0
                elif isinstance(c, str) and c.isprintable():
                    texte.insert(pos, c)
                    pos += 1
        finally:
            curses.curs_set(0)

    def confirmer(self, question):
        self.etat.dire(question + " (o/N)", "info")
        self.dessiner()
        c = self.scr.get_wch()
        self.etat.message = ("", "")
        return isinstance(c, str) and c.lower() in ("o", "y")

    def choisir(self, titre, options):
        """Menu plein écran (↑↓, Entrée, Échap) -> option | None."""
        i = 0
        while True:
            h, w = self.scr.getmaxyx()
            self.scr.erase()
            self.scr.attron(curses.A_REVERSE)
            self.ecrire(0, 0, ajuster(" " + titre, w))
            self.scr.attroff(curses.A_REVERSE)
            visibles = h - 3
            haut = max(0, min(i - visibles // 2, len(options) - visibles))
            for k, o in enumerate(options[haut:haut + visibles]):
                self.ecrire(1 + k, 2, o, curses.A_REVERSE if haut + k == i else 0)
            self.ecrire(h - 1, 0, " ↑↓ choisir · Entrée valider · Échap annuler", self.styles["dim"])
            self.scr.refresh()
            c = self.scr.get_wch()
            if c in (curses.KEY_UP, "k"):
                i = max(0, i - 1)
            elif c in (curses.KEY_DOWN, "j"):
                i = min(len(options) - 1, i + 1)
            elif c in ("\n", "\r", curses.KEY_ENTER):
                return options[i]
            elif c in ("\x1b", "q"):
                return None

    # ------------------------------------------------------------------ actions
    def faire(self, fonction, *args):
        return self.attendre(lambda: fonction(*args))

    def charger(self):
        self.faire(self.etat.charger)

    def tache_cible(self):
        return self.etat.fiche or self.etat.courante()

    def ouvrir_page(self, titre, lignes):
        self.mode, self.titre_page, self.page, self.defilement = "page", titre, lignes, 0

    def commande_commune(self, c):
        """Touches valables dans la liste comme dans la fiche ; retourne True si traitée."""
        e = self.etat
        t = self.tache_cible()
        if c == "d":
            self.faire(e.basculer_termine)
        elif c == "s":
            self.faire(e.basculer_demarrage)
        elif c == "p" and t:
            to = self.saisir("Reporter à (date) : ")
            if to and to.strip():
                self.faire(e.action, "postpone", {"to": to.strip()})
        elif c == "m" and t:
            autres = [p["projet"] for p in e.projets if p["projet"] != e.nom_projet()]
            if not autres:
                e.dire("Aucun autre projet.", "info")
            else:
                cible = self.choisir("Déplacer vers le projet…", autres)
                if cible:
                    self.faire(e.action, "move", {"to": cible})
        elif c == "x" and t:
            if self.confirmer(f"Supprimer « {tronquer(t['titre'], 40)} » ?"):
                self.faire(e.supprimer)
                if not e.fiche:
                    self.mode = "liste"
        elif c == "n" and t:
            texte = self.saisir("Note : ")
            if texte is not None:
                self.faire(e.noter, texte)
        elif c == "e" and t:
            titre = self.saisir("Titre : ", t["titre"])
            if titre is not None and titre.strip() and titre != t["titre"]:
                self.faire(e.modifier, {"titre": titre.strip()})
        elif c == "!" and t:
            self.faire(e.changer_priorite)
        elif c == "?":
            self.ouvrir_page("aide", [(a + (("  " + b) if b else ""), "gras" if not b else "normal") for a, b in TEXTE_AIDE])
            self.mode = "aide"
        else:
            return False
        return True

    def touche_liste(self, c):
        e = self.etat
        h, _ = self.scr.getmaxyx()
        if c in ("q", "Q"):
            return False
        if c in ("j", curses.KEY_DOWN):
            e.bouger(1)
        elif c in ("k", curses.KEY_UP):
            e.bouger(-1)
        elif c == curses.KEY_NPAGE:
            e.bouger(h - 4)
        elif c == curses.KEY_PPAGE:
            e.bouger(-(h - 4))
        elif c == curses.KEY_HOME:
            e.aller(False)
        elif c == curses.KEY_END:
            e.aller(True)
        elif c in ("\n", "\r", curses.KEY_ENTER, "l", curses.KEY_RIGHT):
            if e.courante() and self.faire(e.ouvrir_fiche):
                self.mode, self.defilement = "fiche", 0
        elif c == "a":
            titre = self.saisir("Nouvelle tâche : ")
            if titre is not None:
                self.faire(e.ajouter, titre)
        elif c == "r":
            self.charger()
            e.dire("Liste rechargée.", "info")
        elif c == "/":
            texte = self.saisir("Rechercher : ", e.recherche)
            if texte is not None:
                self.faire(e.definir_recherche, texte)
        elif c == "t":
            texte = self.saisir("Tag : ", e.tag)
            if texte is not None:
                self.faire(e.definir_tag, texte)
        elif c == "f":
            self.faire(e.cycler_statut)
        elif c == "F":
            self.faire(e.cycler_prio)
        elif c == "o":
            self.faire(e.cycler_tri)
        elif c == "c":
            self.faire(e.reinitialiser_filtres)
        elif c == "P":
            noms = [p["projet"] + f"  ({p['a_faire']} à faire)" for p in e.projets]
            choix = self.choisir("Projet", noms) if noms else None
            if choix:
                self.faire(e.changer_projet, choix.split("  (")[0])
        elif c == "g":
            ag = self.faire(e.agenda, 7)
            if ag:
                self.ouvrir_page("agenda", lignes_agenda(ag, self.scr.getmaxyx()[1] - 2, datetime.date.today().isoformat()))
        elif c == "S":
            st = self.faire(e.stats)
            if st:
                self.ouvrir_page("statistiques", lignes_stats(st, self.scr.getmaxyx()[1] - 2))
        else:
            self.commande_commune(c)
        return True

    def touche_fiche(self, c):
        e = self.etat
        t = e.fiche
        if c in ("\x1b", "q", "h", curses.KEY_LEFT):
            e.fermer_fiche()
            self.mode = "liste"
        elif c in ("j", curses.KEY_DOWN):
            self.defilement += 1
        elif c in ("k", curses.KEY_UP):
            self.defilement = max(0, self.defilement - 1)
        elif c == curses.KEY_NPAGE:
            self.defilement += self.scr.getmaxyx()[0] - 4
        elif c == curses.KEY_PPAGE:
            self.defilement = max(0, self.defilement - (self.scr.getmaxyx()[0] - 4))
        elif c == "D":
            texte = self.saisir("Description : ", t.get("description", ""))
            if texte is not None and texte != t.get("description", ""):
                self.faire(e.modifier, {"description": texte})
        elif c == "w":
            texte = self.saisir("Échéance (vide = aucune) : ", t.get("date_echeance") or "")
            if texte is not None and texte.strip() != (t.get("date_echeance") or ""):
                self.faire(e.modifier, {"date_echeance": texte.strip() or None})
        elif c == "t":
            texte = self.saisir("Tags (séparés par des virgules) : ", ", ".join(t.get("tags", [])))
            if texte is not None:
                self.faire(e.modifier, {"tags": [x.strip() for x in texte.split(",") if x.strip()]})
        elif c == "r":
            self.faire(e.ouvrir_fiche, t["id"])
        else:
            self.commande_commune(c)
        if self.mode == "fiche" and not e.fiche:             # fiche fermée par un déplacement ou une suppression
            self.mode = "liste"
        return True

    def touche_page(self, c):
        if c in ("\x1b", "q", "h", curses.KEY_LEFT):
            self.mode = "liste"
        elif c in ("j", curses.KEY_DOWN):
            self.defilement += 1
        elif c in ("k", curses.KEY_UP):
            self.defilement = max(0, self.defilement - 1)
        elif c == curses.KEY_NPAGE:
            self.defilement += self.scr.getmaxyx()[0] - 4
        elif c == curses.KEY_PPAGE:
            self.defilement = max(0, self.defilement - (self.scr.getmaxyx()[0] - 4))
        return True

    def boucle(self):
        self.charger()
        while True:
            self.dessiner()
            try:
                c = self.scr.get_wch()
            except KeyboardInterrupt:
                return
            except curses.error:
                continue
            if c == curses.KEY_RESIZE:
                continue
            self.etat.message = ("", "")
            try:
                if self.mode == "liste":
                    if not self.touche_liste(c):
                        return
                elif self.mode == "fiche":
                    self.touche_fiche(c)
                else:
                    self.touche_page(c)
            except ErreurClient as e:
                self.etat.dire(e.message, "erreur")


def lancer(url=None, projet=None):
    """Point d'entrée de `todo tui` ; retourne un code de sortie."""
    try:
        client = depuis_reglages(url)
    except (RuntimeError, ValueError) as e:
        print(f" ❌ Erreur : {e}", file=sys.stderr)
        return 1
    try:
        client.projets()                                      # joignable ? jeton accepté ?
    except ErreurClient as e:
        aide = " (vérifiez le jeton)" if e.statut == 401 else " (le serveur tourne-t-il ? `todo serve`)" if e.statut == 0 else ""
        print(f" ❌ {client.base} : {e.message}{aide}", file=sys.stderr)
        return 1
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        print(" ❌ Erreur : la TUI demande un terminal interactif.", file=sys.stderr)
        return 1
    locale.setlocale(locale.LC_ALL, "")

    def corps(scr):
        Ecran(scr, Etat(client, projet)).boucle()
    curses.wrapper(corps)
    return 0
