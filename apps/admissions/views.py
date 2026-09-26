from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core import audit
from apps.core.notify import notify
from apps.core.permissions import AKWABA_ADMIN
from apps.core.viewsets import BaseModelSerializer, ScopedModelViewSet, make_serializer

from . import services
from .models import STATUS, IndividualQuote, RecyclingItem, RecyclingReminderSettings

RecyclingItemSerializer = make_serializer(RecyclingItem)


class RecyclingItemViewSet(ScopedModelViewSet):
    resource = "recycling_items"
    queryset = RecyclingItem.objects.prefetch_related("modules")
    serializer_class = RecyclingItemSerializer
    filterset_fields = ["kind", "is_active"]
    search_fields = ["label"]


class RecyclingReminderSettingsSerializer(BaseModelSerializer):
    school_name = serializers.CharField(source="school.commercial_name", read_only=True, default="")

    class Meta:
        model = RecyclingReminderSettings
        fields = "__all__"


class RecyclingReminderSettingsViewSet(ScopedModelViewSet):
    """Une seule fiche par auto-école : la secrétaire/direction paramètre la relance depuis l'admin (§3.3)."""
    resource = "recycling_reminder_settings"
    queryset = RecyclingReminderSettings.objects.all()
    serializer_class = RecyclingReminderSettingsSerializer

    def perform_create(self, serializer):
        user = self.request.user
        school = user.school if user.role != AKWABA_ADMIN else serializer.validated_data.get("school")
        obj, _ = RecyclingReminderSettings.objects.update_or_create(school=school, defaults=serializer.validated_data)
        serializer.instance = obj


class IndividualQuoteSerializer(BaseModelSerializer):
    school_name = serializers.CharField(source="school.commercial_name", read_only=True, default="")
    price = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)
    quote_pdf_url = serializers.SerializerMethodField()
    recycling_items_detail = RecyclingItemSerializer(source="recycling_items", many=True, read_only=True)

    class Meta:
        model = IndividualQuote
        fields = "__all__"
        read_only_fields = ["status", "quote_pdf", "sent_channel", "sent_at", "id_document_hash"]

    def get_quote_pdf_url(self, q):
        if not q.quote_pdf:
            return None
        req = self.context.get("request")
        return req.build_absolute_uri(q.quote_pdf.url) if req else q.quote_pdf.url

    def validate(self, attrs):
        offer = attrs.get("offer", getattr(self.instance, "offer", None))
        if offer == "extension":
            services.validate_extension(
                attrs.get("categories_held", getattr(self.instance, "categories_held", [])),
                attrs.get("categories_to_add", getattr(self.instance, "categories_to_add", [])),
                attrs.get("categories_expiry", getattr(self.instance, "categories_expiry", {})))
        if offer in ("theory_refresh", "practical_refresh") and not attrs.get("license_no", getattr(self.instance, "license_no", "")):
            raise ValidationError({"license_no": "Le numéro de permis existant est requis pour cette offre."})
        return attrs


