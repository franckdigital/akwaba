"""Crée la banque de questions QCM « Code de la route » (banque centrale Akwaba) ainsi qu'un
questionnaire d'entraînement et un examen blanc qui en tirent des questions au hasard.

    python manage.py seed_qcm_bank

Idempotent : relancer la commande met à jour les questions existantes (par code) sans créer de doublons.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.models import Question, Choice, Quiz
from apps.pedagogy.qcm_bank import QUESTIONS


class Command(BaseCommand):
    help = "Crée/actualise la banque de questions QCM et les quiz d'entraînement/examen associés."

    @transaction.atomic
    def handle(self, *args, **options):
        created, updated = 0, 0
        for q in QUESTIONS:
            question, is_new = Question.objects.update_or_create(
                school=None, code=q["code"],
                defaults={
                    "category": "B", "theme": q["theme"], "difficulty": q["difficulty"],
                    "qtype": Question.SINGLE, "text": q["text"], "explanation": q["explanation"], "is_active": True,
                },
            )
            question.choices.all().delete()
            for i, (label, text, is_correct) in enumerate(q["choices"]):
                Choice.objects.create(question=question, label=label, text=text, is_correct=is_correct, order=i)
            created += is_new
            updated += not is_new

        themes = sorted({q["theme"] for q in QUESTIONS})
        Quiz.objects.update_or_create(
            school=None, title="QCM d'entraînement — Code de la route", is_exam=False,
            defaults={"description": "Tirage aléatoire parmi toute la banque de questions.", "category": "B", "mode": Quiz.RANDOM,
                      "themes": themes, "difficulties": ["easy", "medium", "hard"], "num_questions": 20, "duration_minutes": 25,
                      "points_per_question": 1, "max_attempts": 0, "shuffle": True, "show_corrections": True, "is_published": True},
        )
        Quiz.objects.update_or_create(
            school=None, title="Examen blanc — Code de la route", is_exam=True,
            defaults={"description": "Examen blanc chronométré, tirage aléatoire parmi toute la banque de questions.", "category": "B",
                      "mode": Quiz.RANDOM, "themes": themes, "difficulties": ["easy", "medium", "hard"], "num_questions": len(QUESTIONS),
                      "duration_minutes": 40, "points_per_question": 1, "max_attempts": 0, "shuffle": True, "show_corrections": True,
                      "is_published": True, "pass_threshold": 70},
        )
        self.stdout.write(self.style.SUCCESS(
            f"{len(QUESTIONS)} questions ({created} créées, {updated} mises à jour). Quiz d'entraînement et examen blanc prêts."))
