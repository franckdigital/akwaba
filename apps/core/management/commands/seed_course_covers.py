"""Attribue une image de couverture (apps/pedagogy/covers/) aux 6 cours du code de la route.
Les 6 cours utilisent désormais une vraie photo.

    python manage.py seed_course_covers
"""
import os

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.pedagogy.models import Course

_COVERS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "covers")

COURSE_COVERS = {
    "Quelques définitions": "definitions.jpg",
    "Signalisation": "signalisation.jpg",
    "La conduite": "conduite.jpg",
    "Le conducteur": "conducteur.jpg",
    "Le véhicule": "vehicule.jpg",
    "Les permis": "permis.jpg",
}


class Command(BaseCommand):
    help = "Attribue une image de couverture aux 6 cours du code de la route."

    def handle(self, *args, **options):
        done = 0
        for title, filename in COURSE_COVERS.items():
            course = Course.objects.filter(school=None, title=title).first()
            if not course:
                self.stdout.write(self.style.WARNING(f"Cours introuvable : {title}"))
                continue
            path = os.path.join(_COVERS_DIR, filename)
            with open(path, "rb") as fh:
                course.cover.save(filename, ContentFile(fh.read()), save=True)
            done += 1
            self.stdout.write(f"  {title} -> {filename}")
        self.stdout.write(self.style.SUCCESS(f"{done} couverture(s) attribuée(s)."))
