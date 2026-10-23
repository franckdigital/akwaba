"""Complète le catalogue de recyclage (§3.3) avec :

1. Un catalogue de modules de recyclage THÉORIQUE (RecyclingItem kind="module"), un par cours du code de
   la route (Signalisation, La conduite, Le conducteur, Le véhicule, Les permis), chacun relié au cours
   correspondant (apps.pedagogy.Course) pour que le module acheté donne accès au bon contenu (§5.3).
   Tarif : 25 000 FCFA par module.

2. Des formules de recyclage PRATIQUE à la séance (RecyclingItem kind="package", sessions_count renseigné),
   une par module également : Signalisation = 10 séances à 50 000 FCFA, les 4 autres modules = 5 séances
   à 25 000 FCFA chacun.

    python manage.py seed_recycling_sessions

Idempotent : relancer la commande met à jour les lignes existantes (update_or_create par label) sans
créer de doublons.
"""
from django.core.management.base import BaseCommand

from apps.admissions.models import RecyclingItem
from apps.pedagogy.models import Course
from apps.schools.models import School

MODULES = ["Signalisation", "La conduite", "Le conducteur", "Le véhicule", "Les permis"]
THEORY_PRICE = 25000

# Recyclage théorique : un module par cours, 25 000 FCFA chacun.
THEORY_MODULES = [{"label": m, "price": THEORY_PRICE, "course_title": m} for m in MODULES]

# Recyclage pratique : un forfait de séances par module — Signalisation = 10 séances/50 000 F,
# les autres = 5 séances/25 000 F chacun.
PRACTICAL_PACKAGES = [
    {"label": f"Recyclage pratique — {m}", "sessions_count": 10 if m == "Signalisation" else 5,
     "price": 50000 if m == "Signalisation" else 25000, "course_title": m}
    for m in MODULES
]


class Command(BaseCommand):
    help = ("Crée/actualise les formules de recyclage pratique à la séance (10/20 séances) et le catalogue "
            "de modules de recyclage théorique relié aux cours existants (idempotent, par label).")

    # Anciens libellés remplacés par le nouveau catalogue (un module/forfait par cours) : supprimés s'ils
    # existent encore, pour ne pas laisser d'entrées obsolètes dans le catalogue.
    OBSOLETE_LABELS = [
        "Recyclage pratique — 10 séances", "Recyclage pratique — 20 séances",
        "Règles de circulation et priorités", "Vitesse et distances de sécurité",
        "Le conducteur et son comportement", "Code — mise à jour réglementaire",
    ]

    def handle(self, *args, **opts):
        school = School.objects.first()
        if not school:
            return self.stderr.write("Aucune auto-école : lancez d'abord seed_demo.")

        removed, _ = RecyclingItem.objects.filter(school=school, label__in=self.OBSOLETE_LABELS).delete()
        if removed:
            self.stdout.write(f"{removed} ancienne(s) ligne(s) de catalogue supprimée(s).")

        missing_courses = []

        packages_done = 0
        for p in PRACTICAL_PACKAGES:
            course = Course.objects.filter(school=None, title=p["course_title"]).first()
            if not course:
                missing_courses.append(p["course_title"])
            RecyclingItem.objects.update_or_create(
                school=school, label=p["label"],
                defaults={"kind": "package", "price": p["price"], "sessions_count": p["sessions_count"], "course": course, "is_active": True},
            )
            packages_done += 1

        modules_done = 0
        for m in THEORY_MODULES:
            course = Course.objects.filter(school=None, title=m["course_title"]).first()
            if not course:
                missing_courses.append(m["course_title"])
            RecyclingItem.objects.update_or_create(
                school=school, label=m["label"],
                defaults={"kind": "module", "price": m["price"], "course": course, "is_active": True},
            )
            modules_done += 1

        self.stdout.write(self.style.SUCCESS(
            f"{packages_done} formule(s) de recyclage pratique (séances) et {modules_done} module(s) de "
            f"recyclage théorique créés/mis à jour."))
        if missing_courses:
            self.stdout.write(self.style.WARNING(
                "Cours introuvable(s) (module créé sans lien de cours) : " + ", ".join(missing_courses)))
