import secrets

from django.db import migrations

JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 8


def backfill(apps, schema_editor):
    Cohort = apps.get_model("organizations", "Cohort")
    existing = set(Cohort.objects.exclude(join_code__isnull=True).exclude(join_code="").values_list("join_code", flat=True))
    for cohort in Cohort.objects.filter(join_code__isnull=True):
        while True:
            code = "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))
            if code not in existing:
                existing.add(code)
                break
        cohort.join_code = code
        cohort.save(update_fields=["join_code"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0006_cohort_join_code'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
