from django.core.management.base import BaseCommand

from apps.admissions.models import IndividualQuote, RecyclingItem
from apps.schools.models import School


class Command(BaseCommand):
    help = "Crée des demandes de devis d'exemple pour les 4 offres (idempotent)."

    def handle(self, *args, **opts):
        school = School.objects.first()
        if not school:
            return self.stderr.write("Aucune auto-école : lancez d'abord seed_demo.")
        items = []
        for kind, label, price in [("module", "Signalisation routière", 15000), ("module", "Priorités et intersections", 15000),
                                   ("package", "Package recyclage complet", 40000)]:
            items.append(RecyclingItem.objects.get_or_create(school=school, label=label, defaults={"kind": kind, "price": price})[0])

        rows = [
            dict(offer="new_license", id_document_no="CI-DEV-0001", last_name="Kone", first_name="Ibrahim", phone="0700000101",
                 email="ibrahim.kone@example.ci", residence="Yopougon", id_document_type="resident_card", categories_requested=["B"],
                 status="submitted"),
            dict(offer="extension", id_document_no="CI-DEV-0002", last_name="Diallo", first_name="Mariam", phone="0700000102",
                 email="mariam.diallo@example.ci", residence="Cocody", id_document_type="passport", license_no="PC-778812",
                 categories_held=["B"], categories_expiry={}, categories_to_add=["C"], status="approved"),
            dict(offer="theory_refresh", id_document_no="CI-DEV-0003", last_name="Ouattara", first_name="Seydou", phone="0700000103",
                 email="seydou.ouattara@example.ci", residence="Marcory", id_document_type="id_attestation", license_no="PC-114455",
                 status="quoted", base_price=70000, negotiated_price=65000),
            dict(offer="practical_refresh", id_document_no="CI-DEV-0004", last_name="Traore", first_name="Fatou", phone="0700000104",
                 email="fatou.traore@example.ci", residence="Abobo", id_document_type="resident_card", license_no="PC-330021",
                 status="correction_requested", correction_note="Merci de préciser la catégorie à remettre à niveau."),
        ]
        created = 0
        for r in rows:
            if IndividualQuote.objects.filter(school=school, last_name=r["last_name"], first_name=r["first_name"], offer=r["offer"]).exists():
                continue
            q = IndividualQuote.objects.create(school=school, **r)
            if q.offer == "theory_refresh":
                q.recycling_items.set(items[:2])
            created += 1
        self.stdout.write(self.style.SUCCESS(f"{created} demande(s) de devis créée(s) ({len(rows)} prévues)."))
