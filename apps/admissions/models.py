"""Demandes de devis individuelles déposées depuis la vitrine (cahier des charges §2-3).

Point de cadrage retenu : la « vérification de la base du ministère » est une action EXTERNE,
manuelle, faite par la secrétaire hors du système (comme précisé §4.1) — Akwaba ne dispose pas
d'un accès à cette base. Le système enregistre la décision qu'elle rend, il ne l'automatise pas.
Ce qui PEUT être vérifié localement (dates de validité déclarées par le candidat, doublons de
demande, catégories déjà cochées) l'est.
"""
import hashlib
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.crypto import EncryptedCharField
from apps.core.models import TimeStamped
from apps.schools.models import CATEGORIES

OFFERS = [
    ("new_license", "Nouveau permis de conduire"),
    ("extension", "Extension de catégorie"),
    ("theory_refresh", "Recyclage théorique"),
    ("practical_refresh", "Recyclage pratique"),
]
ID_TYPES = [
    ("cni", "Carte nationale d'identité (CNI)"),
    ("cni_foreign", "Carte nationale d'identité (non nationaux)"),
    ("passport", "Passeport"),
    ("resident_card", "Carte de résident"),
    ("consular_card", "Carte consulaire"),
    ("diplomatic_letter", "Lettre diplomatique"),
    ("id_attestation", "Attestation d'identité"),
    ("refugee_card", "Carte d'identité du réfugié"),
    ("driver_license", "Permis de conduire"),
    ("no_id", "Sans identification"),
    ("unknown", "Inconnu"),
    ("other", "Autre"),
]

# §8 — A/B : validité permanente. C, D, E : périodique selon l'âge du titulaire.
PERIODIC_CATEGORIES = {"C", "D", "E"}

STATUS = [
    ("submitted", "Déposée"),
    ("correction_requested", "Correction demandée"),
    ("rejected", "Rejetée"),
    ("approved", "Recevable"),
    ("quoted", "Devis envoyé"),
    ("accepted", "Acceptée"),
]
# Statuts pour lesquels une demande est considérée « en cours » : bloque une nouvelle demande
# du même candidat (anti-doublon, point de vigilance §3.1). Une demande rejetée ou acceptée est
# close : le candidat peut, le cas échéant, en déposer une nouvelle.
ACTIVE_STATUSES = ["submitted", "correction_requested", "approved", "quoted"]


class RecyclingItem(TimeStamped):
    """Catalogue des modules / packages de recyclage théorique, avec tarif (§3.3)."""
    KIND = [("module", "Module"), ("package", "Package")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="recycling_items")
    kind = models.CharField(max_length=10, choices=KIND, default="module")
    label = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    sessions_count = models.PositiveIntegerField(
        "Nombre de séances", null=True, blank=True,
        help_text="Pour les formules de recyclage pratique : nombre de séances de 45 minutes incluses.")
    modules = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="packages",
                                     limit_choices_to={"kind": "module"},
                                     help_text="Modules inclus (uniquement pour un package).")
    course = models.ForeignKey("pedagogy.Course", null=True, blank=True, on_delete=models.SET_NULL, related_name="recycling_items",
                               help_text="Cours associé : donne accès au contenu correspondant selon les modules achetés (§5.3).")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "label"]

    def __str__(self):
        return self.label

    @property
    def duration_minutes(self):
        return self.sessions_count * 45 if self.sessions_count else None


class RecyclingReminderSettings(TimeStamped):
    """Relance automatique et paramétrable depuis l'admin des titulaires d'un permis (§3.3)."""
    school = models.OneToOneField("schools.School", on_delete=models.CASCADE, related_name="recycling_reminder_settings")
    is_active = models.BooleanField(default=False)
    first_reminder_days = models.PositiveIntegerField("Premier rappel (jours après obtention du permis)", default=30)
    repeat_every_days = models.PositiveIntegerField("Rappels suivants tous les (jours)", default=180)
    channels = models.JSONField(default=list, blank=True, help_text='["email", "whatsapp"]')
    message = models.TextField(blank=True, default="Pensez à vos recyclages théorique et pratique chez Akwaba Auto-École !")

    def __str__(self):
        return f"Relance recyclage – {self.school}"


class RecyclingReminderLog(TimeStamped):
    """Historique des relances envoyées : évite les doublons et alimente le calcul de la prochaine échéance."""
    learner = models.ForeignKey("learners.Learner", on_delete=models.CASCADE, related_name="recycling_reminders")
    channel = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["-created_at"]


