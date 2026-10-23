"""Crée/actualise une fiche OfferTypeConfig par type de demande (offer), pour chaque auto-école existante,
PUIS génère/synchronise les 4 plans d'abonnement individuels correspondants (un par type de demande) et
retire de la vente les anciens plans génériques (Découverte, Réussite...) qui ne sont liés à aucun type de
demande — décision produit (§ mise à jour majeure) : les 4 plans par type de demande sont désormais LES
seuls plans individuels proposés à la vente.

Droits inclus par type (§ mise à jour majeure) :
- Nouveau permis / Extension (même formalités) : cours + QCM + examens, tous les modules.
- Recyclage théorique : cours + QCM, PAS d'examens (renforcement de capacités, pas une préparation d'examen).
- Recyclage pratique : aucun flag plateforme — son contenu, ce sont les séances/tarifs par module du
  catalogue de recyclage (RecyclingItem via seed_recycling_sessions), pas un accès cours/QCM/examens.

Reprend le texte déjà affiché par les 4 cartes du formulaire public de devis (web/src/pages/QuoteWizard.jsx,
OFFERS) comme valeurs par défaut de title/description — l'admin peut ensuite les personnaliser par auto-école.

    python manage.py seed_offer_type_configs

Idempotent : update_or_create par (school, offer) ; les anciens plans génériques sont désactivés (is_active
= False), jamais supprimés, pour ne pas casser l'historique des abonnés déjà souscrits dessus.
"""
from django.core.management.base import BaseCommand

from apps.admissions.models import OfferTypeConfig
from apps.admissions.services import sync_plan_for_offer_config
from apps.schools.models import Plan, School

# (offer, title, description, base_price, features, includes_courses, includes_quizzes, includes_exams)
DEFAULTS = [
    ("new_license", "Nouveau permis de conduire",
     "Vous n'avez pas encore de permis : préparez-le avec Akwaba.", 150000,
     ["Cours théoriques (code de la route)", "QCM d'entraînement illimités", "Séances de conduite pratique",
      "Accompagnement jusqu'à l'examen"], True, True, True),
    ("extension", "Extension de catégorie",
     "Vous avez déjà un permis et souhaitez ajouter une catégorie.", 80000,
     ["Formation ciblée sur la nouvelle catégorie", "Cours théoriques complémentaires",
      "Séances de conduite pratique", "Accompagnement jusqu'à l'examen"], True, True, True),
    ("theory_refresh", "Recyclage théorique",
     "Remettez à niveau vos connaissances du code de la route.", 15000,
     ["Modules au choix", "QCM d'entraînement illimités", "Mise à jour réglementaire"], True, True, False),
    ("practical_refresh", "Recyclage pratique",
     "Remettez à niveau votre conduite avec un moniteur.", 90000,
     ["Séances avec un moniteur", "Forfaits par module", "Évaluation de progression"], False, False, False),
]


class Command(BaseCommand):
    help = ("Crée/actualise les 4 fiches OfferTypeConfig (une par type de demande) pour chaque auto-école, "
            "synchronise leur plan d'abonnement individuel, et retire de la vente les anciens plans "
            "génériques non liés à un type de demande. Idempotent.")

    def handle(self, *args, **opts):
        schools = list(School.objects.all())
        if not schools:
            return self.stderr.write("Aucune auto-école : lancez d'abord seed_demo.")

        made = 0
        for school in schools:
            for offer, title, description, base_price, features, courses, quizzes, exams in DEFAULTS:
                config, _ = OfferTypeConfig.objects.update_or_create(
                    school=school, offer=offer,
                    defaults={"title": title, "description": description, "base_price": base_price,
                             "features": features, "includes_courses": courses, "includes_quizzes": quizzes,
                             "includes_exams": exams, "is_active": True},
                )
                sync_plan_for_offer_config(config)
                made += 1

        retired = Plan.objects.filter(audience="individual", linked_offer="").update(is_active=False)

        self.stdout.write(self.style.SUCCESS(
            f"{made} fiche(s) OfferTypeConfig créée(s)/mise(s) à jour (et leur plan synchronisé) pour "
            f"{len(schools)} auto-école(s). {retired} ancien(s) plan(s) générique(s) retiré(s) de la vente."))
