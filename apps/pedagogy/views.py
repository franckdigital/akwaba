from django.db.models import Avg, Case, Count, IntegerField, Sum, When
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core import audit
from apps.core.permissions import AKWABA_ADMIN, LEARNER, allowed
from apps.core.viewsets import SCHOOL, BaseModelSerializer, ScopedModelViewSet, make_serializer, scope_queryset
from apps.learners.models import Learner

from . import services
from .models import THEMES, Attempt, AttemptAnswer, Choice, Course, CourseMaterial, ImportJob, Question, Quiz


# --------------------------------------------------------------------------- cours
class CourseMaterialSerializer(BaseModelSerializer):
    class Meta:
        model = CourseMaterial
        fields = "__all__"


class CourseSerializer(BaseModelSerializer):
    materials = CourseMaterialSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = "__all__"


class CourseViewSet(ScopedModelViewSet):
    resource = "courses"
    queryset = Course.objects.prefetch_related("materials")
    serializer_class = CourseSerializer
    include_global = True
    learner_lookup = SCHOOL
    instructor_lookup = SCHOOL
    filterset_fields = ["training", "theme", "kind", "is_published"]
    search_fields = ["title", "content"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == LEARNER:
            qs = qs.filter(is_published=True)
        return qs


class MaterialViewSet(ScopedModelViewSet):
    resource = "courses"
    queryset = CourseMaterial.objects.all()
    serializer_class = CourseMaterialSerializer
    school_lookup = "course__school"
    include_global = True
    learner_lookup = SCHOOL
    instructor_lookup = SCHOOL
    filterset_fields = ["course"]


# --------------------------------------------------------------------------- questions
class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ["id", "label", "text", "is_correct", "order"]


class QuestionSerializer(BaseModelSerializer):
    choices = ChoiceSerializer(many=True)

    class Meta:
        model = Question
        fields = "__all__"
        validators = []  # unicité (école, code) vérifiée dans validate() : l'école est déduite de l'utilisateur

    def validate(self, attrs):
        request = self.context.get("request")
        if "code" in attrs or self.instance is None:
            if self.instance is not None:
                school_id = self.instance.school_id
            elif attrs.get("school") is not None:
                school_id = attrs["school"].id
            else:
                school_id = getattr(request.user, "school_id", None) if request else None
            dup = Question.objects.filter(school_id=school_id, code=attrs.get("code", getattr(self.instance, "code", "")))
            if self.instance is not None:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                raise serializers.ValidationError({"code": "Ce code existe déjà dans votre banque de questions."})
        qtype = attrs.get("qtype", getattr(self.instance, "qtype", Question.SINGLE))
        choices = attrs.get("choices")
        if choices is None:
            return attrs
        good = [c for c in choices if c.get("is_correct")]
        if qtype == Question.TF:
            if len(choices) != 2 or len(good) != 1:
                raise serializers.ValidationError({"choices": "Vrai/Faux : deux propositions dont une seule correcte."})
        elif qtype == Question.SINGLE:
            if len(choices) < 2 or len(good) != 1:
                raise serializers.ValidationError({"choices": "Réponse unique : au moins 2 propositions, une seule correcte."})
        else:
            if len(choices) < 2 or len(good) < 1:
                raise serializers.ValidationError({"choices": "Choix multiple : au moins 2 propositions dont 1 correcte."})
        return attrs

    def _save_choices(self, question, choices):
        question.choices.all().delete()
        Choice.objects.bulk_create([Choice(question=question, order=i, **c) for i, c in enumerate(
            [{k: v for k, v in c.items() if k not in ("id", "order")} for c in choices])])

    def create(self, validated):
        choices = validated.pop("choices", [])
        q = super().create(validated)
        self._save_choices(q, choices)
        return q

    def update(self, instance, validated):
        choices = validated.pop("choices", None)
        q = super().update(instance, validated)
        if choices is not None:
            self._save_choices(q, choices)
        return q


class QuestionViewSet(ScopedModelViewSet):
    resource = "questions"
    queryset = Question.objects.prefetch_related("choices")
    serializer_class = QuestionSerializer
    include_global = True
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_verbs = {"import_excel": "create", "import_template": "view", "export": "export", "bulk": "change",
                    "analytics": "view", "stats": "view", "image": "change"}
    filterset_fields = ["category", "theme", "difficulty", "qtype", "is_active", "school"]
    search_fields = ["code", "text", "subtheme"]

    def _guard_global(self, instance):
        if instance.school_id is None and self.request.user.role != AKWABA_ADMIN:
            raise PermissionDenied("Question de la banque centrale : modification réservée à Akwaba.")

    def perform_update(self, serializer):
        self._guard_global(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._guard_global(instance)
        super().perform_destroy(instance)

    # ---- actions groupées : supprimer / activer / désactiver / dupliquer
    @action(detail=False, methods=["post"])
    def bulk(self, request):
        act = request.data.get("action")
        ids = request.data.get("ids") or []
        if act not in ("delete", "activate", "deactivate", "duplicate") or not ids:
            return Response({"detail": "Action ou sélection invalide."}, status=400)
        if act == "delete" and not allowed(request.user, "questions", "delete"):
            raise PermissionDenied("Suppression non autorisée.")
        if act == "duplicate" and not allowed(request.user, "questions", "create"):
            raise PermissionDenied("Création non autorisée.")
        qs = self.get_queryset().filter(pk__in=ids)
        if request.user.role != AKWABA_ADMIN:
            qs = qs.filter(school=request.user.school)  # la banque centrale n'est modifiable que par Akwaba
        n = 0
        if act == "delete":
            n = qs.count()
            audit.log(request, "bulk_delete_questions", model="pedagogy.Question", new={"ids": list(qs.values_list("id", flat=True))})
            qs.delete()
        elif act in ("activate", "deactivate"):
            n = qs.update(is_active=(act == "activate"))
            audit.log(request, "bulk_" + act + "_questions", model="pedagogy.Question", new={"count": n})
        else:
            for q in qs.prefetch_related("choices"):
                base, i = q.code + "-COPIE", 1
                code = base
                while Question.objects.filter(school=q.school, code=code).exists():
                    i += 1
                    code = base + str(i)
                copy = Question.objects.create(school=q.school, code=code, category=q.category, theme=q.theme, subtheme=q.subtheme,
                                               difficulty=q.difficulty, qtype=q.qtype, text=q.text, explanation=q.explanation,
                                               is_active=False)
                Choice.objects.bulk_create([Choice(question=copy, label=c.label, text=c.text, is_correct=c.is_correct, order=c.order)
                                            for c in q.choices.all()])
                n += 1
        return Response({"action": act, "count": n})

    # ---- export de la banque au format d'import (ré-importable)
    @action(detail=False, methods=["get"])
    def export(self, request):
        from openpyxl import Workbook
        labels = dict(THEMES)
        types = dict(Question.TYPES)
        diffs = {"easy": "Facile", "medium": "Moyen", "hard": "Difficile"}
        wb = Workbook()
        ws = wb.active
        ws.title = "QCM"
        ws.append(services.COLUMNS + services.OPTIONAL_COLUMNS)
        for q in self.filter_queryset(self.get_queryset()).prefetch_related("choices"):
            ch = list(q.choices.all())
            opts = ["", "", "", ""]
            good = []
            if q.qtype == Question.TF:
                good = ["Vrai" if c.text.lower().startswith("v") else "Faux" for c in ch if c.is_correct][:1]
            else:
                for i, c in enumerate(ch[:4]):
                    opts[i] = c.text
                    if c.is_correct:
                        good.append("ABCD"[i])
            ws.append([q.code, q.category, labels.get(q.theme, q.theme), types[q.qtype], q.text, *opts, ",".join(good), q.explanation,
                       q.subtheme, diffs.get(q.difficulty, "Moyen")])
        resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = 'attachment; filename="banque_questions.xlsx"'
        wb.save(resp)
        audit.log(request, "export_questions", model="pedagogy.Question")
        return resp

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        q = self.get_object()
        agg = AttemptAnswer.objects.filter(question=q, answered=True).aggregate(
            n=Count("id"), ok=Sum(Case(When(is_correct=True, then=1), default=0, output_field=IntegerField())))
        n, ok = agg["n"] or 0, agg["ok"] or 0
        return Response({"answered": n, "correct": ok, "success_rate": round(ok * 100 / n, 1) if n else None,
                         "quizzes": q.quizzes.count()})

    @action(detail=True, methods=["post", "delete"], parser_classes=[MultiPartParser])
    def image(self, request, pk=None):
        q = self.get_object()
        self._guard_global(q)
        if request.method == "DELETE":
            q.image.delete(save=True)
        else:
            f = request.FILES.get("image")
            if not f or not (f.content_type or "").startswith("image/"):
                return Response({"image": "Fichier image requis."}, status=400)
            if f.size > 5 * 1024 * 1024:
                return Response({"image": "Image trop lourde (5 Mo max)."}, status=400)
            q.image = f
            q.save()
        return Response(self.get_serializer(q).data)

    @action(detail=False, methods=["get"])
    def analytics(self, request):
        """Vue d'ensemble de la banque + difficulté réelle des questions (taux de réussite observé)."""
        qs = self.get_queryset()

        def group(field):
            return {r[field]: r["c"] for r in qs.values(field).annotate(c=Count("id"))}
        ans = AttemptAnswer.objects.filter(answered=True, question__in=qs)
        rows = list(ans.values("question", "question__code", "question__text", "question__theme").annotate(
            n=Count("id"), ok=Sum(Case(When(is_correct=True, then=1), default=0, output_field=IntegerField()))))
        for r in rows:
            r["rate"] = round(r["ok"] * 100 / r["n"], 1)
        rated = [r for r in rows if r["n"] >= 3]
        by_theme = {}
        for r in rows:
            t = by_theme.setdefault(r["question__theme"], [0, 0])
            t[0] += r["n"]
            t[1] += r["ok"]
        labels = dict(THEMES)
        return Response({
            "total": qs.count(), "active": qs.filter(is_active=True).count(), "central": qs.filter(school__isnull=True).count(),
            "by_theme": group("theme"), "by_type": group("qtype"), "by_difficulty": group("difficulty"), "by_category": group("category"),
            "never_answered": qs.exclude(id__in=[r["question"] for r in rows]).count(),
            "theme_success": [{"theme": k, "label": labels.get(k, k), "answered": v[0], "rate": round(v[1] * 100 / v[0], 1)}
                              for k, v in by_theme.items()],
            "hardest": sorted(rated, key=lambda r: r["rate"])[:10],
            "easiest": sorted(rated, key=lambda r: -r["rate"])[:10],
        })

    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request):
        resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        blank = str(request.query_params.get("blank", "")).lower() in ("1", "true", "yes")
        resp["Content-Disposition"] = 'attachment; filename="%s"' % ("modele_vide_import_qcm.xlsx" if blank else "modele_import_qcm.xlsx")
        services.build_template(blank=blank).save(resp)
        return resp

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def import_excel(self, request):
        """Analyse (dry_run=true, défaut) ou importe (dry_run=false) un fichier Excel de questions."""
        f = request.FILES.get("file")
        if not f:
            return Response({"file": "Fichier requis."}, status=400)
        commit = str(request.data.get("dry_run", "true")).lower() in ("false", "0", "no")
        update = str(request.data.get("update_existing", "false")).lower() in ("true", "1", "yes")
        school = request.user.school
        if request.user.role == AKWABA_ADMIN:
            school = None
            if request.data.get("school"):
                from apps.schools.models import School
                school = School.objects.filter(pk=request.data["school"]).first()
        quiz = None
        if request.data.get("quiz"):
            quiz = Quiz.objects.filter(pk=request.data["quiz"]).first()
            if quiz is None or (request.user.role != AKWABA_ADMIN and quiz.school_id != request.user.school_id):
                return Response({"quiz": "Questionnaire introuvable."}, status=400)
            if request.user.role == AKWABA_ADMIN:
                school = quiz.school
        title = (request.data.get("new_quiz_title") or "").strip()
        if quiz and title:
            return Response({"detail": "Choisissez un questionnaire existant OU un nouveau titre."}, status=400)
        job = services.import_questions(f, school, request.user, f.name, commit, quiz=quiz, update_existing=update, new_quiz_title=title,
                                        images=services.collect_images(request.FILES.getlist("images")))
        audit.log(request, "import_questions" if commit else "analyse_import", job, new={
            "total": job.total, "valid": job.valid, "errors": job.error_count, "quiz": getattr(job.quiz, "id", None)},
            school_id=getattr(school, "id", None))
        return Response(ImportJobSerializer(job).data, status=201)


class ImportJobSerializer(serializers.ModelSerializer):
    errors = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    quiz_title = serializers.CharField(source="quiz.title", read_only=True, default=None)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True, default=None)

    class Meta:
        model = ImportJob
        fields = ["id", "filename", "quiz", "quiz_title", "user_name", "update_existing", "dry_run", "total", "valid", "imported",
                  "updated", "duplicates", "error_count", "errors", "preview", "summary", "created_at"]

    def get_errors(self, job):
        return [{k: v for k, v in e.items() if k != "data"} for e in job.errors[:200]]

    def get_summary(self, job):
        return f"{job.total} questions analysées — {job.valid} valides — {job.error_count} erreurs"


