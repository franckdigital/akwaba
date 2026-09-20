import re

from django.conf import settings
from django.db.models import Max, Q
from django.http import FileResponse, Http404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core import audit
from apps.core.permissions import AKWABA_ADMIN, DIRECTOR, INSTRUCTOR, LEARNER, ORG_ADMIN, ORG_ROLES, SCHOOL_ROLES
from apps.core.viewsets import BaseModelSerializer, ScopedModelViewSet
from apps.learners.models import Learner
from apps.schools.models import Plan, Subscription
from apps.schools.views import PlanSerializer

from . import providers, services
from .models import LearnerSubscription, OrganizationSubscription, SubscriptionOrder


def frontend_base(request):
    """Origine réelle de l'application web (pour les URL de retour de paiement).

    Le front envoie son origine : sinon l'utilisateur, redirigé vers une autre origine (autre port), y perdrait sa session.
    Une origine n'est acceptée que si elle est autorisée (PUBLIC_WEB_URL, CORS, ou localhost en DEBUG).
    """
    o = (request.data.get("origin") or request.headers.get("Origin") or "").rstrip("/")
    ok = o and (o == settings.PUBLIC_WEB_URL.rstrip("/") or o in getattr(settings, "CORS_ALLOWED_ORIGINS", [])
                or (settings.DEBUG and re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", o)))
    return o if ok else settings.PUBLIC_WEB_URL


MANUAL = ("cash", "transfer", "other")


def _check_proof(f):
    if f is None:
        return
    if f.size > 5 * 1024 * 1024:
        raise serializers.ValidationError({"proof": "Fichier trop lourd (5 Mo max)."})
    if not ((f.content_type or "").startswith("image/") or f.content_type == "application/pdf"):
        raise serializers.ValidationError({"proof": "Image ou PDF uniquement."})


class OrderSerializer(serializers.ModelSerializer):
    has_proof = serializers.SerializerMethodField()
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    learner_name = serializers.CharField(source="learner.full_name", read_only=True, default=None)
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)
    school_name = serializers.CharField(source="school.__str__", read_only=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = SubscriptionOrder
        exclude = ["raw_payload", "created_by", "proof"]

    def get_has_proof(self, o):
        return bool(o.proof)


class OrderViewSet(ScopedModelViewSet):
    resource = "subscription_orders"
    queryset = SubscriptionOrder.objects.select_related("plan", "learner", "organization", "school", "invoice")
    serializer_class = OrderSerializer
    org_lookup = "organization"
    learner_lookup = "learner__user"
    http_method_names = ["get", "post", "head", "options"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_verbs = {"verify": "view", "mock_confirm": "create", "cancel": "create", "grant": "administer", "proof": "view"}
    filterset_fields = ["status", "audience", "plan", "learner", "organization", "school"]
    search_fields = ["provider_ref", "plan__name", "learner__last_name", "organization__name"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role not in (AKWABA_ADMIN, DIRECTOR):
            qs = qs.exclude(audience="school")
        return qs

    def create(self, request, *args, **kwargs):
        """Checkout : crée la commande puis lance le paiement CinetPay (ou l'encaissement manuel du personnel)."""
        d = request.data
        plan = Plan.objects.filter(pk=d.get("plan")).first()
        if not plan:
            return Response({"plan": "Plan introuvable."}, status=400)
        method = d.get("method") or "cinetpay"
        proof = request.FILES.get("proof")
        if method in MANUAL:
            if request.user.role in (LEARNER, ORG_ADMIN):
                raise PermissionDenied("Ce mode de paiement est réservé au personnel de l'auto-école.")
            if proof is None:
                return Response({"proof": "Preuve de paiement obligatoire pour un règlement en espèces / virement (reçu signé, bordereau)."}, status=400)
            _check_proof(proof)
        order = services.create_order(request.user, plan, d)
        if proof is not None and method in MANUAL:
            order.proof, order.proof_reference = proof, (d.get("proof_reference") or "")[:100]
            order.save(update_fields=["proof", "proof_reference"])
        try:
            url = services.start_payment(order, request.user, frontend_base(request))
        except PermissionDenied:
            invoice = order.invoice
            order.delete()
            if invoice:
                invoice.delete()
            raise
        audit.log(request, "subscription_order", order, new={"plan": plan.name, "amount": str(order.amount), "method": order.method})
        order.refresh_from_db()
        return Response({"order": OrderSerializer(order).data, "redirect_url": url, "mock": providers.is_mock() and bool(url)}, status=201)

    @action(detail=True, methods=["get"])
    def proof(self, request, pk=None):
        """Téléchargement protégé (authentifié, tracé) de la preuve de paiement."""
        order = self.get_object()
        if not order.proof:
            raise Http404
        audit.log(request, "download_payment_proof", order)
        return FileResponse(order.proof.open("rb"), as_attachment=False, filename=order.proof.name.split("/")[-1])

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Retour de la page de paiement : re-vérification serveur du statut auprès de CinetPay."""
        order = self.get_object()
        try:
            order = services.finalize(order)
        except providers.PaymentError as e:
            return Response({"detail": str(e), "order": OrderSerializer(order).data}, status=502)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="mock-confirm")
    def mock_confirm(self, request, pk=None):
        order = self.get_object()
        try:
            order = services.mock_confirm(order, request.data.get("success", True) not in (False, "false", "0"))
        except providers.PaymentError as e:
            return Response({"detail": str(e)}, status=404)
        audit.log(request, "subscription_mock_confirm", order, new={"status": order.status})
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status != "pending":
            return Response({"detail": "Seules les commandes en attente peuvent être annulées."}, status=400)
        order.status = "cancelled"
        order.save(update_fields=["status", "updated_at"])
        audit.log(request, "subscription_cancel", order)
        return Response(OrderSerializer(order).data)

    @action(detail=False, methods=["post"])
    def grant(self, request):
        """Octroi gratuit d'un abonnement (geste commercial, partenariat) : commande à 0 FCFA, tracée dans l'audit."""
        plan = Plan.objects.filter(pk=request.data.get("plan")).first()
        if not plan:
            return Response({"plan": "Plan introuvable."}, status=400)
        order = services.create_order(request.user, plan, request.data)
        order.amount, order.method = 0, "grant"
        order.save(update_fields=["amount", "method"])
        if order.invoice:
            order.invoice.delete()
        services.activate(order)
        audit.log(request, "subscription_grant", order, new={"plan": plan.name})
        order.refresh_from_db()
        return Response(OrderSerializer(order).data, status=201)


class SuspensionMixin:
    """suspend / reactivate d'un abonnement (défaut de paiement). Réservé à ceux qui ont le droit « administer »."""

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        sub = services.suspend(self.get_object(), request.data.get("reason", ""), request.user)
        audit.log(request, "subscription_suspend", sub, new={"reason": sub.suspension_reason})
        return Response(self.get_serializer(sub).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        sub = services.reactivate(self.get_object(), request.user)
        audit.log(request, "subscription_reactivate", sub)
        return Response(self.get_serializer(sub).data)


class LearnerSubSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    learner_name = serializers.CharField(source="learner.full_name", read_only=True)
    is_current = serializers.BooleanField(read_only=True)
    days_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = LearnerSubscription
        fields = "__all__"


class LearnerSubscriptionViewSet(SuspensionMixin, ScopedModelViewSet):
    resource = "member_subscriptions"
    queryset = LearnerSubscription.objects.select_related("plan", "learner")
    serializer_class = LearnerSubSerializer
    learner_lookup = "learner__user"
    http_method_names = ["get", "post", "head", "options"]
    action_verbs = {"cancel": "delete", "suspend": "administer", "reactivate": "administer"}
    filterset_fields = ["status", "plan", "learner"]
    search_fields = ["learner__last_name", "learner__first_name", "learner__matricule", "plan__name"]

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sub = self.get_object()
        sub.status = "cancelled"
        sub.save(update_fields=["status", "updated_at"])
        audit.log(request, "subscription_cancel", sub)
        return Response(self.get_serializer(sub).data)


class OrgSubSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    is_current = serializers.BooleanField(read_only=True)
    days_left = serializers.IntegerField(read_only=True)
    seats_used = serializers.SerializerMethodField()
    cohort_details = serializers.SerializerMethodField()
    max_cohorts = serializers.IntegerField(source="plan.max_cohorts", read_only=True)

    class Meta:
        model = OrganizationSubscription
        fields = "__all__"

    def get_seats_used(self, sub):
        return services.seats_used(sub)

    def get_cohort_details(self, sub):
        return [{"id": c.id, "name": c.name, "learners": c.learners.count()} for c in sub.cohorts.all()]


class OrganizationSubscriptionViewSet(SuspensionMixin, ScopedModelViewSet):
    resource = "member_subscriptions"
    queryset = OrganizationSubscription.objects.select_related("plan", "organization").prefetch_related("cohorts")
    serializer_class = OrgSubSerializer
    org_lookup = "organization"
    http_method_names = ["get", "post", "head", "options"]
    action_verbs = {"cohorts": "change", "cancel": "delete", "suspend": "administer", "reactivate": "administer",
                    "suspend_all": "administer", "reactivate_all": "administer"}
    filterset_fields = ["status", "plan", "organization"]
    search_fields = ["organization__name", "plan__name"]

    def _org(self, request):
        from apps.organizations.models import Organization
        org = Organization.objects.filter(pk=request.data.get("organization")).first()
        if org is None or (request.user.role != AKWABA_ADMIN and org.school_id != request.user.school_id):
            raise serializers.ValidationError({"organization": "Entreprise introuvable."})
        return org

    @action(detail=False, methods=["post"], url_path="suspend-all")
    def suspend_all(self, request):
        """Suspend tous les plans actifs d'une entreprise (défaut de paiement)."""
        org = self._org(request)
        subs = services.suspend_organization(org, request.data.get("reason", ""))
        audit.log(request, "subscription_suspend_all", org, model="organizations.Organization", new={"count": len(subs)})
        return Response({"suspended": len(subs), "organization": org.name})

    @action(detail=False, methods=["post"], url_path="reactivate-all")
    def reactivate_all(self, request):
        org = self._org(request)
        subs = services.reactivate_organization(org)
        audit.log(request, "subscription_reactivate_all", org, model="organizations.Organization", new={"count": len(subs)})
        return Response({"reactivated": len(subs), "organization": org.name})

    @action(detail=True, methods=["post"])
    def cohorts(self, request, pk=None):
        """Change les cohortes couvertes (dans la limite du plan et des places souscrites)."""
        sub = self.get_object()
        services.set_cohorts(sub, [int(i) for i in services.as_list(request.data, "cohorts")])
        audit.log(request, "subscription_cohorts", sub, new={"cohorts": [c.id for c in sub.cohorts.all()]})
        return Response(self.get_serializer(sub).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sub = self.get_object()
        sub.status = "cancelled"
        sub.save(update_fields=["status", "updated_at"])
        audit.log(request, "subscription_cancel", sub)
        return Response(self.get_serializer(sub).data)


class MySubscriptionView(APIView):
    """Écran « Mon abonnement » : situation courante + plans proposés + commandes récentes, selon le rôle."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        services.expire_subscriptions()
        if u.role == LEARNER:
            audience = "individual"
        elif u.role in ORG_ROLES:
            audience = "organization"
        elif u.role in (DIRECTOR,) or u.role == AKWABA_ADMIN:
            audience = "school"
        else:
            return Response({"audience": None})
        school = u.school
        data = {"audience": audience, "can_buy": u.role in (LEARNER, ORG_ADMIN, DIRECTOR),
                "required": bool(school and school.subscription_required), "mock": providers.is_mock(),
                "current": None, "upcoming": [], "history": [], "cohorts": [], "learner": None}
        t = services.today()
        plans = Plan.objects.filter(audience=audience, is_active=True).filter(
            Q(available_from__isnull=True) | Q(available_from__lte=t)).filter(Q(available_until__isnull=True) | Q(available_until__gte=t))
        if audience == "school":
            plans = plans.filter(school__isnull=True)
        else:
            plans = plans.filter(Q(school=school) | Q(school__isnull=True))
        if audience == "organization":
            plans = plans.filter(Q(organization__isnull=True) | Q(organization=u.organization)).filter(
                Q(cohort__isnull=True) | Q(cohort__organization=u.organization))
        if audience == "individual":
            learner = Learner.objects.filter(user=u).first()
            if learner:
                plans = plans.filter(Q(category="") | Q(category=learner.category))
                subs = list(LearnerSubscription.objects.filter(learner=learner).select_related("plan"))
                data["learner"] = {"id": learner.id, "category": learner.category, "school": learner.school_id}
        elif audience == "organization":
            org = u.organization
            subs = list(OrganizationSubscription.objects.filter(organization=org).select_related("plan").prefetch_related("cohorts")) if org else []
            if org:
                from apps.organizations.models import Cohort
                covered = {c.id for s in subs if s.status == "active" and s.end_date >= t for c in s.cohorts.all()}
                data["cohorts"] = [{"id": c.id, "name": c.name, "learners": c.learners.count(), "covered": c.id in covered,
                                    "status": c.status} for c in Cohort.objects.filter(organization=org)]
        else:
            subs = list(Subscription.objects.filter(school=school).select_related("plan")) if school else []
        active = [s for s in subs if s.status == "active" and s.end_date >= t]
        active.sort(key=lambda s: s.start_date)
        ser = (lambda s: services.serialize_sub(s)) if audience != "school" else (lambda s: {
            "id": s.id, "plan": s.plan_id, "plan_name": s.plan.name, "start_date": s.start_date, "end_date": s.end_date, "status": s.status,
            "is_current": s.status == "active" and s.start_date <= t <= s.end_date, "days_left": max((s.end_date - t).days, 0),
            "amount_paid": s.amount_paid})
        cur = [s for s in active if s.start_date <= t]
        data["current"] = ser(cur[-1] if cur else active[0]) if active else None
        if data["current"] and not cur:
            data["current"]["is_current"] = False
        data["upcoming"] = [ser(s) for s in active if s.start_date > t]
        data["history"] = [ser(s) for s in sorted(subs, key=lambda s: s.end_date, reverse=True)[:10]]
        if audience == "school" and school:
            from apps.schools.services import usage
            data["usage"] = usage(school)
        data["suspended"] = [{"id": x["id"], "plan_name": x["plan_name"], "end_date": x["end_date"], "reason": x["reason"]} for x in [
            {"id": sub.id, "plan_name": sub.plan.name, "end_date": sub.end_date, "reason": sub.suspension_reason}
            for sub in subs if sub.status == "suspended" and sub.end_date >= t]]
        if audience == "individual" and data["learner"]:
            # bénéficiaire d'une cohorte dont l'abonnement d'entreprise est suspendu : message explicite
            lrn = Learner.objects.filter(user=u).first()
            if lrn and lrn.cohort_id:
                for sub in OrganizationSubscription.objects.filter(cohorts=lrn.cohort_id, status="suspended", end_date__gte=t).select_related("plan"):
                    data["suspended"].append({"id": f"org{sub.id}", "plan_name": f"{sub.plan.name} (abonnement de votre entreprise)",
                                              "end_date": sub.end_date, "reason": sub.suspension_reason})
        latest = max((x.end_date for x in active), default=None)
        plan_rows = PlanSerializer(plans.order_by("sort_order", "price"), many=True).data
        for row, plan in zip(plan_rows, plans.order_by("sort_order", "price")):
            st, en = services.next_period(plan, latest)
            row["starts_on"], row["ends_on"] = st, en
        data["plans"] = plan_rows
        orders = SubscriptionOrder.objects.filter(created_by=u)[:8] if u.role != AKWABA_ADMIN else SubscriptionOrder.objects.none()
        data["orders"] = OrderSerializer(orders, many=True).data
        return Response(data)


class CinetPayWebhookView(APIView):
    """notify_url CinetPay. Le corps n'est jamais cru : le statut est re-vérifié auprès de CinetPay."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    def get(self, request):
        return Response(status=200)   # CinetPay teste l'accessibilité de la notify_url en GET

    def post(self, request):
        ref = request.data.get("merchant_transaction_id") or request.data.get("cpm_trans_id")
        order = SubscriptionOrder.objects.filter(provider_ref=ref).first() if ref else None
        if not order:
            return Response(status=404)
        try:
            order = services.finalize(order)
        except providers.PaymentError:
            return Response(status=502)   # CinetPay renverra la notification
        audit.log(request, "cinetpay_webhook", order, new={"status": order.status}, model="subscriptions.SubscriptionOrder")
        return Response({"result": order.status})
