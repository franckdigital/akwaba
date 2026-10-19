"""Crée le cours « La conduite » en leçons texte (pas de PDF), organisé exactement comme le sommaire du
livre : une section par sous-chapitre (La vitesse, Intersection et priorité, Croisements et dépassements,
L'arrêt et le stationnement, L'autoroute, La conduite de nuit, Les intempéries), une leçon par sujet.

    python manage.py seed_course_conduite

Idempotent : relancer la commande met à jour le cours et ses leçons (par titre) sans créer de doublons.
Contenu source : apps/pedagogy/lessons_conduite.py.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.illustrations import illustration_for
from apps.pedagogy.lesson_pdf import build_lesson_pdf
from apps.pedagogy.lessons_conduite import SECTIONS
from apps.pedagogy.models import Course, CourseMaterial

CHAPTER = "La conduite"


class Command(BaseCommand):
    help = "Crée/actualise le cours « La conduite » en leçons texte, structuré comme le sommaire du livre."

    @transaction.atomic
    def handle(self, *args, **options):
        total_minutes = sum(1 for _, lessons in SECTIONS for _ in lessons) * 4  # ~4 min de lecture par leçon
        course, _ = Course.objects.update_or_create(
            school=None, title="La conduite",
            defaults={
                "kind": "theory", "theme": "code", "level": "all_levels", "language": "Français",
                "summary": "Vitesse, intersections et priorités, croisements et dépassements, arrêt et stationnement, "
                          "autoroute, conduite de nuit et intempéries.",
                "objectives": ["Appliquer la règle de priorité adaptée à chaque intersection.",
                               "Exécuter un dépassement ou un croisement en toute sécurité.",
                               "Adopter la bonne conduite sur autoroute, de nuit et par mauvais temps."],
                "duration_minutes": total_minutes, "is_published": True, "sequential": True,
            },
        )
        # On repart d'un programme propre à chaque exécution (évite les doublons si l'ordre du sommaire change).
        course.materials.all().delete()
        order = 0
        for chapter_num, (section, lessons) in enumerate(SECTIONS, start=1):
            for sub, (title, html) in enumerate(lessons, start=1):
                order += 1
                number = f"{chapter_num}.{sub}"
                pdf = build_lesson_pdf(CHAPTER, section, number, title, html, image_bytes=illustration_for(title))
                m = CourseMaterial.objects.create(
                    course=course, section=section, material_type="pdf", title=title,
                    order=order, duration_minutes=4, is_required=True, download_allowed=True, is_published=True,
                )
                m.file.save(f"conduite-{order:02d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(f"Cours « La conduite » prêt : {len(SECTIONS)} sections, {order} leçons PDF."))
