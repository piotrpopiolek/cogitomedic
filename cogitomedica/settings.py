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
        before_send=before_send_filter,  # type: ignore[arg-type]
    )

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
if ENVIRONMENT == "prod" and not os.environ.get("SECRET_KEY"):
    raise ImproperlyConfigured(
        "SECRET_KEY must be set in production (set the SECRET_KEY environment variable)."
    )

SECRET_KEY = os.environ.get("SECRET_KEY", "unsafe-dev-secret")
DEBUG = os.environ.get("DEBUG", "1") == "1"

PROMETHEUS_METRICS_TOKEN = os.environ.get("PROMETHEUS_METRICS_TOKEN")

# Hosty dozwolone w nagłówku Host. W prod MUSI być ustawione ALLOWED_HOSTS (np. twojadomena.com).
# Domyślnie puste – w dev ustaw w .env (np. ALLOWED_HOSTS=localhost,127.0.0.1).
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()
]
if ENVIRONMENT == "dev" or DEBUG:
    if "web" not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append("web")
_extra_allowed_hosts = [
    host.strip()
    for host in os.environ.get("EXTRA_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]
for _host in _extra_allowed_hosts:
    if _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)

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
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.StaffLocaleMiddleware",
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
    return bool(
        user and user.is_authenticated and (user.is_admin_role or user.is_reception)
    )


def _is_doctor_or_admin_role(request) -> bool:
    user = getattr(request, "user", None)
    return bool(
        user and user.is_authenticated and (user.is_admin_role or user.is_doctor)
    )


if HAS_UNFOLD:
    from apps.core.translation_service import db_gettext_lazy

    UNFOLD = {
        "SITE_TITLE": db_gettext_lazy(
            "administration.site_title", "Cogitomedica Staff"
        ),
        "SITE_HEADER": db_gettext_lazy("administration.site_header", "Cogitomedica"),
        "SITE_SUBHEADER": db_gettext_lazy(
            "administration.site_subheader", "Panel administracyjny"
        ),
        "SIDEBAR": {
            "navigation": [
                {
                    "title": db_gettext_lazy("administration.side_panels", "Panele"),
                    "separator": True,
                    "permission": lambda request: _is_doctor_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy(
                                "administration.side_lekarz", "Lekarz"
                            ),
                            "icon": "stethoscope",
                            "link": lambda request: reverse_lazy("doctor-list"),
                            "permission": lambda request: _is_doctor_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_rejestracja", "Rejestracja"
                            ),
                            "icon": "groups",
                            "link": lambda request: reverse_lazy(
                                "admin_reception_dashboard"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_admin", "Admin"
                            ),
                            "icon": "admin_panel_settings",
                            "link": lambda request: reverse_lazy("admin:index"),
                            "permission": lambda request: _is_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy(
                        "administration.side_users_permissions",
                        "Użytkownicy i uprawnienia",
                    ),
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy(
                                "administration.side_staff_users", "Staff users"
                            ),
                            "icon": "person",
                            "link": lambda request: reverse_lazy(
                                "admin:users_staffuser_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_grupy", "Grupy"
                            ),
                            "icon": "group_work",
                            "link": lambda request: reverse_lazy(
                                "admin:auth_group_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy(
                        "administration.side_patients_readonly",
                        "Pacjenci i kliniki (tylko odczyt)",
                    ),
                    "permission": lambda request: _is_doctor_or_admin_role(request)
                    or _is_reception_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy(
                                "administration.side_pacjenci", "Pacjenci"
                            ),
                            "icon": "person",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_patient_changelist"
                            ),
                            "permission": lambda request: _is_doctor_or_admin_role(
                                request
                            )
                            or _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_placowki", "Placówki"
                            ),
                            "icon": "local_hospital",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_clinicsite_changelist"
                            ),
                            "permission": lambda request: _is_doctor_or_admin_role(
                                request
                            )
                            or _is_reception_or_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_gabinety", "Gabinety"
                            ),
                            "icon": "meeting_room",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_consultingroom_changelist"
                            ),
                            "permission": lambda request: _is_doctor_or_admin_role(
                                request
                            )
                            or _is_reception_or_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy(
                        "administration.side_reception_admin", "Rejestracja (Admin)"
                    ),
                    "permission": lambda request: _is_reception_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy(
                                "administration.side_dashboard_recepcji",
                                "Dashboard operacyjny",
                            ),
                            "icon": "dashboard",
                            "link": lambda request: reverse_lazy(
                                "admin_reception_dashboard"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_kolejki_dzienne", "Kolejki dzienne"
                            ),
                            "icon": "today",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_dailyqueue_changelist"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_kolejki_master_detail",
                                "Kolejki master/detail",
                            ),
                            "icon": "table_rows",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_dailyqueue_master_detail"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_wpisy_kolejki", "Wpisy kolejki"
                            ),
                            "icon": "format_list_numbered",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_queueentry_changelist"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_urzadzenia_tablet",
                                "Urządzenia tablet",
                            ),
                            "icon": "tablet",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_tabletdevice_changelist"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_sesje_formularzy",
                                "Sesje formularzy",
                            ),
                            "icon": "schedule",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_patientformsession_changelist"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_dokumenty_intake_pdf",
                                "Dokumenty intake (PDF)",
                            ),
                            "icon": "picture_as_pdf",
                            "link": lambda request: reverse_lazy(
                                "admin_intake_documents"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_batch_importu",
                                "Batch importu pacjentów",
                            ),
                            "icon": "upload_file",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_patientimportbatch_changelist"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_bledy_importu",
                                "Błędy importu pacjentów",
                            ),
                            "icon": "error",
                            "link": lambda request: reverse_lazy(
                                "admin:reception_patientimporterror_changelist"
                            ),
                            "permission": lambda request: _is_reception_or_admin_role(
                                request
                            ),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy("administration.side_intake", "Intake"),
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy(
                                "administration.side_definicje_zgod", "Definicje zgód"
                            ),
                            "icon": "verified_user",
                            "link": lambda request: reverse_lazy(
                                "admin:intake_consentdefinition_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_pytania_anamnezy",
                                "Pytania anamnezy",
                            ),
                            "icon": "quiz",
                            "link": lambda request: reverse_lazy(
                                "admin:intake_anamnesisquestiondefinition_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_opcje_pytan",
                                "Opcje pytań anamnezy",
                            ),
                            "icon": "list",
                            "link": lambda request: reverse_lazy(
                                "admin:intake_anamnesisoptiondefinition_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_formularze_intake",
                                "Formularze intake",
                            ),
                            "icon": "assignment",
                            "link": lambda request: reverse_lazy(
                                "admin:intake_patientintakeform_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_zgody_formularzy",
                                "Zgody formularzy intake",
                            ),
                            "icon": "how_to_reg",
                            "link": lambda request: reverse_lazy(
                                "admin:intake_patientintakeconsent_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy("administration.side_medical", "Medical"),
                    "permission": lambda request: _is_doctor_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy(
                                "administration.side_dokumenty_medyczne",
                                "Dokumenty medyczne",
                            ),
                            "icon": "description",
                            "link": lambda request: reverse_lazy(
                                "admin:medical_medicaldocument_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_wersje_dokumentow",
                                "Wersje dokumentów",
                            ),
                            "icon": "library_books",
                            "link": lambda request: reverse_lazy(
                                "admin:medical_medicaldocumentversion_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_szablony_lekarza",
                                "Szablony lekarza",
                            ),
                            "icon": "article",
                            "link": lambda request: reverse_lazy(
                                "admin:medical_doctortexttemplate_changelist"
                            ),
                            "permission": lambda request: _is_doctor_or_admin_role(
                                request
                            ),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy(
                        "administration.side_outbox_ops", "Outbox i operacje"
                    ),
                    "permission": lambda request: _is_doctor_or_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy(
                                "administration.side_outbox_events", "Outbox events"
                            ),
                            "icon": "outbox",
                            "link": lambda request: reverse_lazy(
                                "admin:outbox_outboxevent_changelist"
                            ),
                            "permission": lambda request: _is_admin_role(request),
                        },
                        {
                            "title": db_gettext_lazy(
                                "administration.side_audit_events", "Audit events"
                            ),
                            "icon": "fact_check",
                            "link": lambda request: reverse_lazy(
                                "admin:operations_auditevent_changelist"
                            ),
                            "permission": lambda request: _is_doctor_or_admin_role(
                                request
                            ),
                        },
                    ],
                },
                {
                    "title": db_gettext_lazy(
                        "administration.side_api_tools", "API / narzędzia"
                    ),
                    "permission": lambda request: _is_admin_role(request),
                    "items": [
                        {
                            "title": db_gettext_lazy(
                                "administration.side_swagger", "Swagger"
                            ),
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
        # Primary: teal #075255 jak w skompilowanym CSS witryny (post-17.css / post-33.css), nie blue z global-settings.
        "COLORS": {
            "base": {
                "50": "oklch(98.5% .002 247.839)",
                "100": "oklch(96.7% .003 264.542)",
                "200": "oklch(92.8% .006 264.531)",
                "300": "oklch(87.2% .01 258.338)",
                "400": "oklch(70.7% .022 261.325)",
                "500": "oklch(55.1% .027 264.364)",
                "600": "oklch(44.6% .03 256.802)",
                "700": "oklch(37.3% .034 259.733)",
                "800": "oklch(27.8% .033 256.848)",
                "900": "oklch(21% .034 264.665)",
                "950": "oklch(13% .028 261.692)",
            },
            "primary": {
                "50": "oklch(96.5% .022 196)",
                "100": "oklch(92% .045 196)",
                "200": "oklch(84% .07 196)",
                "300": "oklch(72% .09 196)",
                "400": "oklch(58% .095 196)",
                "500": "oklch(48% .088 196)",
                "600": "oklch(35.5% .082 196.2)",
                "700": "oklch(30% .072 196)",
                "800": "oklch(24% .058 196)",
                "900": "oklch(19% .045 196)",
                "950": "oklch(14% .035 196)",
            },
            "font": {
                "subtle-light": "var(--color-base-500)",
                "subtle-dark": "var(--color-base-400)",
                "default-light": "var(--color-base-600)",
                "default-dark": "var(--color-base-300)",
                "important-light": "var(--color-base-900)",
                "important-dark": "var(--color-base-100)",
            },
        },
        "STYLES": [
            lambda request: static("cogitomedica/css/unfold-sidebar-fix.css"),
            lambda request: static("cogitomedica/css/admin-changelist-link.css"),
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


AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = [
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
FORMAT_MODULE_PATH = ["cogitomedica.formats"]
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Europe/Warsaw")
USE_I18N = True
USE_TZ = True


# Ścieżki static/media. Na mydevil serwer serwuje z public_python/public/ → ustaw MYDEVIL_DEPLOY=1.
if os.environ.get("MYDEVIL_DEPLOY", "").strip() in ("1", "true", "yes"):
    STATIC_ROOT = BASE_DIR / "public" / "static"
    MEDIA_ROOT = BASE_DIR / "public" / "media"
    STATIC_URL = "/static/"
    MEDIA_URL = "/media/"
else:
    STATIC_URL = "/static/"
    STATIC_ROOT = BASE_DIR / "staticfiles"
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"

STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

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
PDF_RETENTION_DAYS = int(os.environ.get("PDF_RETENTION_DAYS", "30"))

# SMS (SMSApi smsapi.pl)
SMSAPI_ACCESS_TOKEN = os.environ.get("SMSAPI_ACCESS_TOKEN", "")
SMSAPI_USE_MOCK = os.environ.get("SMSAPI_USE_MOCK", "1")

# HiDrive (Strato)
HIDRIVE_USE_MOCK = os.environ.get("HIDRIVE_USE_MOCK", "0")
HIDRIVE_CLIENT_ID = os.environ.get("HIDRIVE_CLIENT_ID", "")
HIDRIVE_CLIENT_SECRET = os.environ.get("HIDRIVE_CLIENT_SECRET", "")
HIDRIVE_REFRESH_TOKEN = os.environ.get("HIDRIVE_REFRESH_TOKEN", "")
HIDRIVE_TOKEN_URL = os.environ.get(
    "HIDRIVE_TOKEN_URL", "https://my.hidrive.com/oauth2/token"
)
HIDRIVE_API_BASE_URL = os.environ.get(
    "HIDRIVE_API_BASE_URL", "https://api.hidrive.strato.com/2.1"
)
HIDRIVE_TIMEOUT_SECONDS = int(os.environ.get("HIDRIVE_TIMEOUT_SECONDS", "30"))
HIDRIVE_INCOMING_PATH = os.environ.get("HIDRIVE_INCOMING_PATH", "/incoming")
HIDRIVE_PROCESSED_PATH = os.environ.get("HIDRIVE_PROCESSED_PATH", "/processed")
# Logical root for Befund/intake PDFs (same resolution as incoming/processed: /users/<alias><prefix>/…).
HIDRIVE_PATIENTS_DIR_PREFIX = os.environ.get("HIDRIVE_PATIENTS_DIR_PREFIX", "/patients")
if ENVIRONMENT == "prod" and str(HIDRIVE_USE_MOCK).lower() not in ("1", "true", "yes"):
    missing_hidrive = [
        key
        for key, value in {
            "HIDRIVE_CLIENT_ID": HIDRIVE_CLIENT_ID,
            "HIDRIVE_CLIENT_SECRET": HIDRIVE_CLIENT_SECRET,
            "HIDRIVE_REFRESH_TOKEN": HIDRIVE_REFRESH_TOKEN,
        }.items()
        if not str(value or "").strip()
    ]
    if missing_hidrive:
        raise ImproperlyConfigured(
            "Missing required HiDrive settings in production when HIDRIVE_USE_MOCK is disabled: "
            + ", ".join(missing_hidrive)
        )

# Portal wyniki (patient results)
PATIENT_RESULTS_BASE_URL = os.environ.get(
    "PATIENT_RESULTS_BASE_URL", "https://ergebnisse.cogitomedica.pl"
)
PATIENT_RESULTS_OTP_PEPPER = os.environ.get("PATIENT_RESULTS_OTP_PEPPER", "")
if ENVIRONMENT != "dev" and not str(PATIENT_RESULTS_OTP_PEPPER).strip():
    raise ImproperlyConfigured(
        "PATIENT_RESULTS_OTP_PEPPER must be set outside development environments."
    )

# CAPTCHA (Cloudflare Turnstile)
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "")
CAPTCHA_VERIFY_SKIP = os.environ.get("CAPTCHA_VERIFY_SKIP", "0").lower() in (
    "1",
    "true",
    "yes",
)

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Cogitomedica API",
    "DESCRIPTION": "OpenAPI schema for Cogitomedica backend. All API v1 endpoints are documented.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "POSTPROCESSING_HOOKS": ["cogitomedica.openapi_extension.cogito_extend_schema"],
    "SERVERS": [
        {
            "url": "/",
            "description": "Relative to current host (e.g. http://127.0.0.1:8000)",
        }
    ],
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
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
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
    "loggers": {},
}
