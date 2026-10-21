"""Crée le cours « Les permis » (chapitres 14 et 15 du livre source docs/code_route.pdf), une
leçon par sujet numéroté (14.1 à 14.5, 15.1 à 15.4). Chaque leçon incruste un rendu haute
résolution de sa vraie page/double-page du livre (même principe que les autres cours).

    python manage.py seed_course_permis
"""
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.lesson_pdf import build_lesson_pdf_v2
from apps.pedagogy.models import Course, CourseMaterial

CHAPTER = "Les permis"
SECTION_NAMES = {"14": "Les permis", "15": "Le permis à points"}
_CROPS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "data", "permis_page_crops.json")
_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "permis_images")


def _read_img(filename):
    path = os.path.join(_IMG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


def _num_key(num):
    major, minor = num.split(".")
    return (int(major), int(minor))


class Command(BaseCommand):
    help = "Crée/actualise le cours « Les permis », une leçon par sujet numéroté (page du livre incrustée)."

    @transaction.atomic
    def handle(self, *args, **options):
        with open(_CROPS_PATH, encoding="utf-8") as f:
            crops = json.load(f)

        nums = sorted(crops.keys(), key=_num_key)

        course, _ = Course.objects.update_or_create(
            school=None, title=CHAPTER,
            defaults={
                "kind": "theory", "theme": "code", "level": "all_levels", "language": "Français",
                "summary": "Règle générale, catégories de permis, visite médicale, épreuves, sanctions, "
                          "permis à points et permis probatoire.",
                "objectives": ["Connaître les différentes catégories de permis.",
                               "Comprendre le fonctionnement du permis à points.",
                               "Connaître les sanctions et leur récupération."],
                "duration_minutes": len(nums) * 4, "order": 6, "is_published": True, "sequential": True,
            },
        )
        course.materials.all().delete()
        order = 0
        for num in nums:
            order += 1
            entry = crops[num]
            title = entry["title"]
            section = SECTION_NAMES.get(num.split(".")[0], CHAPTER)
            blocks = [{"t": "page_crop", "img_data": _read_img(p)} for p in entry["paths"]]
            pdf = build_lesson_pdf_v2(CHAPTER, section, num, title, blocks, images=[])
            m = CourseMaterial.objects.create(
                course=course, section=section, material_type="pdf", title=title,
                order=order, duration_minutes=4, is_required=True, download_allowed=True, is_published=True,
            )
            m.file.save(f"permis-{order:02d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(f"Cours « {CHAPTER} » prêt : {order} leçons (page du livre incrustée)."))
