"""État et actions de la TUI, sans aucun code d'écran (donc testable sans terminal) : tout passe par `client.Client`."""
from .client import ErreurClient

STATUTS = ("todo", "done", "")                 # "" = toutes
LIBELLES_STATUT = {"todo": "à faire", "done": "terminées", "": "toutes"}
TRIS = ("", "due", "priority", "alpha")
LIBELLES_TRI = {"": "défaut", "due": "échéance", "priority": "priorité", "alpha": "alphabétique"}
PRIORITES = ("low", "medium", "high")
LIBELLES_ACTION = {"done": "Tâche terminée", "undone": "Tâche rouverte", "start": "Tâche démarrée",
                   "unstart": "Démarrage annulé", "postpone": "Échéance reportée", "move": "Tâche déplacée"}


class Etat:
    def __init__(self, client, projet=None):
        self.client = client
        self.projet = projet                   # None = projet courant du serveur
        self.statut, self.recherche, self.tag, self.prio, self.tri = "todo", "", "", "", ""
        self.taches, self.sel = [], 0
        self.projets, self.courant = [], ""
        self.fiche = self.etag = None
        self.message = ("", "")

    # ------------------------------------------------------------------ outils
    def _essayer(self, fonction):
        """Exécute un appel ; en cas d'échec, mémorise le message d'erreur et retourne (None, False)."""
        try:
            return fonction(), True
        except ErreurClient as e:
            self.message = ("erreur", e.message)
            self.derniere_erreur = e
            return None, False

    def dire(self, texte, niveau="ok"):
        self.message = (niveau, texte)

    def filtres(self):
        return {"status": self.statut, "search": self.recherche, "tag": self.tag, "prio": self.prio, "sort": self.tri}

    def libelle_filtres(self):
        parties = [LIBELLES_STATUT[self.statut]]
        if self.recherche:
            parties.append(f"« {self.recherche} »")
        if self.tag:
            parties.append(f"#{self.tag}")
        if self.prio:
            parties.append(f"prio {self.prio}")
        if self.tri:
            parties.append(f"tri {LIBELLES_TRI[self.tri]}")
        return " · ".join(parties)

    # ------------------------------------------------------------------ liste
    def courante(self):
        return self.taches[self.sel] if 0 <= self.sel < len(self.taches) else None

    def charger(self, garder=None):
        """Relit la liste (et les projets) ; garde la sélection sur la même tâche si elle existe encore."""
        garder = garder or (self.courante() or {}).get("id")
        taches, ok = self._essayer(lambda: self.client.taches(self.projet, **self.filtres()))
        if not ok:
            return False
        self.taches = taches
        self.sel = next((i for i, t in enumerate(taches) if t["id"] == garder), min(self.sel, max(len(taches) - 1, 0)))
        donnees, ok = self._essayer(self.client.projets)
        if ok:
            self.projets, self.courant = donnees.get("projets", []), donnees.get("courant", "")
        return True

    def nom_projet(self):
        return self.projet or self.courant or "?"

    def bouger(self, delta):
        if self.taches:
            self.sel = max(0, min(len(self.taches) - 1, self.sel + delta))

    def aller(self, fin):
        self.sel = max(len(self.taches) - 1, 0) if fin else 0

    def cycler_statut(self):
        self.statut = STATUTS[(STATUTS.index(self.statut) + 1) % len(STATUTS)]
        return self.charger()

    def cycler_tri(self):
        self.tri = TRIS[(TRIS.index(self.tri) + 1) % len(TRIS)]
        return self.charger()

    def cycler_prio(self):
        ordre = ("",) + PRIORITES
        self.prio = ordre[(ordre.index(self.prio) + 1) % len(ordre)]
        return self.charger()

    def definir_recherche(self, texte):
        self.recherche = texte.strip()
        return self.charger()

    def definir_tag(self, texte):
        self.tag = texte.strip().lstrip("#")
        return self.charger()

    def reinitialiser_filtres(self):
        self.statut, self.recherche, self.tag, self.prio, self.tri = "todo", "", "", "", ""
        return self.charger()

    def changer_projet(self, nom):
        ancien = self.projet
        self.projet = nom or None
        self.sel = 0
        if not self.charger():
            self.projet = ancien
            return False
        return True

    # ------------------------------------------------------------------ fiche
    def ouvrir_fiche(self, id_=None):
        id_ = id_ or (self.courante() or {}).get("id")
        if not id_:
            return False
        resultat, ok = self._essayer(lambda: self.client.tache(id_, self.projet))
        if ok:
            self.fiche, self.etag = resultat
        return ok

    def fermer_fiche(self):
        self.fiche = self.etag = None

    def _recharger_apres(self, ferme=False):
        self.charger(garder=(self.fiche or {}).get("id"))
        if ferme:
            self.fermer_fiche()
        elif self.fiche:
            self.ouvrir_fiche(self.fiche["id"])

    def _ecrire(self, fonction, succes, ferme=False):
        """Écriture sur la fiche ouverte (avec `If-Match`) ou sur la sélection de la liste (sans)."""
        resultat, ok = self._essayer(fonction)
        if not ok:
            if getattr(self, "derniere_erreur", None) is not None and self.derniere_erreur.conflit and self.fiche:
                self.dire("Tâche modifiée ailleurs : fiche relue, recommencez.", "erreur")
                self.ouvrir_fiche(self.fiche["id"])
            return False
        tache, _ = resultat
        self.dire(succes if tache is not None else "Rien à faire (déjà dans cet état ?).", "ok" if tache is not None else "info")
        self._recharger_apres(ferme)
        return True

    def _cible(self):
        """(id, etag) : la fiche ouverte, sinon la tâche sélectionnée."""
        if self.fiche:
            return self.fiche["id"], self.etag
        t = self.courante()
        return (t["id"], None) if t else (None, None)

    # ------------------------------------------------------------------ écritures
    def action(self, nom, corps=None):
        id_, etag = self._cible()
        if not id_:
            self.dire("Aucune tâche sélectionnée.", "info")
            return False
        return self._ecrire(lambda: self.client.action(id_, nom, corps, self.projet, etag), LIBELLES_ACTION[nom],
                            ferme=(nom == "move"))

    def basculer_termine(self):
        t = self.fiche or self.courante()
        if not t:
            self.dire("Aucune tâche sélectionnée.", "info")
            return False
        return self.action("undone" if t["statut"] != "A FAIRE" else "done")

    def basculer_demarrage(self):
        t = self.fiche or self.courante()
        if not t:
            self.dire("Aucune tâche sélectionnée.", "info")
            return False
        return self.action("unstart" if t.get("demarree") else "start")

    def ajouter(self, titre, rapide=True):
        if not titre.strip():
            self.dire("Titre vide.", "info")
            return False
        champs = {"titre": titre.strip(), **({"saisie_rapide": True} if rapide else {})}
        resultat, ok = self._essayer(lambda: self.client.ajouter(champs, self.projet))
        if not ok:
            return False
        self.dire("Tâche ajoutée.")
        self.charger(garder=(resultat[0] or {}).get("id"))
        return True

    def modifier(self, champs, succes="Tâche modifiée."):
        id_, etag = self._cible()
        if not id_:
            return False
        return self._ecrire(lambda: self.client.modifier(id_, champs, self.projet, etag), succes)

    def noter(self, texte):
        if not texte.strip():
            self.dire("Note vide.", "info")
            return False
        return self.modifier({"note": texte.strip()}, "Note ajoutée.")

    def changer_priorite(self):
        t = self.fiche or self.courante()
        if not t:
            return False
        suivante = PRIORITES[(PRIORITES.index(t["priorite"]) + 1) % len(PRIORITES)]
        return self.modifier({"priorite": suivante}, f"Priorité : {suivante}.")

    def supprimer(self):
        id_, etag = self._cible()
        if not id_:
            return False
        return self._ecrire(lambda: self.client.supprimer(id_, self.projet, etag), "Tâche supprimée (annulable : todo undo).",
                            ferme=True)

    # ------------------------------------------------------------------ autres vues
    def agenda(self, jours=7):
        donnees, ok = self._essayer(lambda: self.client.agenda(self.projet, jours))
        return donnees if ok else None

    def stats(self):
        donnees, ok = self._essayer(lambda: self.client.stats(self.projet))
        return donnees if ok else None
