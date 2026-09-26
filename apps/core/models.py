from django.conf import settings
from django.db import models


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    user_label = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=40)
    model = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    school_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


ALERT_EVENTS = [
    ("registration", "Inscription reçue (accusé au candidat)"),
    ("registration_pending", "Nouvelle inscription à approuver (secrétariat)"),
    ("registration_approved", "Inscription approuvée (candidat)"),
    ("registration_rejected", "Inscription refusée, avec le motif (candidat)"),
    ("quote_rejected", "Demande de devis rejetée, avec le motif (candidat)"),
    ("quote_correction", "Demande de devis à corriger (candidat)"),
    ("individual_quote", "Nouvelle demande de devis individuel (secrétariat)"),
    ("quote_request", "Nouvelle demande de devis entreprise (secrétariat)"),
    ("recycling_reminder", "Relance recyclage (candidat)"),
    ("new_lesson", "Nouvelle séance programmée"),
    ("planning_change", "Changement de planning"),
    ("result", "Résultat de QCM"),
    ("exam_result", "Résultat d'examen"),
    ("certificate_ready", "Certificat disponible"),
    ("payment_confirmed", "Paiement confirmé"),
    ("schedule_settled", "Facture soldée"),
    ("installment_due_soon", "Rappel d'échéance à venir"),
    ("installment_late", "Échéance en retard"),
    ("subscription_active", "Abonnement activé"),
    ("subscription_failed", "Échec de paiement d'abonnement"),
    ("subscription_expiring", "Abonnement bientôt expiré"),
    ("subscription_suspended", "Abonnement suspendu"),
    ("verification", "Code de vérification"),
]
DEFAULT_ALERT_CHANNELS = {
    "registration": ["inapp"], "registration_pending": ["inapp"], "registration_approved": ["inapp", "email", "whatsapp"],
    "registration_rejected": ["inapp", "email", "whatsapp"], "quote_rejected": ["email", "whatsapp"], "quote_correction": ["email", "whatsapp"],
    "individual_quote": ["inapp"], "quote_request": ["inapp"], "recycling_reminder": ["email", "whatsapp"],
    "new_lesson": ["inapp", "sms"], "planning_change": ["inapp", "sms"], "result": ["inapp"], "exam_result": ["inapp"],
    "certificate_ready": ["inapp", "email", "sms"], "payment_confirmed": ["inapp", "sms"], "schedule_settled": ["inapp"],
    "installment_due_soon": ["inapp", "sms"], "installment_late": ["inapp", "sms"], "subscription_active": ["inapp"],
    "subscription_failed": ["inapp"], "subscription_expiring": ["inapp", "sms"], "subscription_suspended": ["inapp", "sms"],
    "verification": ["email", "sms"],
}


class AlertSetting(TimeStamped):
    """Paramétrage, depuis l'admin, des canaux de diffusion (et de l'activation) de chaque type d'alerte.
    Une ligne school=null sert de réglage global par défaut ; une ligne propre à une auto-école la surcharge."""
    school = models.ForeignKey("schools.School", null=True, blank=True, on_delete=models.CASCADE, related_name="alert_settings")
    event = models.CharField(max_length=40, choices=ALERT_EVENTS)
    is_active = models.BooleanField(default=True)
    channels = models.JSONField(default=list, blank=True, help_text='["inapp", "email", "sms", "whatsapp", "push"]')

    class Meta:
        ordering = ["event"]
        constraints = [models.UniqueConstraint(fields=["school", "event"], name="uniq_alert_setting_school_event")]

    def __str__(self):
        return f"{self.get_event_display()} ({self.school or 'global'})"


class Notification(models.Model):
    CHANNELS = [("inapp", "Application"), ("push", "Push"), ("sms", "SMS"), ("email", "E-mail"), ("whatsapp", "WhatsApp")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=10, choices=CHANNELS, default="inapp")
    event = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    status = models.CharField(max_length=10, default="sent")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
