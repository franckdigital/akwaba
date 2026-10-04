from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import AKWABA_ADMIN
from apps.core.viewsets import BaseModelSerializer, ScopedModelViewSet

from .models import ALERT_EVENTS, DEFAULT_ALERT_CHANNELS, AlertSetting, AuditLog, Notification


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


ALL_CHANNELS = [("inapp", "Application"), ("email", "E-mail"), ("sms", "SMS"), ("whatsapp", "WhatsApp"), ("push", "Push")]


class AlertSettingSerializer(BaseModelSerializer):
    class Meta:
        model = AlertSetting
        fields = "__all__"


class AlertSettingViewSet(ScopedModelViewSet):
    """Paramétrage, depuis l'espace admin, de l'activation et des canaux de diffusion de CHAQUE type d'alerte."""
    resource = "alert_settings"
    queryset = AlertSetting.objects.all()
    serializer_class = AlertSettingSerializer
    include_global = True
    filterset_fields = ["event", "is_active", "school"]
    action_verbs = {"registry": "view", "set": "change"}

    @action(detail=False, methods=["get"])
    def registry(self, request):
        """Tous les types d'alerte connus, fusionnés avec le réglage effectif (école > global > défaut du code)."""
        school_id = request.query_params.get("school") or getattr(request.user, "school_id", None)
        rows = []
        for event, label in ALERT_EVENTS:
            qs = AlertSetting.objects.filter(event=event)
            setting = (qs.filter(school_id=school_id).first() if school_id else None) or qs.filter(school__isnull=True).first()
            rows.append({
                "event": event, "label": label,
                "channels": (setting.channels if setting else DEFAULT_ALERT_CHANNELS.get(event, ["inapp"])),
                "is_active": setting.is_active if setting else True,
                "source": "school" if (setting and setting.school_id) else ("global" if setting else "default"),
                "id": setting.id if setting else None,
                "subject": setting.subject if setting else "", "body": setting.body if setting else "",
            })
        return Response({"channels": ALL_CHANNELS, "events": rows})

    @action(detail=False, methods=["post"])
    def set(self, request):
        """Upsert : {"event": ..., "channels": [...], "is_active": true, "school"?: id (vide = réglage global)}."""
        event = request.data.get("event")
        if event not in dict(ALERT_EVENTS):
            return Response({"event": "Type d'alerte inconnu."}, status=400)
        school_id = request.data.get("school")
        if school_id is None and request.user.role != AKWABA_ADMIN:
            school_id = request.user.school_id   # un directeur ne paramètre que sa propre auto-école
        obj, _ = AlertSetting.objects.update_or_create(
            school_id=school_id, event=event,
            defaults={"channels": request.data.get("channels") or [], "is_active": bool(request.data.get("is_active", True)),
                      "subject": str(request.data.get("subject") or "")[:200], "body": str(request.data.get("body") or "")[:4000]})
        return Response(self.get_serializer(obj).data)
