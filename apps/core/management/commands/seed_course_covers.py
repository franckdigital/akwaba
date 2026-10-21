"""Attribue une image de couverture générée (apps/pedagogy/covers/) aux 3 cours du code de la
route : Quelques définitions (livre + loupe), Signalisation (triangle d'alerte), La conduite
(volant). Même dégradé rouge que l'illustration par défaut de l'app.

    python manage.py seed_course_covers
"""
import os

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.pedagogy.models import Course

_COVERS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "covers")

COURSE_COVERS = {
    "Quelques définitions": "definitions.png",
    "Signalisation": "signalisation.png",
    "La conduite": "conduite.png",
}


class Command(BaseCommand):
    help = "Attribue une image de couverture aux cours Quelques définitions / Signalisation / La conduite."

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