class IndividualQuoteViewSet(ScopedModelViewSet):
    """Traitement, côté secrétariat, des demandes de devis individuelles (§2-3)."""
    resource = "individual_quotes"
    queryset = IndividualQuote.objects.select_related("school", "organization").prefetch_related("recycling_items")
    serializer_class = IndividualQuoteSerializer
    include_global = True   # une demande non encore assignée (school=null) reste visible/assignable par le secrétariat
    filterset_fields = ["offer", "status", "organization"]
    search_fields = ["last_name", "first_name", "phone", "email", "license_no"]
    action_verbs = {"decide": "validate", "set_payment": "change", "negotiate_price": "change", "send": "print"}

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """Décision de la secrétaire suite à sa vérification MANUELLE de la base du ministère (§3.1/§3.3, hors système).
        Body : {"decision": "approved"|"rejected"|"correction_requested", "reject_reason"?, "correction_note"?}"""
        quote = self.get_object()
        decision = request.data.get("decision")
        if decision not in ("approved", "rejected", "correction_requested"):
            raise ValidationError({"decision": "Valeur attendue : approved, rejected ou correction_requested."})
        old = self._snapshot(quote)
        quote.status = decision
        if decision == "rejected":
            quote.reject_reason = request.data.get("reject_reason") or \
                "Nous sommes désolés de ne pas pouvoir répondre à votre attente car votre pièce d'identité est enregistrée ailleurs."
        elif decision == "correction_requested":
            quote.correction_note = request.data.get("correction_note") or \
                "Veuillez vérifier la conformité des informations de votre pièce d'identité."
        quote.save(update_fields=["status", "reject_reason", "correction_note", "updated_at"])
        audit.log(request, "decide", quote, old=old, new=self._snapshot(quote))
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=["post"])
    def resubmit(self, request, pk=None):
        """Le candidat corrige et renvoie la MÊME demande (pas de nouvelle fiche, cf. anti-doublon §3.1)."""
        quote = self.get_object()
        if quote.status != "correction_requested":
            raise ValidationError({"detail": "Cette demande n'est pas en attente de correction."})
        for f in ("id_document_type", "id_document_no", "last_name", "first_name", "phone", "email", "residence"):
            if f in request.data:
                setattr(quote, f, request.data[f])
        quote.status = "submitted"
        quote.correction_note = ""
        quote.save()
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=["post"])
    def set_payment(self, request, pk=None):
        """La secrétaire renseigne les montants payés (désactivé si le candidat relève d'une collectivité, §3.1)."""
        quote = self.get_object()
        if quote.organization_id:
            raise PermissionDenied("Candidat rattaché à une collectivité : accès complet prévu par la convention, pas de saisie individuelle.")
        amount = request.data.get("paid_amount")
        if amount is None:
            raise ValidationError({"paid_amount": "Montant requis."})
        quote.paid_amount = amount
        quote.save(update_fields=["paid_amount", "updated_at"])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=["post"])
    def negotiate_price(self, request, pk=None):
        """Le tarif peut être négocié ; il apparaît sur le PDF du devis (§3.1)."""
        quote = self.get_object()
        price = request.data.get("negotiated_price")
        if price is None:
            raise ValidationError({"negotiated_price": "Tarif requis."})
        quote.negotiated_price = price
        quote.save(update_fields=["negotiated_price", "updated_at"])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Envoi du devis PDF par e-mail ou WhatsApp, en un clic (§3.1/§3.2)."""
        quote = self.get_object()
        channel = request.data.get("channel")
        if channel not in ("email", "whatsapp"):
            raise ValidationError({"channel": "Choisir email ou whatsapp."})
        if channel == "email" and not quote.email:
            raise ValidationError({"channel": "Le candidat n'a pas d'e-mail renseigné."})
        if channel == "whatsapp" and not quote.phone:
            raise ValidationError({"channel": "Le candidat n'a pas de téléphone renseigné."})
        services.send_quote(quote, channel)
        audit.log(request, "send_quote", quote, new={"channel": channel})
        return Response(self.get_serializer(quote).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_recycling_items(request):
    """§3.3 — catalogue des modules/packages de recyclage théorique, pour le formulaire public de devis."""
    school_id = request.query_params.get("school")
    qs = RecyclingItem.objects.filter(is_active=True)
    if school_id:
        qs = qs.filter(school_id=school_id)
    return Response([{"id": i.id, "kind": i.kind, "label": i.label, "price": i.price} for i in qs])


class PublicIndividualQuoteSerializer(BaseModelSerializer):
    class Meta:
        model = IndividualQuote
        exclude = ["status", "reject_reason", "correction_note", "base_price", "negotiated_price", "paid_amount",
                   "quote_pdf", "sent_channel", "sent_at", "id_document_hash", "recycling_items"]

    def validate(self, attrs):
        services.check_duplicate(attrs.get("id_document_no", ""))
        offer = attrs.get("offer")
        if offer == "extension":
            services.validate_extension(attrs.get("categories_held", []), attrs.get("categories_to_add", []),
                                        attrs.get("categories_expiry", {}))
        if offer in ("theory_refresh", "practical_refresh") and not attrs.get("license_no"):
            raise ValidationError({"license_no": "Le numéro de permis existant est requis pour cette offre."})
        return attrs


class PublicIndividualQuoteView(APIView):
    """POST public (sans compte) depuis la vitrine — un formulaire par offre (§2-3)."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = PublicIndividualQuoteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        quote = ser.save()
        recycling_ids = request.data.get("recycling_items") or []
        if recycling_ids:
            quote.recycling_items.set(RecyclingItem.objects.filter(pk__in=recycling_ids, school=quote.school))
            quote.base_price = services.compute_recycling_price(quote.recycling_items.all())
            quote.save(update_fields=["base_price"])
        from apps.accounts.models import User
        recipients = User.objects.filter(role__in=["secretary", "director"], is_active=True)
        if quote.school_id:
            recipients = recipients.filter(school_id=quote.school_id)
        for u in recipients:
            notify(u, "individual_quote", "Nouvelle demande de devis",
                  f"{quote.first_name} {quote.last_name} — {quote.get_offer_display()}")
        return Response({"detail": "Demande enregistrée. Vous serez recontacté(e) après vérification.", "id": quote.id}, status=201)
