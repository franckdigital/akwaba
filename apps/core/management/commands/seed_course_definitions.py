"""Crée le cours « Quelques définitions » (lexique du code de la route, chapitre 1 du livre
source docs/code_route.pdf), une leçon par lettre. Chaque leçon incruste un rendu haute
résolution de la vraie page du livre (même principe que pour le cours Signalisation), fidélité
garantie à 100%, au lieu d'un texte reconstruit à la main.

    python manage.py seed_course_definitions

Idempotent : relancer la commande met à jour le cours et ses leçons sans créer de doublons.
Contenu source : apps/pedagogy/data/definitions_page_crops.json + apps/pedagogy/definitions_images/
(générés par apps/pedagogy/../../../scratchpad crop_definitions.py, capture directe du PDF).
"""
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.lesson_pdf import build_lesson_pdf_v2
from apps.pedagogy.models import Course, CourseMaterial

CHAPTER = "Quelques définitions"
_CROPS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "data", "definitions_page_crops.json")
_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "definitions_images")


def _read_img(filename):
    path = os.path.join(_IMG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


class Command(BaseCommand):
    help = "Crée/actualise le cours « Quelques définitions », une leçon par lettre (page du livre incrustée)."

    @transaction.atomic
    def handle(self, *args, **options):
        with open(_CROPS_PATH, encoding="utf-8") as f:
            crops = json.load(f)

        letters = sorted(crops.keys())

        course, _ = Course.objects.update_or_create(
            school=None, title="Quelques définitions",
            defaults={
                "kind": "theory", "theme": "code", "level": "all_levels", "language": "Français",
                "summary": "Lexique des termes utilisés dans le code de la route : agglomération, arrêt, "
                          "stationnement, véhicules, infractions...",
                "objectives": ["Connaître le sens exact des termes employés dans le code de la route.",
                               "Distinguer les différentes catégories de véhicules et de voies."],
                "duration_minutes": len(letters) * 3, "order": 1, "is_published": True, "sequential": True,
            },
        )
        course.materials.all().delete()
        order = 0
        for letter in letters:
            order += 1
            blocks = [{"t": "page_crop", "img_data": _read_img(p)} for p in crops[letter]]
            title = f"Lettre {letter}"
            pdf = build_lesson_pdf_v2(CHAPTER, "Lexique", letter, title, blocks, images=[])
            m = CourseMaterial.objects.create(
                course=course, section="Lexique", material_type="pdf", title=title,
                order=order, duration_minutes=3, is_required=True, download_allowed=True, is_published=True,
            )
            m.file.save(f"definitions-{order:02d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(
            f"Cours « Quelques définitions » prêt : {len(letters)} lettres (page du livre incrustée)."))
