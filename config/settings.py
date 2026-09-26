import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Chargeur minimal de backend/.env (KEY=VALUE) ; les variables déjà définies dans l'environnement gardent la priorité.
_env = BASE_DIR / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

DEBUG = os.environ.get("DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-akwaba-secret-key-change-me-in-production-0123456789")
if not DEBUG and SECRET_KEY.startswith("dev-only"):
    raise RuntimeError("SECRET_KEY doit être définie dans backend/.env en production.")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "apps.core",
    "apps.accounts",
    "apps.schools",
    "apps.learners",
    "apps.pedagogy",
    "apps.practice",
    "apps.organizations",
    "apps.billing",
    "apps.exams",
    "apps.reports",
    "apps.subscriptions",
    "apps.admissions",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "akwaba"),
        "USER": os.environ.get("DB_USER", "root"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"  # = heure d'Abidjan (UTC+0, sans changement d'heure) ; évite CONVERT_TZ, inopérant sans tables de fuseaux MySQL
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o]

REST_FRAMEWORK = {
    "URL_FORMAT_OVERRIDE": None,  # ?format=xlsx|pdf|csv est géré par les vues d'export, pas par DRF
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.FlexiblePagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"login": "30/min", "auth": "60/min", "verify": "20/min", "webhook": "600/min"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Akwaba Auto-École <no-reply@ae-akwabatreich.com>")

# Sécurité
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 15
PASS_THRESHOLD_DEFAULT = 70
PAYMENT_WEBHOOK_SECRET = os.environ.get("PAYMENT_WEBHOOK_SECRET", "dev-webhook-secret")
# --- CinetPay (API v1 « Aurora ») : SANDBOX uniquement par défaut ---
# Renseigner CINETPAY_API_KEY (sk_test_...) et CINETPAY_API_PASSWORD dans backend/.env pour utiliser le sandbox réel.
# Sans identifiants, le mode simulation locale (CINETPAY_MOCK) est activé automatiquement en DEBUG.
CINETPAY_API_KEY = os.environ.get("CINETPAY_API_KEY", "")
CINETPAY_API_PASSWORD = os.environ.get("CINETPAY_API_PASSWORD", "")
CINETPAY_ALLOW_LIVE = os.environ.get("CINETPAY_ALLOW_LIVE", "0") == "1"
CINETPAY_MOCK = os.environ.get("CINETPAY_MOCK", "" if (CINETPAY_API_KEY and CINETPAY_API_PASSWORD) else "1") == "1"
# --- Reconnaissance vocale côté serveur (facultatif) : endpoint compatible OpenAI /v1/audio/transcriptions ---
VOICE_STT_URL = os.environ.get("VOICE_STT_URL", "")
VOICE_STT_KEY = os.environ.get("VOICE_STT_KEY", "")
VOICE_STT_MODEL = os.environ.get("VOICE_STT_MODEL", "whisper-1")
BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://127.0.0.1:8010")
PUBLIC_WEB_URL = os.environ.get("PUBLIC_WEB_URL", "http://localhost:5180")

if not DEBUG:
    if SECRET_KEY.startswith("dev-only") or PAYMENT_WEBHOOK_SECRET.startswith("dev-"):
        raise RuntimeError("Définir SECRET_KEY et PAYMENT_WEBHOOK_SECRET en production.")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

import sys
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# --- Production (DEBUG=0) : derrière nginx en HTTPS ---
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")   # nginx transmet le schéma
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "0") == "1"   # la redirection HTTP->HTTPS est faite par nginx
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
    LOGGING = {
        "version": 1, "disable_existing_loggers": False,
        "formatters": {"std": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std"}},   # récupéré par journald (systemd)
        "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    }
