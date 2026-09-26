import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core import audit
from apps.core.notify import notify
from apps.core.permissions import (AKWABA_ADMIN, DIRECTOR, LEARNER, ORG_ADMIN, ORG_ROLES, SCHOOL_ROLES, INSTRUCTOR,
                                   permissions_for)
from apps.core.viewsets import BaseModelSerializer, ScopedModelViewSet

from apps.organizations.models import Cohort

from . import services as acc_services
from .models import User, VerificationCode


class UserSerializer(BaseModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    cohort = serializers.PrimaryKeyRelatedField(queryset=Cohort.objects.all(), required=False, allow_null=True, write_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    multi_agency = serializers.BooleanField(source="school.multi_agency", read_only=True, default=False)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "full_name", "phone", "role", "role_label", "school", "agency",
                  "organization", "cohort", "email_verified", "phone_verified", "is_active", "password", "date_joined", "voice_enabled", "multi_agency"]
        read_only_fields = ["email_verified", "phone_verified", "date_joined", "voice_enabled"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_email(self, value):
        return value.lower()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        learner = getattr(instance, "learner_profile", None)
        data["cohort"] = learner.cohort_id if learner else None
        data["cohort_name"] = learner.cohort.name if learner and learner.cohort else None
        data["organization_name"] = instance.organization.name if instance.organization_id else None
        return data


def tokens_for(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def session_payload(user):
    return {**tokens_for(user), "user": UserSerializer(user).data, "permissions": permissions_for(user)}


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        ident = (request.data.get("identifier") or request.data.get("email") or "").strip()
        password = request.data.get("password") or ""
        if "@" in ident or not ident:
            email = ident.lower()
        else:                                    # connexion par numéro de téléphone (application mobile)
            found = acc_services.users_by_phone(ident)
            if len(found) > 1:
                return Response({"detail": "Plusieurs comptes utilisent ce numéro : connectez-vous avec votre e-mail."}, status=400)
            email = found[0].email if found else ident.lower()
        user = User.objects.filter(email=email).first()
        if user and user.is_locked:
            audit.log(request, "login_locked", user=user, model="accounts.User")
            return Response({"detail": "Compte temporairement verrouillé. Réessayez plus tard."},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        auth = authenticate(request, username=email, password=password)
        if auth is None:
            if user:
                user.failed_attempts += 1
                if user.failed_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                    user.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                    user.failed_attempts = 0
                user.save(update_fields=["failed_attempts", "locked_until"])
            audit.log(request, "login_failed", user=user, model="accounts.User", new={"email": email})
            return Response({"detail": "Identifiants invalides."}, status=status.HTTP_401_UNAUTHORIZED)
        if not auth.is_active:
            return Response({"detail": "Compte désactivé."}, status=status.HTTP_403_FORBIDDEN)
        auth.failed_attempts = 0
        auth.locked_until = None
        auth.save(update_fields=["failed_attempts", "locked_until"])
        audit.log(request, "login", user=auth, model="accounts.User")
        return Response(session_payload(auth))


class LogoutView(APIView):
    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh")).blacklist()
        except TokenError:
            pass
        audit.log(request, "logout", model="accounts.User")
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        data = UserSerializer(request.user).data
        return Response({"user": data, "permissions": permissions_for(request.user)})

    def patch(self, request):
        ser = UserSerializer(request.user, data={k: v for k, v in request.data.items()
                                                 if k in ("first_name", "last_name", "phone")}, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class ChangePasswordView(APIView):
    def post(self, request):
        old, new = request.data.get("old_password", ""), request.data.get("new_password", "")
        if not request.user.check_password(old):
            return Response({"detail": "Ancien mot de passe incorrect."}, status=400)
        try:
            validate_password(new, request.user)
        except Exception as e:
            return Response({"new_password": list(getattr(e, "messages", [str(e)]))}, status=400)
        request.user.set_password(new)
        request.user.save()
        for t in OutstandingToken.objects.filter(user=request.user):
            from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
            BlacklistedToken.objects.get_or_create(token=t)
        audit.log(request, "password_change", request.user)
        return Response({"detail": "Mot de passe modifié. Reconnectez-vous."})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        user = User.objects.filter(email=(request.data.get("email") or "").lower(), is_active=True).first()
        if user:
            code = VerificationCode.issue(user, "reset")
            send_mail("Réinitialisation de mot de passe Akwaba",
                      f"Votre code de réinitialisation : {code.code} (valable 30 minutes).", None, [user.email],
                      fail_silently=True)
        # réponse identique dans tous les cas (pas d'énumération de comptes)
        return Response({"detail": "Si le compte existe, un code a été envoyé."})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verify"

    def post(self, request):
        user = User.objects.filter(email=(request.data.get("email") or "").lower()).first()
        new = request.data.get("new_password", "")
        if not user or not VerificationCode.consume(user, "reset", request.data.get("code", "")):
            return Response({"detail": "Code invalide ou expiré."}, status=400)
        try:
            validate_password(new, user)
        except Exception as e:
            return Response({"new_password": list(getattr(e, "messages", [str(e)]))}, status=400)
        user.set_password(new)
        user.failed_attempts, user.locked_until = 0, None
        user.save()
        audit.log(request, "password_reset", user, user=user)
        return Response({"detail": "Mot de passe réinitialisé."})


class RequestVerificationView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verify"

    def post(self, request):
        purpose = request.data.get("channel", "email")
        if purpose not in ("email", "phone"):
            return Response({"detail": "Canal invalide."}, status=400)
        code = VerificationCode.issue(request.user, purpose)
        if purpose == "email":
            send_mail("Vérification de votre e-mail Akwaba", f"Code : {code.code}", None, [request.user.email],
                      fail_silently=True)
        else:
            notify(request.user, "verification", "Code de vérification Akwaba", f"Code : {code.code}", channels=("sms",))
        return Response({"detail": "Code envoyé."})


class ConfirmVerificationView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verify"

    def post(self, request):
        purpose = request.data.get("channel", "email")
        if purpose not in ("email", "phone") or not VerificationCode.consume(request.user, purpose, request.data.get("code", "")):
            return Response({"detail": "Code invalide ou expiré."}, status=400)
        field = "email_verified" if purpose == "email" else "phone_verified"
        setattr(request.user, field, True)
        request.user.save(update_fields=[field])
        return Response({"detail": "Vérifié."})


class SessionsView(APIView):
    """Sessions actives (refresh tokens non révoqués) + révocation."""

    def get(self, request):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        black = set(BlacklistedToken.objects.filter(token__user=request.user).values_list("token_id", flat=True))
        rows = [{"id": t.id, "created_at": t.created_at, "expires_at": t.expires_at}
                for t in OutstandingToken.objects.filter(user=request.user, expires_at__gt=timezone.now())
                if t.id not in black]
        return Response(rows)

    def delete(self, request):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        for t in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=t)
        return Response(status=204)


class RegisterSerializer(serializers.Serializer):
    school = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    password = serializers.CharField(min_length=8)
    category = serializers.CharField(required=False, default="B")
    training = serializers.IntegerField(required=False, allow_null=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    sex = serializers.CharField(required=False, allow_blank=True, default="")
    # §4 — à titre personnel ou au titre d'une collectivité ; zone géographique déclarée (§4.1/§5.1) ;
    # devis individuel d'origine, le cas échéant (§2, parcours devis -> inscription).
    zone = serializers.CharField(required=False, allow_blank=True, default="")
    organization = serializers.IntegerField(required=False, allow_null=True)
    id_document_no = serializers.CharField(required=False, allow_blank=True, default="")
    quote = serializers.IntegerField(required=False, allow_null=True)

    def validate_email(self, v):
        if User.objects.filter(email=v.lower()).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cet e-mail.")
        return v.lower()

    def validate_password(self, v):
        validate_password(v)
        return v


class RegisterView(APIView):
    """Inscription en ligne d'un apprenant auprès d'une auto-école."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @transaction.atomic
    def post(self, request):
        import hashlib
        from apps.admissions.models import IndividualQuote
        from apps.learners.models import Learner
        from apps.organizations.models import Organization
        from apps.schools.models import School, Training
        from apps.schools.services import check_limit
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        school = School.objects.filter(pk=d["school"], is_active=True).first()
        if not school:
            return Response({"school": "Auto-école introuvable."}, status=400)
        # §4.1/§5.1 — la zone couverte est vérifiée au moment où le candidat la renseigne dans le formulaire.
        zone = (d.get("zone") or "").strip()
        covered = school.covered_zones or []
        if covered and zone and zone not in covered:
            return Response({"zone": f"Zone non couverte par l'auto-école (zones couvertes : {', '.join(covered)})."}, status=400)
        # Garde-fou technique local (distinct de la vérification manuelle de la base du ministère, §4.1,
        # qui reste une action externe faite par la secrétaire) : pas deux dossiers Akwaba pour la même pièce.
        id_doc = (d.get("id_document_no") or "").strip()
        if id_doc:
            h = hashlib.sha256(id_doc.upper().encode()).hexdigest()
            if Learner.objects.filter(id_document_hash=h).exists():
                return Response({"id_document_no": "Un dossier existe déjà dans le système pour cette pièce d'identité."}, status=400)
        organization = Organization.objects.filter(pk=d.get("organization"), school=school, is_active=True).first() if d.get("organization") else None
        quote = IndividualQuote.objects.filter(pk=d.get("quote")).first() if d.get("quote") else None
        check_limit(school, "learners")
        training = Training.objects.filter(pk=d.get("training"), school=school).first() if d.get("training") else None
        user = User.objects.create_user(d["email"], d["password"], first_name=d["first_name"], last_name=d["last_name"],
                                        phone=d["phone"], role=LEARNER, school=school, organization=organization)
        learner = Learner.objects.create(user=user, school=school, organization=organization, first_name=d["first_name"], last_name=d["last_name"],
                                         email=d["email"], phone=d["phone"], category=d["category"], training=training,
                                         birth_date=d.get("birth_date"), sex=d["sex"], source="online", status="new",
                                         zone=zone, id_document_no=id_doc, quote=quote, approval_status="pending")
        audit.log(request, "register", learner, user=user, new={"email": user.email})
        notify(user, "registration", "Inscription reçue",
              f"Votre inscription à {school} est en cours d'examen par le secrétariat.")
        for staff in User.objects.filter(role__in=["secretary", "director"], school=school, is_active=True):
            notify(staff, "registration_pending", "Nouvelle inscription à approuver", f"{learner.full_name} — dossier en attente.")
        payload = session_payload(user)
        payload["registration_pending_approval"] = True
        return Response(payload, status=201)


class UserViewSet(ScopedModelViewSet):
    resource = "users"
    queryset = User.objects.select_related("school").all()
    serializer_class = UserSerializer
    org_lookup = "organization"
    school_lookup = "school"
    filterset_fields = ["role", "is_active", "school", "organization"]
    search_fields = ["email", "first_name", "last_name", "phone"]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if u.role == LEARNER or u.role == INSTRUCTOR:
            return qs.filter(pk=u.pk)
        return qs

    action_verbs = {"assign": "change", "import_excel": "create", "import_template": "view"}

    @action(detail=False, methods=["post"])
    def assign(self, request):
        """Rattache des comptes (en lot) à une entreprise et/ou une cohorte."""
        from apps.organizations.models import Organization
        ids = request.data.get("ids") or []
        org = Organization.objects.filter(pk=request.data.get("organization")).first() if request.data.get("organization") else None
        cohort = Cohort.objects.filter(pk=request.data.get("cohort")).first() if request.data.get("cohort") else None
        self._cohort_guard(cohort)
        if not ids or (org is None and cohort is None and not request.data.get("clear")):
            return Response({"detail": "Sélectionnez des comptes et une entreprise ou une cohorte."}, status=400)
        done, errors = 0, []
        for u in self.get_queryset().filter(pk__in=ids):
            try:
                with transaction.atomic():
                    acc_services.link_membership(u, org, cohort)
                done += 1
            except serializers.ValidationError as e:
                errors.append({"user": u.email, "message": " ".join(str(x) for v in e.detail.values() for x in (v if isinstance(v, list) else [v]))})
        audit.log(request, "assign_users", model="accounts.User", new={"count": done, "organization": getattr(org, "id", None), "cohort": getattr(cohort, "id", None)})
        return Response({"assigned": done, "errors": errors})

    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request):
        from django.http import HttpResponse
        blank = str(request.query_params.get("blank", "")).lower() in ("1", "true", "yes")
        resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = 'attachment; filename="%s"' % ("modele_vide_import_utilisateurs.xlsx" if blank else "modele_import_utilisateurs.xlsx")
        acc_services.build_template(request.user.school, blank).save(resp)
        return resp

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def import_excel(self, request):
        """Analyse (dry_run=true, défaut) ou crée les comptes d'un fichier Excel."""
        from apps.schools.models import School
        f = request.FILES.get("file")
        if not f:
            return Response({"file": "Fichier requis."}, status=400)
        commit = str(request.data.get("dry_run", "true")).lower() in ("false", "0", "no")
        school = request.user.school
        if request.user.role == AKWABA_ADMIN:
            school = School.objects.filter(pk=request.data.get("school")).first()
        report = acc_services.run_import(f, request.user, school, commit)
        audit.log(request, "import_users" if commit else "analyse_import_users", model="accounts.User", school_id=getattr(school, "id", None),
                  new={"file": f.name, "total": report["total"], "created": report["created"], "errors": report["error_count"]})
        return Response(report)

    def _allowed_roles(self):
        u = self.request.user
        if u.role == AKWABA_ADMIN:
            return None
        if u.role == DIRECTOR:
            return {DIRECTOR, "secretary", "accountant", INSTRUCTOR, LEARNER}
        if u.role == ORG_ADMIN:
            return {r for r in ORG_ROLES}
        return set()

    def _check_role(self, serializer):
        allowed = self._allowed_roles()
        role = serializer.validated_data.get("role")
        if allowed is not None and role and role not in allowed:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Vous ne pouvez pas attribuer ce rôle.")

    def before_create(self, serializer, kwargs):
        self._check_role(serializer)
        u = self.request.user
        if u.role == ORG_ADMIN:
            kwargs["organization"] = u.organization
            kwargs["school"] = u.school
        elif u.role != AKWABA_ADMIN:
            kwargs["organization"] = None

    def _cohort_guard(self, cohort):
        u = self.request.user
        if cohort is not None and u.role == ORG_ADMIN and cohort.organization_id != u.organization_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Cohorte hors de votre organisation.")

    def perform_create(self, serializer):
        pwd = serializer.validated_data.pop("password", None)
        cohort = serializer.validated_data.pop("cohort", None)
        self._cohort_guard(cohort)
        kwargs = {}
        self.before_create(serializer, kwargs)
        if "school" not in kwargs and self.request.user.role != AKWABA_ADMIN:
            kwargs["school"] = self.request.user.school
        if not pwd:
            raise serializers.ValidationError({"password": "Mot de passe requis."})
        instance = serializer.save(**kwargs)
        instance.set_password(pwd)
        instance.save(update_fields=["password"])
        if instance.role == LEARNER or instance.organization_id or cohort:
            acc_services.link_membership(instance, instance.organization, cohort)
        audit.log(self.request, "create", instance, new={"email": instance.email, "role": instance.role,
                                                         "organization": instance.organization_id, "cohort": getattr(cohort, "id", None)})

    def perform_update(self, serializer):
        self._check_role(serializer)
        pwd = serializer.validated_data.pop("password", None)
        has_cohort = "cohort" in serializer.validated_data
        cohort = serializer.validated_data.pop("cohort", None)
        self._cohort_guard(cohort)
        old = {"role": serializer.instance.role, "is_active": serializer.instance.is_active}
        kwargs = {}
        if self.request.user.role != AKWABA_ADMIN:
            kwargs["school"] = serializer.instance.school
        instance = serializer.save(**kwargs)
        if pwd:
            instance.set_password(pwd)
            instance.save(update_fields=["password"])
        if has_cohort or (instance.role == LEARNER and "organization" in serializer.validated_data):
            learner = getattr(instance, "learner_profile", None)
            acc_services.link_membership(instance, instance.organization, cohort if has_cohort else (learner.cohort if learner else None))
        audit.log(self.request, "update", instance, old=old, new={"role": instance.role, "is_active": instance.is_active,
                                                                  "organization": instance.organization_id})


# --------------------------------------------------------------------------- connexion vocale
class VoiceStatusView(APIView):
    def get(self, request):
        u = request.user
        return Response({"enabled": u.voice_enabled, "allowed": u.role in acc_services.VOICE_ROLES,
                         "has_phone": len(acc_services.normalize_phone(u.phone)) >= 10, "phone": u.phone})


class VoiceEnableView(APIView):
    """Active la connexion vocale : un PIN vocal (4-6 chiffres) distinct du mot de passe, confirmé par le mot de passe."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verify"

    def post(self, request):
        u = request.user
        if u.role not in acc_services.VOICE_ROLES:
            return Response({"detail": "La connexion vocale est réservée aux apprenants et moniteurs."}, status=403)
        if not u.check_password(request.data.get("password", "")):
            return Response({"password": "Mot de passe incorrect."}, status=400)
        if len(acc_services.normalize_phone(u.phone)) < 10:
            return Response({"detail": "Renseignez d'abord votre numéro de téléphone (10 chiffres) dans votre profil."}, status=400)
        pin = acc_services.validate_voice_pin(request.data.get("pin"), u.phone)
        others = [x for x in acc_services.users_by_phone(u.phone, voice_only=True) if x.pk != u.pk]
        if others:
            return Response({"detail": "Ce numéro est déjà utilisé par un autre compte vocal : utilisez un numéro qui vous est propre."}, status=400)
        u.voice_pin_hash = make_password(pin)
        u.voice_enabled = True
        u.save(update_fields=["voice_pin_hash", "voice_enabled"])
        audit.log(request, "voice_enable", u)
        return Response({"enabled": True})


class VoiceDisableView(APIView):
    def post(self, request):
        u = request.user
        u.voice_enabled, u.voice_pin_hash = False, ""
        u.save(update_fields=["voice_enabled", "voice_pin_hash"])
        audit.log(request, "voice_disable", u)
        return Response({"enabled": False})


class VoiceLoginView(APIView):
    """Connexion par la voix : numéro de téléphone + PIN vocal dictés. Verrouillage après 5 échecs (comme le mot de passe)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        phone, pin = request.data.get("phone", ""), str(request.data.get("pin", ""))
        generic = Response({"detail": "Numéro ou code vocal incorrect."}, status=status.HTTP_401_UNAUTHORIZED)
        candidates = acc_services.users_by_phone(phone, voice_only=True)
        if len(candidates) != 1 or not re.fullmatch(r"\d{4,6}", pin):
            audit.log(request, "voice_login_failed", model="accounts.User", new={"phone": acc_services.normalize_phone(phone)})
            return generic
        user = candidates[0]
        if user.is_locked:
            return Response({"detail": "Compte temporairement verrouillé. Réessayez plus tard."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        if user.role not in acc_services.VOICE_ROLES or not check_password(pin, user.voice_pin_hash):
            user.failed_attempts += 1
            if user.failed_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                user.failed_attempts = 0
            user.save(update_fields=["failed_attempts", "locked_until"])
            audit.log(request, "voice_login_failed", user=user, model="accounts.User")
            return generic
        user.failed_attempts, user.locked_until = 0, None
        user.save(update_fields=["failed_attempts", "locked_until"])
        audit.log(request, "voice_login", user=user, model="accounts.User")
        return Response(session_payload(user))


class VoiceTranscribeView(APIView):
    """Transcription d'un court enregistrement (secours quand la reconnaissance embarquée est indisponible).

    Nécessite VOICE_STT_URL / VOICE_STT_KEY (service compatible OpenAI /audio/transcriptions). Sinon : 501.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verify"

    def post(self, request):
        import requests
        if not settings.VOICE_STT_URL:
            return Response({"detail": "Reconnaissance vocale serveur non configurée."}, status=501)
        f = request.FILES.get("audio")
        if not f or f.size > 3 * 1024 * 1024:
            return Response({"detail": "Enregistrement requis (3 Mo maximum)."}, status=400)
        try:
            r = requests.post(settings.VOICE_STT_URL, headers={"Authorization": f"Bearer {settings.VOICE_STT_KEY}"},
                              files={"file": (f.name or "voice.m4a", f.read(), f.content_type or "audio/m4a")},
                              data={"model": settings.VOICE_STT_MODEL, "language": "fr"}, timeout=30)
            text = r.json().get("text", "") if r.ok else ""
        except Exception:
            return Response({"detail": "Service de reconnaissance indisponible."}, status=502)
        return Response({"text": text})
