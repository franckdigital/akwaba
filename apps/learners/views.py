import secrets

from django.http import FileResponse, Http404
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.models import User
from apps.core import audit
from apps.core.notify import notify
from apps.core.permissions import AKWABA_ADMIN, LEARNER, ORG_ROLES
from apps.core.viewsets import SCHOOL, ScopedModelViewSet, make_serializer

from .models import Learner, LearnerDocument


class LearnerSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    training_name = serializers.CharField(source="training.name", read_only=True, default=None)
    cohort_name = serializers.CharField(source="cohort.name", read_only=True, default=None)
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Learner
        fields = "__all__"
        read_only_fields = ["matricule", "user"]
        extra_kwargs = {"school": {"required": False}}

    def validate(self, attrs):
        from apps.subscriptions.services import check_cohort_seat
        cohort = attrs.get("cohort")
        if cohort is not None and cohort != getattr(self.instance, "cohort", None):
            check_cohort_seat(cohort, self.instance)
        school = attrs.get("school") or getattr(self.instance, "school", None) or self.context["request"].user.school
        for key in ("training", "agency", "cohort", "group", "organization"):
            obj = attrs.get(key)
            if obj is not None and school is not None and getattr(obj, "school_id", None) not in (None, school.id):
                if key == "group":
                    if obj.cohort.school_id != school.id:
                        raise serializers.ValidationError({key: "Hors de l'auto-école."})
                else:
                    raise serializers.ValidationError({key: "Hors de l'auto-école."})
        return attrs


DocumentSerializer = make_serializer(
    LearnerDocument, exclude=("file",), read_only=("uploaded_by",), extra_fields={
        "file": serializers.FileField(write_only=True),
        "download_url": serializers.SerializerMethodField(),
        "get_download_url": lambda self, obj: f"/api/documents/{obj.pk}/download/"})


class LearnerViewSet(ScopedModelViewSet):
    resource = "learners"
    queryset = Learner.objects.select_related("training", "cohort", "organization")
    serializer_class = LearnerSerializer
    org_lookup = "organization"
    learner_lookup = "user"
    instructor_lookup = "lessons__instructor__user"
    limit_key = "learners"
    action_verbs = {"create_account": "change", "progress": "view", "driving_log": "view", "export": "export",
                    "approve_registration": "validate", "exam_access": "view"}
    filterset_fields = ["status", "category", "training", "cohort", "group", "organization", "agency", "school", "source", "approval_status"]
    search_fields = ["last_name", "first_name", "matricule", "phone", "email", "employee_ref"]
    ordering_fields = ["last_name", "registered_at", "created_at"]

    def before_create(self, serializer, kwargs):
        u = self.request.user
        if u.role in ORG_ROLES:
            kwargs["organization"] = u.organization
            kwargs["source"] = "organization"

    def _own(self):
        return Learner.objects.filter(user=self.request.user).first()

    @action(detail=False, methods=["get"])
    def me(self, request):
        learner = self._own()
        if not learner:
            return Response({"detail": "Aucun dossier apprenant."}, status=404)
        return Response(self.get_serializer(learner).data)

    @action(detail=True, methods=["post"], url_path="create-account")
    def create_account(self, request, pk=None):
        learner = self.get_object()
        if learner.user_id:
            return Response({"detail": "Compte déjà créé."}, status=400)
        email = learner.email or request.data.get("email")
        if not email:
            return Response({"detail": "E-mail requis."}, status=400)
        if User.objects.filter(email=email.lower()).exists():
            return Response({"detail": "Un compte existe déjà avec cet e-mail."}, status=400)
        password = request.data.get("password") or secrets.token_urlsafe(9)
        user = User.objects.create_user(email, password, first_name=learner.first_name, last_name=learner.last_name,
                                        phone=learner.phone, role=LEARNER, school=learner.school,
                                        organization=learner.organization)
        learner.user, learner.email = user, email
        learner.save(update_fields=["user", "email"])
        audit.log(request, "create_account", learner, new={"email": email})
        return Response({"email": email, "temporary_password": password})

    @action(detail=True, methods=["post"], url_path="approve-registration")
    def approve_registration(self, request, pk=None):
        """Décision du secrétariat sur une inscription en ligne (§5) : vérifications propres au système
        (doublon local, zone) déjà faites à la soumission ; ce qui reste ici relève d'une vérification
        MANUELLE externe (base du ministère, permis valide) — hors du système, comme précisé §4.1.
        Body : {"decision": "approved"|"rejected", "reject_reason"?}"""
        learner = self.get_object()
        if learner.approval_status != "pending":
            raise ValidationError({"detail": "Ce dossier n'est pas en attente d'approbation."})
        decision = request.data.get("decision")
        if decision not in ("approved", "rejected"):
            raise ValidationError({"decision": "Valeur attendue : approved ou rejected."})
        old = self._snapshot(learner)
        learner.approval_status = decision
        if decision == "rejected":
            learner.approval_reject_reason = request.data.get("reject_reason") or \
                "Candidat déjà inscrit ailleurs, sans permis de conduire valide pour cette offre, ou zone non couverte."
            if learner.user_id:
                learner.user.is_active = False
                learner.user.save(update_fields=["is_active"])
        else:
            learner.status = "registered" if learner.status == "new" else learner.status
        learner.save(update_fields=["approval_status", "approval_reject_reason", "status", "updated_at"])
        audit.log(request, "approve_registration", learner, old=old, new=self._snapshot(learner))
        if decision == "approved" and learner.user:
            notify(learner.user, "registration_approved", "Inscription validée",
                  f"Votre dossier chez {learner.school} est activé. Bienvenue chez Akwaba Auto-École !",
                  channels=("inapp", "email", "whatsapp"))
        return Response(self.get_serializer(learner).data)

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        from apps.pedagogy.services import learner_progress
        return Response(learner_progress(self.get_object()))

    @action(detail=True, methods=["get"], url_path="exam-access")
    def exam_access(self, request, pk=None):
        """§5.2/§6.1 — palier de paiement et conditions d'accès aux examens (code / conduite)."""
        from apps.admissions.services import exam_access as compute_exam_access
        return Response(compute_exam_access(self.get_object()))

    @action(detail=True, methods=["get"], url_path="driving-log")
    def driving_log(self, request, pk=None):
        from apps.practice.services import driving_log
        return Response(driving_log(self.get_object()))


class DocumentViewSet(ScopedModelViewSet):
    resource = "documents"
    queryset = LearnerDocument.objects.select_related("learner")
    serializer_class = DocumentSerializer
    school_lookup = "learner__school"
    org_lookup = "learner__organization"
    learner_lookup = "learner__user"
    action_verbs = {"download": "view"}
    filterset_fields = ["learner", "doc_type"]

    def perform_create(self, serializer):
        learner = serializer.validated_data["learner"]
        # le scope garantit que l'apprenant est visible par l'utilisateur
        if not Learner.objects.filter(pk=learner.pk).exists() or (
                self.request.user.role != AKWABA_ADMIN and learner.school_id != self.request.user.school_id):
            raise serializers.ValidationError({"learner": "Apprenant inaccessible."})
        instance = serializer.save(uploaded_by=self.request.user)
        audit.log(self.request, "upload_document", instance, new={"learner": learner.pk, "type": instance.doc_type})

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        doc = self.get_object()
        try:
            audit.log(request, "download_document", doc)
            return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.file.name.split("/")[-1])
        except FileNotFoundError:
            raise Http404
