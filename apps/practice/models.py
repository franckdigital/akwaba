from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped
from apps.schools.models import CATEGORIES


class Instructor(TimeStamped):
    STATUS = [("active", "Actif"), ("leave", "En congé"), ("inactive", "Inactif")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="instructor_profile")
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="instructors")
    agency = models.ForeignKey("schools.Agency", null=True, blank=True, on_delete=models.SET_NULL, related_name="instructors")
    last_name = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    categories = models.JSONField(default=list, blank=True)
    specialties = models.CharField(max_length=255, blank=True)
    availability = models.CharField(max_length=255, blank=True)
    hourly_rate = models.DecimalField("Rémunération / heure", max_digits=10, decimal_places=0, default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="active")

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Vehicle(TimeStamped):
    STATE = [("good", "Bon état"), ("maintenance", "En maintenance"), ("out", "Hors service")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="vehicles")
    agency = models.ForeignKey("schools.Agency", null=True, blank=True, on_delete=models.SET_NULL, related_name="vehicles")
    plate = models.CharField("Immatriculation", max_length=30)
    brand = models.CharField(max_length=60, blank=True)
    model = models.CharField(max_length=60, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    category = models.CharField(max_length=10, choices=CATEGORIES, default="B")
    mileage = models.PositiveIntegerField(default=0)
    insurance_expiry = models.DateField(null=True, blank=True)
    technical_visit_expiry = models.DateField(null=True, blank=True)
    state = models.CharField(max_length=12, choices=STATE, default="good")
    instructor = models.ForeignKey(Instructor, null=True, blank=True, on_delete=models.SET_NULL, related_name="vehicles")

    class Meta:
        ordering = ["plate"]
        constraints = [models.UniqueConstraint(fields=["school", "plate"], name="uniq_plate_per_school")]

    def __str__(self):
        return self.plate


class MaintenanceRecord(TimeStamped):
    KINDS = [("oil", "Vidange"), ("tires", "Pneus"), ("brakes", "Freins"), ("battery", "Batterie"),
             ("repair", "Réparation"), ("insurance", "Assurance"), ("technical", "Visite technique"), ("other", "Autre")]
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="maintenance")
    kind = models.CharField(max_length=12, choices=KINDS)
    date = models.DateField()
    mileage = models.PositiveIntegerField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    next_due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]


class FuelRecord(TimeStamped):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="fuel")
    date = models.DateField()
    liters = models.DecimalField(max_digits=8, decimal_places=2)
    mileage = models.PositiveIntegerField()
    cost = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    class Meta:
        ordering = ["-date", "-mileage"]

    @property
    def consumption_l_100(self):
        """Consommation depuis le plein précédent (L/100 km)."""
        prev = (FuelRecord.objects.filter(vehicle=self.vehicle, mileage__lt=self.mileage)
                .order_by("-mileage").first())
        if not prev or self.mileage == prev.mileage:
            return None
        return round(float(self.liters) * 100 / (self.mileage - prev.mileage), 2)


class Room(TimeStamped):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="rooms")
    agency = models.ForeignKey("schools.Agency", null=True, blank=True, on_delete=models.SET_NULL, related_name="rooms")
    name = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(default=20)

    def __str__(self):
        return self.name


class Lesson(TimeStamped):
    """Séance planifiée : conduite, cours théorique ou examen."""
    KINDS = [("practical", "Conduite"), ("theory", "Cours théorique"), ("exam", "Examen")]
    STATUS = [("planned", "Planifiée"), ("done", "Effectuée"), ("cancelled", "Annulée"), ("absent", "Absent")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="lessons")
    kind = models.CharField(max_length=10, choices=KINDS, default="practical")
    learner = models.ForeignKey("learners.Learner", null=True, blank=True, on_delete=models.CASCADE, related_name="lessons")
    cohort = models.ForeignKey("organizations.Cohort", null=True, blank=True, on_delete=models.CASCADE, related_name="lessons")
    instructor = models.ForeignKey(Instructor, null=True, blank=True, on_delete=models.SET_NULL, related_name="lessons")
    vehicle = models.ForeignKey(Vehicle, null=True, blank=True, on_delete=models.SET_NULL, related_name="lessons")
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="lessons")
    title = models.CharField(max_length=200, blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    observations = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="planned")
    # §6 — cours en visioconférence (classe virtuelle) : lien de la session et, une fois terminée, son enregistrement
    # consultable à tout moment par les candidats. Concerne surtout les séances kind="theory".
    meeting_url = models.URLField("Lien de la classe virtuelle", blank=True)
    recording_url = models.URLField("Enregistrement (rediffusion)", blank=True)

    class Meta:
        ordering = ["start"]

    @property
    def duration_hours(self):
        return round((self.end - self.start).total_seconds() / 3600, 2)


CRITERIA = [("vehicle_control", "Maîtrise du véhicule"), ("starting", "Démarrage"), ("braking", "Freinage"),
            ("parking", "Stationnement"), ("reversing", "Marche arrière"), ("traffic", "Circulation"),
            ("code_respect", "Respect du code"), ("behavior", "Comportement"), ("safety", "Sécurité")]


class Evaluation(TimeStamped):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="evaluations")
    learner = models.ForeignKey("learners.Learner", on_delete=models.CASCADE, related_name="evaluations")
    instructor = models.ForeignKey(Instructor, null=True, blank=True, on_delete=models.SET_NULL, related_name="evaluations")
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name="evaluations")
    date = models.DateField()
    scores = models.JSONField(default=dict, help_text="critère -> note /10")
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]

    @property
    def average(self):
        vals = [float(v) for v in self.scores.values() if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None
