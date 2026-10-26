"""Crée/actualise, pour chaque auto-école existante :
  - les 4 MessageTemplate (une par clé : quote_approved, quote_correction_default, quote_quoted,
    account_created), avec le texte PAR DÉFAUT actuellement en dur dans apps.admissions.services
    (constantes DEFAULT_*) — pour que l'admin ait d'emblée quelque chose d'éditable, identique à ce qui
    était envoyé jusqu'ici (aucune régression visuelle) ;
  - les QuoteRejectReason (motifs de refus proposés dans le menu « Rejeter » du staff), copiés VERBATIM
    de l'ancienne constante JS REJECT_REASONS (web/src/resources.jsx), qui devient obsolète côté front une
    fois cette commande exécutée et l'admin web branché sur GET /api/quote-reject-reasons/?offer=....

    python manage.py seed_message_templates

Idempotent : update_or_create par (school, key) pour les gabarits, par (school, offer, order) pour les
motifs de refus.
"""
from django.core.management.base import BaseCommand

from apps.admissions import services
from apps.admissions.models import MessageTemplate, QuoteRejectReason
from apps.schools.models import School

# (key, subject, body) — subject ignoré pour WhatsApp ; vide pour quote_correction_default (pas de sujet,
# ce texte alimente seulement IndividualQuote.correction_note, cf. apps.admissions.services.default_correction_note).
MESSAGE_TEMPLATES = [
    ("quote_approved", services.DEFAULT_QUOTE_APPROVED_SUBJECT, services.DEFAULT_QUOTE_APPROVED_BODY),
    ("quote_correction_default", "", services.DEFAULT_QUOTE_CORRECTION_DEFAULT_BODY),
    ("quote_quoted", services.DEFAULT_QUOTE_QUOTED_SUBJECT, services.DEFAULT_QUOTE_QUOTED_BODY),
    ("account_created", services.DEFAULT_ACCOUNT_CREATED_SUBJECT, services.DEFAULT_ACCOUNT_CREATED_BODY),
]

# Copié verbatim de l'ancienne constante REJECT_REASONS (web/src/resources.jsx), 4 offres x 2 motifs.
REJECT_REASONS = {
    "new_license": [
        "Nous sommes désolés de ne pas pouvoir répondre à votre attente car votre pièce d'identité est enregistrée ailleurs.",
        "Le numéro de la pièce d'identité fournie n'a pas pu être vérifié : merci de nous transmettre une pièce valide.",
    ],
    "extension": [
        "Une ou plusieurs de vos catégories actuellement détenues ne sont plus valides (permis périmé) : merci de les renouveler avant de demander l'extension.",
        "Les informations sur vos catégories détenues ne correspondent pas à nos vérifications : merci de les confirmer.",
    ],
    "theory_refresh": [
        "Le numéro de permis renseigné ne correspond à aucun permis valide dans notre base de vérification.",
        "Les informations de votre permis (numéro ou photo) ne correspondent pas aux données enregistrées : merci de vérifier votre saisie.",
    ],
    "practical_refresh": [
        "Le numéro de permis renseigné ne correspond à aucun permis valide dans notre base de vérification.",
        "Les informations de votre permis (numéro ou photo) ne correspondent pas aux données enregistrées : merci de vérifier votre saisie.",
    ],
}


class Command(BaseCommand):
    help = ("Crée/actualise les 4 MessageTemplate (textes par défaut actuels) et les QuoteRejectReason "
            "(copiés de l'ancienne constante JS REJECT_REASONS) pour chaque auto-école. Idempotent.")

    def handle(self, *args, **opts):
        schools = list(School.objects.all())
        if not schools:
            return self.stderr.write("Aucune auto-école : lancez d'abord seed_demo.")

        tpl_count = 0
        reason_count = 0
        for school in schools:
            for key, subject, body in MESSAGE_TEMPLATES:
                MessageTemplate.objects.update_or_create(
                    school=school, key=key, defaults={"subject": subject, "body": body})
                tpl_count += 1
            for offer, reasons in REJECT_REASONS.items():
                for order, text in enumerate(reasons):
                    QuoteRejectReason.objects.update_or_create(
                        school=school, offer=offer, order=order, defaults={"text": text})
                    reason_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"{tpl_count} modèle(s) de message et {reason_count} motif(s) de refus créé(s)/mis à jour "
            f"pour {len(schools)} auto-école(s)."))
