from django.db.models import Q
from django.http import FileResponse
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core import audit
from apps.core.notify import notify
from apps.core.permissions import AKWABA_ADMIN
from apps.core.viewsets import BaseModelSerializer, ScopedModelViewSet, make_serializer

from . import services
from .models import (PERMIT_BUNDLE_PRICES, STATUS, IndividualQuote, OfferTypeConfig, PermitCandidate, RecyclingItem,
                     RecyclingReminderSettings)

RecyclingItemSerializer = make_serializer(
    RecyclingItem, extra_fields={"duration_minutes": serializers.IntegerField(read_only=True)})


class RecyclingItemViewSet(ScopedModelViewSet):
    resource = "recycling_items"
    queryset = RecyclingItem.objects.prefetch_related("modules")
    serializer_class = RecyclingItemSerializer
    filterset_fields = ["kind", "is_active"]
    search_fields = ["label"]


class OfferTypeConfigSerializer(BaseModelSerializer):
    school_name = serializers.CharField(source="school.commercial_name", read_only=True, default="")
    offer_label = serializers.CharField(source="get_offer_display", read_only=True)

    class Meta:
        model = OfferTypeConfig
        fields = "__all__"


class OfferTypeConfigViewSet(ScopedModelViewSet):
    """Paramétrage, côté secrétariat/direction, du contenu « ce qui est inclus » par type de demande."""
    resource = "offer_type_configs"
    queryset = OfferTypeConfig.objects.select_related("school").prefetch_related("courses", "recycling_items")
    serializer_class = OfferTypeConfigSerializer
    filterset_fields = ["offer", "is_active"]
    search_fields = ["title"]


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
        # Note : license_photo_front/license_photo_back (recto/verso du permis déjà détenu) ne sont
        # pertinentes que pour extension / theory_refresh / practical_refresh (pas new_license, le candidat
        # n'ayant alors pas encore de permis). Volontairement non bloquantes ici : la secrétaire peut les
        # redemander lors du traitement du dossier (cf. resubmit) sans empêcher le dépôt initial de la demande.
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
        services.notify_quote_decision(quote)
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=["post"])
    def resubmit(self, request, pk=None):
        """Le candidat corrige et renvoie la MÊME demande (pas de nouvelle fiche, cf. anti-doublon §3.1)."""
        quote = self.get_object()
        if quote.status != "correction_requested":
            raise ValidationError({"detail": "Cette demande n'est pas en attente de correction."})
        for f in ("id_document_type", "id_document_no", "last_name", "first_name", "phone", "email", "residence",
                 "license_no", "license_photo_front", "license_photo_back"):
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
    return Response([{"id": i.id, "kind": i.kind, "label": i.label, "price": i.price,
                      "sessions_count": i.sessions_count, "duration_minutes": i.duration_minutes} for i in qs])


def _offer_type_config_public_payload(c):
    return {"id": c.id, "school": c.school_id, "offer": c.offer, "offer_label": c.get_offer_display(),
            "title": c.title or c.get_offer_display(), "description": c.description,
            "base_price": c.base_price, "features": c.features,
            "includes_courses": c.includes_courses, "includes_quizzes": c.includes_quizzes,
            "includes_exams": c.includes_exams}


@api_view(["GET"])
@permission_classes([AllowAny])
def public_offer_type_configs(request):
    """Contenu « ce qui est inclus » par type de demande, pour le formulaire public de devis (§2-3) —
    champs sûrs uniquement (pas de tarification interne négociée)."""
    school_id = request.query_params.get("school")
    qs = OfferTypeConfig.objects.filter(is_active=True)
    if school_id:
        qs = qs.filter(school_id=school_id)
    return Response([_offer_type_config_public_payload(c) for c in qs])


