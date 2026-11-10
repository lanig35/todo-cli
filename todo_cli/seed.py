"""Outil de développement : génération de tâches factices (nécessite `faker`)."""
import random
import sys
from datetime import datetime
from datetime import timedelta
from .config import PRIORITES
from . import couleurs
from .sauvegardes import sauvegarder_base
from .taches import ajouter_tache


def peupler_fausses_taches(nombre):
    """Injecte un jeu de données factices complexes pour le test de charge."""
    try:
        from faker import Faker
    except ImportError:
        print(f" {couleurs.CLR_DEL}❌ Erreur :{couleurs.CLR_RESET} Le module 'faker' est requis. Lancez : pip install faker")
        sys.exit(1)

    fake = Faker('fr_FR')
    liste_tags_test = ['pro', 'perso', 'dev', 'achat', 'urgent', 'sante', 'admin']

    print(f" ⏳ Génération de {couleurs.CLR_BOLD}{nombre}{couleurs.CLR_RESET} tâches factices...")

    for _ in range(nombre):
        titre = fake.sentence(nb_words=3)
        description = fake.sentence(nb_words=10)
        priorite = random.choice(PRIORITES)
        jours_ecart = random.randint(-3, 10)
        date_echeance = (datetime.now() + timedelta(days=jours_ecart)).strftime("%Y-%m-%d")

        if random.random() < 0.15:
            date_echeance = None

        tags_choisis = random.sample(liste_tags_test, k=random.randint(0, 2))
        # Pas de sauvegarde à chaque tâche : une seule à la fin
        ajouter_tache(titre, description, priorite, date_echeance, ",".join(tags_choisis),
                      silencieux=True, sauvegarder=False)

    sauvegarder_base()
    print(f" {couleurs.CLR_DONE}🎉 Injection de données de test validée.{couleurs.CLR_RESET}")
