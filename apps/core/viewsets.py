from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from . import audit
from .permissions import (AKWABA_ADMIN, INSTRUCTOR, LEARNER, ORG_ROLES, SCHOOL_ROLES, RBACPermission)

SCHOOL = "SCHOOL"


def scope_queryset(qs, user, view):
    """Restreint un queryset au périmètre de l'utilisateur (multi-tenant)."""
    if user.role == AKWABA_ADMIN:
        return qs
    school_lookup = getattr(view, "school_lookup", "school")

    def school_qs():
        if not school_lookup or not user.school_id:
            return qs.none()
        q = Q(**{school_lookup: user.school_id})
        if getattr(view, "include_global", False):
            q |= Q(**{school_lookup + "__isnull": True})
        return qs.filter(q)

    if user.role in SCHOOL_ROLES:
        return school_qs()
    if user.role in ORG_ROLES:
        lookup = getattr(view, "org_lookup", None)
        if lookup and user.organization_id:
            return qs.filter(**{lookup: user.organization_id}).distinct()
        return qs.none()
    if user.role == INSTRUCTOR:
        lookup = getattr(view, "instructor_lookup", None)
        if lookup == SCHOOL:
            return school_qs()
        if lookup:
            return qs.filter(**{lookup: user}).distinct()
        return qs.none()
    if user.role == LEARNER:
        lookup = getattr(view, "learner_lookup", None)
        if lookup == SCHOOL:
            return school_qs()
        if lookup:
            return qs.filter(**{lookup: user}).distinct()
        return qs.none()
    return qs.none()


class BaseModelSerializer(serializers.ModelSerializer):
    def get_extra_kwargs(self):
        extra = super().get_extra_kwargs()
        if "school" in [f.name for f in self.Meta.model._meta.get_fields()]:
            extra.setdefault("school", {})["required"] = False
        return extra


def make_serializer(model_cls, name=None, read_only=(), exclude=(), depth=0, extra_fields=None):
    attrs = {"model": model_cls, "read_only_fields": tuple(read_only), "depth": depth}
    if exclude:
        attrs["exclude"] = tuple(exclude)
    else:
        attrs["fields"] = "__all__"
    Meta = type("Meta", (), attrs)
    body = {"Meta": Meta}
    body.update(extra_fields or {})
    return type(name or model_cls.__name__ + "Serializer", (BaseModelSerializer,), body)


class ScopedModelViewSet(viewsets.ModelViewSet):
    resource = None
    permission_classes = [IsAuthenticated, RBACPermission]
    action_verbs = {}
    school_lookup = "school"
    org_lookup = None
    learner_lookup = None
    instructor_lookup = None
    include_global = False
    limit_key = None
    filterset_fields = ()
    search_fields = ()

    def get_queryset(self):
        return scope_queryset(super().get_queryset(), self.request.user, self)

    def _has_school_field(self):
        return any(f.name == "school" for f in self.queryset.model._meta.get_fields())

    def _snapshot(self, instance):
        return self.get_serializer(instance).data

    def perform_create(self, serializer):
        user = self.request.user
        kwargs = {}
        if self._has_school_field() and user.role != AKWABA_ADMIN:
            kwargs["school"] = user.school
        if self.limit_key:
            from apps.schools.services import check_limit
            school = kwargs.get("school") or serializer.validated_data.get("school")
            check_limit(school, self.limit_key)
        self.before_create(serializer, kwargs)
        instance = serializer.save(**kwargs)
        audit.log(self.request, "create", instance, new=self._snapshot(instance))
        self.after_create(instance)

    def before_create(self, serializer, kwargs):
        pass

    def after_create(self, instance):
        pass

    def perform_update(self, serializer):
        old = self._snapshot(serializer.instance)
        kwargs = {}
        if self._has_school_field() and self.request.user.role != AKWABA_ADMIN:
            kwargs["school"] = serializer.instance.school
        instance = serializer.save(**kwargs)
        audit.log(self.request, "update", instance, old=old, new=self._snapshot(instance))

    def perform_destroy(self, instance):
        old = self._snapshot(instance)
        audit.log(self.request, "delete", instance, old=old)
        instance.delete()