class MyQuotesView(APIView):
    """Écran « mes demandes » du candidat : ses devis individuels, chacun avec le paramétrage « ce qui est
    inclus » (OfferTypeConfig) correspondant à son (school, offer)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        learner = getattr(request.user, "learner_profile", None)
        if not learner:
            return Response([])
        quotes = IndividualQuote.objects.filter(learner=learner).select_related("school").prefetch_related("recycling_items")
        configs = {(c.school_id, c.offer): c for c in
                  OfferTypeConfig.objects.filter(is_active=True, school_id__in=[q.school_id for q in quotes])}
        data = []
        for q in quotes:
            cfg = configs.get((q.school_id, q.offer))
            data.append({
                "id": q.id, "offer": q.offer, "offer_label": q.get_offer_display(), "status": q.status,
                "status_label": q.get_status_display(), "created_at": q.created_at,
                "base_price": q.base_price, "negotiated_price": q.negotiated_price, "price": q.price,
                "paid_amount": q.paid_amount, "balance": q.balance,
                "reject_reason": q.reject_reason, "correction_note": q.correction_note,
                "offer_type_config": _offer_type_config_public_payload(cfg) if cfg else None,
            })
        return Response(data)


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
        # Idem IndividualQuoteSerializer.validate : license_photo_front/back non bloquantes au dépôt public.
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


@api_view(["GET"])
@permission_classes([AllowAny])
def public_engagement_sheet(request):
    """Téléchargement public de la fiche d'engagement (vitrine, écran d'inscription, e-mails)."""
    return services.engagement_pdf_response()


# --------------------------------------------------------------------------------------------------------
# Candidatures permis de conduire portées par une organisation (ex. opération CAFOP).
class PermitCandidateSerializer(BaseModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    category_bundle_label = serializers.CharField(source="get_category_bundle_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    has_id_document_file = serializers.SerializerMethodField()
    has_id_document_back_file = serializers.SerializerMethodField()
    has_birth_certificate_file = serializers.SerializerMethodField()

    class Meta:
        model = PermitCandidate
        fields = "__all__"
        read_only_fields = ["school", "price"]
        # Documents d'identité : jamais exposés en URL directe (média public) — téléchargement authentifié
        # et tracé uniquement, via les actions dédiées ci-dessous (comme les justificatifs de paiement).
        extra_kwargs = {"id_document_file": {"write_only": True}, "id_document_back_file": {"write_only": True},
                        "birth_certificate_file": {"write_only": True}}

    def get_has_id_document_file(self, o):
        return bool(o.id_document_file)

    def get_has_id_document_back_file(self, o):
        return bool(o.id_document_back_file)

    def get_has_birth_certificate_file(self, o):
        return bool(o.birth_certificate_file)


class PermitCandidateViewSet(ScopedModelViewSet):
    resource = "permit_candidates"
    queryset = PermitCandidate.objects.select_related("organization")
    serializer_class = PermitCandidateSerializer
    org_lookup = "organization"
    filterset_fields = ["organization", "category_bundle", "status"]
    search_fields = ["last_name", "first_name", "contact", "center"]
    action_verbs = {"id_document": "view", "id_document_back": "view", "birth_certificate": "view"}

    def get_queryset(self):
        qs = super().get_queryset()
        month = self.request.query_params.get("month")  # format AAAA-MM
        if month:
            try:
                year, m = (int(x) for x in month.split("-", 1))
                qs = qs.filter(created_at__year=year, created_at__month=m)
            except ValueError:
                pass
        return qs

    def _send_file(self, request, candidate, field, label, action_code):
        f = getattr(candidate, field)
        if not f:
            return Response({"detail": "Aucun fichier."}, status=404)
        # action_code : max 40 caractères (AuditLog.action), rester court plutôt que de reprendre le nom du champ.
        audit.log(request, action_code, candidate)
        return FileResponse(f.open("rb"), as_attachment=True, filename=f"{label}-{candidate.last_name}-{f.name.split('/')[-1]}")

    @action(detail=True, methods=["get"], url_path="id-document")
    def id_document(self, request, pk=None):
        """Pièce d'identité (recto), téléchargement authentifié et tracé."""
        return self._send_file(request, self.get_object(), "id_document_file", "recto", "download_permit_id_doc")

    @action(detail=True, methods=["get"], url_path="id-document-back")
    def id_document_back(self, request, pk=None):
        """Pièce d'identité (verso), téléchargement authentifié et tracé."""
        return self._send_file(request, self.get_object(), "id_document_back_file", "verso", "download_permit_id_back")

    @action(detail=True, methods=["get"], url_path="birth-certificate")
    def birth_certificate(self, request, pk=None):
        """Extrait de naissance, téléchargement authentifié et tracé."""
        return self._send_file(request, self.get_object(), "birth_certificate_file", "naissance", "download_permit_birth")


class PublicPermitCandidateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermitCandidate
        fields = ["organization", "last_name", "first_name", "center", "contact", "category_bundle",
                 "id_document_file", "id_document_back_file", "birth_certificate_file"]


class PublicPermitCandidateView(APIView):
    """POST public (sans compte) depuis la vitrine — inscription groupée portée par une organisation (CAFOP…)."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = PublicPermitCandidateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org = ser.validated_data["organization"]
        candidate = ser.save(school=org.school, price=PERMIT_BUNDLE_PRICES.get(ser.validated_data["category_bundle"], 0))
        from apps.accounts.models import User
        recipients = User.objects.filter(role__in=["secretary", "director"], is_active=True, school_id=org.school_id)
        for u in recipients:
            notify(u, "individual_quote", "Nouvelle candidature permis (organisation)",
                  f"{candidate.first_name} {candidate.last_name} — {org.name} — {candidate.get_category_bundle_display()}")
        return Response({"detail": "Candidature enregistrée. Vous serez recontacté(e) par l'auto-école.", "id": candidate.id}, status=201)
