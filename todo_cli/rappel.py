"""Commande `remind` : rappel des tâches en retard (et du jour) à l'ouverture du terminal ou par cron.

Elle n'écrit rien quand il n'y a rien à signaler, pour pouvoir figurer dans `~/.bashrc` ou une
crontab. Trois fichiers d'état vivent dans le dossier de stockage, hors de la base :
  remind_off     présent : rappels désactivés (`--disable`) ; la variable TODO_NO_REMIND fait de même
  remind_last    date du dernier rappel affiché (`--once-a-day`)
  remind_status  résumé d'une ligne, mis à jour par `--write-status`, à lire depuis l'invite du shell
"""
import json
import os
from datetime import datetime
from . import couleurs, reglages, journal
from .config import PRIORITES, REMIND_LAST, REMIND_OFF, REMIND_STATUS, STATUT_A_FAIRE
from .dates import _jours_restants, _libelle_echeance
from .stockage import _lire_taches


# --------------------------------------------------------------------------- état
def rappels_actifs():
    """Faux si un des interrupteurs coupe les rappels : `remind --disable` (fichier d'état), ou le
    réglage [remind] enabled (TODO_REMIND_ENABLED, fichier de configuration) ; TODO_NO_REMIND les coupe
    toujours. Les interrupteurs se cumulent : un seul suffit pour couper."""
    return reglages.obtenir("remind", "enabled") and not os.path.exists(REMIND_OFF)


