from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped
from apps.schools.models import CATEGORIES

THEMES = [("code", "Code de la route"), ("signs", "Signalisation"), ("priority", "Priorités"),
          ("safety", "Sécurité routière"), ("regulation", "Réglementation"), ("mechanics", "Mécanique"),
          ("behavior", "Comportement du conducteur"), ("defensive", "Conduite préventive"),
          ("firstaid", "Premiers secours"), ("other", "Autre")]
DIFFICULTY = [("easy", "Facile"), ("medium", "Moyen"), ("hard", "Difficile")]


class Course(TimeStamped):
    KINDS = [("theory", "Théorique"), ("practical", "Pratique")]
    school = models.ForeignKey("schools.School", null=True, blank=True, on_delete=models.CASCADE, related_name="courses")
    training = models.ForeignKey("schools.Training", null=True, blank=True, on_delete=models.SET_NULL, related_name="courses")
    kind = models.CharField(max_length=10, choices=KINDS, default="theory")
    theme = models.CharField(max_length=20, choices=THEMES, default="code")
    title = models.CharField(max_length=200)
    summary = models.CharField("Résumé", max_length=255, blank=True)
    cover = models.ImageField("Image de couverture", upload_to="courses/covers/", null=True, blank=True)
    content = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    sequential = models.BooleanField(
        "Parcours séquentiel obligatoire", default=False,
        help_text="Un contenu obligatoire reste verrouillé pour l'apprenant tant que le contenu obligatoire précédent n'est pas terminé.")

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title


class CourseMaterial(TimeStamped):
    """Contenu d'un cours : plusieurs formats (texte, PDF, vidéo, audio, image, PowerPoint, Word, Excel, lien, intégration, autre)."""
    TYPES = [("text", "Texte"), ("pdf", "PDF"), ("video", "Vidéo"), ("audio", "Audio"), ("image", "Image"),
             ("ppt", "PowerPoint"), ("word", "Word"), ("excel", "Excel"), ("link", "Lien externe"),
             ("embed", "Vidéo en ligne (YouTube, Vimeo)"), ("other", "Autre fichier")]
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials")
    material_type = models.CharField(max_length=10, choices=TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="courses/files/", null=True, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    url = models.URLField(blank=True)
    text = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    duration_minutes = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField("Obligatoire pour la progression", default=True)
    download_allowed = models.BooleanField("Téléchargement autorisé", default=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class MaterialProgress(models.Model):
    """Contenu marqué comme terminé par un utilisateur (apprenant, moniteur…)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="material_progress")
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE, related_name="progress")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "material"], name="uniq_progress_user_material")]


class Question(TimeStamped):
    TF, SINGLE, MULTI = "tf", "single", "multi"
    TYPES = [(TF, "Vrai/Faux"), (SINGLE, "Réponse unique"), (MULTI, "Choix multiple")]
    school = models.ForeignKey("schools.School", null=True, blank=True, on_delete=models.CASCADE, related_name="questions",
                               help_text="Vide = banque centrale Akwaba, visible de toutes les auto-écoles")
    code = models.CharField(max_length=60)
    category = models.CharField(max_length=10, choices=CATEGORIES, default="B")
    theme = models.CharField(max_length=20, choices=THEMES, default="code")
    subtheme = models.CharField(max_length=100, blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY, default="medium")
    qtype = models.CharField(max_length=10, choices=TYPES, default=SINGLE)
    text = models.TextField()
    image = models.ImageField(upload_to="questions/", null=True, blank=True)
    explanation = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["school", "code"], name="uniq_question_code_per_school")]

    def __str__(self):
        return f"{self.code} - {self.text[:60]}"

    def correct_ids(self):
        return set(self.choices.filter(is_correct=True).values_list("id", flat=True))


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    label = models.CharField(max_length=5, help_text="A, B, C, D / Vrai, Faux")
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]


class Quiz(TimeStamped):
    MANUAL, RANDOM = "manual", "random"
    MODES = [(MANUAL, "Sélection manuelle"), (RANDOM, "Tirage aléatoire")]
    school = models.ForeignKey("schools.School", null=True, blank=True, on_delete=models.CASCADE, related_name="quizzes")
    training = models.ForeignKey("schools.Training", null=True, blank=True, on_delete=models.SET_NULL, related_name="quizzes")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=10, choices=CATEGORIES, default="B")
    mode = models.CharField(max_length=10, choices=MODES, default=RANDOM)
    questions = models.ManyToManyField(Question, blank=True, related_name="quizzes")
    themes = models.JSONField("Thèmes (tirage)", default=list, blank=True)
    difficulties = models.JSONField("Difficultés (tirage)", default=list, blank=True)
    num_questions = models.PositiveIntegerField(default=20)
    duration_minutes = models.PositiveIntegerField(default=30)
    points_per_question = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    max_attempts = models.PositiveIntegerField("Tentatives max (0 = illimité)", default=0)
    shuffle = models.BooleanField(default=True)
    show_corrections = models.BooleanField(default=True)
    is_exam = models.BooleanField("Examen final", default=False)
    pass_threshold = models.PositiveSmallIntegerField("Seuil de réussite (%)", default=70)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Attempt(TimeStamped):
    IN_PROGRESS, FINISHED, EXPIRED = "in_progress", "finished", "expired"
    STATUS = [(IN_PROGRESS, "En cours"), (FINISHED, "Terminée"), (EXPIRED, "Expirée")]
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    learner = models.ForeignKey("learners.Learner", on_delete=models.CASCADE, related_name="attempts")
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUS, default=IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)
    score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    passed = models.BooleanField(default=False)
    is_exam = models.BooleanField(default=False)
    threshold = models.PositiveSmallIntegerField(default=70)

    class Meta:
        ordering = ["-started_at"]

    @property
    def result_label(self):
        if self.status == self.IN_PROGRESS:
            return "EN COURS"
        return "ADMIS" if self.passed else "NON ADMIS"


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="+")
    position = models.PositiveIntegerField(default=0)
    selected = models.JSONField(default=list, blank=True)
    answered = models.BooleanField(default=False)
    is_correct = models.BooleanField(default=False)
    points = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="uniq_answer_per_question")]


class ImportJob(TimeStamped):
    school = models.ForeignKey("schools.School", null=True, blank=True, on_delete=models.CASCADE, related_name="import_jobs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    filename = models.CharField(max_length=255)
    quiz = models.ForeignKey(Quiz, null=True, blank=True, on_delete=models.SET_NULL, related_name="imports")
    update_existing = models.BooleanField(default=False)
    updated = models.PositiveIntegerField(default=0)
    dry_run = models.BooleanField(default=True)
    total = models.PositiveIntegerField(default=0)
    valid = models.PositiveIntegerField(default=0)
    imported = models.PositiveIntegerField(default=0)
    duplicates = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    header = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    preview = models.JSONField(default=list)

    class Meta:
        ordering = ["-created_at"]
