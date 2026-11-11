import pytest

from outils import jour, prochain


def ajouter(todo, texte, *options):
    r = todo("add", texte, *options)
    assert r.code == 0, r.texte
    return r


def tache(todo):
    """L'unique tâche de la base."""
    taches = list(todo.taches().values())
    assert len(taches) == 1
    return taches[0]


def test_exemple_complet(todo):
    r = ajouter(todo, "Appeler Paul demain !high #pro #urgent")
    t = tache(todo)
    assert (t["titre"], t["priorite"], t["date_echeance"], t["tags"]) == ("Appeler Paul", "high", jour(1), ["pro", "urgent"])
    assert "Compris dans le titre" in r.texte and f"échéance {jour(1)}" in r.texte
    assert "priorité HIGH" in r.texte and "#pro #urgent" in r.texte


@pytest.mark.parametrize("mot, attendu", [
    ("demain", jour(1)), ("Demain", jour(1)), ("aujourd'hui", jour(0)), ("après-demain", jour(2)),
    ("apres-demain", jour(2)), ("+3d", jour(3)), ("+2w", jour(14)), ("2030-05-17", "2030-05-17"),
    ("@demain", jour(1)), ("@+3d", jour(3)), ("@2030-05-17", "2030-05-17"),
    ("lundi", prochain(0).strftime("%Y-%m-%d")), ("@vendredi", prochain(4).strftime("%Y-%m-%d")),
    ("friday", prochain(4).strftime("%Y-%m-%d")),
])
def test_dates(todo, mot, attendu):
    ajouter(todo, f"Tâche {mot} suite")
    t = tache(todo)
    assert t["date_echeance"] == attendu and t["titre"] == "Tâche suite"


def test_date_en_debut_ou_fin_de_titre(todo):
    ajouter(todo, "demain Réunion")
    assert tache(todo)["titre"] == "Réunion" and tache(todo)["date_echeance"] == jour(1)


@pytest.mark.parametrize("marque, attendu", [
    ("!high", "high"), ("!HIGH", "high"), ("!haute", "high"), ("!h", "high"),
    ("!medium", "medium"), ("!moyenne", "medium"), ("!m", "medium"),
    ("!low", "low"), ("!basse", "low"), ("!l", "low"),
])
def test_priorites(todo, marque, attendu):
    ajouter(todo, f"Faire {marque} ceci")
    t = tache(todo)
    assert t["priorite"] == attendu and t["titre"] == "Faire ceci"


def test_tags(todo):
    ajouter(todo, "Acheter #Courses du pain #maison #courses #long-tag_2")
    t = tache(todo)
    assert t["titre"] == "Acheter du pain" and t["tags"] == ["courses", "maison", "long-tag_2"]  # minuscules, sans doublon


@pytest.mark.parametrize("marque, attendu", [("~weekly", "1w"), ("~2w", "2w"), ("~mensuel", "1m"), ("~daily", "1d")])
def test_recurrence(todo, marque, attendu):
    r = ajouter(todo, f"Sauvegarde {marque}")
    t = tache(todo)
    assert t["recurrence"] == attendu and t["titre"] == "Sauvegarde"
    assert t["date_echeance"] == jour(0)                      # échéance par défaut d'une récurrente
    assert "répétition" in r.texte


def test_recurrence_avec_date(todo):
    ajouter(todo, "Relevé ~monthly @2030-01-15")
    t = tache(todo)
    assert t["recurrence"] == "1m" and t["date_echeance"] == "2030-01-15" and t["titre"] == "Relevé"


@pytest.mark.parametrize("texte", [
    "Rapport #42",                 # tag : doit commencer par une lettre
    "Super !",                     # point d'exclamation seul
    "Bravo !bravo",                # priorité inconnue
    "Voir @truc",                  # date inconnue
    "Voir @",                      # arobase seul
    "Cycle ~xyz",                  # récurrence inconnue
    "Tarif 100% garanti",
    "Réunion à 10h",
    "Un titre sans marqueur",
])
def test_faux_positifs_restent_dans_le_titre(todo, texte):
    r = ajouter(todo, texte)
    t = tache(todo)
    assert t["titre"] == texte and t["priorite"] == "medium" and t["date_echeance"] is None and t["tags"] == []
    assert "Compris" not in r.texte


