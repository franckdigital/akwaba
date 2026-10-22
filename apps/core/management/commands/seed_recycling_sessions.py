"""Complète le catalogue de recyclage (§3.3) avec :

1. Des formules de recyclage PRATIQUE à la séance (RecyclingItem kind="package", sessions_count renseigné) :
   « 10 séances » et « 20 séances » de 45 minutes chacune. Tarif de référence : les formations complètes
   facturées par seed_demo (code + conduite, ~20h de pratique) tournent autour de 150 000 à 450 000 FCFA ;
   on retient ici un tarif à la séance dégressif par palier pour le recyclage (séances isolées, pas de
   formation complète).

2. Un petit catalogue de modules de recyclage THÉORIQUE (RecyclingItem kind="module"), chacun relié au
   cours correspondant (apps.pedagogy.Course) pour que le module acheté donne accès au bon contenu (§5.3).

    python manage.py seed_recycling_sessions

Idempotent : relancer la commande met à jour les lignes existantes (update_or_create par label) sans
créer de doublons.
"""
from django.core.management.base import BaseCommand

from apps.admissions.models import RecyclingItem
from apps.pedagogy.models import Course
from apps.schools.models import School

# Recyclage pratique : forfaits à la séance (45 min/séance).
PRACTICAL_PACKAGES = [
    {"label": "Recyclage pratique — 10 séances", "sessions_count": 10, "price": 90000},
    {"label": "Recyclage pratique — 20 séances", "sessions_count": 20, "price": 160000},
]

# Recyclage théorique : modules reliés aux cours déjà seedés (seed_course_*).
THEORY_MODULES = [
    {"label": "Signalisation", "price": 15000, "course_title": "Signalisation"},
    {"label": "Règles de circulation et priorités", "price": 15000, "course_title": "La conduite"},
    {"label": "Vitesse et distances de sécurité", "price": 12000, "course_title": "La conduite"},
    {"label": "Le conducteur et son comportement", "price": 12000, "course_title": "Le conducteur"},
    {"label": "Code — mise à jour réglementaire", "price": 18000, "course_title": "Les permis"},
]


class Command(BaseCommand):
    help = ("Crée/actualise les formules de recyclage pratique à la séance (10/20 séances) et le catalogue "
            "de modules de recyclage théorique relié aux cours existants (idempotent, par label).")

    def handle(self, *args, **opts):
        school = School.objects.first()
        if not school:
            return self.stderr.write("Aucune auto-école : lancez d'abord seed_demo.")

        packages_done = 0
        for p in PRACTICAL_PACKAGES:
            RecyclingItem.objects.update_or_create(
                school=school, label=p["label"],
                defaults={"kind": "package", "price": p["price"], "sessions_count": p["sessions_count"], "is_active": True},
            )
            packages_done += 1

        modules_done = 0
        missing_courses = []
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
