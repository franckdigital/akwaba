from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.schools.models import School


class Command(BaseCommand):
    help = "Crée (ou met à jour) un compte du personnel avec e-mail et WhatsApp pour recevoir les alertes."

    def add_arguments(self, p):
        p.add_argument("--email", required=True)
        p.add_argument("--phone", required=True)
        p.add_argument("--role", default="director")
        p.add_argument("--first", default="Numerix")
        p.add_argument("--last", default="Digital")
        p.add_argument("--password", default="Akwaba@2026")

    def handle(self, *a, **o):
        school = School.objects.first()
        u, created = User.objects.get_or_create(email=o["email"], defaults=dict(
            first_name=o["first"], last_name=o["last"], role=o["role"], school=school, email_verified=True))
        u.phone, u.role, u.school, u.is_active = o["phone"], o["role"], school, True
        if created:
            u.set_password(o["password"])
        u.save()
        self.stdout.write(self.style.SUCCESS(f"{'Créé' if created else 'Mis à jour'} : {u.email} ({u.role}) {u.phone}"))
