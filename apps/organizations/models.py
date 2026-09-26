from decimal import Decimal

from django.db import models

from apps.core.models import TimeStamped
from apps.schools.models import CATEGORIES

ORG_TYPES = [("company", "Entreprise"), ("university", "Université"), ("grande_ecole", "Grande école"),
             ("school", "École"), ("administration", "Administration"), ("ngo", "ONG"),
             ("association", "Association"), ("other", "Autre")]


class Organization(TimeStamped):
    """Entreprise / établissement partenaire d'une auto-école (B2B / B2B2C)."""
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="organizations")
    org_type = models.CharField(max_length=20, choices=ORG_TYPES, default="company")
    name = models.CharField(max_length=200)
    registration_no = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    contact_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    negotiated_price = models.DecimalField(
        "Tarif négocié par candidat", max_digits=12, decimal_places=0, null=True, blank=True,
        help_text="Tarif propre à cette collectivité, appliqué à chaque candidat qui lui est rattaché (ex. INSAAC).")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Contract(TimeStamped):
    STATUS = [("draft", "Brouillon"), ("active", "Actif"), ("completed", "Terminé"), ("cancelled", "Annulé")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="contracts")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="contracts")
    training = models.ForeignKey("schools.Training", on_delete=models.PROTECT, related_name="contracts")
    reference = models.CharField(max_length=60, blank=True)
    category = models.CharField(max_length=10, choices=CATEGORIES, default="B")
    beneficiaries_count = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField("Tarif par bénéficiaire", max_digits=12, decimal_places=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    organization_contribution = models.DecimalField("Contribution organisation / bénéficiaire", max_digits=12,
                                                    decimal_places=0, default=0)
    installments_count = models.PositiveSmallIntegerField("Échéances apprenant", default=1)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="draft")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference or f"Contrat #{self.pk}"

    @property
    def net_price(self):
        """Prix net par bénéficiaire après remise."""
        return (self.unit_price * (Decimal(100) - self.discount_percent) / Decimal(100)).quantize(Decimal("1"))

    @property
    def learner_contribution(self):
        return max(self.net_price - self.organization_contribution, Decimal(0))

    @property
    def organization_total(self):
        return min(self.organization_contribution, self.net_price) * self.beneficiaries_count


class Cohort(TimeStamped):
    STATUS = [("planned", "Planifiée"), ("running", "En cours"), ("done", "Terminée"), ("cancelled", "Annulée")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="cohorts")
    agency = models.ForeignKey("schools.Agency", null=True, blank=True, on_delete=models.SET_NULL, related_name="cohorts")
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL, related_name="cohorts")
    contract = models.ForeignKey(Contract, null=True, blank=True, on_delete=models.SET_NULL, related_name="cohorts")
    training = models.ForeignKey("schools.Training", on_delete=models.PROTECT, related_name="cohorts")
    name = models.CharField(max_length=200)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    capacity = models.PositiveIntegerField(default=20)
    location = models.CharField(max_length=200, blank=True)
    instructors = models.ManyToManyField("practice.Instructor", blank=True, related_name="cohorts")
    status = models.CharField(max_length=12, choices=STATUS, default="planned")

    class Meta:
        ordering = ["-start_date", "name"]

    def __str__(self):
        return self.name


class Group(TimeStamped):
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(max_length=100)
    instructor = models.ForeignKey("practice.Instructor", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="groups")

    class Meta:
        ordering = ["cohort", "name"]

    def __str__(self):
        return f"{self.cohort} / {self.name}"


class QuoteRequest(TimeStamped):
    """Demande de devis B2B/B2B2C déposée depuis la vitrine (prospect sans compte)."""
    STATUS = [("new", "Nouvelle"), ("contacted", "Contactée"), ("converted", "Convertie"), ("rejected", "Rejetée")]
    contact_name = models.CharField(max_length=150)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30, blank=True)
    formation_label = models.CharField(max_length=200)
    beneficiaries_count = models.PositiveIntegerField(default=1)
    desired_start_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="new")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.contact_name} - {self.formation_label}"