class ImportJobViewSet(ScopedModelViewSet):
    resource = "imports"
    queryset = ImportJob.objects.all()
    serializer_class = ImportJobSerializer
    http_method_names = ["get", "head", "options"]
    action_verbs = {"errors": "view"}
    filterset_fields = ["dry_run", "quiz"]

    @action(detail=True, methods=["get"])
    def errors(self, request, pk=None):
        job = self.get_object()
        resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="erreurs_import_{job.pk}.xlsx"'
        services.errors_workbook(job).save(resp)
        return resp


# --------------------------------------------------------------------------- questionnaires
class QuizSerializer(BaseModelSerializer):
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = "__all__"
        read_only_fields = ["is_exam"]

    def get_question_count(self, quiz):
        if quiz.mode == Quiz.MANUAL:
            return quiz.questions.count()
        return quiz.num_questions

    def validate_pass_threshold(self, v):
        if not 1 <= v <= 100:
            raise serializers.ValidationError("Seuil entre 1 et 100.")
        return v


class QuizAdminActions:
    """Gestion des questionnaires / examens (composition, aperçu, duplication, statistiques).

    Toutes ces actions exigent le droit « change » : elles exposent les bonnes réponses,
    donc jamais accessibles aux apprenants.
    """

    def _scoped_questions(self, ids):
        qs = Question.objects.filter(pk__in=ids)
        u = self.request.user
        if u.role != AKWABA_ADMIN:
            qs = qs.filter(school=u.school) | qs.filter(school__isnull=True)
        return qs

    @action(detail=True, methods=["post"])
    def compose(self, request, pk=None):
        """Ajoute / retire / remplace les questions d'un questionnaire (mode manuel)."""
        quiz = self.get_object()
        if quiz.school_id is None and request.user.role != AKWABA_ADMIN:
            raise PermissionDenied("Questionnaire central : modification réservée à Akwaba.")
        d = request.data
        if d.get("set") is not None:
            quiz.questions.set(self._scoped_questions(d["set"]))
        if d.get("add"):
            quiz.questions.add(*self._scoped_questions(d["add"]))
        if d.get("remove"):
            quiz.questions.remove(*d["remove"])
        quiz.mode = Quiz.MANUAL
        quiz.num_questions = quiz.questions.count()
        quiz.save(update_fields=["mode", "num_questions", "updated_at"])
        audit.log(request, "compose_quiz", quiz, new={"questions": quiz.num_questions})
        return Response({"question_count": quiz.num_questions})

    @action(detail=True, methods=["get"])
    def questions(self, request, pk=None):
        quiz = self.get_object()
        if quiz.mode == Quiz.MANUAL:
            qs = quiz.questions.prefetch_related("choices")
        else:  # aperçu du réservoir de tirage
            qs = services.question_pool(quiz, quiz.school or request.user.school).prefetch_related("choices")
        return Response({"mode": quiz.mode, "count": qs.count(), "questions": QuestionSerializer(qs[:500], many=True).data})

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        quiz = self.get_object()
        qs = list(quiz.questions.all())
        quiz.pk = None
        quiz.title = quiz.title + " (copie)"
        quiz.is_published = False
        quiz.save()
        quiz.questions.set(qs)
        audit.log(request, "duplicate_quiz", quiz)
        return Response(self.get_serializer(quiz).data, status=201)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        quiz = self.get_object()
        done = Attempt.objects.filter(quiz=quiz).exclude(status=Attempt.IN_PROGRESS)
        n = done.count()
        per_q = list(AttemptAnswer.objects.filter(attempt__in=done, answered=True).values("question", "question__code", "question__text")
                     .annotate(n=Count("id"), ok=Sum(Case(When(is_correct=True, then=1), default=0, output_field=IntegerField()))))
        for r in per_q:
            r["rate"] = round(r["ok"] * 100 / r["n"], 1)
        avg = done.aggregate(a=Avg("percent"), d=Avg("duration_seconds"))
        return Response({
            "attempts": n, "learners": done.values("learner").distinct().count(),
            "average_percent": round(float(avg["a"] or 0), 1), "average_duration_seconds": int(avg["d"] or 0),
            "pass_rate": round(done.filter(passed=True).count() * 100 / n, 1) if n else 0,
            "hardest": sorted(per_q, key=lambda r: r["rate"])[:5],
        })


