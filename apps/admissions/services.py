import hashlib
import logging
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.messaging import send_text
from apps.core.notify import notify, notify_contact

from .models import ACTIVE_STATUSES, PERIODIC_CATEGORIES, IndividualQuote, RecyclingReminderLog, RecyclingReminderSettings

logger = logging.getLogger(__name__)

CATEGORY_LABELS = dict([("A", "A"), ("B", "B"), ("C", "C"), ("D", "D"), ("E", "E"), ("OTHER", "Autre")])

# §5.2 — palier de paiement : arbitrage retenu = 50 % fixe, la même pour toutes les offres (nouveau permis / recyclages).
# Un candidat rattaché à une collectivité a accès complet (§3.1/§5.2), sans palier.
CODE_EXAM_RATIO = Decimal("0.5")
PRACTICAL_EXAM_RATIO = Decimal("1")


# --------------------------------------------------------------------------- §5.2/§6.1 — palier de paiement
def payment_ratio(learner):
    """Part payée des factures de formation du candidat (hors devis/brouillons/annulées).
    Une collectivité couvre l'accès complet prévu par la convention : ratio = 1.
    Renvoie None quand le candidat n'a aucune facturation de formation : le palier de paiement
    (§5.2) ne s'applique alors pas — comportement historique conservé (dossiers créés par le staff,
    formations gratuites, ou facturation gérée hors du système)."""
    if learner.organization_id:
        return Decimal(1)
    from apps.billing.models import Invoice
    qs = Invoice.objects.filter(learner=learner, kind=Invoice.INVOICE).exclude(status__in=("draft", "cancelled"))
    total = sum((i.total for i in qs), Decimal(0))
    if total <= 0:
        return None
    paid = sum((i.paid for i in qs), Decimal(0))
    return min(paid / total, Decimal(1))


def theory_course_completed(learner):
    """§6.1 — « cours théorique validé » : tous les cours théoriques accessibles au candidat (selon son offre,
    §5.3) sont à 100 % de leurs contenus obligatoires. Aucun cours théorique accessible => non validé."""
    from apps.pedagogy.views import course_progress
    courses = list(visible_courses(learner).filter(kind="theory"))
    if not courses:
        return False
    done_ids = set(learner.user.material_progress.values_list("material_id", flat=True)) if learner.user_id else set()
    return all(course_progress(c, done_ids)["percent"] == 100 for c in courses)


def exam_access(learner):
    """§5.2/§6.1 — accès aux examens : renvoie l'état des deux paliers (code = théorique, practical = conduite)."""
    ratio = payment_ratio(learner)
    payment_ok = ratio is None or ratio >= CODE_EXAM_RATIO
    payment_ok_full = ratio is None or ratio >= PRACTICAL_EXAM_RATIO
    from apps.pedagogy.services import exam_eligibility
    qcm_ok = exam_eligibility(learner)["eligible"]
    theory_ok = theory_course_completed(learner)
    return {
        "payment_ratio": float(ratio) if ratio is not None else None,
        "code": {"ok": payment_ok and qcm_ok and theory_ok, "payment_ok": payment_ok,
                "qcm_ok": qcm_ok, "theory_course_ok": theory_ok, "required_ratio": float(CODE_EXAM_RATIO)},
        "practical": {"ok": payment_ok_full, "payment_ok": payment_ok_full, "required_ratio": float(PRACTICAL_EXAM_RATIO)},
    }


# --------------------------------------------------------------------------- §5.3 — contenu de cours selon l'offre
def visible_courses(learner):
    """§5.3 : nouveau permis => cours complet ; recyclage théorique => cours des modules demandés ;
    recyclage pratique => pas de cours théorique (séances programmées uniquement, gérées ailleurs) ;
    pas de devis rattaché (dossier créé par le staff, ou extension) => accès complet, comportement historique."""
    from apps.pedagogy.models import Course
    qs = Course.objects.filter(is_published=True).prefetch_related("materials")
    offer = learner.quote.offer if learner.quote_id else None
    if offer == "theory_refresh":
        course_ids = list(learner.quote.recycling_items.exclude(course__isnull=True).values_list("course_id", flat=True))
        return qs.filter(pk__in=course_ids)
    if offer == "practical_refresh":
        return qs.filter(kind="practical")
    return qs


