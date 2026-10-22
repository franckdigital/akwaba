"""Crée/actualise une fiche OfferTypeConfig par type de demande (offer), pour chaque auto-école existante.

Reprend le texte déjà affiché par les 4 cartes du formulaire public de devis (web/src/pages/QuoteWizard.jsx,
OFFERS) comme valeurs par défaut de title/description — l'admin peut ensuite les personnaliser par auto-école.

    python manage.py seed_offer_type_configs

Idempotent : update_or_create par (school, offer).
"""
from django.core.management.base import BaseCommand

from apps.admissions.models import OfferTypeConfig
from apps.schools.models import School

# (offer, title, description, base_price, features)
DEFAULTS = [
    ("new_license", "Nouveau permis de conduire",
     "Vous n'avez pas encore de permis : préparez-le avec Akwaba.", 150000,
     ["Cours théoriques (code de la route)", "QCM d'entraînement illimités", "Séances de conduite pratique",
      "Accompagnement jusqu'à l'examen"]),
    ("extension", "Extension de catégorie",
     "Vous avez déjà un permis et souhaitez ajouter une catégorie.", 80000,
     ["Formation ciblée sur la nouvelle catégorie", "Cours théoriques complémentaires",
      "Séances de conduite pratique", "Accompagnement jusqu'à l'examen"]),
    ("theory_refresh", "Recyclage théorique",
     "Remettez à niveau vos connaissances du code de la route.", 15000,
     ["Modules/packages au choix", "QCM d'entraînement illimités", "Mise à jour réglementaire"]),
    ("practical_refresh", "Recyclage pratique",
     "Remettez à niveau votre conduite avec un moniteur.", 90000,
     ["Séances avec un moniteur", "Forfaits 10 ou 20 séances", "Évaluation de progression"]),
]


class Command(BaseCommand):
    help = "Crée/actualise une fiche OfferTypeConfig (ce qui est inclus) par type de demande, pour chaque auto-école. Idempotent."

    def handle(self, *args, **opts):
        schools = list(School.objects.all())
        if not schools:
            return self.stderr.write("Aucune auto-école : lancez d'abord seed_demo.")

        made = 0
        for school in schools:
            for offer, title, description, base_price, features in DEFAULTS:
                OfferTypeConfig.objects.update_or_create(
                    school=school, offer=offer,
                    defaults={"title": title, "description": description, "base_price": base_price,
                             "features": features, "includes_courses": True, "includes_quizzes": True,
                             "includes_exams": offer in ("new_license", "extension"), "is_active": True},
                )
                made += 1

        self.stdout.write(self.style.SUCCESS(
            f"{made} fiche(s) OfferTypeConfig créée(s)/mise(s) à jour pour {len(schools)} auto-école(s)."))
