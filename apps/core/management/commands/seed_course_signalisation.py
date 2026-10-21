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


def _read_img(filename):
    path = os.path.join(_IMG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


def _resolve_lesson(lesson):
    """Chaque bloc (sous-titre/légende) porte déjà le panneau qui lui correspond exactement
    (appariement spatial fait à l'extraction) : on résout son chemin en octets. Les images
    jamais réclamées par une légende proche (ex. photo d'illustration générale) sont ajoutées
    à la fin, dans l'ordre de lecture du livre."""
    blocks = []
    for b in lesson["blocks"]:
        b = dict(b)
        path = b.pop("img_path", None)
        if path:
            b["img_data"] = _read_img(path)
        blocks.append(b)
    leftover = [_read_img(im["path"]) for im in lesson.get("leftover_images", [])]
    leftover = [raw for raw in leftover if raw]
    return blocks, leftover


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
                "duration_minutes": len(lessons) * 4, "order": 2, "is_published": True, "sequential": True,
            },
        )
        course.materials.all().delete()
        order = 0
        for lesson in lessons:
            order += 1
            blocks, leftover_images = _resolve_lesson(lesson)
            pdf = build_lesson_pdf_v2(CHAPTER, "Signalisation", lesson["num"], lesson["title"], blocks, images=leftover_images)
            m = CourseMaterial.objects.create(
                course=course, section="Signalisation", material_type="pdf", title=lesson["title"],
                order=order, duration_minutes=4, is_required=True, download_allowed=True, is_published=True,
            )
            m.file.save(f"signalisation-{order:02d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(f"Cours « Signalisation » prêt : {order} leçons."))