def document_hash(id_document_no):
    return hashlib.sha256(id_document_no.strip().upper().encode()).hexdigest() if id_document_no else ""


def check_duplicate(id_document_no, exclude_pk=None):
    """§3.1 point de vigilance : une seule demande de devis « en cours » par pièce d'identité."""
    h = document_hash(id_document_no)
    if not h:
        return
    qs = IndividualQuote.objects.filter(id_document_hash=h, status__in=ACTIVE_STATUSES)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    existing = qs.first()
    if existing:
        raise ValidationError({"id_document_no": "Une demande de devis est déjà en cours pour cette pièce d'identité "
                                                  f"(statut : {existing.get_status_display()}). Une seule demande à la fois par candidat."})


def expired_held_categories(categories_held, categories_expiry, today=None):
    """Catégories périodiques (C/D/E) déclarées par le candidat comme détenues et dont la date fournie est dépassée."""
    today = today or timezone.localdate()
    expired = []
    for cat in categories_held or []:
        if cat not in PERIODIC_CATEGORIES:
            continue
        raw = (categories_expiry or {}).get(cat)
        if not raw:
            continue
        try:
            d = date.fromisoformat(raw)
        except (TypeError, ValueError):
            continue
        if d < today:
            expired.append(cat)
    return expired


def rejection_message_for_expired_categories(expired):
    """Libellé générique avec la ou les vraies catégories expirées (arbitrage retenu : pas de texte figé « CDE »)."""
    label = "/".join(expired)
    return f"Nous vous prions de bien vouloir revoir la validité de votre permis {label}."


def validate_extension(categories_held, categories_to_add, categories_expiry):
    if len(categories_to_add or []) != 1:
        raise ValidationError({"categories_to_add": "Une seule catégorie à ajouter à la fois."})
    if categories_to_add[0] in (categories_held or []):
        raise ValidationError({"categories_to_add": "Cette catégorie est déjà détenue : choisissez-en une autre."})
    expired = expired_held_categories(categories_held, categories_expiry)
    if expired:
        raise ValidationError({"categories_held": rejection_message_for_expired_categories(expired)})


def compute_recycling_price(recycling_items):
    return sum((i.price for i in recycling_items), start=0)


def validate_quote_request(attrs):
    """Règles communes à tout dépôt de demande de devis individuelle — formulaire public (sans compte) ou
    dépôt authentifié par un candidat déjà connecté (§D) : anti-doublon par pièce d'identité (§3.1), cohérence
    des catégories en cas d'extension, permis existant requis pour les recyclages. Extrait de
    PublicIndividualQuoteSerializer pour être réutilisé tel quel par MyQuotesView.post (§D) sans dupliquer la
    logique."""
    check_duplicate(attrs.get("id_document_no", ""))
    offer = attrs.get("offer")
    if offer == "extension":
        validate_extension(attrs.get("categories_held", []), attrs.get("categories_to_add", []),
                           attrs.get("categories_expiry", {}))
    if offer in ("theory_refresh", "practical_refresh") and not attrs.get("license_no"):
        raise ValidationError({"license_no": "Le numéro de permis existant est requis pour cette offre."})
    return attrs


def quote_pdf_bytes(quote):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    y = h - 60
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, y, str(quote.school) if quote.school else "Akwaba Auto-École")
    y -= 30
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "DEVIS")
    y -= 10
    c.setFont("Helvetica", 9)
    c.drawString(50, y, f"Réf. AKW-DEV-{quote.pk:06d}  ·  {timezone.localdate():%d/%m/%Y}")
    y -= 30
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Candidat")
    y -= 16
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"{quote.first_name} {quote.last_name}")
    y -= 14
    c.drawString(50, y, f"Offre : {quote.get_offer_display()}")
    y -= 14
    if quote.offer == "new_license" and quote.categories_requested:
        c.drawString(50, y, "Catégories demandées : " + ", ".join(quote.categories_requested))
        y -= 14
    if quote.offer == "extension" and quote.categories_to_add:
        c.drawString(50, y, "Catégorie en extension : " + ", ".join(quote.categories_to_add))
        y -= 14
    if quote.offer in ("theory_refresh", "practical_refresh"):
        items = list(quote.recycling_items.all())
        if items:
            c.drawString(50, y, "Modules / packages : " + ", ".join(i.label for i in items))
            y -= 14
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Tarif : {int(quote.price):,} FCFA".replace(",", " "))
    if quote.negotiated_price is not None and quote.negotiated_price != quote.base_price:
        y -= 16
        c.setFont("Helvetica", 9)
        c.drawString(50, y, f"(tarif négocié — tarif catalogue : {int(quote.base_price):,} FCFA)".replace(",", " "))
    y -= 20
    c.setFont("Helvetica", 9)
    c.drawString(50, y, f"Déjà réglé : {int(quote.paid_amount):,} FCFA  ·  Solde : {int(quote.balance):,} FCFA".replace(",", " "))
    c.showPage()
    c.save()
    return buf.getvalue()


