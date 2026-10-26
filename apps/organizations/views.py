from datetime import date, timedelta

from django.db import transaction
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core import audit
from apps.core.permissions import ORG_ADMIN, ORG_ROLES
from apps.core.viewsets import SCHOOL, BaseModelSerializer, ScopedModelViewSet, make_serializer
from apps.learners.models import Learner

from .models import Cohort, Contract, Group, Organization, QuoteRequest, resolve_join_code

OrganizationSerializer = make_serializer(Organization, extra_fields={
    "learners_count": serializers.SerializerMethodField(),
    "get_learners_count": lambda self, o: o.learners.count()})
GroupSerializer = make_serializer(Group, extra_fields={
    "learners_count": serializers.SerializerMethodField(),
    "get_learners_count": lambda self, o: o.learners.count()})


class OrganizationViewSet(ScopedModelViewSet):
    resource = "organizations"
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    org_lookup = "id"
    filterset_fields = ["org_type", "is_active", "school"]
    search_fields = ["name", "contact_name", "email"]


class ContractSerializer(BaseModelSerializer):
    net_price = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)
    learner_contribution = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)
    organization_total = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    training_name = serializers.CharField(source="training.name", read_only=True)

    class Meta:
        model = Contract
        fields = "__all__"

    def validate(self, attrs):
        org = attrs.get("organization") or getattr(self.instance, "organization", None)
        training = attrs.get("training") or getattr(self.instance, "training", None)
        if org and training and org.school_id != training.school_id:
            raise serializers.ValidationError("L'organisation et la formation doivent relever de la même auto-école.")
        price = attrs.get("unit_price", getattr(self.instance, "unit_price", 0))
        contrib = attrs.get("organization_contribution", getattr(self.instance, "organization_contribution", 0))
        discount = attrs.get("discount_percent", getattr(self.instance, "discount_percent", 0))
        net = price * (100 - discount) / 100
        if contrib > net:
            raise serializers.ValidationError({"organization_contribution": "La contribution dépasse le prix net."})
        return attrs


class ContractViewSet(ScopedModelViewSet):
    resource = "contracts"
    queryset = Contract.objects.select_related("organization", "training")
    serializer_class = ContractSerializer
    org_lookup = "organization"
    action_verbs = {"generate_invoices": "create"}
    filterset_fields = ["status", "organization", "training", "school"]
    search_fields = ["reference", "organization__name"]

    @action(detail=True, methods=["post"], url_path="generate-invoices")
    def generate_invoices(self, request, pk=None):
        """Facture l'organisation (sa contribution) et chaque bénéficiaire (part apprenant, en échéances)."""
        from apps.billing.services import generate_contract_invoices
        contract = self.get_object()
        first_due = request.data.get("first_due_date")
        first_due = date.fromisoformat(first_due) if first_due else date.today() + timedelta(days=30)
        result = generate_contract_invoices(contract, first_due)
        audit.log(request, "generate_invoices", contract, new=result)
        return Response(result, status=201)


class CohortSerializer(BaseModelSerializer):
    learners_count = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)
    training_name = serializers.CharField(source="training.name", read_only=True)
    subscription = serializers.SerializerMethodField()
    # Lecture seule : généré automatiquement (Cohort.save) et modifiable uniquement via l'action dédiée
    # /cohorts/{id}/regenerate-code/ — exposé ici pour que le sélecteur de cohorte du formulaire admin
    # (« Nouvel utilisateur », import Excel) puisse l'afficher une fois la cohorte choisie (§B.3).
    join_code = serializers.CharField(read_only=True)

    class Meta:
        model = Cohort
        fields = "__all__"

    def get_learners_count(self, c):
        return c.learners.count()

    def get_subscription(self, c):
        """Plan de l'entreprise qui couvre cette cohorte (bénéficiaires => accès)."""
        from django.utils import timezone
        sub = (c.subscriptions.filter(status__in=["active", "suspended"], end_date__gte=timezone.localdate())
               .select_related("plan").order_by("-status", "end_date").first())
        if not sub:
            return None
        return {"plan_name": sub.plan.name, "status": sub.status, "end_date": sub.end_date, "seats": sub.seats,
                "reason": sub.suspension_reason}

    def validate(self, attrs):
        s, e = attrs.get("start_date"), attrs.get("end_date")
        if s and e and e < s:
            raise serializers.ValidationError({"end_date": "La fin doit suivre le début."})
        return attrs


def _seat_ok(cohort):
    from rest_framework.exceptions import ValidationError
    from apps.subscriptions.services import check_cohort_seat
    try:
        check_cohort_seat(cohort)
        return True
    except ValidationError:
        return False


HEADERS = {"nom": "last_name", "last_name": "last_name", "prenom": "first_name", "prénom": "first_name",
           "first_name": "first_name", "matricule": "employee_ref", "telephone": "phone", "téléphone": "phone",
           "phone": "phone", "email": "email", "e-mail": "email", "mail": "email"}


