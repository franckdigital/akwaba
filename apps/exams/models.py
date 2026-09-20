import secrets

from django.db import models

from apps.core.models import TimeStamped
from apps.pedagogy.models import Quiz


class Exam(Quiz):
    """Examen final théorique = Quiz marqué is_exam (proxy pour l'API /exams/)."""

    class Meta:
        proxy = True
        verbose_name = "Examen"


def _token():
    return secrets.token_urlsafe(24)


class Certificate(TimeStamped):
    VALID, REVOKED = "valid", "revoked"
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="certificates")
    learner = models.ForeignKey("learners.Learner", on_delete=models.CASCADE, related_name="certificates")
    attempt = models.OneToOneField("pedagogy.Attempt", on_delete=models.CASCADE, related_name="certificate")
    number = models.CharField(max_length=40, unique=True)
    verification_token = models.CharField(max_length=64, unique=True, default=_token)
    training_name = models.CharField(max_length=200)
    category = models.CharField(max_length=10)
    score = models.CharField(max_length=20)
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    issued_at = models.DateField()
    status = models.CharField(max_length=10, choices=[(VALID, "Valide"), (REVOKED, "Révoqué")], default=VALID)

    class Meta:
        ordering = ["-issued_at", "-id"]

    def __str__(self):
        return self.number
