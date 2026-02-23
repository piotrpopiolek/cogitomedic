"""Django settings for Cogitomedica."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
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

HAS_UNFOLD = importlib.util.find_spec("unfold") is not None

INSTALLED_APPS = [
    "corsheaders",
]

if HAS_UNFOLD:
    INSTALLED_APPS.append("unfold")

INSTALLED_APPS += [
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


def _is_admin_role(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and getattr(user, "role", None) == "ADMIN")


if HAS_UNFOLD:
    UNFOLD = {
        "SITE_TITLE": "Cogitomedica Staff",
        "SITE_HEADER": "Cogitomedica",
        "SITE_SUBHEADER": "Panel administracyjny",
        "SIDEBAR": {
            "navigation": [
                {
                    "title": "Panele",
                    "separator": True,
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": "Lekarz",
                            "icon": "stethoscope",
                            "link": lambda request: reverse_lazy("doctor-list"),
                        },
                        {
                            "title": "Rejestracja",
                            "icon": "groups",
                            "link": lambda request: reverse_lazy("tablet:home"),
                        },
                        {
                            "title": "Admin",
                            "icon": "admin_panel_settings",
                            "link": lambda request: reverse_lazy("admin:index"),
                        },
                    ],
                },
                {
                    "title": "Użytkownicy i uprawnienia",
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": "Staff users",
                            "icon": "person",
                            "link": lambda request: reverse_lazy("admin:users_staffuser_changelist"),
                        },
                        {
                            "title": "Grupy",
                            "icon": "group_work",
                            "link": lambda request: reverse_lazy("admin:auth_group_changelist"),
                        },
                    ],
                },
                {
                    "title": "Rejestracja",
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": "Pacjenci",
                            "icon": "person_add",
                            "link": lambda request: reverse_lazy("admin:reception_patient_changelist"),
                        },
                        {
                            "title": "Historia kontaktu pacjenta",
                            "icon": "history",
                            "link": lambda request: reverse_lazy("admin:reception_patientcontacthistory_changelist"),
                        },
                        {
                            "title": "Placówki",
                            "icon": "local_hospital",
                            "link": lambda request: reverse_lazy("admin:reception_clinicsite_changelist"),
                        },
                        {
                            "title": "Gabinety",
                            "icon": "meeting_room",
                            "link": lambda request: reverse_lazy("admin:reception_consultingroom_changelist"),
                        },
                        {
                            "title": "Kolejki dzienne",
                            "icon": "today",
                            "link": lambda request: reverse_lazy("admin:reception_dailyqueue_changelist"),
                        },
                        {
                            "title": "Wpisy kolejki",
                            "icon": "format_list_numbered",
                            "link": lambda request: reverse_lazy("admin:reception_queueentry_changelist"),
                        },
                        {
                            "title": "Urządzenia tablet",
                            "icon": "tablet",
                            "link": lambda request: reverse_lazy("admin:reception_tabletdevice_changelist"),
                        },
                        {
                            "title": "Sesje formularzy",
                            "icon": "schedule",
                            "link": lambda request: reverse_lazy("admin:reception_patientformsession_changelist"),
                        },
                        {
                            "title": "Batch importu pacjentów",
                            "icon": "upload_file",
                            "link": lambda request: reverse_lazy("admin:reception_patientimportbatch_changelist"),
                        },
                        {
                            "title": "Błędy importu pacjentów",
                            "icon": "error",
                            "link": lambda request: reverse_lazy("admin:reception_patientimporterror_changelist"),
                        },
                    ],
                },
                {
                    "title": "Intake",
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": "Definicje zgód",
                            "icon": "verified_user",
                            "link": lambda request: reverse_lazy("admin:intake_consentdefinition_changelist"),
                        },
                        {
                            "title": "Pytania anamnezy",
                            "icon": "quiz",
                            "link": lambda request: reverse_lazy("admin:intake_anamnesisquestiondefinition_changelist"),
                        },
                        {
                            "title": "Opcje pytań anamnezy",
                            "icon": "list",
                            "link": lambda request: reverse_lazy("admin:intake_anamnesisoptiondefinition_changelist"),
                        },
                        {
                            "title": "Formularze intake",
                            "icon": "assignment",
                            "link": lambda request: reverse_lazy("admin:intake_patientintakeform_changelist"),
                        },
                        {
                            "title": "Zgody formularzy intake",
                            "icon": "how_to_reg",
                            "link": lambda request: reverse_lazy("admin:intake_patientintakeconsent_changelist"),
                        },
                    ],
                },
                {
                    "title": "Medical",
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": "Dokumenty medyczne",
                            "icon": "description",
                            "link": lambda request: reverse_lazy("admin:medical_medicaldocument_changelist"),
                        },
                        {
                            "title": "Wersje dokumentów",
                            "icon": "library_books",
                            "link": lambda request: reverse_lazy("admin:medical_medicaldocumentversion_changelist"),
                        },
                        {
                            "title": "Szablony lekarza",
                            "icon": "article",
                            "link": lambda request: reverse_lazy("admin:medical_doctortexttemplate_changelist"),
                        },
                    ],
                },
                {
                    "title": "Outbox i operacje",
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": "Outbox events",
                            "icon": "outbox",
                            "link": lambda request: reverse_lazy("admin:outbox_outboxevent_changelist"),
                        },
                        {
                            "title": "Audit events",
                            "icon": "fact_check",
                            "link": lambda request: reverse_lazy("admin:operations_auditevent_changelist"),
                        },
                    ],
                },
                {
                    "title": "API / narzędzia",
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": "Swagger",
                            "icon": "description",
                            "link": lambda request: reverse_lazy("api-swagger"),
                        },
                    ],
                },
            ],
        },
        "LOGIN": {
            "redirect_after": lambda request: reverse_lazy("admin:index"),
        },
    }

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
AUTHENTICATION_BACKENDS = [
    "apps.users.auth_backends.StaffRoleAdminBackend",
    "django.contrib.auth.backends.ModelBackend",
]


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
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
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

# Redirect unauthenticated users to doctor panel login (panel lekarza)
LOGIN_URL = "/doctor/login/"

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

CSRF_TRUSTED_ORIGINS = [
    "https://sentimentless-lourie-predesirously.ngrok-free.dev",
]