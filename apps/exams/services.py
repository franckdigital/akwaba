from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.notify import notify

from .models import Certificate


def verify_url(cert):
    return f"{settings.PUBLIC_WEB_URL}/verify/{cert.verification_token}"


@transaction.atomic
def issue_certificate(attempt):
    """Génère automatiquement le certificat si score >= seuil (idempotent)."""
    if not attempt.passed:
        return None
    existing = Certificate.objects.filter(attempt=attempt).first()
    if existing:
        return existing
    learner = attempt.learner
    training = learner.training or attempt.quiz.training
    cert = Certificate.objects.create(
        school=attempt.school, learner=learner, attempt=attempt, number="tmp-%s" % attempt.pk,
        training_name=training.name if training else attempt.quiz.title, category=attempt.quiz.category,
        score=f"{attempt.correct_count}/{attempt.total_questions}", percent=attempt.percent,
        issued_at=timezone.localdate())
    cert.number = f"AKW-CERT-{cert.issued_at:%Y}-{cert.pk:06d}"
    cert.save(update_fields=["number"])
    notify(learner.user, "certificate_ready", "Certificat disponible",
           f"Votre certificat {cert.number} est disponible.", channels=("inapp", "email", "sms"))
    return cert


def certificate_pdf(cert):
    import qrcode
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    w, h = landscape(A4)
    c = canvas.Canvas(buf, pagesize=(w, h))
    green = HexColor("#0f6b3e")
    c.setStrokeColor(green)
    c.setLineWidth(6)
    c.rect(20, 20, w - 40, h - 40)
    c.setLineWidth(1)
    c.rect(32, 32, w - 64, h - 64)
    c.setFillColor(green)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(w / 2, h - 90, "CERTIFICAT DE RÉUSSITE")
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 14)
    c.drawCentredString(w / 2, h - 120, str(cert.school))
    c.setFont("Helvetica", 13)
    c.drawCentredString(w / 2, h - 175, "Il est certifié que")
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(w / 2, h - 215, cert.learner.full_name.upper())
    c.setFont("Helvetica", 13)
    c.drawCentredString(w / 2, h - 250, "a réussi l'examen final théorique de la formation")
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 275, f"{cert.training_name} - Permis {cert.category}")
    c.setFont("Helvetica", 13)
    c.drawCentredString(w / 2, h - 305, f"Score : {cert.score}  -  Taux de réussite : {cert.percent} %")
    c.drawCentredString(w / 2, h - 325, f"Délivré le {cert.issued_at:%d/%m/%Y}")
    c.setFont("Helvetica", 11)
    c.drawString(60, 90, f"N° {cert.number}")
    if cert.status == Certificate.REVOKED:
        c.setFillColor(HexColor("#b91c1c"))
        c.setFont("Helvetica-Bold", 40)
        c.drawCentredString(w / 2, h / 2 - 40, "RÉVOQUÉ")
        c.setFillColorRGB(0, 0, 0)
    qr = qrcode.make(verify_url(cert))
    img = BytesIO()
    qr.save(img, format="PNG")
    img.seek(0)
    c.drawImage(ImageReader(img), w - 170, 50, 100, 100)
    c.setFont("Helvetica", 8)
    c.drawString(w - 190, 40, "Scannez pour vérifier l'authenticité")
    c.line(w / 2 - 90, 100, w / 2 + 90, 100)
    c.setFont("Helvetica-Oblique", 11)
    c.drawCentredString(w / 2, 85, cert.school.signatory_name or cert.school.manager_name or "La Direction")
    c.showPage()
    c.save()
    return buf.getvalue()
