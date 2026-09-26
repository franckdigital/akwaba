from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.crypto import EncryptedCharField
from apps.core.models import TimeStamped
from apps.schools.models import CATEGORIES

STATUSES = [
    ("new", "Nouveau"), ("registered", "Inscrit"), ("in_training", "Formation en cours"),
    ("training_done", "Formation terminée"), ("exam_scheduled", "Examen programmé"),
    ("passed", "Admis"), ("failed", "Échec"), ("licensed", "Permis obtenu"), ("dropped", "Abandonné"),
]
SOURCES = [("secretary", "Secrétaire"), ("online", "En ligne"), ("organization", "Organisation")]
APPROVAL_STATUSES = [("pending", "En attente d'approbation"), ("approved", "Approuvée"), ("rejected", "Rejetée")]


class Learner(TimeStamped):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="learner_profile")
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="learners")
    agency = models.ForeignKey("schools.Agency", null=True, blank=True, on_delete=models.SET_NULL, related_name="learners")
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="learners")
    cohort = models.ForeignKey("organizations.Cohort", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="learners")
    group = models.ForeignKey("organizations.Group", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="learners")
    training = models.ForeignKey("schools.Training", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="learners")
    matricule = models.CharField(max_length=40, blank=True)
    employee_ref = models.CharField("Matricule employeur/établissement", max_length=60, blank=True)
    last_name = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=[("M", "Masculin"), ("F", "Féminin")], blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to="learners/photos/", null=True, blank=True)
    id_document_no = EncryptedCharField("N° pièce d'identité", blank=True)
    id_document_hash = models.CharField(max_length=64, blank=True, db_index=True)
    zone = models.CharField("Zone géographique déclarée", max_length=100, blank=True)
    category = models.CharField(max_length=10, choices=CATEGORIES, default="B")
    status = models.CharField(max_length=20, choices=STATUSES, default="new")
    source = models.CharField(max_length=15, choices=SOURCES, default="secretary")
    registered_at = models.DateField(default=timezone.localdate)
    license_obtained_at = models.DateField(
        "Date d'obtention du permis", null=True, blank=True,
        help_text="Renseignée automatiquement au passage du statut à « Permis obtenu » ; sert de point de départ aux relances de recyclage.")

    # §4-5 — inscription en ligne soumise à l'approbation du secrétariat avant activation du dossier.
    # Par défaut « approved » : seule l'inscription publique (source=online) démarre « pending ».
    approval_status = models.CharField(max_length=10, choices=APPROVAL_STATUSES, default="approved")
    approval_reject_reason = models.TextField(blank=True)
    quote = models.ForeignKey("admissions.IndividualQuote", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="learners", help_text="Devis individuel à l'origine de cette inscription, le cas échéant.")
    org_sequence_no = models.PositiveIntegerField(
        "Numéro d'ordre (collectivité)", null=True, blank=True,
        help_text="Calculé automatiquement au sein de la collectivité rattachée (ex. INSAAC).")

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [models.UniqueConstraint(fields=["school", "matricule"], name="uniq_matricule_per_school")]

    def __str__(self):
        return f"{self.last_name} {self.first_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def save(self, *args, **kwargs):
        if not self.matricule:
            self.matricule = next_matricule(self.school_id)
        if self.status == "licensed" and not self.license_obtained_at:
            self.license_obtained_at = timezone.localdate()
        if self.id_document_no:
            import hashlib
            self.id_document_hash = hashlib.sha256(self.id_document_no.strip().upper().encode()).hexdigest()
        if self.organization_id and not self.org_sequence_no:
            self.org_sequence_no = Learner.objects.filter(organization_id=self.organization_id).count() + 1
        super().save(*args, **kwargs)


def next_matricule(school_id):
    year = timezone.localdate().year
    prefix = f"AKW{school_id}-{year}-"
    last = (Learner.objects.filter(school_id=school_id, matricule__startswith=prefix)
            .order_by("-matricule").values_list("matricule", flat=True).first())
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


DOC_TYPES = [("cni", "CNI"), ("photo", "Photo"), ("medical", "Certificat médical"), ("admin", "Justificatif administratif"),
             ("payment", "Justificatif de paiement"), ("exam", "Document d'examen"), ("certificate", "Certificat de réussite"),
             ("other", "Autre")]


class LearnerDocument(TimeStamped):
    learner = models.ForeignKey(Learner, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=15, choices=DOC_TYPES)
    title = models.CharField(max_length=150, blank=True)
    file = models.FileField(upload_to="learners/docs/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
