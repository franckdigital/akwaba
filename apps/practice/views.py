from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core import audit
from apps.core.notify import notify
from apps.core.permissions import INSTRUCTOR, LEARNER
from apps.core.viewsets import SCHOOL, BaseModelSerializer, ScopedModelViewSet, make_serializer

from . import services
from .models import (Evaluation, FuelRecord, Instructor, Lesson, MaintenanceRecord, Room, Vehicle, VirtualClass, VirtualClassAttendance,
                     VirtualClassQuestion)


class InstructorSerializer(BaseModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Instructor
        fields = "__all__"

    def get_full_name(self, obj):
        return str(obj)


class InstructorViewSet(ScopedModelViewSet):
    resource = "instructors"
    queryset = Instructor.objects.all()
    serializer_class = InstructorSerializer
    limit_key = "instructors"
    learner_lookup = SCHOOL
    instructor_lookup = SCHOOL
    filterset_fields = ["status", "agency", "school"]
    search_fields = ["last_name", "first_name", "phone", "email"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == INSTRUCTOR and self.action != "list":
            return qs
        return qs

    @action(detail=False, methods=["get"])
    def me(self, request):
        ins = Instructor.objects.filter(user=request.user).first()
        if not ins:
            return Response({"detail": "Aucun profil moniteur."}, status=404)
        return Response(self.get_serializer(ins).data)


class VehicleSerializer(BaseModelSerializer):
    alerts = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = "__all__"

    def get_alerts(self, v):
        soon = timezone.localdate() + timedelta(days=30)
        out = []
        for label, d in (("Assurance", v.insurance_expiry), ("Visite technique", v.technical_visit_expiry)):
            if d and d < timezone.localdate():
                out.append(f"{label} expirée")
            elif d and d <= soon:
                out.append(f"{label} expire bientôt")
        return out


class VehicleViewSet(ScopedModelViewSet):
    resource = "vehicles"
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    learner_lookup = None
    instructor_lookup = SCHOOL
    filterset_fields = ["state", "category", "agency", "instructor", "school"]
    search_fields = ["plate", "brand", "model"]


class MaintenanceSerializer(BaseModelSerializer):
    class Meta:
        model = MaintenanceRecord
        fields = "__all__"


class MaintenanceViewSet(ScopedModelViewSet):
    resource = "maintenance"
    queryset = MaintenanceRecord.objects.select_related("vehicle")
    serializer_class = MaintenanceSerializer
    school_lookup = "vehicle__school"
    filterset_fields = ["vehicle", "kind"]

    def perform_create(self, serializer):
        vehicle = serializer.validated_data["vehicle"]
        self.check_vehicle(vehicle)
        instance = serializer.save()
        audit.log(self.request, "create", instance, new=self._snapshot(instance))

    def check_vehicle(self, vehicle):
        u = self.request.user
        if u.role != "akwaba_admin" and vehicle.school_id != u.school_id:
            raise serializers.ValidationError({"vehicle": "Véhicule inaccessible."})


class FuelSerializer(BaseModelSerializer):
    consumption_l_100 = serializers.FloatField(read_only=True)

    class Meta:
        model = FuelRecord
        fields = "__all__"


class FuelViewSet(MaintenanceViewSet):
    resource = "fuel"
    queryset = FuelRecord.objects.select_related("vehicle")
    serializer_class = FuelSerializer
    school_lookup = "vehicle__school"

    def perform_create(self, serializer):
        vehicle = serializer.validated_data["vehicle"]
        self.check_vehicle(vehicle)
        instance = serializer.save()
        if instance.mileage > vehicle.mileage:
            vehicle.mileage = instance.mileage
            vehicle.save(update_fields=["mileage"])
        audit.log(self.request, "create", instance, new=self._snapshot(instance))


RoomSerializer = make_serializer(Room)


class RoomViewSet(ScopedModelViewSet):
    resource = "rooms"
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    learner_lookup = None
    instructor_lookup = SCHOOL


class LessonSerializer(BaseModelSerializer):
    learner_name = serializers.CharField(source="learner.full_name", read_only=True, default=None)
    instructor_name = serializers.CharField(source="instructor.__str__", read_only=True, default=None)
    vehicle_plate = serializers.CharField(source="vehicle.plate", read_only=True, default=None)
    duration_hours = serializers.FloatField(read_only=True)
    evaluation = serializers.SerializerMethodField()

    def get_evaluation(self, lesson):
        ev = next(iter(lesson.evaluations.all()), None)          # une séance ne porte qu'une seule évaluation
        return {"id": ev.id, "average": ev.average} if ev else None

    class Meta:
        model = Lesson
        fields = "__all__"

    def validate(self, attrs):
        start = attrs.get("start", getattr(self.instance, "start", None))
        end = attrs.get("end", getattr(self.instance, "end", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end": "La fin doit être postérieure au début."})
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        learner = attrs.get("learner", getattr(self.instance, "learner", None))
        is_new = self.instance is None
        if kind == "exam" and learner is not None and is_new:
            # §5.2/§6.1 — l'examen de conduite (practice.Lesson kind="exam") n'est programmable
            # qu'une fois le candidat individuel soldé (collectivité : accès complet, pas de palier).
            from apps.admissions.services import PRACTICAL_EXAM_RATIO, payment_ratio
            ratio = payment_ratio(learner)
            if ratio is not None and ratio < PRACTICAL_EXAM_RATIO:
                raise serializers.ValidationError({"kind": f"Examen de conduite non programmable : paiement à {round(float(ratio) * 100)} % "
                                                           "(solde intégral requis, §5.2)."})
        user = self.context["request"].user
        if user.role == "instructor":
            # un moniteur ne planifie que ses propres séances
            own = Instructor.objects.filter(user=user).first()
            if own is None:
                raise serializers.ValidationError({"instructor": "Aucun profil moniteur associé à votre compte."})
            if self.instance is not None and self.instance.instructor_id not in (None, own.id):
                raise serializers.ValidationError({"detail": "Cette séance n'est pas la vôtre."})
            attrs["instructor"] = own
        school = user.school or attrs.get("school") or getattr(self.instance, "school", None)
        if school is not None:
            for key in ("learner", "instructor", "vehicle", "room", "cohort"):
                obj = attrs.get(key)
                if obj is not None and getattr(obj, "school_id", None) != school.id:
                    raise serializers.ValidationError({key: "Hors de l'auto-école."})
        probe = Lesson(school=school, kind=attrs.get("kind", getattr(self.instance, "kind", "practical")),
                       learner=attrs.get("learner", getattr(self.instance, "learner", None)),
                       instructor=attrs.get("instructor", getattr(self.instance, "instructor", None)),
                       vehicle=attrs.get("vehicle", getattr(self.instance, "vehicle", None)),
                       room=attrs.get("room", getattr(self.instance, "room", None)),
                       cohort=attrs.get("cohort", getattr(self.instance, "cohort", None)), start=start, end=end)
        probe.pk = getattr(self.instance, "pk", None)
        status = attrs.get("status", getattr(self.instance, "status", "planned"))
        if status != "cancelled":
            conflicts = services.find_conflicts(probe)
            if conflicts:
                raise serializers.ValidationError({"conflicts": conflicts})
        return attrs


class LessonViewSet(ScopedModelViewSet):
    resource = "lessons"
    queryset = Lesson.objects.select_related("learner", "instructor", "vehicle", "room").prefetch_related("evaluations")
    serializer_class = LessonSerializer
    org_lookup = "learner__organization"
    learner_lookup = "learner__user"
    instructor_lookup = "instructor__user"
    filterset_fields = {"kind": ["exact"], "status": ["exact"], "learner": ["exact"], "instructor": ["exact"],
                        "vehicle": ["exact"], "cohort": ["exact"], "start": ["gte", "lte", "date"]}
    action_verbs = {"complete": "change", "attend": "view"}

    def after_create(self, lesson):
        if lesson.learner and lesson.learner.user:
            notify(lesson.learner.user, "new_lesson", "Nouvelle séance planifiée",
                   f"{lesson.get_kind_display()} le {timezone.localtime(lesson.start):%d/%m/%Y à %H:%M}.",
                   channels=("inapp", "push"))
        if lesson.instructor and lesson.instructor.user:
            notify(lesson.instructor.user, "new_lesson", "Nouvelle séance planifiée",
                   f"{lesson.get_kind_display()} le {timezone.localtime(lesson.start):%d/%m/%Y à %H:%M}.")

    def perform_update(self, serializer):
        old_start = serializer.instance.start
        super().perform_update(serializer)
        lesson = serializer.instance
        if lesson.start != old_start and lesson.learner and lesson.learner.user:
            notify(lesson.learner.user, "planning_change", "Modification de planning",
                   f"Séance déplacée au {timezone.localtime(lesson.start):%d/%m/%Y à %H:%M}.", channels=("inapp", "push"))

    @action(detail=True, methods=["post"])
    def attend(self, request, pk=None):
        """§6 — le candidat marque lui-même sa présence à ses séances, directement dans l'application."""
        lesson = self.get_object()
        if request.user.role == "learner" and getattr(lesson.learner, "user_id", None) != request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Vous ne pouvez marquer votre présence que sur vos propres séances.")
        if lesson.status != "planned":
            return Response({"detail": "Cette séance n'est plus programmée."}, status=400)
        if timezone.now() < lesson.start:
            return Response({"detail": "La séance n'a pas encore commencé."}, status=400)
        lesson.status = "done"
        lesson.save(update_fields=["status", "updated_at"])
        if lesson.learner and lesson.learner.status in ("registered", "new"):
            lesson.learner.status = "in_training"
            lesson.learner.save(update_fields=["status"])
        audit.log(request, "attend_lesson", lesson)
        return Response(self.get_serializer(lesson).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        lesson = self.get_object()
        lesson.status = "done"
        if request.data.get("observations"):
            lesson.observations = request.data["observations"]
        lesson.save()
        if lesson.learner and lesson.learner.status in ("registered", "new"):
            lesson.learner.status = "in_training"
            lesson.learner.save(update_fields=["status"])
        audit.log(request, "complete_lesson", lesson)
        return Response(self.get_serializer(lesson).data)


class EvaluationSerializer(BaseModelSerializer):
    average = serializers.FloatField(read_only=True)
    learner_name = serializers.CharField(source="learner.full_name", read_only=True)

    class Meta:
        model = Evaluation
        fields = "__all__"

    def validate(self, attrs):
        lesson = attrs.get("lesson")
        user = self.context["request"].user
        if user.role == "instructor" and self.instance is None and lesson is None:
            raise serializers.ValidationError({"lesson": "Une évaluation se fait sur une séance : choisissez la séance concernée."})
        if lesson is not None:
            learner = attrs.get("learner") or getattr(self.instance, "learner", None)
            if learner is not None and lesson.learner_id != learner.id:
                raise serializers.ValidationError({"lesson": "Cette séance ne concerne pas cet apprenant."})
            user = self.context["request"].user
            if user.role == "instructor" and getattr(lesson.instructor, "user_id", None) != user.id:
                raise serializers.ValidationError({"lesson": "Vous ne pouvez évaluer que vos propres séances."})
            dup = Evaluation.objects.filter(lesson=lesson)
            if self.instance is not None:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                raise serializers.ValidationError({"lesson": "Cette séance a déjà été évaluée : une seule évaluation par séance."})
        return attrs

    def validate_scores(self, scores):
        from .models import CRITERIA
        keys = {k for k, _ in CRITERIA}
        for k, v in scores.items():
            if k not in keys:
                raise serializers.ValidationError(f"Critère inconnu : {k}")
            if v is not None and not 0 <= float(v) <= 10:
                raise serializers.ValidationError(f"{k} : note entre 0 et 10.")
        return scores


class EvaluationViewSet(ScopedModelViewSet):
    resource = "evaluations"
    queryset = Evaluation.objects.select_related("learner")
    serializer_class = EvaluationSerializer
    org_lookup = "learner__organization"
    learner_lookup = "learner__user"
    instructor_lookup = "instructor__user"
    filterset_fields = ["learner", "instructor", "lesson"]

    def before_create(self, serializer, kwargs):
        u = self.request.user
        if u.role == INSTRUCTOR and "instructor" not in serializer.validated_data:
            kwargs["instructor"] = Instructor.objects.filter(user=u).first()


# --------------------------------------------------------------------------- classes virtuelles
def vclass_status(vc, now=None):
    now = now or timezone.now()
    if now < vc.scheduled_start:
        return "scheduled"
    return "live" if now <= vc.scheduled_end else "ended"


class VirtualClassSerializer(BaseModelSerializer):
    status = serializers.SerializerMethodField()
    duration_minutes = serializers.SerializerMethodField()
    instructor_name = serializers.SerializerMethodField()
    attendances = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()
    joined = serializers.SerializerMethodField()

    class Meta:
        model = VirtualClass
        fields = "__all__"
        read_only_fields = ["created_by"]

    def get_status(self, vc):
        return vclass_status(vc)

    def get_instructor_name(self, vc):
        return str(vc.instructor) if vc.instructor_id else None

    def get_duration_minutes(self, vc):
        return int((vc.scheduled_end - vc.scheduled_start).total_seconds() // 60)

    def get_attendances(self, vc):
        return [{"user": a.user_id, "joined_at": a.joined_at} for a in vc.attendances.all()]

    def _is_learner(self):
        return getattr(self.context["request"].user, "role", None) == LEARNER

    def get_questions(self, vc):
        user = self.context["request"].user
        rows = vc.questions.all()
        if self._is_learner():   # un apprenant ne voit que ses propres questions
            rows = [q for q in rows if q.user_id == user.id]
        return [{"id": q.id, "question": q.question, "answer": q.answer, "user": q.user_id,
                 "user_name": q.user.get_full_name() or q.user.email, "created_at": q.created_at} for q in rows]

    def get_joined(self, vc):
        uid = self.context["request"].user.id
        return any(a.user_id == uid and a.joined_at for a in vc.attendances.all())

    def to_representation(self, vc):
        data = super().to_representation(vc)
        if self._is_learner():
            data.pop("host_url", None)   # lien hôte réservé à l'équipe pédagogique
        return data

    def validate(self, attrs):
        start = attrs.get("scheduled_start", getattr(self.instance, "scheduled_start", None))
        end = attrs.get("scheduled_end", getattr(self.instance, "scheduled_end", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"scheduled_end": "La fin doit être postérieure au début."})
        return attrs


class VirtualClassViewSet(ScopedModelViewSet):
    """Classes virtuelles : planifiées par l'équipe, rejointes (présence enregistrée) par les apprenants, rediffusées ensuite."""
    resource = "virtual_classes"
    queryset = VirtualClass.objects.select_related("instructor").prefetch_related("attendances", "questions__user")
    serializer_class = VirtualClassSerializer
    learner_lookup = SCHOOL
    instructor_lookup = SCHOOL
    action_verbs = {"join": "view", "leave": "view", "ask": "view", "answer": "change"}
    filterset_fields = ["provider", "cohort", "instructor"]
    search_fields = ["title"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == LEARNER:
            from apps.learners.models import Learner
            learner = Learner.objects.filter(user=user).first()
            cohort_id = learner.cohort_id if learner else None
            qs = qs.filter(models_q_cohort(cohort_id))
        return qs

    def before_create(self, serializer, kwargs):
        kwargs["created_by"] = self.request.user

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        """Rejoindre la classe : la présence du candidat est enregistrée directement dans l'application."""
        vc = self.get_object()
        if vclass_status(vc) == "ended":
            return Response({"detail": "Cette classe est terminée."}, status=400)
        att, _ = VirtualClassAttendance.objects.get_or_create(virtual_class=vc, user=request.user)
        att.joined_at = timezone.now()
        att.save(update_fields=["joined_at", "updated_at"])
        return Response({"join_url": vc.join_url, "passcode": vc.passcode})

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        vc = self.get_object()
        att = VirtualClassAttendance.objects.filter(virtual_class=vc, user=request.user).first()
        if att and att.joined_at:
            att.left_at = timezone.now()
            att.duration_seconds = int((att.left_at - att.joined_at).total_seconds())
            att.save(update_fields=["left_at", "duration_seconds", "updated_at"])
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        vc = self.get_object()
        text = (request.data.get("question") or "").strip()
        if not text:
            return Response({"question": "Saisissez votre question."}, status=400)
        VirtualClassQuestion.objects.create(virtual_class=vc, user=request.user, question=text)
        return Response(self.get_serializer(vc).data, status=201)

    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        vc = self.get_object()
        q = vc.questions.filter(pk=request.data.get("question_id")).first()
        if q is None:
            return Response({"detail": "Question introuvable."}, status=404)
        q.answer = request.data.get("answer", "")
        q.answered_by = request.user
        q.answered_at = timezone.now()
        q.save(update_fields=["answer", "answered_by", "answered_at", "updated_at"])
        return Response(self.get_serializer(vc).data)


def models_q_cohort(cohort_id):
    from django.db.models import Q
    return Q(cohort__isnull=True) | Q(cohort_id=cohort_id) if cohort_id else Q(cohort__isnull=True)