def _lire(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _ecrire(chemin, texte):
    """Écriture atomique ; un échec (disque en lecture seule…) n'est jamais fatal pour un rappel."""
    tmp = f"{chemin}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(texte)
        os.replace(tmp, chemin)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _supprimer(chemin):
    try:
        os.remove(chemin)
    except FileNotFoundError:
        pass


def etat_rappels():
    """État des rappels : actif ou non, ce qui les coupe, et date du dernier rappel `--once-a-day`.

    Plusieurs interrupteurs peuvent être actifs en même temps : `desactive_par` les liste tous
    (« commande remind --disable », « variable TODO_NO_REMIND », « fichier »…).
    """
    raisons = []
    if os.path.exists(REMIND_OFF):
        raisons.append("commande remind --disable")
    valeur, origine = reglages.obtenir_avec_origine("remind", "enabled")
    if not valeur:
        raisons.append(origine)
    return {"actif": not raisons, "desactive_par": raisons, "dernier_rappel": _lire(REMIND_LAST) or None}


def _afficher_json(document):
    print(json.dumps(document, indent=2, ensure_ascii=False))


def desactiver_rappels(fmt="table"):
    _ecrire(REMIND_OFF, "")
    journal.noter(modifie=True, state="disabled")
    _ecrire(REMIND_STATUS, "")  # le résumé affiché dans l'invite disparaît tout de suite
    if fmt == "json":
        return _afficher_json(etat_rappels())
    print(f" 🔕 Rappels désactivés. Pour les réactiver : {couleurs.CLR_BOLD}todo remind --enable{couleurs.CLR_RESET}")


def activer_rappels(fmt="table"):
    _supprimer(REMIND_OFF)
    journal.noter(modifie=True, state="enabled")
    _supprimer(REMIND_LAST)  # le prochain `--once-a-day` peut s'afficher dès maintenant
    if fmt == "json":
        return _afficher_json(etat_rappels())
    print(f" 🔔 Rappels activés.")
    if not reglages.obtenir("remind", "enabled"):
        _, origine = reglages.obtenir_avec_origine("remind", "enabled")
        print(f"    {couleurs.CLR_DIM}Attention : ils restent coupés ici par le réglage [remind] enabled ({origine}).{couleurs.CLR_RESET}")


def afficher_etat_rappels(fmt="table"):
    if fmt == "json":
        return _afficher_json(etat_rappels())
    if os.path.exists(REMIND_OFF):
        print(f" 🔕 Rappels désactivés (todo remind --enable pour les réactiver).")
    elif not reglages.obtenir("remind", "enabled"):
        _, origine = reglages.obtenir_avec_origine("remind", "enabled")
        print(f" 🔕 Rappels coupés par le réglage [remind] enabled ({origine}).")
    else:
        print(f" 🔔 Rappels activés.")
    dernier = _lire(REMIND_LAST)
    if dernier:
        print(f"    {couleurs.CLR_DIM}Dernier rappel affiché avec --once-a-day : {dernier}.{couleurs.CLR_RESET}")


# --------------------------------------------------------------------------- contenu
def _ordre(t):
    """Priorité haute d'abord, puis échéance la plus ancienne, puis création, id (déterministe)."""
    return (-PRIORITES.index(t['priorite']), t['date_echeance'], t.get('date_creation') or "", t['id'])


def construire_rappel(taches, aujourdhui, bientot=0):
    """Répartit les tâches à faire en retard / pour aujourd'hui / dans les `bientot` prochains jours."""
    retards, du_jour, a_venir = [], [], []
    for t in taches:
        if t['statut'] != STATUT_A_FAIRE:
            continue
        jours = _jours_restants(t, aujourdhui)
        if jours is None:
            continue
        if jours < 0:
            retards.append(t)
        elif jours == 0:
            du_jour.append(t)
        elif jours <= bientot:
            a_venir.append(t)
    for liste in (retards, du_jour, a_venir):
        liste.sort(key=_ordre)
    return retards, du_jour, a_venir


def _compteurs(retards, du_jour, a_venir):
    """['2 tâche(s) en retard', "1 pour aujourd'hui", '3 dans les prochains jours'] (parties non vides)."""
    morceaux = []
    if retards:
        morceaux.append(f"{len(retards)} tâche(s) en retard")
    if du_jour:
        morceaux.append(f"{len(du_jour)} pour aujourd'hui")
    if a_venir:
        morceaux.append(f"{len(a_venir)} dans les prochains jours")
    return morceaux


def resume_une_ligne(retards, du_jour, a_venir):
    """Résumé court, sans couleur, pour l'invite du shell ; chaîne vide s'il n'y a rien."""
    morceaux = []
    if retards:
        morceaux.append(f"{len(retards)} en retard")
    if du_jour:
        morceaux.append(f"{len(du_jour)} aujourd'hui")
    if a_venir:
        morceaux.append(f"{len(a_venir)} à venir")
    return ("⚠ " + " · ".join(morceaux) + " ") if morceaux else ""


def _ligne(t, aujourdhui):
    prio = {"high": couleurs.CLR_P_HIGH, "medium": couleurs.CLR_P_MED, "low": couleurs.CLR_P_LOW}[t['priorite']]
    return (f"   {prio}[{t['priorite'].upper()}]{couleurs.CLR_RESET} {couleurs.CLR_BOLD}{t['titre']}{couleurs.CLR_RESET}"
            f"{_libelle_echeance(t, aujourdhui)} {couleurs.CLR_DIM}(id: {t['id'][:8]}){couleurs.CLR_RESET}")


def texte_rappel(retards, du_jour, a_venir, aujourdhui, limite):
    """Le rappel complet (en-tête, `limite` tâches au plus, pied de page), ou '' s'il n'y a rien."""
    if not (retards or du_jour or a_venir):
        return ""
    couleur = couleurs.CLR_DEL if retards else couleurs.CLR_P_HIGH
    lignes = [f" {couleur}{couleurs.CLR_BOLD}⚠️  {' · '.join(_compteurs(retards, du_jour, a_venir))}{couleurs.CLR_RESET}"]
    toutes = retards + du_jour + a_venir
    lignes.extend(_ligne(t, aujourdhui) for t in toutes[:limite])
    if len(toutes) > limite:
        lignes.append(f"   {couleurs.CLR_DIM}… et {len(toutes) - limite} autre(s){couleurs.CLR_RESET}")
    suite = "todo next" if not retards else "todo list --overdue"
    lignes.append(f" {couleurs.CLR_DIM}→ {suite}{couleurs.CLR_RESET}")
    return "\n".join(lignes)


# --------------------------------------------------------------------------- commande
def _taches_json(taches, aujourdhui):
    """Les tâches telles que `list --format json` les décrit, plus `jours_restants` (négatif = en retard)."""
    return [{**t, "jours_restants": _jours_restants(t, aujourdhui)} for t in taches]


def rappel_json(bientot=0):
    """Document JSON du rappel : toujours émis (même vide), sans limite de nombre de tâches.

    Contrairement au texte, qui reste muet quand il n'y a rien à signaler, un consommateur de JSON
    (jq, script) a besoin d'un document valide à chaque appel. Si les rappels sont désactivés, les
    listes sont vides et `desactive_par` en donne la raison.
    """
    aujourdhui = datetime.now().date()
    etat = etat_rappels()
    retards, du_jour, a_venir = construire_rappel(_lire_taches(), aujourdhui, bientot) if etat["actif"] else ([], [], [])
    return {
        "date": aujourdhui.isoformat(),
        "actif": etat["actif"],
        "desactive_par": etat["desactive_par"],
        "bientot_jours": bientot,
        "compteurs": {"retards": len(retards), "aujourdhui": len(du_jour), "a_venir": len(a_venir),
                      "total": len(retards) + len(du_jour) + len(a_venir)},
        "retards": _taches_json(retards, aujourdhui),
        "aujourdhui": _taches_json(du_jour, aujourdhui),
        "a_venir": _taches_json(a_venir, aujourdhui),
    }


def rappeler(limite=5, bientot=0, une_fois_par_jour=False, ecrire_statut=False, fmt="table"):
    """Affiche le rappel (ou, avec `ecrire_statut`, met à jour le résumé d'une ligne sans rien afficher)."""
    if fmt == "json":
        return _afficher_json(rappel_json(bientot))
    if not rappels_actifs():
        if ecrire_statut:
            _ecrire(REMIND_STATUS, "")
        return

    aujourdhui = datetime.now().date()
    retards, du_jour, a_venir = construire_rappel(_lire_taches(), aujourdhui, bientot)

    if ecrire_statut:
        _ecrire(REMIND_STATUS, resume_une_ligne(retards, du_jour, a_venir))
        return

    texte = texte_rappel(retards, du_jour, a_venir, aujourdhui, limite)
    if not texte:
        return
    if une_fois_par_jour:
        if _lire(REMIND_LAST) == aujourdhui.isoformat():
            return
        _ecrire(REMIND_LAST, aujourdhui.isoformat())
    print(texte)
