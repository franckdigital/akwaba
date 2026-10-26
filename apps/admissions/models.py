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


class OfferTypeConfig(TimeStamped):
    """Paramétrage admin du contenu « ce qui est inclus » par type de demande (offre), par auto-école —
    alimente les 4 cartes du formulaire public de devis et l'écran « mes demandes » du candidat."""
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="offer_type_configs")
    offer = models.CharField(max_length=20, choices=OFFERS)
    title = models.CharField(max_length=120, blank=True, help_text="Titre affiché ; vide = libellé par défaut de l'offre.")
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    # Dupliqué depuis apps.schools.models.BILLING_CYCLES (à garder synchronisé si cette liste évolue) plutôt
    # qu'importé : schools.models importe déjà OFFERS depuis ce module, un import en sens inverse créerait
    # un cycle d'imports circulaire au chargement de Django.
    BILLING_CYCLES = [("monthly", "1 mois"), ("quarterly", "3 mois"), ("semi_annual", "6 mois"), ("yearly", "12 mois (1 an)"),
                      ("lifetime", "À vie"), ("custom", "Durée personnalisée (jours)")]
    billing_cycle = models.CharField(max_length=15, choices=BILLING_CYCLES, default="yearly",
                                     help_text="Durée de validité de l'abonnement généré pour cette formule.")
    custom_days = models.PositiveIntegerField("Durée personnalisée (jours)", null=True, blank=True)
    courses = models.ManyToManyField("pedagogy.Course", blank=True, related_name="offer_type_configs")
    recycling_items = models.ManyToManyField(RecyclingItem, blank=True, related_name="offer_type_configs")
    includes_courses = models.BooleanField(default=True)
    includes_quizzes = models.BooleanField(default=True)
    includes_exams = models.BooleanField(default=False)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("school", "offer")]
        ordering = ["school", "offer"]

    def __str__(self):
        return f"{self.get_offer_display()} — {self.school}"


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

    # Apprenant résultant de cette demande, une fois l'inscription effectuée (cf. RegisterView, parcours
    # devis -> inscription). Renseigné en miroir de Learner.quote (relation inverse) pour permettre à
    # IndividualQuote.learner d'être consulté directement (jointure "mes demandes" côté apprenant).
    learner = models.ForeignKey("learners.Learner", null=True, blank=True, on_delete=models.SET_NULL, related_name="quotes")

    base_price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    negotiated_price = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    quote_pdf = models.FileField(upload_to="individual_quotes/pdf/", null=True, blank=True)
    # Conservés pour compat (dernier canal cliqué manuellement) — mais l'envoi e-mail et l'envoi WhatsApp sont
    # désormais deux actions indépendantes (chacune peut être déclenchée séparément, avant ou après l'autre) :
    # d'où les deux horodatages distincts ci-dessous, utilisés par l'admin pour afficher chaque bouton comme
    # « envoyé » ou non sans jamais désactiver l'autre canal.
    sent_channel = models.CharField(max_length=10, choices=[("email", "E-mail"), ("whatsapp", "WhatsApp")], blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    quote_emailed_at = models.DateTimeField(null=True, blank=True)
    quote_whatsapp_sent_at = models.DateTimeField(null=True, blank=True)

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


# --------------------------------------------------------------------------------------------------------
# §produit — « je veux pouvoir créer et mettre à jour les messages par mail et WhatsApp pour les demandes
# depuis l'admin » : remplace les chaînes figées de services.py (QUOTE_DECISION_NOTIFICATIONS,
# _quote_pdf_message, messages "compte créé") par un gabarit éditable par auto-école. Variables disponibles
# documentées ci-dessous ET exposées en lecture par l'API (cf. apps.admissions.views.MessageTemplateSerializer.
# available_variables), pour que l'admin web affiche l'aide sans dupliquer cette liste côté JS.
#
#   quote_approved           : {prenom}, {nom}, {offre}
#   quote_correction_default : {prenom}, {nom}, {offre} — texte PRÉ-REMPLI quand la secrétaire clique
#                              « Demander correction » sans taper de note personnalisée (correction_note
#                              reste par ailleurs un texte libre saisi au cas par cas, non concerné ici)
#   quote_quoted              : {prenom}, {nom}, {offre}, {prix}, {lien_devis} (lien_devis inclut son
#                              préfixe " : " et est vide si le PDF n'est pas encore généré)
#   account_created            : {prenom}, {nom}, {email}, {mot_de_passe}, {code_cohorte} (ligne complète
#                              pré-formatée avec retour à la ligne, vide si non applicable — ex. compte
#                              individuel créé depuis la vitrine, sans cohorte)
AVAILABLE_VARIABLES = {
    "quote_approved": ["prenom", "nom", "offre"],
    "quote_correction_default": ["prenom", "nom", "offre"],
    "quote_quoted": ["prenom", "nom", "offre", "prix", "lien_devis"],
    "account_created": ["prenom", "nom", "email", "mot_de_passe", "code_cohorte"],
}


class MessageTemplate(TimeStamped):
    """Contenu, éditable depuis l'admin par auto-école, des messages candidat (e-mail/WhatsApp) liés aux
    devis individuels. `body` est rendu via services.render_template (substitution sûre : une variable
    absente du contexte devient une chaîne vide, jamais une exception) — cf. AVAILABLE_VARIABLES ci-dessus
    pour les variables disponibles par clé.

    §décision produit — unification « compte créé » : les 3 points d'entrée qui envoyaient un message
    « votre compte a été créé, voici vos identifiants » (devis vitrine approuvé automatiquement, import
    Excel d'une cohorte unique, import Excel multi-cohortes) sont regroupés sous UNE seule clé
    (account_created) plutôt que 2-3 gabarits séparés : leur contenu était déjà quasi identique (même sujet
    dans les 3 cas, même structure de corps), la seule vraie variation — la ligne optionnelle du code de
    cohorte — est couverte par la variable {code_cohorte} (vide quand non applicable) plutôt que par un
    gabarit distinct.

    `subject` est ignoré pour WhatsApp (pas de sujet sur ce canal). Une ligne absente pour (school, key)
    => le texte par défaut actuellement en dur (constantes DEFAULT_* de apps.admissions.services) continue
    de s'appliquer : aucune régression avant que l'admin ne configure quoi que ce soit, ni avant l'exécution
    de la commande seed_message_templates."""
    KEYS = [
        ("quote_approved", "Devis approuvé"),
        ("quote_correction_default", "Correction demandée — texte par défaut"),
        ("quote_quoted", "Devis envoyé (PDF disponible)"),
        ("account_created", "Compte créé automatiquement (après approbation d'un devis vitrine, ou import de cohorte)"),
    ]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="message_templates")
    key = models.CharField(max_length=40, choices=KEYS)
    subject = models.CharField(max_length=150, blank=True, help_text="E-mail uniquement ; ignoré pour WhatsApp.")
    body = models.TextField(help_text="Variables disponibles : {prenom}, {nom}, ... (voir doc par clé, apps.admissions.models.AVAILABLE_VARIABLES)")

    class Meta:
        unique_together = [("school", "key")]
        ordering = ["school", "key"]

    def __str__(self):
        return f"{self.get_key_display()} — {self.school}"


class QuoteRejectReason(TimeStamped):
    """Motifs de refus proposés à la secrétaire dans le menu « Rejeter » (web RejectMenu), par type d'offre
    et par auto-école — remplace la constante JS figée REJECT_REASONS (anciennement web/src/resources.jsx)
    comme SOURCE DE VÉRITÉ : désormais gérée (créée/modifiée/supprimée/réordonnée) depuis l'admin plutôt que
    codée en dur côté front."""
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="quote_reject_reasons")
    offer = models.CharField(max_length=20, choices=OFFERS)
    text = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["school", "offer", "order"]

    def __str__(self):
        return f"{self.text[:60]} ({self.get_offer_display()})"
