from django.db import models

from apps.core.models import TimeStamped

CATEGORIES = [("A", "Permis A"), ("A1", "Permis A1"), ("B", "Permis B"), ("C", "Permis C"),
              ("D", "Permis D"), ("E", "Permis E"), ("OTHER", "Autre")]


class School(TimeStamped):
    legal_name = models.CharField("Raison sociale", max_length=200)
    commercial_name = models.CharField("Nom commercial", max_length=200, blank=True)
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)
    registration_no = models.CharField("RCCM / identifiant", max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    manager_name = models.CharField("Responsable", max_length=150, blank=True)
    categories = models.JSONField(default=list, blank=True)
    opening_hours = models.CharField("Horaires", max_length=255, blank=True)
    pass_threshold = models.PositiveSmallIntegerField("Seuil de réussite (%)", default=70)
    covered_zones = models.JSONField(
        "Zones géographiques couvertes", default=list, blank=True,
        help_text="Ex: [\"Abidjan\"]. Une inscription en ligne dont la zone déclarée n'y figure pas est refusée (§4.1/§5.1). Vide = aucune restriction.")
    multi_agency = models.BooleanField("Fonctionne avec plusieurs agences (sites)", default=False)
    exam_min_average = models.PositiveSmallIntegerField("Score moyen requis aux QCM pour accéder aux examens blancs (%)", default=60)
    payment_rules = models.TextField("Règles de paiement", blank=True)
    exam_rules = models.TextField("Règles d'examen", blank=True)
    certificate_settings = models.JSONField(default=dict, blank=True)
    signatory_name = models.CharField("Signataire du certificat", max_length=150, blank=True)
    subscription_required = models.BooleanField(
        "Abonnement obligatoire pour accéder aux QCM / examens", default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["legal_name"]

    def __str__(self):
        return self.commercial_name or self.legal_name


class Agency(TimeStamped):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="agencies")
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    manager_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["school", "name"]
        verbose_name_plural = "agencies"

    def __str__(self):
        return f"{self.name}"


class Training(TimeStamped):
    """Formation du catalogue d'une auto-école."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="trainings")
    category = models.CharField(max_length=10, choices=CATEGORIES)
    name = models.CharField(max_length=200)
    theory_hours = models.PositiveIntegerField(default=0)
    practical_hours = models.PositiveIntegerField(default=0)
    duration_days = models.PositiveIntegerField("Durée (jours)", default=30)
    program = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    validation_conditions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["school", "category", "name"]

    def __str__(self):
        return self.name

    @property
    def total_hours(self):
        return self.theory_hours + self.practical_hours


BILLING_CYCLES = [("monthly", "1 mois"), ("quarterly", "3 mois"), ("semi_annual", "6 mois"), ("yearly", "12 mois (1 an)"),
                  ("lifetime", "À vie"), ("custom", "Durée personnalisée (jours)")]
CYCLE_DAYS = {"monthly": 30, "quarterly": 90, "semi_annual": 180, "yearly": 365, "lifetime": 365 * 100}


class Plan(TimeStamped):
    """Plan d'abonnement. Trois publics :

    - individual   : particulier (accès QCM / examens / cours) ;
    - organization : entreprise ou établissement, avec prise en compte des COHORTES couvertes et des places (bénéficiaires) ;
    - school       : auto-école (SaaS : limites d'usage de la plateforme, défini par Akwaba).
    `school` vide = plan proposé par Akwaba à toutes les auto-écoles ; sinon plan propre à l'auto-école.
    """
    AUDIENCES = [("individual", "Particuliers"), ("organization", "Entreprises & établissements"), ("school", "Auto-écoles (SaaS)")]
    audience = models.CharField(max_length=15, choices=AUDIENCES, default="school")
    school = models.ForeignKey(School, null=True, blank=True, on_delete=models.CASCADE, related_name="plans")
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=255, blank=True)
    price = models.DecimalField("Prix (par période)", max_digits=12, decimal_places=0, default=0)
    currency = models.CharField(max_length=3, default="XOF")
    billing_cycle = models.CharField(max_length=15, choices=BILLING_CYCLES, default="monthly")
    features = models.JSONField(default=list, blank=True)
    is_featured = models.BooleanField("Mis en avant", default=False)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # --- période de validité : durée de l'abonnement + fenêtre de vente du plan
    custom_days = models.PositiveIntegerField("Durée personnalisée (jours)", null=True, blank=True)
    available_from = models.DateField("Vendu à partir du", null=True, blank=True)
    available_until = models.DateField("Vendu jusqu'au", null=True, blank=True)
    # --- plan réservé (négocié) à une entreprise et/ou une cohorte
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.CASCADE,
                                     related_name="dedicated_plans")
    cohort = models.ForeignKey("organizations.Cohort", null=True, blank=True, on_delete=models.CASCADE,
                               related_name="dedicated_plans")
    # --- limites d'usage (auto-écoles)
    max_learners = models.PositiveIntegerField(default=100)
    max_instructors = models.PositiveIntegerField(default=5)
    max_agencies = models.PositiveIntegerField(default=1)
    storage_mb = models.PositiveIntegerField(default=1024)
    # --- cohortes (organisations ; 0 = illimité)
    max_cohorts = models.PositiveIntegerField(default=5)
    included_beneficiaries = models.PositiveIntegerField("Places (bénéficiaires) incluses", default=0)
    extra_beneficiary_price = models.DecimalField("Prix d'une place supplémentaire", max_digits=10, decimal_places=0, default=0)
    # --- droits d'accès (particuliers / organisations)
    category = models.CharField("Permis concerné (vide = tous)", max_length=10, blank=True)
    includes_quizzes = models.BooleanField(default=True)
    includes_exams = models.BooleanField(default=True)
    includes_courses = models.BooleanField(default=True)

    class Meta:
        ordering = ["audience", "sort_order", "price"]

    def __str__(self):
        return self.name

    @property
    def duration_days(self):
        if self.billing_cycle == "custom":
            return self.custom_days or 30
        return CYCLE_DAYS.get(self.billing_cycle, 30)

    @property
    def is_on_sale(self):
        from django.utils import timezone
        t = timezone.localdate()
        return (self.is_active and (self.available_from is None or self.available_from <= t)
                and (self.available_until is None or self.available_until >= t))


class Subscription(TimeStamped):
    STATUS = [("active", "Actif"), ("expired", "Expiré"), ("suspended", "Suspendu"), ("pending", "En attente")]
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=STATUS, default="active")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    auto_renew = models.BooleanField(default=True)

    class Meta:
        ordering = ["-end_date"]