class CohortViewSet(ScopedModelViewSet):
    resource = "cohorts"
    queryset = Cohort.objects.select_related("organization", "training").prefetch_related("learners")
    serializer_class = CohortSerializer
    org_lookup = "organization"
    learner_lookup = "learners__user"
    instructor_lookup = "instructors__user"
    limit_key = "cohorts"
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_verbs = {"import_learners": "create", "import_template": "view", "stats": "view", "regenerate_code": "change"}
    filterset_fields = ["status", "organization", "training", "agency", "school"]
    search_fields = ["name", "location"]

    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["Nom", "Prénom", "Matricule", "Téléphone", "E-mail"])
        ws.append(["KOUASSI", "Awa", "EMP-001", "0700000000", "awa@exemple.ci"])
        resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = 'attachment; filename="modele_import_apprenants.xlsx"'
        wb.save(resp)
        return resp

    @action(detail=True, methods=["post"], url_path="import-learners", parser_classes=[MultiPartParser])
    def import_learners(self, request, pk=None):
        from openpyxl import load_workbook

        from apps.accounts.models import User
        from apps.accounts.services import gen_password
        from apps.core.permissions import LEARNER
        from apps.schools.services import check_limit

        def send_credentials(user, password):
            # Même circuit d'envoi que les devis, gabarit éditable depuis l'admin partagé avec les 2 autres
            # points de création de compte (cf. apps.admissions.services.send_account_created_credentials :
            # MessageTemplate key="account_created", unifié pour ne pas dupliquer ce texte 3 fois).
            # §B.1 — la cohorte est fixe pour tout l'import : le code d'adhésion est transmis avec les
            # identifiants, requis à la première connexion (cf. LoginView.post).
            from apps.admissions.services import send_account_created_credentials
            send_account_created_credentials(user, password, school_id=cohort.school_id, cohort=cohort)

        cohort = self.get_object()
        f = request.FILES.get("file")
        if not f:
            return Response({"file": "Fichier requis."}, status=400)
        try:
            ws = load_workbook(f, read_only=True, data_only=True).active
            rows = list(ws.iter_rows(values_only=True))
        except Exception:
            return Response({"file": "Fichier Excel illisible."}, status=400)
        if not rows:
            return Response({"file": "Fichier vide."}, status=400)
        header = [HEADERS.get(str(h or "").strip().lower()) for h in rows[0]]
        if "last_name" not in header or "first_name" not in header:
            return Response({"file": "Colonnes 'Nom' et 'Prénom' obligatoires."}, status=400)
        create_accounts = str(request.data.get("create_accounts", "")).lower() in ("1", "true", "on", "yes")
        created, accounts_created, errors = 0, 0, []
        used = cohort.learners.count()
        emails = set(Learner.objects.filter(school=cohort.school).exclude(email="").values_list("email", flat=True))
        refs = set(Learner.objects.filter(school=cohort.school, organization=cohort.organization)
                   .exclude(employee_ref="").values_list("employee_ref", flat=True))
        user_emails = set(User.objects.exclude(email="").values_list("email", flat=True))
        pending_credentials = []   # (user, mot de passe) : notifiés après le commit, pour ne jamais notifier sur une transaction annulée
        with transaction.atomic():
            for idx, row in enumerate(rows[1:], start=2):
                rec = {h: ("" if v is None else str(v).strip()) for h, v in zip(header, row) if h}
                if not any(rec.values()):
                    continue
                if not rec.get("last_name") or not rec.get("first_name"):
                    errors.append({"row": idx, "message": "Nom ou prénom manquant."})
                elif rec.get("email") and rec["email"].lower() in emails:
                    errors.append({"row": idx, "message": "E-mail déjà utilisé."})
                elif create_accounts and rec.get("email") and rec["email"].lower() in user_emails:
                    errors.append({"row": idx, "message": "E-mail déjà associé à un compte existant."})
                elif create_accounts and not rec.get("email"):
                    errors.append({"row": idx, "message": "E-mail requis pour créer un compte de connexion."})
                elif rec.get("employee_ref") and rec["employee_ref"] in refs:
                    errors.append({"row": idx, "message": "Matricule déjà importé."})
                elif used >= cohort.capacity:
                    errors.append({"row": idx, "message": "Capacité de la cohorte atteinte."})
                elif not _seat_ok(cohort):
                    errors.append({"row": idx, "message": "Toutes les places de l'abonnement sont utilisées."})
                else:
                    check_limit(cohort.school, "learners")
                    user = None
                    if create_accounts:
                        password = gen_password()
                        user = User.objects.create_user(
                            rec["email"].lower(), password, first_name=rec["first_name"], last_name=rec["last_name"],
                            phone=rec.get("phone", ""), role=LEARNER, school=cohort.school, organization=cohort.organization)
                        pending_credentials.append((user, password))
                        accounts_created += 1
                    Learner.objects.create(
                        user=user, school=cohort.school, organization=cohort.organization, cohort=cohort, training=cohort.training,
                        category=cohort.training.category, source="organization", status="registered", agency=cohort.agency,
                        email=rec.get("email", "").lower(), **{k: rec.get(k, "") for k in ("last_name", "first_name", "phone", "employee_ref")})
                    created += 1
                    used += 1
                    if rec.get("email"):
                        emails.add(rec["email"].lower())
                        user_emails.add(rec["email"].lower())
                    if rec.get("employee_ref"):
                        refs.add(rec["employee_ref"])
        for user, password in pending_credentials:
            try: send_credentials(user, password)
            except Exception: pass   # l'import ne doit jamais échouer à cause d'un envoi (email/WhatsApp mal configuré, etc.)
        audit.log(request, "import_learners", cohort, new={"created": created, "accounts_created": accounts_created, "errors": len(errors)})
        return Response({"created": created, "accounts_created": accounts_created, "errors": errors, "total": created + len(errors)})

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        from apps.reports.services import cohort_stats
        return Response(cohort_stats(self.get_object()))

    @action(detail=True, methods=["post"], url_path="regenerate-code")
    def regenerate_code(self, request, pk=None):
        """Régénère le code d'adhésion (ex. fuite, remplacement) : réservé au personnel (verbe « change »)."""
        cohort = self.get_object()
        old = cohort.join_code
        cohort.join_code = ""
        cohort.save()
        audit.log(request, "regenerate_join_code", cohort, old={"join_code": old}, new={"join_code": cohort.join_code})
        return Response({"join_code": cohort.join_code})