def send_quote(quote, channel):
    """§3.1/3.2 — envoi du devis par e-mail ou WhatsApp, au choix, en un clic (action manuelle du secrétariat).

    §C — décision produit : le candidat doit systématiquement recevoir une copie sur LES DEUX canaux (e-mail
    ET WhatsApp, selon les coordonnées renseignées), sans que la secrétaire ait à cliquer sur les deux boutons
    séparément. Le canal manuel choisi ici reçoit le message « riche » (devis en pièce jointe / lien direct) ;
    notify_quote_decision() complète ensuite avec l'AUTRE canal uniquement (`exclude_channel=channel`), pour ne
    jamais notifier deux fois le même canal pour le même évènement.
    """
    from django.core.files.base import ContentFile
    pdf_bytes = quote_pdf_bytes(quote)
    quote.quote_pdf.save(f"devis-{quote.pk}.pdf", ContentFile(pdf_bytes), save=False)
    quote.status = "quoted"
    quote.sent_channel = channel
    quote.sent_at = timezone.now()
    quote.save(update_fields=["quote_pdf", "status", "sent_channel", "sent_at", "updated_at"])
    if channel == "email" and quote.email:
        send_mail("Votre devis Akwaba Auto-École",
                  f"Bonjour {quote.first_name},\n\nVeuillez trouver votre devis en pièce jointe.\n\n"
                  f"Tarif : {int(quote.price)} FCFA.\n\nAkwaba Auto-École",
                  None, [quote.email], fail_silently=True)
    elif channel == "whatsapp" and quote.phone:
        pdf_url = f"{settings.BACKEND_BASE_URL}{quote.quote_pdf.url}"
        send_text("whatsapp", quote.phone,
                  f"Bonjour {quote.first_name}, voici votre devis Akwaba Auto-École : {pdf_url}\n"
                  f"Tarif : {int(quote.price)} FCFA.")
    notify_quote_decision(quote, exclude_channel=channel)
    return quote


def send_recycling_reminders(today=None):
    """Relance automatique et paramétrable (depuis l'admin, §3.3) des candidats déjà titulaires d'un permis.
    Idempotent (à planifier chaque jour, comme send_reminders) : s'appuie sur RecyclingReminderLog pour
    ne pas relancer deux fois le même jour, et respecte l'échéance propre à chaque auto-école."""
    from apps.learners.models import Learner
    today = today or timezone.localdate()
    sent = 0
    for settings_ in RecyclingReminderSettings.objects.filter(is_active=True).select_related("school"):
        learners = Learner.objects.filter(school=settings_.school, status="licensed", license_obtained_at__isnull=False)
        for learner in learners:
            days = (today - learner.license_obtained_at).days
            if days < settings_.first_reminder_days:
                continue
            due = (days - settings_.first_reminder_days) % max(settings_.repeat_every_days, 1) == 0
            if not due:
                continue
            if RecyclingReminderLog.objects.filter(learner=learner, created_at__date=today).exists():
                continue
            channels = tuple(settings_.channels or ["email"])
            if learner.user:
                notify(learner.user, "recycling_reminder", "Pensez à votre recyclage",
                      settings_.message, channels=channels)
            RecyclingReminderLog.objects.create(learner=learner, channel=",".join(channels))
            sent += 1
    return sent


def _quote_pdf_message(quote):
    link = f" : {settings.BACKEND_BASE_URL}{quote.quote_pdf.url}" if quote.quote_pdf else ""
    return f"Bonjour {quote.first_name}, voici votre devis Akwaba Auto-École{link}\nTarif : {int(quote.price)} FCFA."


