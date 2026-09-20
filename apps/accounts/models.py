import random
from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.permissions import ROLE_CHOICES, LEARNER


def normalize_phone(phone):
    """10 derniers chiffres (préfixe pays +225 ignoré) : forme de comparaison des numéros de téléphone."""
    import re
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("225") and len(digits) > 10:
        digits = digits[3:]
    return digits[-10:]


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("E-mail requis")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", "akwaba_admin")
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    phone_norm = models.CharField(max_length=10, blank=True, db_index=True, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=LEARNER)
    school = models.ForeignKey("schools.School", null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    agency = models.ForeignKey("schools.Agency", null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="users")
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    voice_enabled = models.BooleanField("Connexion vocale activée", default=False)
    voice_pin_hash = models.CharField(max_length=128, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        self.phone_norm = normalize_phone(self.phone)
        fields = kwargs.get("update_fields")
        if fields is not None and "phone" in fields:
            kwargs["update_fields"] = list(set(fields) | {"phone_norm"})
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())


class VerificationCode(models.Model):
    PURPOSES = [("email", "E-mail"), ("phone", "Téléphone"), ("reset", "Mot de passe")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="codes")
    purpose = models.CharField(max_length=10, choices=PURPOSES)
    code = models.CharField(max_length=8)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def issue(cls, user, purpose, minutes=30):
        cls.objects.filter(user=user, purpose=purpose, used=False).update(used=True)
        return cls.objects.create(user=user, purpose=purpose, code=f"{random.SystemRandom().randint(0, 999999):06d}",
                                  expires_at=timezone.now() + timedelta(minutes=minutes))

    @classmethod
    def consume(cls, user, purpose, code):
        obj = cls.objects.filter(user=user, purpose=purpose, code=code, used=False,
                                 expires_at__gt=timezone.now()).first()
        if obj:
            obj.used = True
            obj.save(update_fields=["used"])
        return obj is not None