class GroupViewSet(ScopedModelViewSet):
    resource = "groups"
    queryset = Group.objects.select_related("cohort")
    serializer_class = GroupSerializer
    school_lookup = "cohort__school"
    org_lookup = "cohort__organization"
    learner_lookup = "learners__user"
    instructor_lookup = "instructor__user"
    filterset_fields = ["cohort"]

    def perform_create(self, serializer):
        cohort = serializer.validated_data["cohort"]
        u = self.request.user
        if u.role != "akwaba_admin" and cohort.school_id != u.school_id:
            raise serializers.ValidationError({"cohort": "Cohorte inaccessible."})
        instance = serializer.save()
        audit.log(self.request, "create", instance, new=self._snapshot(instance))


QuoteRequestSerializer = make_serializer(QuoteRequest, read_only=("status",))


class QuoteRequestAdminSerializer(BaseModelSerializer):
    class Meta:
        model = QuoteRequest
        fields = "__all__"


class QuoteRequestViewSet(ScopedModelViewSet):
    """Demandes de devis de la vitrine : traitées par l'équipe Akwaba uniquement."""
    resource = "quotes"
    queryset = QuoteRequest.objects.all()
    serializer_class = QuoteRequestAdminSerializer
    school_lookup = None
    http_method_names = ["get", "patch", "delete", "head", "options"]
    filterset_fields = ["status"]
    search_fields = ["contact_name", "contact_email", "formation_label"]

    def get_queryset(self):
        from apps.core.permissions import AKWABA_ADMIN
        qs = QuoteRequest.objects.all()
        return qs if self.request.user.role == AKWABA_ADMIN else qs.none()


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView


@api_view(["GET"])
@permission_classes([AllowAny])
def public_organizations(request):
    """§4.2 — liste des collectivités disposant d'une fiche d'engagement (visibles à l'inscription en ligne).
    Si une collectivité recherchée n'y figure pas, c'est qu'elle n'a pas encore de fiche enregistrée."""
    school_id = request.query_params.get("school")
    qs = Organization.objects.filter(is_active=True)
    if school_id:
        qs = qs.filter(school_id=school_id)
    return Response([{"id": o.id, "name": o.name, "org_type": o.org_type} for o in qs])


@api_view(["GET"])
@permission_classes([AllowAny])
def public_cohort_code(request, code):
    """Résolution publique d'un code d'adhésion cohorte (saisi à l'inscription en ligne), sans donnée sensible.

    Jugement : « valide » = cohorte « planned »/« running » (pas de littéral « active » dans Cohort.STATUS) et non
    complète (capacity=0 = illimité, même convention que OrganizationSubscription.seats). `category` reflète
    uniquement le contrat lié, le cas échéant (pas de repli sur la catégorie de la formation).
    """
    cohort, error = resolve_join_code(code)
    if cohort is None:
        return Response({"valid": False, "detail": error}, status=404)
    return Response({
        "valid": True,
        "organization_name": cohort.organization.name if cohort.organization_id else None,
        "cohort_name": cohort.name,
        "category": cohort.contract.category if cohort.contract_id else None,
    })


class PublicQuoteView(APIView):
    """POST public (sans compte) depuis la vitrine."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = QuoteRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        quote = ser.save()
        from apps.accounts.models import User
        from apps.core.notify import notify
        for admin in User.objects.filter(role="akwaba_admin", is_active=True):
            notify(admin, "quote_request", "Nouvelle demande de devis",
                   f"{quote.contact_name} - {quote.formation_label} ({quote.beneficiaries_count} bénéficiaires)")
        return Response({"detail": "Demande enregistrée."}, status=201)