# §C — décision produit : toute décision prise sur un devis individuel (pas seulement le refus/la correction)
# déclenche une notification candidat, sur les DEUX canaux (e-mail + WhatsApp) à chaque fois — events/messages
# par statut, réutilisés par notify_quote_decision() ci-dessous.
QUOTE_DECISION_NOTIFICATIONS = {
    "approved": ("quote_approved", "Votre demande de devis est approuvée",
                lambda q: f"Bonjour {q.first_name}, votre demande de devis a été approuvée par l'auto-école. "
                          "Votre devis chiffré va vous être transmis très prochainement."),
    "rejected": ("quote_rejected", "Votre demande de devis",
                lambda q: f"Bonjour {q.first_name}, {q.reject_reason}"),
    "correction_requested": ("quote_correction", "Votre demande de devis : une correction est nécessaire",
                             lambda q: f"Bonjour {q.first_name}, {q.correction_note}"),
    "quoted": ("quote_quoted", "Votre devis est disponible", _quote_pdf_message),
}


def notify_quote_decision(quote, exclude_channel=None):
    """Le candidat est informé par e-mail ET WhatsApp (selon les coordonnées renseignées) de toute décision
    prise sur son devis — approbation, refus (avec motif), correction demandée, ou mise à disposition du
    devis chiffré (§C). Appelé par IndividualQuoteViewSet.decide() pour approved/rejected/correction_requested,
    et par send_quote() pour quoted.

    `exclude_channel` évite de notifier deux fois le MÊME canal pour le MÊME évènement quand send_quote() a
    déjà envoyé manuellement le devis sur ce canal (bouton « envoyer par e-mail/WhatsApp », §3.1/§3.2) : seul
    le canal complémentaire est alors notifié ici.
    """
    entry = QUOTE_DECISION_NOTIFICATIONS.get(quote.status)
    if entry is None:
        return []
    event, title, message_fn = entry
    channels = tuple(c for c in ("email", "whatsapp") if c != exclude_channel)
    if not channels:
        return []
    return notify_contact(event, title, message_fn(quote), email=quote.email, phone=quote.phone,
                          school_id=quote.school_id, channels=channels)


def _send_quote_account_credentials(user, password):
    """§ décision produit — message dédié à la création automatique du compte à l'approbation d'un devis vitrine
    (candidat public, sans compte) : identifiant (e-mail), mot de passe provisoire, consigne de changement.
    DISTINCT de notify_quote_decision() (qui informe de la décision elle-même) : envoyé en PLUS, pas à la place,
    sur les deux canaux (e-mail ET WhatsApp, selon les coordonnées disponibles), même circuit que
    apps.organizations.views.CohortViewSet.import_learners/apps.accounts.services._send_import_credentials."""
    body = (f"Bonjour {user.first_name}, votre compte Akwaba Auto-École a été créé automatiquement suite à "
           "l'approbation de votre demande.\n"
           f"Identifiant (e-mail) : {user.email}\nMot de passe provisoire : {password}\n"
           "Connectez-vous sur l'application pour commencer, puis pensez à changer votre mot de passe.")
    if user.email:
        send_mail("Votre compte Akwaba Auto-École", body, None, [user.email], fail_silently=True)
    if user.phone:
        send_text("whatsapp", user.phone, body)


