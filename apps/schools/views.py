from datetime import timedelta

from django.db.models import ProtectedError, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.models import User
from apps.core import audit
from apps.core.permissions import DIRECTOR
from apps.core.viewsets import SCHOOL, BaseModelSerializer, ScopedModelViewSet, make_serializer

from . import services
from .models import Agency, Plan, School, Subscription, Training

AgencySerializer = make_serializer(Agency)
TrainingSerializer = make_serializer(Training, extra_fields={
    "total_hours": serializers.IntegerField(read_only=True)})


class PlanSerializer(BaseModelSerializer):
    audience_label = serializers.CharField(source="get_audience_display", read_only=True)
    billing_cycle_label = serializers.CharField(source="get_billing_cycle_display", read_only=True)
    duration_days = serializers.IntegerField(read_only=True)
    school_name = serializers.CharField(source="school.__str__", read_only=True, default=None)
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)
    cohort_name = serializers.CharField(source="cohort.name", read_only=True, default=None)
    is_on_sale = serializers.BooleanField(read_only=True)
    subscribers = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = "__all__"

    def get_subscribers(self, plan):
        return plan.learner_subscriptions.filter(status="active").count() + plan.organization_subscriptions.filter(
            status="active").count() + plan.subscriptions.filter(status="active").count()

    def validate_features(self, v):
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise serializers.ValidationError("Liste de textes attendue.")
        return [x.strip() for x in v if x.strip()]

    def validate(self, attrs):
        user = self.context["request"].user
        g = lambda k, d=None: attrs.get(k, getattr(self.instance, k, d))
        if g("billing_cycle") == "custom" and not g("custom_days"):
            raise serializers.ValidationError({"custom_days": "Indiquez la durée de validité en jours."})
        if g("available_from") and g("available_until") and g("available_until") < g("available_from"):
            raise serializers.ValidationError({"available_until": "La fin de la période de vente doit suivre le début."})
        org, cohort = g("organization"), g("cohort")
        if (org or cohort) and g("audience", "school") != "organization":
            raise serializers.ValidationError({"organization": "Seuls les plans d'organisation peuvent être réservés à une entreprise / cohorte."})
        if cohort and org is None:
            attrs["organization"] = org = cohort.organization
        if cohort and org and cohort.organization_id != org.id:
            raise serializers.ValidationError({"cohort": "Cette cohorte n'appartient pas à l'entreprise choisie."})
        if org:
            if user.role != "akwaba_admin" and org.school_id != user.school_id:
                raise serializers.ValidationError({"organization": "Entreprise hors de votre auto-école."})
            attrs["school"] = org.school                      # un plan réservé appartient à l'auto-école de l'entreprise
        audience = attrs.get("audience", getattr(self.instance, "audience", "school"))
        if audience == "school" and user.role != "akwaba_admin":
            raise serializers.ValidationError({"audience": "Les plans SaaS des auto-écoles sont gérés par Akwaba."})
        if audience == "organization" and attrs.get("included_beneficiaries", getattr(self.instance, "included_beneficiaries", 0)) == 0 \
                and attrs.get("extra_beneficiary_price", getattr(self.instance, "extra_beneficiary_price", 0)) > 0:
            raise serializers.ValidationError({"included_beneficiaries": "Définissez des places incluses pour proposer des places supplémentaires."})
        return attrs

SubscriptionSerializer = make_serializer(Subscription, extra_fields={
    "school_name": serializers.CharField(source="school.__str__", read_only=True),
    "plan_name": serializers.CharField(source="plan.name", read_only=True)})


class SchoolSerializer(serializers.ModelSerializer):
    director_email = serializers.EmailField(write_only=True, required=False)
    director_password = serializers.CharField(write_only=True, required=False, min_length=8)
    director_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = School
        fields = "__all__"

    def validate_pass_threshold(self, v):
        if not 1 <= v <= 100:
            raise serializers.ValidationError("Le seuil doit être compris entre 1 et 100.")
        return v


