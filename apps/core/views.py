from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import AKWABA_ADMIN
from apps.core.viewsets import ScopedModelViewSet

from .models import AuditLog, Notification


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = "__all__"


class AuditLogViewSet(ScopedModelViewSet):
    """Journal d'audit en lecture seule (admin Akwaba : tout ; directeur : son auto-école)."""
    resource = "audit"
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    school_lookup = "school_id"
    http_method_names = ["get", "head", "options"]
    filterset_fields = ["action", "model", "user", "object_id"]
    search_fields = ["user_label", "object_repr", "action", "model"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
        read_only_fields = ["user", "channel", "event", "title", "message", "created_at", "status"]


class NotificationViewSet(ScopedModelViewSet):
    resource = "notifications"
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]
    action_verbs = {"mark_all_read": "view", "unread_count": "view"}
    filterset_fields = ["is_read", "event", "channel"]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        return Response(status=405)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        n = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"updated": n})

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(is_read=False).count()})
