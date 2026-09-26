import json
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core import audit
from apps.core.permissions import AKWABA_ADMIN, LEARNER
from apps.core.viewsets import BaseModelSerializer, ScopedModelViewSet, make_serializer

from . import services
from .models import MOBILE_MONEY, Expense, Installment, Invoice, InvoiceLine, Payment


class InvoiceLineSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)

    class Meta:
        model = InvoiceLine
        fields = ["id", "description", "quantity", "unit_price", "amount"]


class InstallmentSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)

    class Meta:
        model = Installment
        fields = ["id", "invoice", "number", "amount", "due_date", "paid_amount", "balance", "status"]
        read_only_fields = ["invoice", "number", "amount", "paid_amount"]


class InvoiceSerializer(BaseModelSerializer):
    lines = InvoiceLineSerializer(many=True, required=False)
    installments = InstallmentSerializer(many=True, read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    learner_name = serializers.CharField(source="learner.full_name", read_only=True, default=None)
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)

    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = ["number", "paid", "parent"]

    def validate(self, attrs):
        school = self.context["request"].user.school or attrs.get("school")
        for key in ("learner", "organization", "contract", "cohort"):
            obj = attrs.get(key)
            if obj is not None and school is not None and obj.school_id != school.id:
                raise serializers.ValidationError({key: "Hors de l'auto-école."})
        if not attrs.get("learner") and not attrs.get("organization") and not self.instance:
            raise serializers.ValidationError("Un apprenant ou une organisation est requis.")
        if not attrs.get("lines") and not attrs.get("total") and not self.instance:
            raise serializers.ValidationError({"total": "Montant ou lignes requis."})
        return attrs

    def create(self, validated):
        lines = validated.pop("lines", [])
        if lines:
            validated["total"] = sum(Decimal(l["quantity"]) * l["unit_price"] for l in lines)
        with transaction.atomic():
            inv = Invoice.objects.create(**validated)
            for l in lines:
                InvoiceLine.objects.create(invoice=inv, **l)
        return inv

    def update(self, instance, validated):
        lines = validated.pop("lines", None)
        if instance.payments.filter(status="confirmed").exists() and "total" in validated:
            raise serializers.ValidationError({"total": "Facture déjà partiellement payée."})
        inst = super().update(instance, validated)
        if lines is not None:
            inst.lines.all().delete()
            for l in lines:
                InvoiceLine.objects.create(invoice=inst, **l)
            inst.total = sum(Decimal(l["quantity"]) * l["unit_price"] for l in lines)
            inst.save(update_fields=["total"])
            inst.recompute()
        return inst


class InvoiceViewSet(ScopedModelViewSet):
    resource = "invoices"
    queryset = Invoice.objects.select_related("learner", "organization").prefetch_related("lines", "installments")
    serializer_class = InvoiceSerializer
    org_lookup = "organization"
    learner_lookup = "learner__user"
    action_verbs = {"pdf": "print", "installments": "create", "convert": "create", "credit_note": "create"}
    filterset_fields = ["kind", "status", "learner", "organization", "contract", "cohort", "school"]
    search_fields = ["number", "title", "learner__last_name", "learner__first_name", "organization__name"]

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        inv = self.get_object()
        resp = HttpResponse(services.invoice_pdf(inv), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{inv.number}.pdf"'
        return resp

    @action(detail=True, methods=["post"])
    def installments(self, request, pk=None):
        inv = self.get_object()
        first = request.data.get("first_due_date") or str(timezone.localdate())
        items = services.make_installments(inv, int(request.data.get("count", 1)), date.fromisoformat(first[:10]),
                                           int(request.data.get("interval_days", 30)))
        audit.log(request, "create_installments", inv, new={"count": len(items)})
        return Response(InstallmentSerializer(items, many=True).data, status=201)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        quote = self.get_object()
        if quote.kind != Invoice.QUOTE:
            return Response({"detail": "Seul un devis peut être converti."}, status=400)
        quote.kind, quote.number, quote.status = Invoice.INVOICE, "", "issued"
        quote.issue_date = timezone.localdate()
        quote.save()
        audit.log(request, "convert_quote", quote)
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=["post"], url_path="credit-note")
    def credit_note(self, request, pk=None):
        inv = self.get_object()
        amount = Decimal(str(request.data.get("amount", 0)))
        if inv.kind != Invoice.INVOICE or amount <= 0 or amount > inv.total:
            return Response({"detail": "Avoir invalide."}, status=400)
        with transaction.atomic():
            note = Invoice.objects.create(school=inv.school, kind=Invoice.CREDIT, learner=inv.learner,
                                          organization=inv.organization, contract=inv.contract, parent=inv,
                                          title=request.data.get("reason", "Avoir"), total=amount, status="issued",
                                          issue_date=timezone.localdate())
            inv.total -= amount
            inv.save(update_fields=["total"])
            inv.recompute()
        audit.log(request, "credit_note", note, new={"parent": inv.number, "amount": str(amount)})
        return Response(self.get_serializer(note).data, status=201)


