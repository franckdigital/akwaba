import json

from django.core.serializers.json import DjangoJSONEncoder

from .models import AuditLog


def client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


def _clean(data):
    if data is None:
        return None
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder, default=str))


def log(request, action, obj=None, old=None, new=None, user=None, model="", school_id=None):
    user = user or (getattr(request, "user", None) if request else None)
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    if obj is not None:
        model = model or obj._meta.label
        school_id = school_id or getattr(obj, "school_id", None)
    if school_id is None and user is not None:
        school_id = getattr(user, "school_id", None)
    return AuditLog.objects.create(
        user=user,
        user_label=str(user) if user else "",
        action=action,
        model=model,
        object_id=str(getattr(obj, "pk", "") or ""),
        object_repr=str(obj)[:255] if obj is not None else "",
        old_value=_clean(old),
        new_value=_clean(new),
        ip_address=client_ip(request),
        school_id=school_id,
    )
