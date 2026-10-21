"""Crée le cours « Quelques définitions » (lexique du code de la route, chapitre 1 du livre
source docs/code_route.pdf), fidèle au texte réel : une leçon par lettre (A, B, C...), chaque
terme de cette lettre étant un sous-titre avec sa définition exacte.

    python manage.py seed_course_definitions

Idempotent : relancer la commande met à jour le cours et ses leçons sans créer de doublons.
Contenu source : apps/pedagogy/data/definitions_lessons.json (extrait directement du PDF).
"""
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.lesson_pdf import build_lesson_pdf_v2
from apps.pedagogy.models import Course, CourseMaterial

CHAPTER = "Quelques définitions"
_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "data", "definitions_lessons.json")


class Command(BaseCommand):
    help = "Crée/actualise le cours « Quelques définitions », une leçon par lettre du lexique."

    @transaction.atomic
    def handle(self, *args, **options):
        with open(_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)

        letters = sorted(data.keys())
        total_terms = sum(len(data[l]) for l in letters)

        course, _ = Course.objects.update_or_create(
            school=None, title="Quelques définitions",
            defaults={
                "kind": "theory", "theme": "code", "level": "all_levels", "language": "Français",
                "summary": "Lexique des termes utilisés dans le code de la route : agglomération, arrêt, "
                          "stationnement, véhicules, infractions...",
                "objectives": ["Connaître le sens exact des termes employés dans le code de la route.",
                               "Distinguer les différentes catégories de véhicules et de voies."],
                "duration_minutes": len(letters) * 3, "is_published": True, "sequential": True,
            },
        )
        course.materials.all().delete()
        order = 0
        for letter in letters:
            order += 1
            blocks = []
            for i, item in enumerate(data[letter]):
                if i == 0:
                    blocks.append({"t": "quote", "text": f"{item['term']} : {item['def']}"})
                else:
                    blocks.append({"t": "h", "text": item["term"]})
                    blocks.append({"t": "p", "text": item["def"]})
            title = f"Lettre {letter}"
            pdf = build_lesson_pdf_v2(CHAPTER, "Lexique", letter, title, blocks, images=[])
            m = CourseMaterial.objects.create(
                course=course, section="Lexique", material_type="pdf", title=title,
                order=order, duration_minutes=3, is_required=True, download_allowed=True, is_published=True,
            )
            m.file.save(f"definitions-{order:02d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(
            f"Cours « Quelques définitions » prêt : {len(letters)} lettres, {total_terms} termes."))
