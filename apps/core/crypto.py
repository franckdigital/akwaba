import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

_PREFIX = "enc::"


def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


class EncryptedCharField(models.CharField):
    """Chiffre la valeur au repos (données sensibles : n° de pièce d'identité...)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 255)
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value or str(value).startswith(_PREFIX):
            return value
        return _PREFIX + _fernet().encrypt(str(value).encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value and value.startswith(_PREFIX):
            try:
                return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
            except InvalidToken:
                return ""
        return value

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs
