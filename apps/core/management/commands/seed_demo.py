from datetime import date, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Expense
from apps.billing.services import generate_contract_invoices
from apps.learners.models import Learner
from apps.organizations.models import Cohort, Contract, Organization
from apps.pedagogy.models import Choice, Course, Question, Quiz
from apps.practice.models import Instructor, Lesson, Room, Vehicle
from apps.schools.models import Agency, Plan, School, Subscription, Training

PASSWORD = "Akwaba@2026"

# code, thème, type, énoncé, propositions, bonne(s) réponse(s), explication
QUESTIONS = [
    ("Q001", "signs", "single", "Que signifie un panneau triangulaire à bordure rouge ?", ["Interdiction", "Danger", "Obligation", "Indication"], "B", "Les panneaux triangulaires à bordure rouge signalent un danger."),
    ("Q002", "signs", "single", "Un panneau rond à fond bleu indique généralement :", ["Un danger", "Une obligation", "Une fin d'interdiction", "Un stationnement payant"], "B", "Le fond bleu rond correspond à une obligation."),
    ("Q003", "signs", "tf", "Un panneau STOP impose de marquer un arrêt complet.", ["Vrai", "Faux"], "Vrai", "Le STOP impose l'arrêt absolu, même si la voie est libre."),
    ("Q004", "priority", "tf", "À une intersection sans signalisation, la priorité est à droite.", ["Vrai", "Faux"], "Vrai", "C'est la règle de la priorité à droite."),
    ("Q005", "priority", "single", "Dans un rond-point sans signalisation particulière, qui a la priorité ?", ["Celui qui entre", "Celui qui est déjà engagé", "Le plus rapide", "Le véhicule le plus gros"], "B", "Les véhicules engagés dans le giratoire sont prioritaires."),
    ("Q006", "safety", "multi", "Quels équipements sont obligatoires dans un véhicule ?", ["Triangle de présignalisation", "Autoradio", "Gilet de sécurité", "Extincteur de salon"], "A,C", "Triangle et gilet de sécurité sont obligatoires."),
    ("Q007", "safety", "tf", "La ceinture de sécurité est obligatoire à toutes les places.", ["Vrai", "Faux"], "Vrai", "Elle est obligatoire pour tous les occupants."),
    ("Q008", "safety", "single", "La distance de sécurité doit permettre :", ["De doubler facilement", "De s'arrêter sans heurter le véhicule devant", "De klaxonner", "D'accélérer"], "B", "Elle permet d'éviter la collision en cas de freinage."),
    ("Q009", "regulation", "single", "En agglomération, la vitesse maximale autorisée est en principe de :", ["30 km/h", "50 km/h", "70 km/h", "90 km/h"], "B", "50 km/h sauf indication contraire."),
    ("Q010", "regulation", "tf", "Le téléphone tenu à la main est autorisé pendant la conduite.", ["Vrai", "Faux"], "Faux", "L'usage du téléphone tenu en main est interdit."),
    ("Q011", "regulation", "multi", "Quels documents doivent être présentés lors d'un contrôle ?", ["Permis de conduire", "Carte grise", "Attestation d'assurance", "Carnet de santé"], "A,B,C", "Permis, carte grise et assurance."),
    ("Q012", "mechanics", "single", "Le témoin d'huile allumé en roulant signifie :", ["Le niveau de carburant est bas", "Une pression d'huile insuffisante", "Les phares sont allumés", "Le frein à main est serré"], "B", "Arrêtez-vous rapidement pour éviter la casse moteur."),
    ("Q013", "mechanics", "single", "Quelle est la profondeur minimale légale des sculptures d'un pneu ?", ["0,5 mm", "1,6 mm", "3 mm", "5 mm"], "B", "1,6 mm est le minimum légal."),
    ("Q014", "behavior", "tf", "L'alcool diminue les réflexes et le champ visuel.", ["Vrai", "Faux"], "Vrai", "Même à faible dose, l'alcool altère la conduite."),
    ("Q015", "behavior", "multi", "Quels facteurs augmentent le risque d'accident ?", ["Fatigue", "Vitesse excessive", "Respect des distances", "Somnolence"], "A,B,D", "Fatigue, vitesse et somnolence sont des facteurs majeurs."),
    ("Q016", "defensive", "single", "Conduire de manière préventive, c'est :", ["Anticiper les comportements des autres usagers", "Rouler vite pour dégager la route", "Ne jamais freiner", "Suivre de près"], "A", "L'anticipation réduit les risques."),
    ("Q017", "defensive", "tf", "Sous la pluie, il faut augmenter les distances de sécurité.", ["Vrai", "Faux"], "Vrai", "La distance de freinage est allongée sur chaussée mouillée."),
    ("Q018", "firstaid", "single", "Face à un accident, quelle est la première action ?", ["Déplacer les blessés", "Protéger et alerter", "Donner à boire", "Partir"], "B", "Protéger, alerter, puis secourir."),
    ("Q019", "firstaid", "tf", "Il faut toujours retirer le casque d'un motard blessé.", ["Vrai", "Faux"], "Faux", "On ne retire le casque qu'en cas de nécessité vitale, par des personnes formées."),
    ("Q020", "code", "single", "Le feu orange fixe signifie :", ["Passer vite", "S'arrêter sauf si l'arrêt est dangereux", "Accélérer", "Priorité"], "B", "Il faut s'arrêter sauf si le freinage est dangereux."),
    ("Q021", "code", "single", "Le dépassement est interdit :", ["En ligne droite", "Avant un sommet de côte sans visibilité", "Sur route à 2 voies", "De jour"], "B", "Sans visibilité suffisante, le dépassement est interdit."),
    ("Q022", "code", "tf", "Le clignotant doit être mis avant de changer de direction.", ["Vrai", "Faux"], "Vrai", "Il signale la manœuvre suffisamment tôt."),
    ("Q023", "signs", "single", "Une ligne continue au centre de la chaussée signifie :", ["Dépassement autorisé", "Interdiction de la franchir", "Zone piétonne", "Stationnement"], "B", "La ligne continue ne se franchit pas."),
    ("Q024", "priority", "multi", "Quels usagers sont prioritaires ?", ["Ambulance en intervention", "Véhicule de pompiers en intervention", "Taxi", "Bus de tourisme"], "A,B", "Les véhicules d'urgence avec avertisseurs sont prioritaires."),
    ("Q025", "safety", "single", "Le rétroviseur intérieur doit être réglé :", ["Avant de démarrer", "Après 10 km", "Jamais", "En roulant"], "A", "Réglez les rétroviseurs à l'arrêt, avant de partir."),
    ("Q026", "regulation", "tf", "Le permis B autorise la conduite d'un camion de 12 tonnes.", ["Vrai", "Faux"], "Faux", "Le permis B est limité aux véhicules de 3,5 t maximum."),
    ("Q027", "mechanics", "single", "Le rôle des freins ABS est :", ["Augmenter la vitesse", "Éviter le blocage des roues au freinage", "Économiser le carburant", "Chauffer le moteur"], "B", "L'ABS conserve la maniabilité pendant le freinage."),
    ("Q028", "behavior", "single", "Face à un usager agressif, il faut :", ["Répondre par des appels de phares", "Rester calme et ne pas réagir", "Le bloquer", "Le suivre"], "B", "Garder son calme évite l'escalade."),
    ("Q029", "firstaid", "multi", "Que faut-il faire devant une hémorragie externe ?", ["Comprimer la plaie", "Alerter les secours", "Laisser saigner", "Donner de l'alcool"], "A,B", "Comprimer directement et alerter."),
    ("Q030", "code", "tf", "Il est permis de stationner devant une sortie de garage.", ["Vrai", "Faux"], "Faux", "Le stationnement gênant est interdit."),
]


