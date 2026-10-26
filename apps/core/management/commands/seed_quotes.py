"""Crée un jeu de demandes de devis de démonstration COUVRANT TOUS LES SCÉNARIOS possibles (les 6 statuts
du workflow × les 4 types d'offre, + quelques cas particuliers — convention organisation, pièce jointe
permis, plusieurs catégories à ajouter), pour simuler le parcours complet côté candidat (« Mes demandes »,
QuoteWizard) et côté secrétariat (« Devis candidats », resources.jsx) sans avoir à déposer de vraies
demandes à la main.

    python manage.py seed_quotes

Idempotent : update_or_create par (school, last_name, first_name, offer). Nécessite au préalable
seed_demo (auto-école) et, pour les scénarios de recyclage, seed_recycling_sessions (catalogue de modules/
forfaits).
"""
from django.core.management.base import BaseCommand

from apps.admissions.models import IndividualQuote, RecyclingItem
from apps.organizations.models import Organization
from apps.schools.models import School

# Un scénario par (offre, statut) — 24 au total — plus quelques variantes (convention, pièce jointe,
# extension à plusieurs catégories) pour couvrir les cas particuliers de l'affichage admin/candidat.
ROWS = [
    # ───────────────────────── Nouveau permis ─────────────────────────
    dict(offer="new_license", id_document_no="CI0100000001", last_name="Kone", first_name="Ibrahim", phone="0700000101",
         email="ibrahim.kone@example.ci", residence="Yopougon", id_document_type="cni", categories_requested=["B"],
         status="submitted"),
    dict(offer="new_license", id_document_no="CI0100000002", last_name="Toure", first_name="Aminata", phone="0700000201",
         email="aminata.toure@example.ci", residence="Adjame", id_document_type="passport", categories_requested=["A"],
         status="correction_requested",
         correction_note="La photo de votre pièce d'identité est illisible. Merci de la renvoyer plus nette."),
    dict(offer="new_license", id_document_no="CI0100000003", last_name="Silue", first_name="Bakary", phone="0700000301",
         email="bakary.silue@example.ci", residence="Williamsville", id_document_type="cni_foreign", categories_requested=["B"],
         status="rejected", reject_reason="Pièce d'identité déjà utilisée pour un autre dossier enregistré."),
    dict(offer="new_license", id_document_no="CI0198765432", last_name="Bamba", first_name="Awa", phone="0700000105",
         email="awa.bamba@example.ci", residence="Koumassi", id_document_type="cni", categories_requested=["A"],
         status="approved", base_price=150000),
    dict(offer="new_license", id_document_no="CI0100000005", last_name="Coulibaly", first_name="Moussa", phone="0700000501",
         email="moussa.coulibaly@example.ci", residence="Port-Bouet", id_document_type="cni", categories_requested=["B", "A"],
         status="quoted", base_price=150000, negotiated_price=135000),
    dict(offer="new_license", id_document_no="CI0100000006", last_name="Yao", first_name="Grace", phone="0700000601",
         email="grace.yao@example.ci", residence="Cocody", id_document_type="cni", categories_requested=["B"],
         status="accepted", base_price=150000, negotiated_price=150000, paid_amount=75000),

    # ───────────────────────── Extension de catégorie ─────────────────────────
    dict(offer="extension", id_document_no="22CI100001", last_name="Diaby", first_name="Fanta", phone="0700000102",
         email="fanta.diaby@example.ci", residence="Cocody", id_document_type="driver_license", license_no="PC-100001",
         categories_held=["B"], categories_expiry={}, categories_to_add=["A"], status="submitted"),
    dict(offer="extension", id_document_no="22CI998877", last_name="Kouassi", first_name="Yves", phone="0700000106",
         email="yves.kouassi@example.ci", residence="Treichville", id_document_type="passport", license_no="PC-220099",
         categories_held=["A"], categories_expiry={}, categories_to_add=["B"], status="correction_requested",
         correction_note="Veuillez renseigner le type et le numéro de la pièce d'identité utilisée pour votre précédent permis."),
    dict(offer="extension", id_document_no="22CI100003", last_name="Ngatta", first_name="Paul", phone="0700000302",
         email="paul.ngatta@example.ci", residence="Yopougon", id_document_type="cni", license_no="PC-100003",
         categories_held=["B"], categories_expiry={}, categories_to_add=["C"], status="rejected",
         reject_reason="Catégorie C non accessible : permis B détenu depuis moins de 2 ans."),
    dict(offer="extension", id_document_no="22CI445566", last_name="Diallo", first_name="Mariam", phone="0700000102",
         email="mariam.diallo@example.ci", residence="Cocody", id_document_type="driver_license", license_no="PC-778812",
         categories_held=["B"], categories_expiry={}, categories_to_add=["C", "D"], status="approved"),
    dict(offer="extension", id_document_no="22CI100005", last_name="Zadi", first_name="Chantal", phone="0700000502",
         email="chantal.zadi@example.ci", residence="Marcory", id_document_type="cni", license_no="PC-100005",
         categories_held=["B"], categories_expiry={"C": "2027-06-01"}, categories_to_add=["C"], status="quoted",
         base_price=40000, negotiated_price=40000),
    dict(offer="extension", id_document_no="22CI100006", last_name="Brou", first_name="Kevin", phone="0700000602",
         email="kevin.brou@example.ci", residence="Bingerville", id_document_type="cni", license_no="PC-100006",
         categories_held=["A"], categories_expiry={}, categories_to_add=["B"], status="accepted",
         base_price=40000, negotiated_price=40000, paid_amount=40000),

    # ───────────────────────── Recyclage théorique (modules du catalogue) ─────────────────────────
    dict(offer="theory_refresh", id_document_no="22CI200001", last_name="Kacou", first_name="Edwige", phone="0700000103",
         email="edwige.kacou@example.ci", residence="Marcory", id_document_type="id_attestation", license_no="PC-200001",
         status="submitted", _items=["Signalisation"]),
    dict(offer="theory_refresh", id_document_no="22CI200002", last_name="Gnahore", first_name="Serge", phone="0700000203",
         email="serge.gnahore@example.ci", residence="Yopougon", id_document_type="cni", license_no="PC-200002",
         status="correction_requested", correction_note="Le numéro de permis renseigné ne correspond à aucun format valide.",
         _items=["La conduite"]),
    dict(offer="theory_refresh", id_document_no="22CI200003", last_name="Assale", first_name="Nadege", phone="0700000303",
         email="nadege.assale@example.ci", residence="Abobo", id_document_type="cni", license_no="PC-200003",
         status="rejected", reject_reason="Permis non retrouvé dans la base : merci de vous rapprocher du secrétariat.",
         _items=["Le conducteur"]),
    dict(offer="theory_refresh", id_document_no="22CI200004", last_name="Kragbe", first_name="Herve", phone="0700000403",
         email="herve.kragbe@example.ci", residence="Treichville", id_document_type="driver_license", license_no="PC-200004",
         status="approved", _items=["Le véhicule", "Les permis"]),
    dict(offer="theory_refresh", id_document_no="22CI114455", last_name="Ouattara", first_name="Seydou", phone="0700000104",
         email="seydou.ouattara@example.ci", residence="Marcory", id_document_type="id_attestation", license_no="PC-114455",
         status="quoted", base_price=50000, negotiated_price=45000, _items=["Signalisation", "La conduite"]),
    dict(offer="theory_refresh", id_document_no="22CI200006", last_name="Angoran", first_name="Linda", phone="0700000603",
         email="linda.angoran@example.ci", residence="Cocody", id_document_type="cni", license_no="PC-200006",
         status="accepted", base_price=25000, negotiated_price=25000, paid_amount=25000, _items=["Signalisation"]),

    # ───────────────────────── Recyclage pratique (forfaits de séances du catalogue) ─────────────────────────
    dict(offer="practical_refresh", id_document_no="22CI330021", last_name="Traore", first_name="Fatou", phone="0700000104",
         email="fatou.traore@example.ci", residence="Abobo", id_document_type="resident_card", license_no="PC-330021",
         status="submitted", _items=["Recyclage pratique — Signalisation"]),
    dict(offer="practical_refresh", id_document_no="22CI300002", last_name="Soro", first_name="Aboubakar", phone="0700000204",
         email="aboubakar.soro@example.ci", residence="Yopougon", id_document_type="cni", license_no="PC-300002",
         status="correction_requested", correction_note="Merci de joindre une photo lisible du recto et du verso de votre permis.",
         _items=["Recyclage pratique — La conduite"]),
    dict(offer="practical_refresh", id_document_no="22CI300003", last_name="Dosso", first_name="Rokia", phone="0700000304",
         email="rokia.dosso@example.ci", residence="Marcory", id_document_type="cni", license_no="PC-300003",
         status="rejected", reject_reason="Permis suspendu : recyclage pratique impossible tant que la suspension est en cours.",
         _items=["Recyclage pratique — Le conducteur"]),
    dict(offer="practical_refresh", id_document_no="22CI300004", last_name="Beugre", first_name="Olivier", phone="0700000404",
         email="olivier.beugre@example.ci", residence="Cocody", id_document_type="driver_license", license_no="PC-300004",
         status="approved", _items=["Recyclage pratique — Le véhicule"]),
    dict(offer="practical_refresh", id_document_no="22CI300005", last_name="Yapi", first_name="Solange", phone="0700000504",
         email="solange.yapi@example.ci", residence="Treichville", id_document_type="cni", license_no="PC-300005",
         status="quoted", base_price=25000, negotiated_price=25000, _items=["Recyclage pratique — Les permis"]),
    dict(offer="practical_refresh", id_document_no="22CI300006", last_name="Niamke", first_name="Josephine", phone="0700000604",
         email="josephine.niamke@example.ci", residence="Bingerville", id_document_type="cni", license_no="PC-300006",
         status="accepted", base_price=50000, negotiated_price=50000, paid_amount=20000,
         _items=["Recyclage pratique — Signalisation"]),
]

