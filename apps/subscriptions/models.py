from django.db import models
from django.utils import timezone

from apps.core.models import TimeStamped


class SubscriptionOrder(TimeStamped):
    """Commande d'abonnement : achat d'un plan par un particulier, une organisation (cohortes) ou une auto-école."""
    STATUS = [("pending", "En attente de paiement"), ("paid", "Payée"), ("failed", "Échouée"), ("cancelled", "Annulée")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="subscription_orders")
    audience = models.CharField(max_length=15)
    plan = models.ForeignKey("schools.Plan", on_delete=models.PROTECT, related_name="orders")
    learner = models.ForeignKey("learners.Learner", null=True, blank=True, on_delete=models.SET_NULL, related_name="subscription_orders")
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="subscription_orders")
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cohort_ids = models.JSONField(default=list, blank=True)
    extra_seats = models.PositiveIntegerField(default=0)
    seats = models.PositiveIntegerField(default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    currency = models.CharField(max_length=3, default="XOF")
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    method = models.CharField(max_length=15, default="cinetpay")
    payer_phone = models.CharField(max_length=30, blank=True)
    provider_ref = models.CharField(max_length=100, blank=True, db_index=True)
    invoice = models.OneToOneField("billing.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="subscription_order")
    paid_at = models.DateTimeField(null=True, blank=True)
    raw_payload = models.JSONField(null=True, blank=True)
    result_id = models.PositiveIntegerField(null=True, blank=True, help_text="Id de l'abonnement activé")
    proof = models.FileField("Preuve de paiement", upload_to="payment_proofs/", null=True, blank=True)
    proof_reference = models.CharField("Référence du reçu / virement", max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Commande #{self.pk} {self.plan}"


class _Period(TimeStamped):
    STATUS = [("active", "Actif"), ("expired", "Expiré"), ("cancelled", "Annulé"), ("suspended", "Suspendu")]
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True

    @property
    def is_current(self):
        today = timezone.localdate()
        return self.status == "active" and self.start_date <= today <= self.end_date

    @property
    def days_left(self):
        return max((self.end_date - timezone.localdate()).days, 0)


class LearnerSubscription(_Period):
    """Abonnement d'un particulier."""
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="learner_subscriptions")
    learner = models.ForeignKey("learners.Learner", on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey("schools.Plan", on_delete=models.PROTECT, related_name="learner_subscriptions")
    order = models.ForeignKey(SubscriptionOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-end_date"]


class OrganizationSubscription(_Period):
    """Abonnement d'une entreprise / d'un établissement : couvre des cohortes et un nombre de places."""
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="organization_subscriptions")
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey("schools.Plan", on_delete=models.PROTECT, related_name="organization_subscriptions")
    cohorts = models.ManyToManyField("organizations.Cohort", blank=True, related_name="subscriptions")
    seats = models.PositiveIntegerField(default=0)
    order = models.ForeignKey(SubscriptionOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-end_date"]
