from decimal import Decimal

from django.db import models

from apps.core.models import TimeStamped


class Invoice(TimeStamped):
    QUOTE, INVOICE, CREDIT = "quote", "invoice", "credit_note"
    KINDS = [(QUOTE, "Devis"), (INVOICE, "Facture"), (CREDIT, "Avoir")]
    STATUS = [("draft", "Brouillon"), ("issued", "Émise"), ("partial", "Partiellement payée"), ("paid", "Payée"),
              ("cancelled", "Annulée")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="invoices")
    kind = models.CharField(max_length=12, choices=KINDS, default=INVOICE)
    number = models.CharField(max_length=40, blank=True)
    learner = models.ForeignKey("learners.Learner", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="invoices")
    contract = models.ForeignKey("organizations.Contract", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="invoices")
    cohort = models.ForeignKey("organizations.Cohort", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="credit_notes")
    title = models.CharField(max_length=255, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    paid = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    status = models.CharField(max_length=12, choices=STATUS, default="issued")
    issue_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number or f"Facture #{self.pk}"

    @property
    def balance(self):
        return self.total - self.paid

    def save(self, *args, **kwargs):
        new = self.pk is None
        super().save(*args, **kwargs)
        if not self.number:
            prefix = {"quote": "DEV", "invoice": "FAC", "credit_note": "AV"}[self.kind]
            self.number = f"{prefix}-{self.school_id}-{self.created_at:%Y}-{self.pk:06d}"
            super().save(update_fields=["number"])

    def recompute(self):
        """Recalcule le montant payé / statut à partir des paiements confirmés."""
        if self.kind == self.QUOTE or self.status in ("cancelled", "draft"):
            return
        self.paid = sum((p.amount for p in self.payments.filter(status="confirmed")), Decimal(0))
        if self.paid <= 0:
            self.status = "issued"
        elif self.paid >= self.total:
            self.status = "paid"
        else:
            self.status = "partial"
        self.save(update_fields=["paid", "status", "updated_at"])


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    @property
    def amount(self):
        return self.quantity * self.unit_price


class Installment(TimeStamped):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="installments")
    number = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    due_date = models.DateField()
    paid_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    class Meta:
        ordering = ["invoice", "number"]

    @property
    def balance(self):
        return self.amount - self.paid_amount

    @property
    def status(self):
        from django.utils import timezone
        today = timezone.localdate()
        if self.paid_amount >= self.amount:
            return "paid"
        if self.due_date < today:
            return "late"
        if self.paid_amount > 0:
            return "partial"
        if self.due_date == today:
            return "due"
        return "upcoming"


PAYMENT_METHODS = [("orange_money", "Orange Money"), ("mtn_momo", "MTN MoMo"), ("moov_money", "Moov Money"),
                   ("wave", "Wave"), ("cinetpay", "CinetPay (Mobile Money / Carte)"), ("cash", "Espèces"), ("transfer", "Virement"), ("card", "Carte bancaire"),
                   ("other", "Autre")]
MOBILE_MONEY = {"orange_money", "mtn_momo", "moov_money", "wave"}


class Payment(TimeStamped):
    STATUS = [("pending", "En attente"), ("confirmed", "Confirmé"), ("failed", "Échoué")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="payments")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=15, choices=PAYMENT_METHODS)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    payer_phone = models.CharField(max_length=30, blank=True)
    provider_ref = models.CharField(max_length=100, blank=True, db_index=True)
    reference = models.CharField(max_length=100, blank=True)
    receipt_number = models.CharField(max_length=40, blank=True)
    receipt_file = models.FileField("Reçu / justificatif signé", upload_to="payments/receipts/", null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    raw_payload = models.JSONField(null=True, blank=True)
    recorded_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class Expense(TimeStamped):
    CATEGORIES = [("salary", "Salaires"), ("commission", "Commissions"), ("fuel", "Carburant"),
                  ("maintenance", "Maintenance"), ("rent", "Loyers"), ("supplies", "Fournitures"),
                  ("communication", "Communication"), ("other", "Autres charges")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="expenses")
    agency = models.ForeignKey("schools.Agency", null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses")
    category = models.CharField(max_length=15, choices=CATEGORIES)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    vehicle = models.ForeignKey("practice.Vehicle", null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses")
    instructor = models.ForeignKey("practice.Instructor", null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses")

    class Meta:
        ordering = ["-date"]