def test_titre_reduit_a_rien_est_conserve(todo):
    for texte in ("demain", "#pro", "!high", "@lundi ~daily"):
        todo("add", texte)
    assert sorted(t["titre"] for t in todo.taches().values()) == sorted(["demain", "#pro", "!high", "@lundi ~daily"])
    assert all(t["priorite"] == "medium" and t["tags"] == [] for t in todo.taches().values())


def test_le_dernier_marqueur_l_emporte(todo):
    ajouter(todo, "Truc !low !high demain +2d")
    t = tache(todo)
    assert t["priorite"] == "high" and t["date_echeance"] == jour(2) and t["titre"] == "Truc"


def test_espaces_normalises_seulement_si_extraction(todo):
    ajouter(todo, "Deux   espaces  demain")
    assert tache(todo)["titre"] == "Deux espaces"


# ------------------------------------------------------------ options explicites et --literal
def test_option_explicite_prioritaire_et_mot_conserve(todo):
    ajouter(todo, "Plan demain !low #x", "--due", "+5d")
    t = tache(todo)
    assert t["date_echeance"] == jour(5)
    assert t["titre"] == "Plan demain" and t["priorite"] == "low" and t["tags"] == ["x"]


@pytest.mark.parametrize("option, valeur, reste", [
    ("--prio", "high", "!low"), ("--tags", "a,b", "#x"), ("--repeat", "daily", "~weekly"),
])
def test_chaque_option_neutralise_son_marqueur(todo, option, valeur, reste):
    ajouter(todo, f"Titre {reste} demain", option, valeur)
    t = tache(todo)
    assert reste in t["titre"] and t["date_echeance"] == jour(1)      # la date, elle, reste interprétée
    if option == "--prio":
        assert t["priorite"] == "high"
    if option == "--tags":
        assert t["tags"] == ["a", "b"]
    if option == "--repeat":
        assert t["recurrence"] == "1d"


def test_tags_vides_explicites_neutralisent_les_hashtags(todo):
    ajouter(todo, "Titre #x", "--tags", "")
    assert tache(todo)["titre"] == "Titre #x" and tache(todo)["tags"] == []


def test_literal(todo):
    r = ajouter(todo, "Plan demain !high #pro ~weekly", "--literal")
    t = tache(todo)
    assert t["titre"] == "Plan demain !high #pro ~weekly" and t["priorite"] == "medium"
    assert t["date_echeance"] is None and t["tags"] == [] and t["recurrence"] is None
    assert "Compris" not in r.texte


def test_literal_avec_options(todo):
    ajouter(todo, "Plan demain", "--literal", "--due", "+2d", "--prio", "low")
    t = tache(todo)
    assert t["titre"] == "Plan demain" and t["date_echeance"] == jour(2) and t["priorite"] == "low"


def test_description_non_concernee(todo):
    ajouter(todo, "Titre demain", "--desc", "voir demain !high")
    assert tache(todo)["description"] == "voir demain !high"


# ------------------------------------------------------------ comportements inchangés
def test_options_classiques_inchangees(todo):
    ajouter(todo, "Rapport", "--prio", "high", "--due", "2026-12-25", "--tags", "pro,x", "--desc", "d")
    t = tache(todo)
    assert (t["priorite"], t["date_echeance"], t["tags"]) == ("high", "2026-12-25", ["pro", "x"])


def test_priorite_par_defaut_toujours_medium(todo):
    ajouter(todo, "Rien")
    assert tache(todo)["priorite"] == "medium"


def test_priorite_invalide_toujours_refusee(todo):
    assert todo("add", "X", "--prio", "urgent").code == 2


def test_une_sauvegarde_et_pas_de_couleur_dans_un_pipe(todo):
    r = ajouter(todo, "Appeler demain !high")
    assert len(todo.sauvegardes()) == 1 and "\x1b" not in r.out
    assert "\x1b[" in todo("add", "Appeler demain !high", "--color", "always").out


def test_aide_documente_la_saisie_rapide(todo):
    sortie = todo("add", "--help").out
    assert "--literal" in sortie and "demain" in sortie
