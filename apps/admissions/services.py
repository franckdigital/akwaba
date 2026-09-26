import hashlib
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.core.mail import send_mail
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.notify import notify

from .models import ACTIVE_STATUSES, PERIODIC_CATEGORIES, IndividualQuote, RecyclingReminderLog, RecyclingReminderSettings

CATEGORY_LABELS = dict([("A", "A"), ("A1", "A1"), ("B", "B"), ("C", "C"), ("D", "D"), ("E", "E"), ("OTHER", "Autre")])

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
    """§3.1/3.2 — envoi du devis par e-mail ou WhatsApp, au choix, en un clic."""
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
    elif channel == "whatsapp":
        import logging
        logging.getLogger("akwaba.notify").info("[whatsapp] -> %s : devis #%s (%s FCFA)", quote.phone, quote.pk, int(quote.price))
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
