"""Envoi de notifications multi-canaux.

Les canaux SMS / WhatsApp / push sont journalisés (stub) : brancher ici le
fournisseur réel (Orange SMS API, Twilio, FCM/Expo Push...).

Toutes les alertes sont paramétrables depuis l'admin (AlertSetting) : activation et canaux de
diffusion. Un réglage propre à l'auto-école du destinataire prime sur le réglage global (school=null) ;
en l'absence de tout réglage, les canaux par défaut du code appelant (DEFAULT_ALERT_CHANNELS) s'appliquent.
"""
import logging

from django.core.mail import send_mail

from .models import DEFAULT_ALERT_CHANNELS, AlertSetting, Notification

logger = logging.getLogger("akwaba.notify")


def _resolve_channels(user, event, fallback):
    school_id = getattr(user, "school_id", None)
    qs = AlertSetting.objects.filter(event=event)
    setting = (qs.filter(school_id=school_id).first() if school_id else None) or qs.filter(school__isnull=True).first()
    if setting is None:
        return tuple(fallback), True
    return tuple(setting.channels or []), setting.is_active


def notify(user, event, title, message="", channels=("inapp",)):
    if user is None:
        return []
    channels, active = _resolve_channels(user, event, channels or DEFAULT_ALERT_CHANNELS.get(event, ("inapp",)))
    if not active or not channels:
        return []
    created = []
    for ch in channels:
        status = "sent"
        try:
            if ch == "email" and user.email:
                send_mail(title, message, None, [user.email], fail_silently=True)
            elif ch in ("sms", "whatsapp", "push"):
                logger.info("[%s] -> %s : %s", ch, getattr(user, "phone", "") or user.pk, title)
        except Exception:  # pragma: no cover
            status = "failed"
        created.append(Notification.objects.create(
            user=user, channel=ch, event=event, title=title, message=message, status=status))
    return created


def notify_contact(event, title, message, email="", phone="", school_id=None, channels=("email", "whatsapp")):
    """Alerte envoyée à un contact qui n'a pas (encore) de compte (ex. auteur d'une demande de devis).
    Mêmes réglages d'activation et de canaux (AlertSetting) que notify() ; aucune ligne Notification (pas d'utilisateur)."""
    qs = AlertSetting.objects.filter(event=event)
    setting = (qs.filter(school_id=school_id).first() if school_id else None) or qs.filter(school__isnull=True).first()
    if setting is not None:
        if not setting.is_active:
            return []
        channels = tuple(setting.channels or [])
    sent = []
    for ch in channels:
        if ch == "email" and email:
            send_mail(title, message, None, [email], fail_silently=True)
            sent.append(ch)
        elif ch in ("sms", "whatsapp", "push") and phone:
            logger.info("[%s] -> %s : %s", ch, phone, title)
            sent.append(ch)
    return sent
