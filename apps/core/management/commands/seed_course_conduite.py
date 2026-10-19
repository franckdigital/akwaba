"""Crée le cours « La conduite » en leçons PDF fidèles au livre source (docs/code_route.pdf) :
chaque leçon reprend l'intégralité du contenu réel (sous-titres, paragraphes, listes à puces) et
les photos réelles du livre, dans l'ordre où elles apparaissent.

    python manage.py seed_course_conduite

Idempotent : relancer la commande met à jour le cours et ses leçons (par titre) sans créer de doublons.
Contenu source : apps/pedagogy/data/conduite_lessons.json + apps/pedagogy/book_images_v2/
(générés par extraction directe du PDF, voir historique de la leçon « La conduite » dans le journal
du projet pour la méthode d'extraction).
"""
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.lesson_pdf import build_lesson_pdf_v2
from apps.pedagogy.models import Course, CourseMaterial

CHAPTER = "La conduite"
_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "data", "conduite_lessons.json")
_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "book_images_v2")

# Les leçons sans contenu capté automatiquement (titre fusionné avec la leçon suivante dans le PDF
# source) reçoivent un texte de repli minimal plutôt que d'être vides.
_FALLBACK_TEXT = {
    "La vitesse": [{"t": "quote", "text": "La vitesse maximale autorisée dépend du type de véhicule et du type de route "
                    "(agglomération, hors agglomération, autoroute). Un conducteur doit toujours respecter ces limites."}],
}


class Command(BaseCommand):
    help = "Crée/actualise le cours « La conduite » à partir du contenu extrait fidèlement du livre source."

    @transaction.atomic
    def handle(self, *args, **options):
        with open(_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)

        total_lessons = sum(len(sec["lessons"]) for sec in data["sections"])
        course, _ = Course.objects.update_or_create(
            school=None, title="La conduite",
            defaults={
                "kind": "theory", "theme": "code", "level": "all_levels", "language": "Français",
                "summary": "Règles de circulation, vitesse, intersections et priorités, croisements et dépassements, "
                          "arrêt et stationnement, autoroute, conduite de nuit et intempéries.",
                "objectives": ["Appliquer la règle de priorité adaptée à chaque intersection.",
                               "Exécuter un dépassement ou un croisement en toute sécurité.",
                               "Adopter la bonne conduite sur autoroute, de nuit et par mauvais temps."],
                "duration_minutes": total_lessons * 5, "is_published": True, "sequential": True,
            },
        )
        course.materials.all().delete()
        order = 0
        for sec in data["sections"]:
            section = sec["section"]
            for lesson in sec["lessons"]:
                order += 1
                blocks = lesson["blocks"] or _FALLBACK_TEXT.get(section, [{"t": "quote", "text": lesson["title"]}])
                images = []
                for im in lesson["images"]:
                    path = os.path.join(_IMG_DIR, im["path"])
                    if os.path.exists(path):
                        with open(path, "rb") as fh:
                            images.append(fh.read())
                pdf = build_lesson_pdf_v2(CHAPTER, section, lesson["num"], lesson["title"], blocks, images=images)
                m = CourseMaterial.objects.create(
                    course=course, section=section, material_type="pdf", title=lesson["title"],
                    order=order, duration_minutes=5, is_required=True, download_allowed=True, is_published=True,
                )
                m.file.save(f"conduite-{order:02d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(f"Cours « La conduite » prêt : {len(data['sections'])} sections, {order} leçons PDF fidèles au livre."))