class QuizViewSet(QuizAdminActions, ScopedModelViewSet):
    resource = "quizzes"
    queryset = Quiz.objects.filter(is_exam=False)
    serializer_class = QuizSerializer
    include_global = True
    learner_lookup = SCHOOL
    instructor_lookup = SCHOOL
    action_verbs = {"start": "view", "compose": "change", "questions": "change", "duplicate": "create", "stats": "change"}
    filterset_fields = ["category", "mode", "training", "is_published", "school"]
    search_fields = ["title"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == LEARNER:
            u = self.request.user
            qs = qs.filter(is_published=True, category=getattr(getattr(u, "learner_profile", None), "category", "B"))
        return qs

    def before_create(self, serializer, kwargs):
        serializer.validated_data["is_exam"] = False

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        quiz = self.get_object()
        learner = Learner.objects.filter(user=request.user).first()
        if request.user.role != LEARNER or learner is None:
            raise PermissionDenied("Réservé aux apprenants.")
        attempt = services.start_attempt(quiz, learner)
        return Response(AttemptViewSet.detail_payload(attempt), status=201)


# --------------------------------------------------------------------------- tentatives
class AttemptViewSet(ScopedModelViewSet):
    resource = "attempts"
    queryset = Attempt.objects.select_related("quiz", "learner")
    serializer_class = serializers.Serializer
    org_lookup = "learner__organization"
    learner_lookup = "learner__user"
    instructor_lookup = "learner__lessons__instructor__user"
    http_method_names = ["get", "post", "head", "options"]
    action_verbs = {"answer": "change", "finish": "change", "review": "view", "progress": "view", "reset": "delete"}
    filterset_fields = ["quiz", "learner", "status", "passed", "is_exam"]
    search_fields = ["learner__last_name", "learner__first_name", "learner__matricule", "quiz__title"]
    ordering_fields = ["started_at", "percent"]

    @staticmethod
    def detail_payload(attempt):
        attempt = Attempt.objects.select_related("quiz").get(pk=attempt.pk)
        data = services.attempt_summary(attempt)
        data["duration_limit_minutes"] = attempt.quiz.duration_minutes
        data["show_corrections"] = attempt.quiz.show_corrections
        if attempt.status == Attempt.IN_PROGRESS:
            data["questions"] = services.attempt_questions(attempt)
        else:
            data["review"] = services.attempt_review(attempt)
        return data

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        rows = [services.attempt_summary(a) | {"learner": a.learner_id, "learner_name": a.learner.full_name}
                for a in (page if page is not None else qs)]
        return self.get_paginated_response(rows) if page is not None else Response(rows)

    def retrieve(self, request, *args, **kwargs):
        return Response(self.detail_payload(self.get_object()))

    def _own_attempt(self):
        attempt = self.get_object()
        if attempt.learner.user_id != self.request.user.id:
            raise PermissionDenied("Cette tentative ne vous appartient pas.")
        return attempt

    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        attempt = self._own_attempt()
        ans = services.answer_question(attempt, request.data.get("question"), request.data.get("choices") or [])
        if attempt.quiz.show_corrections:
            return Response(services.correction_payload(ans))
        return Response({"question": ans.question_id, "answered": True})

    @action(detail=True, methods=["post"])
    def finish(self, request, pk=None):
        attempt = self._own_attempt()
        attempt = services.finish_attempt(attempt)
        return Response(self.detail_payload(attempt))

    @action(detail=True, methods=["get"])
    def review(self, request, pk=None):
        attempt = self.get_object()
        if attempt.status == Attempt.IN_PROGRESS:
            raise PermissionDenied("Tentative en cours.")
        return Response(self.detail_payload(attempt))

    @action(detail=False, methods=["get"])
    def progress(self, request):
        learner = Learner.objects.filter(user=request.user).first()
        if not learner:
            return Response({"detail": "Aucun dossier apprenant."}, status=404)
        return Response(services.learner_progress(learner))


def _reset_attempt(self, request, pk=None):
    """Supprime une tentative pour permettre à l'apprenant de la repasser (action tracée dans l'audit)."""
    attempt = self.get_object()
    if hasattr(attempt, "certificate"):
        return Response({"detail": "Un certificat a été délivré pour cette tentative : elle ne peut pas être réinitialisée."}, status=400)
    audit.log(request, "reset_attempt", attempt, old=services.attempt_summary(attempt))
    attempt.delete()
    return Response(status=204)


_reset_attempt.__name__ = "reset"
AttemptViewSet.reset = action(detail=True, methods=["post"])(_reset_attempt)
