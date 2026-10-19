"""Nettoie les anciennes questions QCM au préfixe « CR- » (banque centrale), remplacées par la nouvelle
banque sourcée du livre de code de la route (voir `seed_qcm_bank`).

Par sécurité :
  - les questions jamais utilisées dans une tentative d'apprenant sont supprimées définitivement ;
  - celles déjà répondues au moins une fois (historique protégé, on_delete=PROTECT) sont seulement
    désactivées (is_active=False) : elles disparaissent des tirages mais les résultats passés des
    apprenants restent corrects et consultables.

    python manage.py cleanup_legacy_qcm            # aperçu (ne modifie rien)
    python manage.py cleanup_legacy_qcm --apply     # applique le nettoyage
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef

from apps.pedagogy.models import AttemptAnswer, Question


class Command(BaseCommand):
    help = "Supprime (ou désactive si déjà utilisées) les anciennes questions QCM au préfixe CR-."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Applique réellement le nettoyage (sinon, aperçu seul).")
        parser.add_argument("--prefix", default="CR-", help="Préfixe des questions à nettoyer (défaut : CR-).")

    @transaction.atomic
    def handle(self, *args, **options):
        prefix = options["prefix"]
        qs = Question.objects.filter(code__startswith=prefix)
        used = qs.filter(Exists(AttemptAnswer.objects.filter(question=OuterRef("pk"))))
        unused = qs.exclude(pk__in=used.values("pk"))
        self.stdout.write(f"Questions « {prefix}* » : {qs.count()} au total — {unused.count()} supprimables, {used.count()} déjà utilisées (seront désactivées).")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Aperçu uniquement : relancez avec --apply pour appliquer le nettoyage."))
            return

        n_unused = unused.count()
        unused.delete()
        n_deactivated = used.update(is_active=False)
        self.stdout.write(self.style.SUCCESS(f"{n_unused} questions supprimées, {n_deactivated} désactivées (historique des apprenants préservé)."))
