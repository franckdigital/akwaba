"""Crée le cours « Le véhicule » (chapitre 13 du livre source docs/code_route.pdf), une leçon
par sujet numéroté (13.1 à 13.9). Chaque leçon incruste un rendu haute résolution de sa vraie
page/double-page du livre (même principe que La conduite / Signalisation / Quelques définitions).

    python manage.py seed_course_vehicule
"""
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.lesson_pdf import build_lesson_pdf_v2
from apps.pedagogy.models import Course, CourseMaterial

CHAPTER = "Le véhicule"
SECTION = "Le véhicule"
_CROPS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "data", "vehicule_page_crops.json")
_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "vehicule_images")


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
    help = "Crée/actualise le cours « Le véhicule », une leçon par sujet numéroté (page du livre incrustée)."

    @transaction.atomic
    def handle(self, *args, **options):
        with open(_CROPS_PATH, encoding="utf-8") as f:
            crops = json.load(f)

        nums = sorted(crops.keys(), key=_num_key)

        course, _ = Course.objects.update_or_create(
            school=None, title=CHAPTER,
            defaults={
                "kind": "theory", "theme": "code", "level": "all_levels", "language": "Français",
                "summary": "Généralités, transport de personnes, entretien, pneumatiques, freinage, "
                          "éclairage, autres équipements, pollution et remorques.",
                "objectives": ["Connaître les équipements obligatoires et leur entretien.",
                               "Comprendre les règles de transport de personnes et de charges.",
                               "Connaître les règles relatives aux remorques."],
                "duration_minutes": len(nums) * 4, "order": 5, "is_published": True, "sequential": True,
            },
        )
        course.materials.all().delete()
        order = 0
        for num in nums:
            order += 1
            entry = crops[num]
            title = entry["title"]
            blocks = [{"t": "page_crop", "img_data": _read_img(p)} for p in entry["paths"]]
            pdf = build_lesson_pdf_v2(CHAPTER, SECTION, num, title, blocks, images=[])
            m = CourseMaterial.objects.create(
                course=course, section=SECTION, material_type="pdf", title=title,
                order=order, duration_minutes=4, is_required=True, download_allowed=True, is_published=True,
            )
            m.file.save(f"vehicule-{order:02d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(f"Cours « {CHAPTER} » prêt : {order} leçons (page du livre incrustée)."))
