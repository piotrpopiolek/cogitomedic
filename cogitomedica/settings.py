"""Django settings for Cogitomedica."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
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

PROMETHEUS_METRICS_TOKEN = os.environ.get("PROMETHEUS_METRICS_TOKEN")

# Hosty dozwolone w nagłówku Host. W prod MUSI być ustawione ALLOWED_HOSTS (np. twojadomena.com).
# Domyślnie puste – w dev ustaw w .env (np. ALLOWED_HOSTS=localhost,127.0.0.1).
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
if ENVIRONMENT == "dev" or DEBUG:
    if "web" not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append("web")
    # Quick Tunnel (trycloudflare.com) – dowolna subdomena
    if ".trycloudflare.com" not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(".trycloudflare.com")

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
    "apps.patient_results",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.core.middleware.CsrfTrustTunnelOriginMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.TranslationRequestMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_ratelimit.middleware.RatelimitMiddleware",
]

# Rate limit: 429 response when exceeded. View must return JsonResponse (API style).
RATELIMIT_VIEW = "apps.core.views.ratelimited_view"

ROOT_URLCONF = "cogitomedica.urls"


def _is_admin_role(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_admin_role)


def _is_reception_or_admin_role(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and (user.is_admin_role or user.is_reception))


def _is_doctor_or_admin_role(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and (user.is_admin_role or user.is_doctor))


if HAS_UNFOLD:
    from apps.core.translation_service import db_gettext_lazy

    UNFOLD = {
        "SITE_TITLE": db_gettext_lazy("administration.site_title", "Cogitomedica Staff"),
        "SITE_HEADER": db_gettext_lazy("administration.site_header", "Cogitomedica"),
        "SITE_SUBHEADER": db_gettext_lazy("administration.site_subheader", "Panel administracyjny"),
        "SIDEBAR": {
            "navigation": [
                {
                    "title": db_gettext_lazy("administration.side_panels", "Panele"),
                    "separator": True,
                    "permission": lambda request: _is_doctor_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy("administration.side_lekarz", "Lekarz"),
                            "icon": "stethoscope",
                            "link": lambda request: reverse_lazy("doctor-list"),
                            "permission": lambda request: _is_doctor_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_rejestracja", "Rejestracja"),
                            "icon": "groups",
                            "link": lambda request: reverse_lazy("admin_reception_dashboard"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_admin", "Admin"),
                            "icon": "admin_panel_settings",
                            "link": lambda request: reverse_lazy("admin:index"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy("administration.side_users_permissions", "Użytkownicy i uprawnienia"),
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy("administration.side_staff_users", "Staff users"),
                            "icon": "person",
                            "link": lambda request: reverse_lazy("admin:users_staffuser_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_grupy", "Grupy"),
                            "icon": "group_work",
                            "link": lambda request: reverse_lazy("admin:auth_group_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy("administration.side_patients_readonly", "Pacjenci i kliniki (tylko odczyt)"),
                    "permission": lambda request: _is_doctor_or_admin_role(request) or _is_reception_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy("administration.side_pacjenci", "Pacjenci"),
                            "icon": "person",
                            "link": lambda request: reverse_lazy("admin:reception_patient_changelist"),
                            "permission": lambda request: _is_doctor_or_admin_role(request) or _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_historia_kontaktu", "Historia kontaktu"),
                            "icon": "history",
                            "link": lambda request: reverse_lazy("admin:reception_patientcontacthistory_changelist"),
                            "permission": lambda request: _is_doctor_or_admin_role(request) or _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_placowki", "Placówki"),
                            "icon": "local_hospital",
                            "link": lambda request: reverse_lazy("admin:reception_clinicsite_changelist"),
                            "permission": lambda request: _is_doctor_or_admin_role(request) or _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_gabinety", "Gabinety"),
                            "icon": "meeting_room",
                            "link": lambda request: reverse_lazy("admin:reception_consultingroom_changelist"),
                            "permission": lambda request: _is_doctor_or_admin_role(request) or _is_reception_or_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy("administration.side_reception_admin", "Rejestracja (Admin)"),
                    "permission": lambda request: _is_reception_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy("administration.side_dashboard_recepcji", "Dashboard operacyjny"),
                            "icon": "dashboard",
                            "link": lambda request: reverse_lazy("admin_reception_dashboard"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_kolejki_dzienne", "Kolejki dzienne"),
                            "icon": "today",
                            "link": lambda request: reverse_lazy("admin:reception_dailyqueue_changelist"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_kolejki_master_detail", "Kolejki master/detail"),
                            "icon": "table_rows",
                            "link": lambda request: reverse_lazy("admin:reception_dailyqueue_master_detail"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_wpisy_kolejki", "Wpisy kolejki"),
                            "icon": "format_list_numbered",
                            "link": lambda request: reverse_lazy("admin:reception_queueentry_changelist"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_urzadzenia_tablet", "Urządzenia tablet"),
                            "icon": "tablet",
                            "link": lambda request: reverse_lazy("admin:reception_tabletdevice_changelist"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_sesje_formularzy", "Sesje formularzy"),
                            "icon": "schedule",
                            "link": lambda request: reverse_lazy("admin:reception_patientformsession_changelist"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_dokumenty_intake_pdf", "Dokumenty intake (PDF)"),
                            "icon": "picture_as_pdf",
                            "link": lambda request: reverse_lazy("admin_intake_documents"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_batch_importu", "Batch importu pacjentów"),
                            "icon": "upload_file",
                            "link": lambda request: reverse_lazy("admin:reception_patientimportbatch_changelist"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_bledy_importu", "Błędy importu pacjentów"),
                            "icon": "error",
                            "link": lambda request: reverse_lazy("admin:reception_patientimporterror_changelist"),
                            "permission": lambda request: _is_reception_or_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy("administration.side_intake", "Intake"),
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy("administration.side_definicje_zgod", "Definicje zgód"),
                            "icon": "verified_user",
                            "link": lambda request: reverse_lazy("admin:intake_consentdefinition_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_pytania_anamnezy", "Pytania anamnezy"),
                            "icon": "quiz",
                            "link": lambda request: reverse_lazy("admin:intake_anamnesisquestiondefinition_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_opcje_pytan", "Opcje pytań anamnezy"),
                            "icon": "list",
                            "link": lambda request: reverse_lazy("admin:intake_anamnesisoptiondefinition_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_formularze_intake", "Formularze intake"),
                            "icon": "assignment",
                            "link": lambda request: reverse_lazy("admin:intake_patientintakeform_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_zgody_formularzy", "Zgody formularzy intake"),
                            "icon": "how_to_reg",
                            "link": lambda request: reverse_lazy("admin:intake_patientintakeconsent_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy("administration.side_medical", "Medical"),
                    "permission": lambda request: _is_doctor_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy("administration.side_dokumenty_medyczne", "Dokumenty medyczne"),
                            "icon": "description",
                            "link": lambda request: reverse_lazy("admin:medical_medicaldocument_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_wersje_dokumentow", "Wersje dokumentów"),
                            "icon": "library_books",
                            "link": lambda request: reverse_lazy("admin:medical_medicaldocumentversion_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_szablony_lekarza", "Szablony lekarza"),
                            "icon": "article",
                            "link": lambda request: reverse_lazy("admin:medical_doctortexttemplate_changelist"),
                            "permission": lambda request: _is_doctor_or_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy("administration.side_outbox_ops", "Outbox i operacje"),
                    "permission": lambda request: _is_doctor_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy("administration.side_outbox_events", "Outbox events"),
                            "icon": "outbox",
                            "link": lambda request: reverse_lazy("admin:outbox_outboxevent_changelist"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy("administration.side_audit_events", "Audit events"),
                            "icon": "fact_check",
                            "link": lambda request: reverse_lazy("admin:operations_auditevent_changelist"),
                            "permission": lambda request: _is_doctor_or_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy("administration.side_api_tools", "API / narzędzia"),
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy("administration.side_swagger", "Swagger"),
                            "icon": "description",
                            "link": lambda request: reverse_lazy("api-swagger"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                    ],
                },
            ],
        },
        "LOGIN": {
            "redirect_after": lambda request: reverse_lazy("admin:index"),
        },
        "STYLES": [
            lambda request: static("cogitomedica/css/unfold-sidebar-fix.css"),
        ],
        "SCRIPTS": [
            lambda request: static("admin/js/unfold-force-light.js"),
        ],
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
                "apps.core.context_processors.admin_submit_button_translations",
            ],
        },
    },
]

WSGI_APPLICATION = "cogitomedica.wsgi.application"

AUTH_USER_MODEL = "users.StaffUser"
AUTHENTICATION_BACKENDS = [
    "apps.users.auth_backends.StaffGroupAdminBackend",
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
LANGUAGES = [("de", "German"), ("en", "English"), ("pl", "Polish")]
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
# Prawdopodobieństwo (0.0–1.0) losowego błędu w mockach HiDrive i SMS, aby testować retry. Domyślnie 0 (wyłączone).
OUTBOX_MOCK_RANDOM_FAILURE_RATE = float(os.environ.get("OUTBOX_MOCK_RANDOM_FAILURE_RATE", "0"))

# SMS (SMSApi smsapi.pl)
SMSAPI_ACCESS_TOKEN = os.environ.get("SMSAPI_ACCESS_TOKEN", "")
SMSAPI_USE_MOCK = os.environ.get("SMSAPI_USE_MOCK", "0")

# Portal wyniki (patient results)
PATIENT_RESULTS_BASE_URL = os.environ.get("PATIENT_RESULTS_BASE_URL", "https://ergebnisse.cogitomedica.pl")
PATIENT_RESULTS_OTP_PEPPER = os.environ.get("PATIENT_RESULTS_OTP_PEPPER", "")

# CAPTCHA (Cloudflare Turnstile)
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "")
CAPTCHA_VERIFY_SKIP = os.environ.get("CAPTCHA_VERIFY_SKIP", "0").lower() in ("1", "true", "yes")

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

# PDF import: INFO logs (completed import, extracted text preview) visible in console/Docker.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "apps.reception.pdf_import": {
            "level": "INFO",
            "handlers": ["console"],
        },
    },
}