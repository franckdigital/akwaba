"""Crée le cours « La conduite » (chapitres 3 à 10 du livre source docs/code_route.pdf), une
leçon par sujet numéroté (3.1, 4.1, 5.1...). Chaque leçon incruste un rendu haute résolution de
sa vraie page/double-page du livre (même principe que pour Signalisation et Quelques
définitions), fidélité garantie à 100%.

    python manage.py seed_course_conduite

Idempotent : relancer la commande met à jour le cours et ses leçons sans créer de doublons.
Contenu source : apps/pedagogy/data/conduite_page_crops.json + apps/pedagogy/conduite_images/
(générés par capture directe du PDF).
"""
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.lesson_pdf import build_lesson_pdf_v2
from apps.pedagogy.models import Course, CourseMaterial

CHAPTER = "La conduite"
_CROPS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "data", "conduite_page_crops.json")
_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "conduite_images")

# Nom de la section (sous-chapitre du livre) pour chaque numéro de chapitre.
SECTION_NAMES = {
    "3": "Les règles de circulation", "4": "La vitesse", "5": "Intersection et priorité",
    "6": "Croisements et dépassements", "7": "L'arrêt et le stationnement", "8": "L'autoroute",
    "9": "La conduite de nuit", "10": "Les intempéries",
}


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
    help = "Crée/actualise le cours « La conduite », une leçon par sujet numéroté (page du livre incrustée)."

    @transaction.atomic
    def handle(self, *args, **options):
        with open(_CROPS_PATH, encoding="utf-8") as f:
            crops = json.load(f)

        nums = sorted(crops.keys(), key=_num_key)

        course, _ = Course.objects.update_or_create(
            school=None, title="La conduite",
            defaults={
                "kind": "theory", "theme": "code", "level": "all_levels", "language": "Français",
                "summary": "Règles de circulation, vitesse, intersections et priorités, croisements et dépassements, "
                          "arrêt et stationnement, autoroute, conduite de nuit et intempéries.",
                "objectives": ["Appliquer la règle de priorité adaptée à chaque intersection.",
                               "Exécuter un dépassement ou un croisement en toute sécurité.",
                               "Adopter la bonne conduite sur autoroute, de nuit et par mauvais temps."],
                "duration_minutes": len(nums) * 4, "order": 3, "is_published": True, "sequential": True,
            },
        )
        course.materials.all().delete()
        order = 0
        for num in nums:
            order += 1
            entry = crops[num]
            title = entry["title"]
            section = SECTION_NAMES.get(num.split(".")[0], f"Chapitre {num.split('.')[0]}")
            blocks = [{"t": "page_crop", "img_data": _read_img(p)} for p in entry["paths"]]
            pdf = build_lesson_pdf_v2(CHAPTER, section, num, title, blocks, images=[])
            m = CourseMaterial.objects.create(
                course=course, section=section, material_type="pdf", title=title,
                order=order, duration_minutes=4, is_required=True, download_allowed=True, is_published=True,
            )
            m.file.save(f"conduite-{order:03d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(
            f"Cours « La conduite » prêt : {order} leçons (page du livre incrustée)."))
