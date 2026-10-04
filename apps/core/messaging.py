"""Fournisseurs d'envoi SMS / WhatsApp.

Configuration par variables d'environnement (backend/.env) :
  WHATSAPP_PROVIDER = meta | twilio | log      (WhatsApp Business Cloud API de Meta, Twilio, ou simple journal)
  SMS_PROVIDER      = twilio | log
Sans identifiants valides, l'envoi est journalisé (aucune erreur bloquante).
"""
import base64
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("akwaba.notify")


def e164(phone):
    """Numéro au format international (+225…) : un numéro ivoirien à 10 chiffres reçoit le préfixe +225."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if len(digits) == 10:
        digits = "225" + digits
    return "+" + digits


def _post(url, data, headers, timeout=10):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (URL fournisseur fixe)
        return r.status, r.read().decode("utf-8", "replace")


def _twilio(to, body, whatsapp):
    sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
    sender = settings.TWILIO_WHATSAPP_FROM if whatsapp else settings.TWILIO_SMS_FROM
    if not (sid and token and sender):
        return False
    prefix = "whatsapp:" if whatsapp else ""
    data = urllib.parse.urlencode({"To": prefix + to, "From": (sender if sender.startswith(prefix) else prefix + sender), "Body": body}).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    _post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data,
          {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    return True


def _meta_whatsapp(to, body):
    token, phone_id = settings.WHATSAPP_ACCESS_TOKEN, settings.WHATSAPP_PHONE_NUMBER_ID
    if not (token and phone_id):
        return False
    payload = {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": body[:4000]}}
    _post(f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{phone_id}/messages", json.dumps(payload).encode(),
          {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return True


def send_text(channel, phone, body):
    """Envoie un SMS ou un message WhatsApp. Retourne True si remis au fournisseur, False si simplement journalisé."""
    to = e164(phone)
    if not to:
        return False
    whatsapp = channel == "whatsapp"
    provider = (settings.WHATSAPP_PROVIDER if whatsapp else settings.SMS_PROVIDER).lower()
    try:
        if provider == "twilio" and _twilio(to, body, whatsapp):
            return True
        if provider == "meta" and whatsapp and _meta_whatsapp(to, body):
            return True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.error("[%s/%s] échec d'envoi vers %s : %s", channel, provider, to, exc)
        return False
    logger.info("[%s] (journal) -> %s : %s", channel, to, body[:120])
    return False
