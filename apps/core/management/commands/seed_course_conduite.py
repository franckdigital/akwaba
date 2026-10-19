"""Crée le cours « La conduite » en leçons PDF fidèles au livre source (docs/code_route.pdf) :
chaque module du livre (introduction d'un sujet + chaque sous-titre comme MARCHE NORMALE,
CIRCULATION EN FILES...) devient sa propre leçon, accessible individuellement depuis la sidebar,
avec son texte complet et sa photo réelle.

    python manage.py seed_course_conduite

Idempotent : relancer la commande met à jour le cours et ses leçons sans créer de doublons.
Contenu source : apps/pedagogy/data/conduite_lessons.json + apps/pedagogy/book_images_v2/
(générés par extraction directe du PDF).
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


def _prettify(heading):
    """« CIRCULATION EN FILES » -> « Circulation en files »."""
    return heading.strip().capitalize()


def _load_images(lesson):
    out = []
    for im in lesson["images"]:
        path = os.path.join(_IMG_DIR, im["path"])
        if os.path.exists(path):
            with open(path, "rb") as fh:
                out.append(fh.read())
    return out


def split_into_modules(lesson, section):
    """Découpe une entrée du livre (ex. 3.1 Les règles de circulation) en modules indépendants :
    un module « introduction » (texte avant le premier sous-titre) puis un module par sous-titre
    (MARCHE NORMALE, CIRCULATION EN FILES...), chacun avec sa propre photo. Chaque module devient
    une leçon à part entière dans la sidebar.
    """
    blocks = lesson["blocks"] or _FALLBACK_TEXT.get(section, [{"t": "quote", "text": lesson["title"]}])
    images = _load_images(lesson)
    img_idx = 0
    modules = []

    first_h = next((i for i, b in enumerate(blocks) if b["t"] == "h"), len(blocks))
    intro = blocks[:first_h]
    if intro:
        # Si le sujet n'a aucun sous-titre (pas de "h" dans tout le contenu), toutes ses images
        # reviennent à ce module d'introduction plutôt que de rester orphelines.
        intro_images = []
        if first_h == len(blocks) and images:
            intro_images = list(images)
            img_idx = len(images)
        modules.append({"title": lesson["title"], "blocks": intro, "images": intro_images})

    i = first_h
    while i < len(blocks):
        heading = blocks[i]["text"]
        j = i + 1
        while j < len(blocks) and blocks[j]["t"] != "h":
            j += 1
        seg = blocks[i + 1:j]
        image = images[img_idx] if img_idx < len(images) else None
        img_idx += 1
        modules.append({"title": _prettify(heading), "blocks": seg, "images": [image] if image else []})
        i = j

    if not modules:
        modules.append({"title": lesson["title"], "blocks": [{"t": "quote", "text": lesson["title"]}], "images": []})
    return modules


class Command(BaseCommand):
    help = "Crée/actualise le cours « La conduite », chaque module du livre devenant une leçon de la sidebar."

    @transaction.atomic
    def handle(self, *args, **options):
        with open(_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)

        all_modules = []
        for sec in data["sections"]:
            for lesson in sec["lessons"]:
                for mod in split_into_modules(lesson, sec["section"]):
                    all_modules.append((sec["section"], lesson["num"], mod))

        course, _ = Course.objects.update_or_create(
            school=None, title="La conduite",
            defaults={
                "kind": "theory", "theme": "code", "level": "all_levels", "language": "Français",
                "summary": "Règles de circulation, vitesse, intersections et priorités, croisements et dépassements, "
                          "arrêt et stationnement, autoroute, conduite de nuit et intempéries.",
                "objectives": ["Appliquer la règle de priorité adaptée à chaque intersection.",
                               "Exécuter un dépassement ou un croisement en toute sécurité.",
                               "Adopter la bonne conduite sur autoroute, de nuit et par mauvais temps."],
                "duration_minutes": len(all_modules) * 3, "is_published": True, "sequential": True,
            },
        )
        course.materials.all().delete()
        order = 0
        for section, num, mod in all_modules:
            order += 1
            images = mod["images"]
            pdf = build_lesson_pdf_v2(CHAPTER, section, num, mod["title"], mod["blocks"], images=images)
            m = CourseMaterial.objects.create(
                course=course, section=section, material_type="pdf", title=mod["title"],
                order=order, duration_minutes=3, is_required=True, download_allowed=True, is_published=True,
            )
            m.file.save(f"conduite-{order:03d}.pdf", pdf, save=True)
        self.stdout.write(self.style.SUCCESS(
            f"Cours « La conduite » prêt : {len(data['sections'])} sections, {order} leçons (une par module du livre)."))
