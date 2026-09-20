"""Envoi de notifications multi-canaux.

Les canaux SMS / WhatsApp / push sont journalisés (stub) : brancher ici le
fournisseur réel (Orange SMS API, Twilio, FCM/Expo Push...).
"""
import logging

from django.core.mail import send_mail

from .models import Notification

logger = logging.getLogger("akwaba.notify")


def notify(user, event, title, message="", channels=("inapp",)):
    if user is None:
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