class InstallmentViewSet(ScopedModelViewSet):
    resource = "installments"
    queryset = Installment.objects.select_related("invoice", "invoice__learner")
    serializer_class = InstallmentSerializer
    school_lookup = "invoice__school"
    org_lookup = "invoice__organization"
    learner_lookup = "invoice__learner__user"
    http_method_names = ["get", "patch", "head", "options"]
    filterset_fields = ["invoice"]

    def get_queryset(self):
        qs = super().get_queryset()
        st = self.request.query_params.get("status")
        today = timezone.localdate()
        from django.db.models import F
        if st == "late":
            qs = qs.filter(due_date__lt=today, paid_amount__lt=F("amount"))
        elif st == "paid":
            qs = qs.filter(paid_amount__gte=F("amount"))
        elif st == "due":
            qs = qs.filter(due_date=today, paid_amount__lt=F("amount"))
        return qs


class PaymentSerializer(BaseModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    has_receipt_file = serializers.SerializerMethodField()

    def get_has_receipt_file(self, p):
        return bool(p.receipt_file)

    class Meta:
        model = Payment
        fields = "__all__"
        extra_kwargs = {"receipt_file": {"write_only": True}}
        read_only_fields = ["status", "provider_ref", "receipt_number", "paid_at", "raw_payload", "recorded_by"]


class PaymentViewSet(ScopedModelViewSet):
    resource = "payments"
    queryset = Payment.objects.select_related("invoice")
    serializer_class = PaymentSerializer
    org_lookup = "invoice__organization"
    learner_lookup = "invoice__learner__user"
    http_method_names = ["get", "post", "head", "options"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_verbs = {"receipt": "print", "sandbox_confirm": "create", "proof": "view", "attach_proof": "create"}
    filterset_fields = ["status", "method", "invoice", "school"]
    search_fields = ["provider_ref", "reference", "receipt_number", "invoice__number"]

    def perform_create(self, serializer):
        u = self.request.user
        inv = serializer.validated_data["invoice"]
        if u.role != AKWABA_ADMIN and inv.school_id != u.school_id:
            raise serializers.ValidationError({"invoice": "Facture inaccessible."})
        if u.role == LEARNER and (not inv.learner or inv.learner.user_id != u.id):
            raise PermissionDenied("Cette facture ne vous concerne pas.")
        if inv.kind != Invoice.INVOICE or inv.status in ("cancelled", "draft"):
            raise serializers.ValidationError({"invoice": "Facture non payable."})
        amount = serializer.validated_data["amount"]
        if amount <= 0 or amount > inv.balance:
            raise serializers.ValidationError({"amount": f"Montant invalide (reste à payer : {int(inv.balance)})."})
        method = serializer.validated_data["method"]
        is_online = method in MOBILE_MONEY or method == "card"
        if u.role == LEARNER and not is_online:
            raise PermissionDenied("Les apprenants paient en ligne (Mobile Money / carte).")
        if method == "cash" and not serializer.validated_data.get("receipt_file"):
            raise serializers.ValidationError({"receipt_file": "Joignez le reçu signé du paiement en espèces (PDF ou photo)."})
        f = serializer.validated_data.get("receipt_file")
        if f is not None and (f.size > 10 * 1024 * 1024 or not f.name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg"))):
            raise serializers.ValidationError({"receipt_file": "PDF, PNG ou JPG de 10 Mo maximum."})
        if is_online:
            # jamais confirmé ici : uniquement via le webhook du fournisseur
            payment = serializer.save(school=inv.school, status="pending", provider_ref=services.new_provider_ref(method),
                                      recorded_by=u)
        else:
            payment = serializer.save(school=inv.school, status="pending", recorded_by=u)
            services.confirm_payment(payment)
            payment.refresh_from_db()
        audit.log(self.request, "create", payment, new={"amount": str(payment.amount), "method": payment.method,
                                                        "status": payment.status})
        self.created = payment

    @action(detail=True, methods=["get"])
    def proof(self, request, pk=None):
        """Reçu / justificatif téléversé par la secrétaire (téléchargement authentifié et tracé)."""
        p = self.get_object()
        if not p.receipt_file:
            return Response({"detail": "Aucun justificatif."}, status=404)
        audit.log(request, "download_payment_proof", p)
        return FileResponse(p.receipt_file.open("rb"), as_attachment=True, filename=p.receipt_file.name.split("/")[-1])

    @action(detail=True, methods=["post"], url_path="attach-proof")
    def attach_proof(self, request, pk=None):
        """Ajoute (ou remplace) le reçu d'un paiement déjà enregistré."""
        p = self.get_object()
        if request.user.role == LEARNER:
            raise PermissionDenied("Réservé au secrétariat.")
        f = request.FILES.get("file")
        if f is None or f.size > 10 * 1024 * 1024 or not f.name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
            return Response({"file": "PDF, PNG ou JPG de 10 Mo maximum."}, status=400)
        p.receipt_file = f
        p.save(update_fields=["receipt_file", "updated_at"])
        audit.log(request, "attach_payment_proof", p)
        return Response(self.get_serializer(p).data)

    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        p = self.get_object()
        if p.status != "confirmed":
            return Response({"detail": "Paiement non confirmé."}, status=400)
        resp = HttpResponse(services.receipt_pdf(p), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{p.receipt_number}.pdf"'
        return resp

    @action(detail=True, methods=["post"], url_path="sandbox-confirm")
    def sandbox_confirm(self, request, pk=None):
        """Simulateur de fournisseur (DEBUG uniquement) : émet un événement signé vers le même traitement que le webhook."""
        if not settings.DEBUG:
            return Response({"detail": "Indisponible."}, status=404)
        p = self.get_object()
        ok = request.data.get("success", True) not in (False, "false", "0")
        data = {"provider_ref": p.provider_ref, "status": "success" if ok else "failed", "amount": str(int(p.amount))}
        _, outcome = services.process_provider_event(data)
        audit.log(request, "sandbox_provider_event", p, new={"outcome": outcome})
        p.refresh_from_db()
        return Response(self.get_serializer(p).data)


class PaymentWebhookView(APIView):
    """Webhook fournisseur Mobile Money. Authentifié par signature HMAC-SHA256 (en-tête X-Signature)."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    def post(self, request):
        body = request.body
        if not services.verify_signature(body, request.headers.get("X-Signature", "")):
            audit.log(request, "webhook_rejected", model="billing.Payment")
            return Response({"detail": "Signature invalide."}, status=401)
        try:
            data = json.loads(body)
        except ValueError:
            return Response({"detail": "JSON invalide."}, status=400)
        payment, outcome = services.process_provider_event(data)
        audit.log(request, "webhook_" + outcome, payment, new=data, model="billing.Payment")
        if outcome == "unknown":
            return Response({"detail": "Paiement inconnu."}, status=404)
        if outcome == "amount_mismatch":
            return Response({"detail": "Montant incohérent."}, status=422)
        return Response({"result": outcome})


payment_webhook = PaymentWebhookView.as_view()


ExpenseSerializer = make_serializer(Expense)


class ExpenseViewSet(ScopedModelViewSet):
    resource = "expenses"
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    filterset_fields = ["category", "agency", "vehicle", "instructor", "school"]
    search_fields = ["description"]
    ordering_fields = ["date", "amount"]
