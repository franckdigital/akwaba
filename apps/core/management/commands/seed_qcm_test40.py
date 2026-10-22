"""Crée le test « Code de la route — 40 questions » (banque centrale Akwaba), extrait du chapitre 16
« Questions » / chapitre 17 « Réponses » du livre (docs/code_route.pdf, pages 208-239), avec photos
réelles pour 35 des 40 questions (les 5 questions « Question écrite » du livre n'ont pas de photo).

    python manage.py seed_qcm_test40

Idempotent : relancer la commande met à jour les questions existantes (par code) et réaffecte le
quiz manuel sans créer de doublons.
"""
import os

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.models import Question, Choice, Quiz
from apps.pedagogy.qcm_bank_test40 import QUESTIONS

_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pedagogy", "qcm_images")


class Command(BaseCommand):
    help = "Crée/actualise le test de 40 questions « Code de la route » tiré du livre et son quiz manuel."

    @transaction.atomic
    def handle(self, *args, **options):
        created, updated, with_image, without_image = 0, 0, 0, 0
        questions = []
        for q in QUESTIONS:
            question, is_new = Question.objects.update_or_create(
                school=None, code=q["code"],
                defaults={
                    "category": "B", "theme": q["theme"], "difficulty": q["difficulty"],
                    "qtype": q["qtype"], "text": q["text"], "explanation": q["explanation"], "is_active": True,
                },
            )
            question.choices.all().delete()
            for i, (label, text, is_correct) in enumerate(q["choices"]):
                Choice.objects.create(question=question, label=label, text=text, is_correct=is_correct, order=i)

            if q["image_path"]:
                path = os.path.join(_IMAGES_DIR, q["image_path"])
                if question.image:
                    question.image.delete(save=False)
                with open(path, "rb") as fh:
                    question.image.save(q["image_path"], ContentFile(fh.read()), save=True)
                with_image += 1
            else:
                without_image += 1

            created += is_new
            updated += not is_new
            questions.append(question)

        quiz, _ = Quiz.objects.update_or_create(
            school=None, title="Test Code de la route — 40 questions",
            defaults={"description": "Test d'entraînement complet de 40 questions tirées du livre « Code de la route » "
                                      "(chapitre 16), avec photos de conduite réelles et corrections détaillées.",
                      "category": "B", "mode": Quiz.MANUAL, "num_questions": len(questions),
                      "duration_minutes": 40, "points_per_question": 1, "max_attempts": 0,
                      "shuffle": False, "show_corrections": True, "is_exam": True, "pass_threshold": 70,
                      "is_published": True},
        )
        quiz.questions.set(questions)
        quiz.num_questions = quiz.questions.count()
        quiz.save(update_fields=["num_questions"])

        self.stdout.write(self.style.SUCCESS(
            f"{len(QUESTIONS)} questions ({created} créées, {updated} mises à jour) — "
            f"{with_image} avec photo, {without_image} sans photo (« Question écrite » du livre). "
            f"Quiz « {quiz.title} » prêt avec {quiz.num_questions} questions."))
