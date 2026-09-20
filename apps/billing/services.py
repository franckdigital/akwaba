import hmac
import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.notify import notify

from .models import Installment, Invoice, InvoiceLine, Payment


def make_installments(invoice, count, first_due, interval_days=30):
    if count < 1 or count > 60:
        raise ValidationError({"count": "Nombre d'échéances entre 1 et 60."})
    if invoice.payments.filter(status="confirmed").exists():
        raise ValidationError({"detail": "Des paiements existent déjà : échéancier non modifiable."})
    with transaction.atomic():
        invoice.installments.all().delete()
        total = int(invoice.total)
        base = total // count
        rest = total - base * count
        items = []
        for i in range(count):
            amount = base + (rest if i == count - 1 else 0)
            items.append(Installment(invoice=invoice, number=i + 1, amount=amount,
                                     due_date=first_due + timedelta(days=interval_days * i)))
        Installment.objects.bulk_create(items)
    return list(invoice.installments.all())


def reallocate(invoice):
    """Répartit les paiements confirmés sur les échéances, dans l'ordre."""
    remaining = sum((p.amount for p in invoice.payments.filter(status="confirmed")), Decimal(0))
    for inst in invoice.installments.order_by("number"):
        part = min(inst.amount, remaining)
        if inst.paid_amount != part:
            inst.paid_amount = part
            inst.save(update_fields=["paid_amount", "updated_at"])
        remaining -= part


def new_receipt_number(payment):
    return f"REC-{payment.school_id}-{timezone.localdate():%Y%m}-{payment.pk:06d}"


@transaction.atomic
def confirm_payment(payment, payload=None):
    """Point unique de confirmation : appelé par le webhook fournisseur ou l'encaissement d'un caissier."""
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == "confirmed":
        return payment
    invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
    payment.status = "confirmed"
    payment.paid_at = timezone.now()
    if payload is not None:
        payment.raw_payload = payload
    payment.save()
    payment.receipt_number = new_receipt_number(payment)
    payment.save(update_fields=["receipt_number"])
    invoice.recompute()
    reallocate(invoice)
    from apps.subscriptions.services import on_invoice_paid  # abonnement acheté : activation après confirmation
    on_invoice_paid(invoice)
    learner = invoice.learner
    if learner and learner.user:
        notify(learner.user, "payment_confirmed", "Paiement confirmé",
               f"{int(payment.amount)} FCFA reçus (reçu {payment.receipt_number}).", channels=("inapp", "sms"))
        if invoice.status == "paid":
            notify(learner.user, "schedule_settled", "Facture soldée", f"La facture {invoice.number} est entièrement payée.")
        if learner.status == "new":
            learner.status = "registered"
            learner.save(update_fields=["status"])
    return payment


def fail_payment(payment, payload=None):
    if payment.status == "pending":
        payment.status = "failed"
        payment.raw_payload = payload
        payment.save(update_fields=["status", "raw_payload", "updated_at"])
    return payment


def sign(body: bytes) -> str:
    return hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str) -> bool:
    return bool(signature) and hmac.compare_digest(sign(body), signature)


def new_provider_ref(method):
    return f"{method[:3].upper()}-{secrets.token_hex(6).upper()}"


def process_provider_event(data):
    """Traite un événement fournisseur (déjà authentifié). Idempotent."""
    payment = Payment.objects.filter(provider_ref=data.get("provider_ref")).first()
    if not payment:
        return None, "unknown"
    if data.get("status") == "success":
        if Decimal(str(data.get("amount", "0"))) != payment.amount:
            return payment, "amount_mismatch"
        confirm_payment(payment, data)
        return payment, "confirmed"
    fail_payment(payment, data)
    return payment, "failed"


@transaction.atomic
def generate_contract_invoices(contract, first_due):
    """Facture organisation + factures apprenants (part apprenant en échéances)."""
    school = contract.school
    result = {"organization_invoice": None, "learner_invoices": 0}
    org_amount = min(contract.organization_contribution, contract.net_price) * contract.beneficiaries_count
    if org_amount > 0 and not Invoice.objects.filter(contract=contract, organization=contract.organization,
                                                      learner__isnull=True, kind="invoice").exists():
        inv = Invoice.objects.create(school=school, organization=contract.organization, contract=contract,
                                     title=f"{contract.training.name} - part organisation", total=org_amount,
                                     issue_date=timezone.localdate(), due_date=first_due)
        InvoiceLine.objects.create(invoice=inv, description=f"Contribution {contract.organization.name}",
                                   quantity=contract.beneficiaries_count,
                                   unit_price=min(contract.organization_contribution, contract.net_price))
        result["organization_invoice"] = inv.number
    from apps.learners.models import Learner
    learners = Learner.objects.filter(school=school, organization=contract.organization, training=contract.training)
    learners = learners.filter(cohort__contract=contract) | learners.filter(cohort__isnull=True)
    part = contract.learner_contribution
    if part > 0:
        for learner in learners.distinct():
            if Invoice.objects.filter(contract=contract, learner=learner, kind="invoice").exists():
                continue
            inv = Invoice.objects.create(school=school, learner=learner, organization=None, contract=contract,
                                         title=f"{contract.training.name} - part apprenant", total=part,
                                         issue_date=timezone.localdate(), due_date=first_due)
            InvoiceLine.objects.create(invoice=inv, description=contract.training.name, quantity=1, unit_price=part)
            if contract.installments_count > 1:
                make_installments(inv, contract.installments_count, first_due)
            result["learner_invoices"] += 1
    return result