# Candidats rattachés à une organisation (convention) : la saisie de paiement individuel est désactivée
# côté admin et le candidat bénéficie de l'accès complet prévu par la convention (cf. IndividualQuote.organization).
ORG_ROWS = [
    dict(offer="new_license", id_document_no="22CI400001", last_name="Kamara", first_name="Issiaka", phone="0700000701",
         email="issiaka.kamara@example.ci", residence="Yopougon", id_document_type="cni", categories_requested=["B"],
         status="approved"),
    dict(offer="theory_refresh", id_document_no="22CI400002", last_name="Doumbia", first_name="Aicha", phone="0700000702",
         email="aicha.doumbia@example.ci", residence="Abobo", id_document_type="cni", license_no="PC-400002",
         status="quoted", base_price=25000, negotiated_price=25000, _items=["Signalisation"]),
]


class Command(BaseCommand):
    help = ("Crée/actualise un jeu complet de demandes de devis de démonstration — les 6 statuts du "
            "workflow pour chacune des 4 offres, plus quelques cas particuliers (convention organisation) "
            "— pour simuler le parcours candidat et secrétariat de bout en bout. Idempotent.")

    def handle(self, *args, **opts):
        school = School.objects.first()
        if not school:
            return self.stderr.write("Aucune auto-école : lancez d'abord seed_demo.")

        catalogue = {i.label: i for i in RecyclingItem.objects.filter(school=school)}
        organization = Organization.objects.filter(school=school).first()

        all_rows = list(ROWS)
        if organization:
            for row in ORG_ROWS:
                all_rows.append({**row, "organization": organization})
        elif ORG_ROWS:
            self.stdout.write(self.style.WARNING(
                "Aucune organisation trouvée : scénarios « convention » ignorés (lancez d'abord seed_demo "
                "avec une organisation, ou créez-en une depuis l'admin)."))

        created, updated, missing_items = 0, 0, set()
        for row in all_rows:
            r = dict(row)
            item_labels = r.pop("_items", [])
            q, is_new = IndividualQuote.objects.update_or_create(
                school=school, last_name=r["last_name"], first_name=r["first_name"], offer=r["offer"], defaults=r,
            )
            if item_labels:
                items = [catalogue[label] for label in item_labels if label in catalogue]
                q.recycling_items.set(items)
                missing_items |= set(item_labels) - set(catalogue)
            created += 1 if is_new else 0
            updated += 0 if is_new else 1

        self.stdout.write(self.style.SUCCESS(
            f"{created} demande(s) de devis créée(s), {updated} mise(s) à jour ({len(all_rows)} au total : "
            f"les 6 statuts × les 4 types d'offre, + convention organisation si disponible)."))
        if missing_items:
            self.stdout.write(self.style.WARNING(
                "Module(s)/forfait(s) introuvable(s) dans le catalogue (lancez d'abord seed_recycling_sessions) : "
                + ", ".join(sorted(missing_items))))
