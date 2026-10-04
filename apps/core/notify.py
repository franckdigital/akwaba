"""Envoi de notifications multi-canaux.

Les canaux SMS / WhatsApp / push sont journalisés (stub) : brancher ici le
fournisseur réel (Orange SMS API, Twilio, FCM/Expo Push...).

Toutes les alertes sont paramétrables depuis l'admin (AlertSetting) : activation et canaux de
diffusion. Un réglage propre à l'auto-école du destinataire prime sur le réglage global (school=null) ;
en l'absence de tout réglage, les canaux par défaut du code appelant (DEFAULT_ALERT_CHANNELS) s'appliquent.
"""
import logging

from django.core.mail import send_mail

from .messaging import send_text
from .models import DEFAULT_ALERT_CHANNELS, AlertSetting, Notification

logger = logging.getLogger("akwaba.notify")


class _Safe(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _render(setting, title, message, name=""):
    """Applique le modèle de message configuré par l'admin (variables {titre} {message} {nom}) ; texte d'origine sinon."""
    if setting is None or not (setting.subject or setting.body):
        return title, message
    ctx = _Safe(titre=title, message=message, nom=name)
    try:
        return ((setting.subject or "{titre}").format_map(ctx), (setting.body or "{message}").format_map(ctx))
    except (ValueError, IndexError, KeyError, AttributeError):
        return title, message


def _get_setting(event, school_id):
    qs = AlertSetting.objects.filter(event=event)
    return (qs.filter(school_id=school_id).first() if school_id else None) or qs.filter(school__isnull=True).first()


def _resolve_channels(user, event, fallback):
    setting = _get_setting(event, getattr(user, "school_id", None))
    if setting is None:
        return tuple(fallback), True, None
    return tuple(setting.channels or []), setting.is_active, setting


def notify(user, event, title, message="", channels=("inapp",)):
    if user is None:
        return []
    channels, active, setting = _resolve_channels(user, event, channels or DEFAULT_ALERT_CHANNELS.get(event, ("inapp",)))
    if not active or not channels:
        return []
    title, message = _render(setting, title, message, getattr(user, "first_name", ""))
    created = []
    for ch in channels:
        status = "sent"
        try:
            if ch == "email" and user.email:
                send_mail(title, message, None, [user.email], fail_silently=True)
            elif ch in ("sms", "whatsapp"):
                send_text(ch, getattr(user, "phone", ""), f"{title}\n{message}".strip())
            elif ch == "push":
                logger.info("[push] -> %s : %s", user.pk, title)
        except Exception:  # pragma: no cover
            status = "failed"
        created.append(Notification.objects.create(
            user=user, channel=ch, event=event, title=title, message=message, status=status))
    return created


def notify_contact(event, title, message, email="", phone="", school_id=None, channels=("email", "whatsapp")):
    """Alerte envoyée à un contact qui n'a pas (encore) de compte (ex. auteur d'une demande de devis).
    Mêmes réglages d'activation et de canaux (AlertSetting) que notify() ; aucune ligne Notification (pas d'utilisateur)."""
    setting = _get_setting(event, school_id)
    if setting is not None:
        if not setting.is_active:
            return []
        channels = tuple(setting.channels or [])
        title, message = _render(setting, title, message)
    sent = []
    for ch in channels:
        if ch == "email" and email:
            send_mail(title, message, None, [email], fail_silently=True)
            sent.append(ch)
        elif ch in ("sms", "whatsapp") and phone:
            send_text(ch, phone, f"{title}\n{message}".strip())
            sent.append(ch)
    return sent
