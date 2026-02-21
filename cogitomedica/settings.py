"""Django settings for Cogitomedica."""

from __future__ import annotations

import os
from pathlib import Path

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
from django.templatetags.static import static
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def before_send_filter(event: dict, hint: dict) -> dict:
    """Filter sensitive request metadata before sending to Sentry."""
    request = event.get("request", {})
    headers = request.get("headers", {})
    for header_name in ["authorization", "cookie", "x-api-key"]:
        if header_name in headers:
            headers[header_name] = "[FILTERED]"

    request_url = request.get("url")
    if isinstance(request_url, str) and (
        "token=" in request_url or "password=" in request_url
    ):
        request["url"] = "[FILTERED]"

    extra = event.get("extra", {})
    for key_name in ["password", "token", "secret", "key"]:
        if key_name in extra:
            extra[key_name] = "[FILTERED]"

    return event

SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=False,
        traces_sample_rate=1.0,
        before_send=before_send_filter,
    )

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
if ENVIRONMENT == "prod" and not os.environ.get("SECRET_KEY"):
    raise ImproperlyConfigured("SECRET_KEY must be set in production (set the SECRET_KEY environment variable).")

SECRET_KEY = os.environ.get("SECRET_KEY", "unsafe-dev-secret")
DEBUG = os.environ.get("DEBUG", "1") == "1"

# Hosty dozwolone w nagłówku Host. W prod MUSI być ustawione ALLOWED_HOSTS (np. twojadomena.com).
# Domyślnie puste – w dev ustaw w .env (np. ALLOWED_HOSTS=localhost,127.0.0.1).
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

CSRF_TRUSTED_ORIGINS = [
    "https://sentimentless-lourie-predesirously.ngrok-free.dev",
]

INSTALLED_APPS = [
    # "unfold",
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.users",
    "apps.reception",
    "apps.intake",
    "apps.medical",
    "apps.outbox",
    "apps.integrations",
    "apps.operations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_ratelimit.middleware.RatelimitMiddleware",
]

# Rate limit: 429 response when exceeded. View must return JsonResponse (API style).
RATELIMIT_VIEW = "apps.core.views.ratelimited_view"

ROOT_URLCONF = "cogitomedica.urls"

 # UNFOLD = {
 #   "SITE_TITLE": "Cogitomedica Admin",
 #   "SITE_HEADER": "Cogitomedica Digital Consents",
 #   "SITE_SUBHEADER": "Panel zarządzania",
 #   "ENVIRONMENT": "cogitomedica.admin_callbacks.environment_callback",
 #   "DASHBOARD_CALLBACK": "cogitomedica.admin_callbacks.dashboard_callback",
 #   "SIDEBAR": {
 #       "navigation": [
 #           {
 #                 "title": "Poczekalnia",
 #                   "items": [
 #                   {"title": "Dashboard", "icon": "dashboard", "link": lambda r: reverse_lazy("admin:index")},
 #                   # ... linki do modeli
 #               ],
 #           },
 #       ],
 #   },
    #"LOGIN": {
    #    "image": lambda request: static("login-bg.jpg"),
    #    "redirect_after": lambda request: reverse_lazy("admin:index"),
    #    # "form": "twoja_app.forms.CustomLoginForm",  # opcjonalnie – usuń albo wskaż prawdziwą ścieżkę
    #},
#}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "cogitomedica.wsgi.application"

AUTH_USER_MODEL = "users.StaffUser"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME"),
        "USER": os.environ.get("DB_USER"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST"),
        "PORT": os.environ.get("DB_PORT"),
    }
}


AUTH_PASSWORD_VALIDATORS = [
    # {
    #     "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    # },
    # {
    #     "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    # },
    # {
    #     "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    # },
    # {
    #     "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    # },
]


LANGUAGE_CODE = "de-de"
LANGUAGES = [("de", "German"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

SECURE_SSL_REDIRECT = ENVIRONMENT == "prod"
CSRF_COOKIE_SECURE = ENVIRONMENT == "prod"
SESSION_COOKIE_SECURE = ENVIRONMENT == "prod"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE_SECONDS", "1800"))
SESSION_SAVE_EVERY_REQUEST = True
SECURE_HSTS_SECONDS = 31536000 if ENVIRONMENT == "prod" else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = ENVIRONMENT == "prod"
SECURE_HSTS_PRELOAD = ENVIRONMENT == "prod"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TASKS = {
    "default": {
        "BACKEND": os.environ.get(
            "TASKS_BACKEND",
            "django.tasks.backends.immediate.ImmediateBackend",
        ),
        "QUEUES": [],
    }
}
OUTBOX_BATCH_SIZE = int(os.environ.get("OUTBOX_BATCH_SIZE", "10"))
OUTBOX_MAX_RETRIES = int(os.environ.get("OUTBOX_MAX_RETRIES", "10"))
OUTBOX_BASE_BACKOFF_SECONDS = int(os.environ.get("OUTBOX_BASE_BACKOFF_SECONDS", "30"))

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Cogitomedica API",
    "DESCRIPTION": "OpenAPI schema for Cogitomedica backend. All API v1 endpoints are documented.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "POSTPROCESSING_HOOKS": ["cogitomedica.openapi_extension.cogito_extend_schema"],
    "SERVERS": [{"url": "/", "description": "Relative to current host (e.g. http://127.0.0.1:8000)"}],
}

# CORS: dozwolone origins dla requestów z przeglądarki (np. frontend na innym porcie).
# W dev domyślnie localhost; w prod ustaw CORS_ALLOWED_ORIGINS w .env (np. https://app.example.com).
_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
if _origins_env:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]
elif ENVIRONMENT == "dev" or DEBUG:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
else:
    CORS_ALLOWED_ORIGINS = []
CORS_ALLOW_CREDENTIALS = True
