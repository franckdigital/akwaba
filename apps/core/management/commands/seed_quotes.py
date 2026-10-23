"""Crée des demandes de devis de démonstration, une (ou plusieurs) par type d'offre, pour vérifier dans
l'admin (« Demandes de devis » / « Devis candidats ») que l'affichage correspond bien aux dernières
évolutions : types de pièce d'identité étendus, catégories à ajouter multiples (extension), modules/
forfaits de séances réels du catalogue de recyclage (cf. seed_recycling_sessions), statuts variés.

    python manage.py seed_quotes

Idempotent : update_or_create par (school, last_name, first_name, offer).
"""
from django.core.management.base import BaseCommand

from apps.admissions.models import IndividualQuote, RecyclingItem
from apps.schools.models import School

ROWS = [
    # --- Nouveau permis ---
    dict(offer="new_license", id_document_no="CI0123456789", last_name="Kone", first_name="Ibrahim", phone="0700000101",
         email="ibrahim.kone@example.ci", residence="Yopougon", id_document_type="cni", categories_requested=["B"],
         status="submitted"),
    dict(offer="new_license", id_document_no="CI0198765432", last_name="Bamba", first_name="Awa", phone="0700000105",
         email="awa.bamba@example.ci", residence="Koumassi", id_document_type="cni", categories_requested=["A"],
         status="approved"),

    # --- Extension de catégorie (plusieurs catégories à ajouter à la fois) ---
    dict(offer="extension", id_document_no="22CI445566", last_name="Diallo", first_name="Mariam", phone="0700000102",
         email="mariam.diallo@example.ci", residence="Cocody", id_document_type="driver_license", license_no="PC-778812",
         categories_held=["B"], categories_expiry={}, categories_to_add=["C", "D"], status="approved"),
    dict(offer="extension", id_document_no="22CI998877", last_name="Kouassi", first_name="Yves", phone="0700000106",
         email="yves.kouassi@example.ci", residence="Treichville", id_document_type="passport", license_no="PC-220099",
         categories_held=["A"], categories_expiry={}, categories_to_add=["B"], status="correction_requested",
         correction_note="Veuillez renseigner le type et le numéro de la pièce d'identité utilisée pour votre précédent permis."),

    # --- Recyclage théorique (modules réels du catalogue, kind="module") ---
    dict(offer="theory_refresh", id_document_no="22CI114455", last_name="Ouattara", first_name="Seydou", phone="0700000103",
         email="seydou.ouattara@example.ci", residence="Marcory", id_document_type="id_attestation", license_no="PC-114455",
         status="quoted", base_price=50000, negotiated_price=45000, _items=["Signalisation", "La conduite"]),

    # --- Recyclage pratique (forfaits de séances réels du catalogue, kind="package") ---
    dict(offer="practical_refresh", id_document_no="22CI330021", last_name="Traore", first_name="Fatou", phone="0700000104",
         email="fatou.traore@example.ci", residence="Abobo", id_document_type="resident_card", license_no="PC-330021",
         status="submitted", _items=["Recyclage pratique — Signalisation"]),
]


class Command(BaseCommand):
    help = ("Crée/actualise des demandes de devis de démonstration (une par type d'offre au minimum), "
            "avec les modules/forfaits réels du catalogue de recyclage. Idempotent.")

    def handle(self, *args, **opts):
        school = School.objects.first()
        if not school:
            return self.stderr.write("Aucune auto-école : lancez d'abord seed_demo.")

        catalogue = {i.label: i for i in RecyclingItem.objects.filter(school=school)}

        created, updated = 0, 0
        for row in ROWS:
            r = dict(row)
            item_labels = r.pop("_items", [])
            _, is_new = IndividualQuote.objects.update_or_create(
                school=school, last_name=r["last_name"], first_name=r["first_name"], offer=r["offer"], defaults=r,
            )
            q = IndividualQuote.objects.get(school=school, last_name=r["last_name"], first_name=r["first_name"], offer=r["offer"])
            if item_labels:
                items = [catalogue[label] for label in item_labels if label in catalogue]
                q.recycling_items.set(items)
                if len(items) < len(item_labels):
                    missing = set(item_labels) - set(catalogue)
                    self.stdout.write(self.style.WARNING(
                        f"  Module(s)/forfait(s) introuvable(s) dans le catalogue (lancez d'abord "
                        f"seed_recycling_sessions) : {', '.join(missing)}"))
            created += 1 if is_new else 0
            updated += 0 if is_new else 1

        self.stdout.write(self.style.SUCCESS(
            f"{created} demande(s) de devis créée(s), {updated} mise(s) à jour ({len(ROWS)} au total, "
            f"les 4 types d'offre sont couverts)."))