class IndividualQuote(TimeStamped):
    school = models.ForeignKey("schools.School", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="individual_quotes")
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="individual_quotes",
                                     help_text="Collectivité : si renseignée, la saisie de paiement individuel est désactivée (§3.1) : "
                                               "le candidat bénéficie de l'accès complet prévu par la convention.")
    offer = models.CharField(max_length=20, choices=OFFERS)

    # Identité (commune aux 4 offres) — §2, §3.1
    id_document_type = models.CharField(max_length=30, choices=ID_TYPES, blank=True)
    id_document_no = EncryptedCharField(blank=True)
    id_document_hash = models.CharField(max_length=64, blank=True, db_index=True)
    last_name = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    residence = models.CharField("Lieu de résidence", max_length=255, blank=True)

    # Photos du permis déjà détenu — pertinent pour les offres extension / recyclage théorique / recyclage
    # pratique (pas pour "new_license", le candidat n'ayant alors pas encore de permis).
    license_photo_front = models.FileField("Photo du permis (recto)", upload_to="quotes/license_photos/", null=True, blank=True)
    license_photo_back = models.FileField("Photo du permis (verso)", upload_to="quotes/license_photos/", null=True, blank=True)

    # §3.1 — Nouveau permis de conduire
    categories_requested = models.JSONField(default=list, blank=True)

    # §3.2 — Extension (permis déjà détenu) ; §3.3 réutilise license_no/nom pour les recyclages
    license_no = models.CharField("N° de permis existant", max_length=60, blank=True)
    categories_held = models.JSONField(default=list, blank=True, help_text="Catégories déjà détenues, cochées par le candidat.")
    categories_expiry = models.JSONField(default=dict, blank=True,
                                         help_text='{"C": "2027-01-01", ...} déclaré par le candidat (catégories périodiques C/D/E).')
    categories_to_add = models.JSONField(default=list, blank=True,
                                         help_text="Catégorie demandée en extension : une seule à la fois (§3.2).")

    # §3.3 — Recyclage théorique : modules/packages choisis
    recycling_items = models.ManyToManyField(RecyclingItem, blank=True, related_name="quotes")

    status = models.CharField(max_length=20, choices=STATUS, default="submitted")
    reject_reason = models.TextField(blank=True)
    correction_note = models.TextField(blank=True)

    base_price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    negotiated_price = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    quote_pdf = models.FileField(upload_to="individual_quotes/pdf/", null=True, blank=True)
    sent_channel = models.CharField(max_length=10, choices=[("email", "E-mail"), ("whatsapp", "WhatsApp")], blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.last_name} {self.first_name} — {self.get_offer_display()}"

    @property
    def price(self):
        return self.negotiated_price if self.negotiated_price is not None else self.base_price

    @property
    def balance(self):
        return max(self.price - self.paid_amount, Decimal(0))

    def save(self, *args, **kwargs):
        if self.id_document_no:
            self.id_document_hash = hashlib.sha256(self.id_document_no.strip().upper().encode()).hexdigest()
        super().save(*args, **kwargs)


# --------------------------------------------------------------------------------------------------------
# Candidatures permis de conduire portées par une organisation (ex. opération CAFOP « un élève-maître, un
# permis de conduire ») : un formulaire simplifié par forfait de catégories, à tarif fixe par organisation.
PERMIT_BUNDLES = [
    ("A", "A — Permis moto"),
    ("B", "B — Permis véhicule léger"),
    ("AB", "AB — Moto + véhicule léger"),
    ("BCDE", "BCDE — Véhicule léger, marchandises, personnes, remorque"),
    ("ABCDE", "ABCDE — Toutes catégories"),
]
PERMIT_BUNDLE_PRICES = {"A": 70000, "B": 70000, "AB": 75000, "BCDE": 80000, "ABCDE": 80000}


class PermitCandidate(TimeStamped):
    """Candidat au permis de conduire inscrit via une organisation partenaire (opération groupée)."""
    STATUS = [("submitted", "Déposée"), ("contacted", "Contactée"), ("registered", "Inscrite")]
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="permit_candidates")
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="permit_candidates")
    last_name = models.CharField("Nom", max_length=100)
    first_name = models.CharField("Prénom(s)", max_length=150)
    center = models.CharField("Centre (ex. CAFOP de…)", max_length=150, blank=True)
    contact = models.CharField("Contact", max_length=30)
    category_bundle = models.CharField(max_length=10, choices=PERMIT_BUNDLES)
    price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    id_document_file = models.FileField("Pièce d'identité (recto)", upload_to="permit_candidates/id/", null=True, blank=True)
    id_document_back_file = models.FileField("Pièce d'identité (verso)", upload_to="permit_candidates/id/", null=True, blank=True)
    birth_certificate_file = models.FileField("Photocopie extrait de naissance", upload_to="permit_candidates/birth/", null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="submitted")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.last_name} {self.first_name} — {self.category_bundle}"

    def save(self, *args, **kwargs):
        if not self.price:
            self.price = PERMIT_BUNDLE_PRICES.get(self.category_bundle, 0)
        super().save(*args, **kwargs)
