from django.core.management.base import BaseCommand

from apps.schools.models import Plan, School

# (audience, nom, description, prix, cycle, options)
PLANS = [
    # --- SaaS auto-écoles (Akwaba)
    ("school", "Basic", "Pour démarrer : 1 agence, jusqu'à 100 apprenants.", 25000, "monthly",
     dict(max_learners=100, max_instructors=3, max_agencies=1, max_cohorts=3, features=["100 apprenants", "3 moniteurs", "1 agence", "Support e-mail"])),
    ("school", "Standard", "Pour une auto-école en croissance.", 60000, "monthly",
     dict(max_learners=500, max_instructors=10, max_agencies=3, max_cohorts=15, is_featured=True,
          features=["500 apprenants", "10 moniteurs", "3 agences", "15 cohortes", "Import Excel illimité"])),
    ("school", "Premium", "Réseau d'auto-écoles, volumes élevés.", 150000, "monthly",
     dict(max_learners=5000, max_instructors=50, max_agencies=20, max_cohorts=200, features=["5 000 apprenants", "50 moniteurs", "20 agences", "Support prioritaire"])),
    # --- Particuliers
    ("individual", "Découverte", "Accès aux QCM d'entraînement pendant 1 mois.", 5000, "monthly",
     dict(includes_exams=False, includes_courses=True, sort_order=1, features=["QCM d'entraînement illimités", "Corrections détaillées", "Suivi de progression"])),
    ("individual", "Réussite", "QCM + examen final pendant 3 mois.", 12000, "quarterly",
     dict(is_featured=True, sort_order=2, features=["QCM d'entraînement illimités", "Examen final + certificat", "Cours théoriques", "Suivi de progression"])),
    ("individual", "Permis B — Annuel", "Accès complet 12 mois, catégorie Permis B.", 35000, "yearly",
     dict(category="B", sort_order=3, features=["Tout le plan Réussite", "12 mois d'accès", "Tarif préférentiel"])),
    # --- Entreprises et établissements (cohortes + places)
    ("organization", "Équipe", "1 cohorte, 20 bénéficiaires inclus.", 90000, "quarterly",
     dict(max_cohorts=1, included_beneficiaries=20, extra_beneficiary_price=4000, sort_order=1,
          features=["1 cohorte", "20 bénéficiaires inclus", "Places supplémentaires à 4 000 FCFA", "Rapport de progression"])),
    ("organization", "Entreprise", "Jusqu'à 3 cohortes, 100 bénéficiaires inclus.", 350000, "semi_annual",
     dict(max_cohorts=3, included_beneficiaries=100, extra_beneficiary_price=3000, is_featured=True, sort_order=2,
          features=["3 cohortes", "100 bénéficiaires inclus", "Places supplémentaires à 3 000 FCFA", "Tableau de bord RH", "Rapports PDF / Excel"])),
    ("organization", "Établissement", "Universités, écoles, ONG : 10 cohortes, 500 bénéficiaires.", 1200000, "yearly",
     dict(max_cohorts=10, included_beneficiaries=500, extra_beneficiary_price=2000, sort_order=3,
          features=["10 cohortes", "500 bénéficiaires inclus", "Places supplémentaires à 2 000 FCFA", "Rapport final de formation"])),
]


class Command(BaseCommand):
    help = "Crée les plans d'abonnement de démonstration (SaaS auto-écoles, particuliers, entreprises & établissements). Idempotent."

    def handle(self, *args, **opts):
        made = 0
        for audience, name, desc, price, cycle, opt in PLANS:
            # plans globaux Akwaba (school vide) ; les plans « school » existants (Basic/Standard/Premium) sont mis à jour
            plan, created = Plan.objects.get_or_create(audience=audience, name=name, school=None,
                                                       defaults=dict(description=desc, price=price, billing_cycle=cycle, **opt))
            if not created and audience == "school":
                plan.price, plan.billing_cycle, plan.description = price, cycle, desc
                plan.save(update_fields=["price", "billing_cycle", "description"])
            made += created
        self.stdout.write(self.style.SUCCESS(f"{made} plan(s) créé(s), {Plan.objects.count()} au total."))