def auto_create_account_for_quote(quote):
    """§ décision produit — « l'inscription du candidat individuel doit se faire automatiquement, pilotée par le
    système » : quand le secrétariat approuve un devis déposé depuis la vitrine PUBLIQUE (aucun compte rattaché
    encore), le compte (User + Learner) est créé automatiquement, pour que le candidat puisse se connecter et
    bénéficier de l'ouverture des fonctionnalités, puis payer son abonnement pour accéder aux ressources (§B,
    cf. apps.subscriptions.services.build_order). Appelée par IndividualQuoteViewSet.decide() uniquement pour
    decision == "approved".

    Ne s'applique PAS (même « process » pour tout le monde, mais rien à créer ici) :
    - si `quote.learner_id` est déjà renseigné : candidat déjà authentifié (ex. dépôt via POST /my-quotes/) ou
      inscription déjà effectuée avant l'approbation — seul le déblocage lié au statut du devis compte alors ;
    - si `quote.organization_id` est renseigné : candidat d'une collectivité, toujours créé par le staff (import
      Excel / création en masse), jamais par cette création automatique déclenchée côté vitrine.

    Défensif à chaque étape (ne doit JAMAIS empêcher l'approbation elle-même, déjà enregistrée en base avant cet
    appel) : renvoie None et journalise un avertissement plutôt que de lever, dès qu'un préalable manque
    (e-mail absent, compte déjà existant pour cet e-mail, auto-école non encore assignée au devis)."""
    if quote.learner_id is not None or quote.organization_id is not None:
        return None
    if not quote.email:
        logger.warning("Devis #%s approuvé sans e-mail renseigné : création automatique du compte impossible.", quote.pk)
        return None
    if not quote.school_id:
        logger.warning("Devis #%s approuvé sans auto-école assignée : création automatique du compte impossible.", quote.pk)
        return None
    from apps.accounts.models import User
    from apps.accounts.services import gen_password
    from apps.core.permissions import LEARNER
    from apps.learners.models import Learner
    email = quote.email.strip().lower()
    if User.objects.filter(email=email).exists():
        logger.warning("Devis #%s approuvé : un compte existe déjà pour %s, création automatique ignorée.", quote.pk, email)
        return None
    category = ""
    if quote.offer == "new_license" and quote.categories_requested:
        category = quote.categories_requested[0]
    elif quote.offer == "extension" and quote.categories_to_add:
        category = quote.categories_to_add[0]
    password = gen_password()
    user = User.objects.create_user(email, password, first_name=quote.first_name, last_name=quote.last_name,
                                    phone=quote.phone, role=LEARNER, school=quote.school)
    learner_kwargs = dict(user=user, school=quote.school, first_name=quote.first_name, last_name=quote.last_name,
                          email=email, phone=quote.phone, source="online", status="new", quote=quote)
    if category:
        learner_kwargs["category"] = category
    learner = Learner.objects.create(**learner_kwargs)
    quote.learner = learner
    quote.save(update_fields=["learner", "updated_at"])
    _send_quote_account_credentials(user, password)
    return user


def sync_plan_for_offer_config(config):
    """Génère/maintient à jour le Plan individuel « attaché » à ce type de demande (OfferTypeConfig), vendable
    séparément depuis l'écran « mes demandes » du candidat, EN PLUS des plans génériques (Découverte/Réussite…) —
    décision produit : chacune des 4 offres devient son propre plan achetable, purement additif.

    Idempotent, clé = (school, linked_offer=config.offer) : ré-exécuté à chaque sauvegarde de la config (admin)
    et par la commande sync_offer_type_plans (tous les OfferTypeConfig), pour garder le Plan synchronisé plutôt
    que de le créer une seule fois puis le laisser diverger.

    Choix de modélisation (Plan n'a pas de champ `is_on_sale`/`duration_days` — ce sont des propriétés calculées) :
    - `is_active` du plan reflète `config.is_active` (désactiver la config retire le plan de la vente au prochain
      sync, puisque `Plan.is_on_sale` vaut `is_active and dans la fenêtre de vente` — on laisse available_from/
      until vides pour que is_on_sale ne dépende que de is_active) ;
    - `billing_cycle`/`custom_days` sont désormais paramétrables depuis l'admin (champ équivalent sur
      OfferTypeConfig, même liste de choix) plutôt que figés à "yearly" — la période de validité de chaque
      formule peut donc être ajustée par la secrétaire/direction sans toucher au code.
    """
    from apps.schools.models import Plan
    plan, _ = Plan.objects.update_or_create(
        school=config.school, linked_offer=config.offer,
        defaults=dict(
            audience="individual",
            name=config.title or config.get_offer_display(),
            price=config.base_price,
            billing_cycle=config.billing_cycle,
            custom_days=config.custom_days,
            includes_courses=config.includes_courses,
            includes_quizzes=config.includes_quizzes,
            includes_exams=config.includes_exams,
            features=config.features,
            is_active=config.is_active,
        ))
    return plan


def engagement_pdf_response():
    """Fiche d'engagement (à télécharger, remplir et signer par le candidat pour confirmer son engagement)."""
    from pathlib import Path
    from django.http import FileResponse
    path = Path(__file__).parent / "assets" / "fiche_engagement.pdf"
    return FileResponse(open(path, "rb"), as_attachment=True, filename="fiche_engagement_akwaba.pdf", content_type="application/pdf")
