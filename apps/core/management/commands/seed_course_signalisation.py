"""Crée le cours « Signalisation » (chapitre 2 du livre source docs/code_route.pdf), fidèle au
texte et aux panneaux réels : une leçon par point numéroté (2.1 à 2.16), avec ses sous-titres,
ses légendes de panneaux et leurs vignettes réelles.

    python manage.py seed_course_signalisation

Idempotent : relancer la commande met à jour le cours et ses leçons sans créer de doublons.
Contenu source : apps/pedagogy/data/signalisation_lessons.json + apps/pedagogy/signal_images_v2/
(générés par extraction directe du PDF).
"""
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.lesson_pdf import build_lesson_pdf_v2
from apps.pedagogy.models import Course, CourseMaterial

CHAPTER = "Signalisation"
_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "data", "signalisation_lessons.json")
_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "signal_images_v2")


def _load_images(lesson):
    out = []
    for im in lesson["images"]:
        path = os.path.join(_IMG_DIR, im["path"])
        if os.path.exists(path):
            with open(path, "rb") as fh:
                out.append(fh.read())
    return out


class Command(BaseCommand):
    help = "Crée/actualise le cours « Signalisation », une leçon par point numéroté du livre (2.1-2.16)."

    @transaction.atomic
    def handle(self, *args, **options):
        with open(_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)

        lessons = [l for sec in data["sections"] for l in sec["lessons"]]

        course, _ = Course.objects.update_or_create(
            school=None, title="Signalisation",
            defaults={
                "kind": "theory", "theme": "code", "level": "all_levels", "language": "Français",
                "summary": "Panneaux de danger, d'interdiction, d'obligation, d'indication, de direction, "
                          "de localisation, marques sur la route et signalisation temporaire.",
                "objectives": ["Reconnaître les principales familles de panneaux et leur signification.",
                               "Identifier les marques au sol et la signalisation temporaire de chantier."],
                "duration_minutes": len(lessons) * 4, "is_published": True, "sequential": True,
            },
        )
        course.materials.all().delete()
        order = 0
        for lesson in lessons:
            order += 1
            images = _load_images(lesson)
            pdf = build_lesson_pdf_v2(CHAPTER, "Signalisation", lesson["num"], lesson["title"], lesson["blocks"], images=images)
            m = CourseMaterial.objects.create(
                course=course, section="Signalisation", material_type="pdf", title=lesson["title"],
                order=order, duration_minutes=4, is_required=True, download_allowed=True, is_published=True,
            )
            m.file.save(f"signalisation-{order:02d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(f"Cours « Signalisation » prêt : {order} leçons."))
