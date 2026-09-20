from django.core.management.base import BaseCommand

from apps.billing.services import send_installment_reminders
from apps.subscriptions.services import expire_subscriptions, send_subscription_reminders


class Command(BaseCommand):
    help = "Rappels d'échéances et d'expiration d'abonnements, clôture des abonnements expirés (à planifier chaque jour : cron / Celery beat)."

    def handle(self, *args, **opts):
        self.stdout.write(f"{send_installment_reminders()} rappel(s) d'échéance envoyé(s).")
        self.stdout.write(f"{expire_subscriptions()} abonnement(s) clôturé(s), {send_subscription_reminders()} rappel(s) d'expiration envoyé(s).")