class SchoolViewSet(ScopedModelViewSet):
    resource = "schools"
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    school_lookup = "id"
    org_lookup = "organizations"
    learner_lookup = SCHOOL
    instructor_lookup = SCHOOL
    search_fields = ["legal_name", "commercial_name", "registration_no"]
    filterset_fields = ["is_active"]

    def perform_create(self, serializer):
        d = serializer.validated_data
        email, pwd, name = d.pop("director_email", None), d.pop("director_password", None), d.pop("director_name", "")
        school = serializer.save()
        if email and pwd:
            first, _, last = (name or school.manager_name or "Directeur").partition(" ")
            User.objects.create_user(email, pwd, first_name=first, last_name=last or school.legal_name, role=DIRECTOR,
                                     school=school)
        audit.log(self.request, "create", school, new={"legal_name": school.legal_name})

    def perform_update(self, serializer):
        serializer.validated_data.pop("director_email", None)
        serializer.validated_data.pop("director_password", None)
        serializer.validated_data.pop("director_name", None)
        super().perform_update(serializer)

    @action(detail=True, methods=["get"])
    def usage(self, request, pk=None):
        return Response(services.usage(self.get_object()))


class AgencyViewSet(ScopedModelViewSet):
    resource = "agencies"
    queryset = Agency.objects.all()
    serializer_class = AgencySerializer
    limit_key = "agencies"
    learner_lookup = SCHOOL
    instructor_lookup = SCHOOL
    org_lookup = "school__organizations"
    filterset_fields = ["is_active", "school"]
    search_fields = ["name", "address"]


class TrainingViewSet(ScopedModelViewSet):
    resource = "trainings"
    queryset = Training.objects.all()
    serializer_class = TrainingSerializer
    learner_lookup = SCHOOL
    instructor_lookup = SCHOOL
    org_lookup = "school__organizations"
    filterset_fields = ["category", "is_active", "school"]
    search_fields = ["name", "program"]


class PlanViewSet(ScopedModelViewSet):
    """Plans d'abonnement : Akwaba (plans globaux + SaaS) et chaque auto-école (plans particuliers / organisations)."""
    resource = "plans"
    queryset = Plan.objects.select_related("school")
    serializer_class = PlanSerializer
    filterset_fields = ["audience", "is_active", "billing_cycle", "school"]
    search_fields = ["name", "description"]

    def get_queryset(self):
        u = self.request.user
        qs = Plan.objects.select_related("school")
        if u.role == "akwaba_admin":
            return qs
        own = Q(school=u.school) if u.school_id else Q(pk__in=[])
        if u.role == "director":
            return qs.filter(own | Q(school__isnull=True))
        if u.role in ("secretary", "accountant"):
            return qs.filter(own | Q(school__isnull=True), audience__in=["individual", "organization"])
        audience = "individual" if u.role == "learner" else "organization"
        qs = qs.filter(own | Q(school__isnull=True), audience=audience, is_active=True)
        if audience == "organization":
            qs = qs.filter(Q(organization__isnull=True) | Q(organization=u.organization_id))
        return qs

    def _guard(self, plan):
        u = self.request.user
        if u.role != "akwaba_admin" and (plan.school_id is None or plan.audience == "school"):
            raise PermissionDenied("Plan géré par Akwaba : lecture seule. Créez le vôtre pour votre auto-école.")

    def perform_update(self, serializer):
        self._guard(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._guard(instance)
        try:
            super().perform_destroy(instance)
        except ProtectedError:
            raise serializers.ValidationError({"detail": "Ce plan a des abonnements : désactivez-le au lieu de le supprimer."})


class SubscriptionViewSet(ScopedModelViewSet):
    resource = "subscriptions"
    queryset = Subscription.objects.select_related("school", "plan")
    serializer_class = SubscriptionSerializer
    filterset_fields = ["status", "school", "plan"]

    def perform_create(self, serializer):
        instance = serializer.save()
        audit.log(self.request, "create", instance, new=self._snapshot(instance))

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        sub = self.get_object()
        sub.status = "suspended"
        sub.save(update_fields=["status"])
        audit.log(request, "suspend", sub)
        return Response(self.get_serializer(sub).data)

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        sub = self.get_object()
        months = int(request.data.get("months", 1))
        sub.end_date = max(sub.end_date, timezone.localdate()) + timedelta(days=30 * months)
        sub.status = "active"
        sub.save(update_fields=["end_date", "status"])
        audit.log(request, "renew", sub)
        return Response(self.get_serializer(sub).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_schools(request):
    """Liste publique minimale pour l'inscription en ligne."""
    rows = []
    for s in School.objects.filter(is_active=True):
        rows.append({"id": s.id, "name": str(s), "address": s.address,
                     "trainings": [{"id": t.id, "name": t.name, "category": t.category, "price": t.price}
                                   for t in s.trainings.filter(is_active=True)]})
    return Response(rows)