def send_installment_reminders(today=None):
    """Rappels : échéance à J-3, du jour, en retard. À lancer chaque jour (cron / Celery beat)."""
    today = today or timezone.localdate()
    sent = 0
    for inst in Installment.objects.filter(paid_amount__lt=F("amount"), due_date__lte=today + timedelta(days=3)).select_related(
            "invoice__learner__user"):
        learner = inst.invoice.learner
        if not learner or not learner.user:
            continue
        if inst.due_date < today:
            event, title = "installment_late", "Échéance en retard"
        elif inst.due_date == today:
            event, title = "installment_today", "Échéance du jour"
        else:
            event, title = "installment_soon", "Échéance prochaine"
        notify(learner.user, event, title, f"{int(inst.balance)} FCFA à régler avant le {inst.due_date:%d/%m/%Y}.",
               channels=("inapp", "sms"))
        sent += 1
    return sent


# --------------------------------------------------------------------------- PDF
def _pdf(build):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    build(c, A4)
    c.showPage()
    c.save()
    return buf.getvalue()


def invoice_pdf(invoice):
    def build(c, size):
        w, h = size
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, h - 60, f"{invoice.get_kind_display().upper()} {invoice.number}")
        c.setFont("Helvetica", 11)
        c.drawString(50, h - 85, str(invoice.school))
        who = invoice.learner.full_name if invoice.learner else (invoice.organization.name if invoice.organization else "")
        c.drawString(50, h - 115, f"Client : {who}")
        c.drawString(50, h - 130, f"Date : {invoice.issue_date or invoice.created_at:%d/%m/%Y}   Échéance : {invoice.due_date or '-'}")
        y = h - 170
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "Description")
        c.drawString(330, y, "Qté")
        c.drawString(390, y, "P.U.")
        c.drawString(470, y, "Montant")
        c.setFont("Helvetica", 11)
        for line in invoice.lines.all():
            y -= 18
            c.drawString(50, y, line.description[:45])
            c.drawString(330, y, f"{line.quantity}")
            c.drawString(390, y, f"{int(line.unit_price):,}".replace(",", " "))
            c.drawString(470, y, f"{int(line.amount):,}".replace(",", " "))
        y -= 30
        c.setFont("Helvetica-Bold", 12)
        c.drawString(330, y, f"Total : {int(invoice.total):,} FCFA".replace(",", " "))
        c.setFont("Helvetica", 11)
        c.drawString(330, y - 16, f"Payé : {int(invoice.paid):,} FCFA".replace(",", " "))
        c.drawString(330, y - 32, f"Reste : {int(invoice.balance):,} FCFA".replace(",", " "))
        y -= 70
        if invoice.installments.exists():
            c.setFont("Helvetica-Bold", 11)
            c.drawString(50, y, "Échéancier")
            c.setFont("Helvetica", 10)
            for i in invoice.installments.all():
                y -= 15
                c.drawString(50, y, f"#{i.number}  {i.due_date:%d/%m/%Y}  {int(i.amount):,} FCFA  payé {int(i.paid_amount):,}".replace(",", " "))
    return _pdf(build)


def receipt_pdf(payment):
    def build(c, size):
        w, h = size
        c.setFont("Helvetica-Bold", 20)
        c.drawString(50, h - 70, f"REÇU {payment.receipt_number}")
        c.setFont("Helvetica", 12)
        inv = payment.invoice
        lines = [str(payment.school), "",
                 f"Reçu de : {inv.learner.full_name if inv.learner else (inv.organization.name if inv.organization else '')}",
                 f"Facture : {inv.number}", f"Mode de paiement : {payment.get_method_display()}",
                 f"Référence : {payment.provider_ref or payment.reference or '-'}",
                 f"Date : {timezone.localtime(payment.paid_at):%d/%m/%Y %H:%M}" if payment.paid_at else "",
                 f"Montant : {int(payment.amount):,} FCFA".replace(",", " "),
                 f"Reste à payer sur la facture : {int(inv.balance):,} FCFA".replace(",", " ")]
        y = h - 110
        for ln in lines:
            c.drawString(50, y, ln)
            y -= 20
    return _pdf(build)
