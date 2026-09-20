from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core import audit
from apps.core.permissions import LEARNER, ORG_ROLES
from apps.core.viewsets import SCHOOL, BaseModelSerializer, ScopedModelViewSet
from apps.learners.models import Learner
from apps.pedagogy import services as quiz_services
from apps.pedagogy.models import Attempt
from apps.pedagogy.views import AttemptViewSet, QuizAdminActions, QuizSerializer

from . import services
from .models import Certificate, Exam


class ExamSerializer(QuizSerializer):
    class Meta(QuizSerializer.Meta):
        model = Exam


class ExamViewSet(QuizAdminActions, ScopedModelViewSet):
    resource = "exams"
    queryset = Exam.objects.filter(is_exam=True)
    serializer_class = ExamSerializer
    include_global = True
    learner_lookup = SCHOOL
    instructor_lookup = SCHOOL
    org_lookup = "school__organizations"
    action_verbs = {"start": "view", "results": "view", "compose": "change", "questions": "change", "duplicate": "create", "stats": "change"}
    filterset_fields = ["category", "training", "is_published", "school"]
    search_fields = ["title"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == LEARNER:
            learner = Learner.objects.filter(user=self.request.user).first()
            qs = qs.filter(is_published=True, category=learner.category if learner else "B")
        return qs

    def before_create(self, serializer, kwargs):
        kwargs["is_exam"] = True
        school = self.request.user.school
        if school and "pass_threshold" not in self.request.data:
            kwargs["pass_threshold"] = school.pass_threshold

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        exam = self.get_object()
        learner = Learner.objects.filter(user=request.user).first()
        if request.user.role != LEARNER or learner is None:
            raise PermissionDenied("Réservé aux apprenants.")
        attempt = quiz_services.start_attempt(exam, learner)
        return Response(AttemptViewSet.detail_payload(attempt), status=201)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        exam = self.get_object()
        rows = Attempt.objects.filter(quiz=exam).select_related("learner").order_by("-started_at")
        u = request.user
        if u.role in ORG_ROLES:
            rows = rows.filter(learner__organization=u.organization)
        return Response([quiz_services.attempt_summary(a) | {"learner": a.learner_id, "learner_name": a.learner.full_name,
                                                             "matricule": a.learner.matricule}
                         for a in rows if a.status != Attempt.IN_PROGRESS])


class CertificateSerializer(BaseModelSerializer):
    learner_name = serializers.CharField(source="learner.full_name", read_only=True)
    verify_url = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        exclude = ["verification_token"]
        read_only_fields = ["number", "attempt", "learner", "school", "training_name", "category", "score", "percent",
                            "issued_at"]

    def get_verify_url(self, c):
        return services.verify_url(c)


class CertificateViewSet(ScopedModelViewSet):
    resource = "certificates"
    queryset = Certificate.objects.select_related("learner", "school")
    serializer_class = CertificateSerializer
    org_lookup = "learner__organization"
    learner_lookup = "learner__user"
    http_method_names = ["get", "post", "head", "options"]
    action_verbs = {"pdf": "print", "revoke": "administer"}
    filterset_fields = ["status", "learner", "category", "school"]
    search_fields = ["number", "learner__last_name", "learner__first_name"]

    def create(self, request, *args, **kwargs):
        raise PermissionDenied("Les certificats sont générés automatiquement à la réussite de l'examen.")

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        cert = self.get_object()
        resp = HttpResponse(services.certificate_pdf(cert), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{cert.number}.pdf"'
        return resp

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        cert = self.get_object()
        cert.status = Certificate.REVOKED
        cert.save(update_fields=["status"])
        audit.log(request, "revoke_certificate", cert)
        return Response(self.get_serializer(cert).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_certificate(request, code):
    """Vérification publique (QR code) : authenticité, titulaire, formation, date, numéro, statut."""
    base = Certificate.objects.select_related("learner", "school")
    cert = base.filter(verification_token=code).first() or base.filter(number=code).first()
    if not cert:
        return Response({"authentic": False, "detail": "Certificat introuvable."}, status=404)
    return Response({
        "authentic": cert.status == Certificate.VALID, "status": cert.status,
        "status_label": cert.get_status_display(), "holder": cert.learner.full_name, "training": cert.training_name,
        "category": cert.category, "date": cert.issued_at, "number": cert.number, "school": str(cert.school),
        "score": cert.score, "percent": cert.percent})