class Command(BaseCommand):
    help = "Crée des données de démonstration (comptes, banque de questions, cohorte, factures...)."

    @transaction.atomic
    def handle(self, *args, **opts):
        today = timezone.localdate()
        call_command("seed_plans")
        User.objects.filter(email="admin@ae-akwabatreich.com").exists() or User.objects.create_user(
            "admin@ae-akwabatreich.com", PASSWORD, first_name="Admin", last_name="Akwaba", role="akwaba_admin", is_staff=True, is_superuser=True,
            email_verified=True)

        school, created = School.objects.get_or_create(legal_name="Akwaba Auto-École Treichville SARL", defaults=dict(
            commercial_name="Akwaba Auto-École", registration_no="CI-ABJ-2024-B-00123", address="Rue 12, Treichville, Abidjan",
            phone="+2250700000000", email="contact@ae-akwabatreich.com", manager_name="Kouamé Yao", categories=["A", "B", "C"],
            opening_hours="Lun-Sam 07h30-18h00", pass_threshold=70, signatory_name="Kouamé Yao"))
        if not created:
            self.stdout.write("Données de démo déjà présentes.")
            return
        Subscription.objects.create(school=school, plan=Plan.objects.get(name="Standard"), start_date=today,
                                    end_date=today + timedelta(days=365), amount_paid=720000)
        agency = Agency.objects.create(school=school, name="Agence Treichville", address="Treichville", manager_name="Kouamé Yao")
        Agency.objects.create(school=school, name="Agence Cocody", address="Cocody Angré")

        def mk(email, role, first, last, **kw):
            return User.objects.create_user(email, PASSWORD, first_name=first, last_name=last, role=role, school=school,
                                            email_verified=True, **kw)
        mk("directeur@ae-akwabatreich.com", "director", "Kouamé", "Yao", agency=agency)
        mk("secretaire@ae-akwabatreich.com", "secretary", "Aïcha", "Traoré", agency=agency)
        mk("comptable@ae-akwabatreich.com", "accountant", "Marc", "Bamba", agency=agency)

        training_b = Training.objects.create(school=school, category="B", name="Permis B - Formation complète", theory_hours=20,
                                             practical_hours=20, duration_days=60, price=250000, program="Code + conduite",
                                             validation_conditions="Examen final théorique >= 70 %")
        Training.objects.create(school=school, category="A", name="Permis A - Moto", theory_hours=15, practical_hours=10,
                                duration_days=45, price=150000)
        Training.objects.create(school=school, category="C", name="Permis C - Poids lourds", theory_hours=30, practical_hours=25,
                                duration_days=90, price=450000)

        # Cours (la banque QCM se charge par import Excel : docs/qcm_code_de_la_route.xlsx)
        Course.objects.create(school=school, training=training_b, theme="signs", title="La signalisation routière", order=1,
                              content="Panneaux de danger, d'interdiction, d'obligation et d'indication.")
        Course.objects.create(school=school, training=training_b, theme="priority", title="Les priorités", order=2,
                              content="Priorité à droite, ronds-points, véhicules prioritaires.")

        # Personnel roulant
        instr_user = mk("moniteur@ae-akwabatreich.com", "instructor", "Ismaël", "Koné", agency=agency)
        instructor = Instructor.objects.create(user=instr_user, school=school, agency=agency, first_name="Ismaël", last_name="Koné",
                                               phone="+2250701010101", email="moniteur@ae-akwabatreich.com", categories=["B"], hourly_rate=3000)
        vehicle = Vehicle.objects.create(school=school, agency=agency, plate="1234 AB 01", brand="Toyota", model="Yaris", year=2021,
                                         category="B", mileage=42000, insurance_expiry=today + timedelta(days=200),
                                         technical_visit_expiry=today + timedelta(days=20), instructor=instructor)
        room = Room.objects.create(school=school, agency=agency, name="Salle de code 1", capacity=25)
        Expense.objects.create(school=school, agency=agency, category="fuel", amount=45000, date=today, vehicle=vehicle, description="Plein")
        Expense.objects.create(school=school, agency=agency, category="rent", amount=300000, date=today, description="Loyer du mois")

        # Apprenant particulier
        lu = mk("apprenant@ae-akwabatreich.com", "learner", "Awa", "Kouassi")
        learner = Learner.objects.create(user=lu, school=school, agency=agency, training=training_b, first_name="Awa",
                                         last_name="Kouassi", email="apprenant@ae-akwabatreich.com", phone="+2250702020202", category="B",
                                         status="in_training", sex="F", birth_date=date(2000, 5, 12))
        start = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
        Lesson.objects.create(school=school, kind="practical", learner=learner, instructor=instructor, vehicle=vehicle,
                              start=start, end=start + timedelta(hours=1), location="Circuit Treichville")
        Lesson.objects.create(school=school, kind="theory", room=room, instructor=instructor, title="Cours de code - signalisation",
                              start=start + timedelta(days=1), end=start + timedelta(days=1, hours=2))

        # Organisation + contrat + cohorte
        org = Organization.objects.create(school=school, name="Entreprise ABC", org_type="company", contact_name="Mme Diallo",
                                          phone="+2250703030303", email="rh.abc@ae-akwabatreich.com")
        User.objects.create_user("rh.abc@ae-akwabatreich.com", PASSWORD, first_name="Fatou", last_name="Diallo", role="hr", school=school,
                                 organization=org, email_verified=True)
        User.objects.create_user("admin.abc@ae-akwabatreich.com", PASSWORD, first_name="Jean", last_name="Aka", role="org_admin", school=school,
                                 organization=org, email_verified=True)
        contract = Contract.objects.create(school=school, organization=org, training=training_b, reference="CT-ABC-2026-01",
                                           category="B", beneficiaries_count=3, unit_price=250000, organization_contribution=150000,
                                           installments_count=4, status="active", start_date=today,
                                           end_date=today + timedelta(days=90))
        cohort = Cohort.objects.create(school=school, agency=agency, organization=org, contract=contract, training=training_b,
                                       name="Cohorte Permis B - Entreprise ABC - Septembre 2026", start_date=today,
                                       end_date=today + timedelta(days=60), capacity=20, location="Treichville", status="running")
        cohort.instructors.add(instructor)
        for last, first in [("Konan", "Yves"), ("Diabaté", "Salif"), ("N'Guessan", "Clarisse")]:
            Learner.objects.create(school=school, agency=agency, organization=org, cohort=cohort, training=training_b,
                                   last_name=last, first_name=first, category="B", source="organization", status="registered",
                                   employee_ref=f"ABC-{last[:3].upper()}")
        generate_contract_invoices(contract, today + timedelta(days=30))
        self.stdout.write(self.style.SUCCESS(f"Démo créée. Mot de passe commun : {PASSWORD}"))
        for e in ["admin@ae-akwabatreich.com", "directeur@ae-akwabatreich.com", "secretaire@ae-akwabatreich.com", "comptable@ae-akwabatreich.com", "moniteur@ae-akwabatreich.com",
                  "apprenant@ae-akwabatreich.com", "rh.abc@ae-akwabatreich.com", "admin.abc@ae-akwabatreich.com"]:
            self.stdout.write("  " + e)
