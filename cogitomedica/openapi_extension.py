"""
OpenAPI schema for Cogitomedica API v1.

API uses Django view functions (not DRF), so drf-spectacular does not auto-discover them.
We serve the full schema from cogito_openapi_schema_view so /api/docs works without DRF views.

Request/response body schemas are generated from Pydantic models (openapi_schemas) so the
documentation stays in sync with api_schemas in each app.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from cogitomedica.openapi_schemas import (
    COMPONENTS_REF_PREFIX,
    get_components_schemas,
    get_request_body_schema_for,
    get_response_schema_for,
)

PREFIX = "/api/v1"

# Standard domain error JSON (``json_domain_error``); matches ``ApiLocalizedErrorBody`` in components.
_API_LOCALIZED_ERROR_SCHEMA: dict[str, Any] = {
    "$ref": f"{COMPONENTS_REF_PREFIX}ApiLocalizedErrorBody"
}

# Staff list pagination — aligned with apps.core.api_utils (DEFAULT_LIST_LIMIT=20, MAX_LIST_LIMIT=100).
_OPENAPI_PAGE_SCHEMA = {
    "type": "integer",
    "minimum": 1,
    "default": 1,
    "description": "Page number (1-based).",
}
_OPENAPI_PAGE_SIZE_SCHEMA = {
    "type": "integer",
    "minimum": 1,
    "maximum": 100,
    "default": 20,
    "description": "Page size; default 20, maximum 100.",
}
_OPENAPI_LIST_LIMIT_SCHEMA = {
    "type": "integer",
    "minimum": 1,
    "maximum": 100,
    "default": 20,
    "description": "Maximum items; default 20, maximum 100 (parse_list_limit; same as page_size).",
}
PAGE_Q = {"name": "page", "in": "query", "schema": _OPENAPI_PAGE_SCHEMA}
PAGE_SIZE_Q = {"name": "page_size", "in": "query", "schema": _OPENAPI_PAGE_SIZE_SCHEMA}
LIST_LIMIT_Q = {"name": "limit", "in": "query", "schema": _OPENAPI_LIST_LIMIT_SCHEMA}

# Operations that do not require authentication (no lock icon in Swagger UI).
NO_AUTH_OPERATIONS = {
    (f"{PREFIX}/observability/health", "get"),
    (f"{PREFIX}/observability/monitoring/grafana", "get"),
    (f"{PREFIX}/observability/monitoring/prometheus", "get"),
    (f"{PREFIX}/observability/monitoring/alertmanager", "get"),
    (f"{PREFIX}/observability/monitoring/tempo", "get"),
    (f"{PREFIX}/observability/monitoring/otel-collector", "get"),
    (f"{PREFIX}/auth/login", "post"),
    (f"{PREFIX}/patient-results/request-otp", "post"),
    (f"{PREFIX}/patient-results/verify-otp", "post"),
}

# OpenAPI 3 security scheme: session cookie (Django). Used so Swagger UI shows lock icon.
SECURITY_SCHEME_SESSION = "sessionCookie"

# Minimal OpenAPI 3 path definitions: method -> operation dict (summary, tags, responses).
# Path parameters use {param} and are documented via parameters when needed.
COGITO_PATHS = {
    f"{PREFIX}/observability/health": {
        "get": {
            "summary": "Health check",
            "description": "Returns service and dependency status (DB, outbox). No auth.",
            "tags": ["Observability"],
            "responses": {
                "200": {"description": "OK or degraded"},
                "503": {"description": "Service unavailable"},
            },
        },
    },
    f"{PREFIX}/observability/metrics": {
        "get": {
            "summary": "Prometheus metrics",
            "description": "Eksport metryk w formacie Prometheus. Wymaga nagłówka `Authorization: Bearer <PROMETHEUS_METRICS_TOKEN>` lub zalogowanej sesji z rolą ADMIN.",
            "tags": ["Observability"],
            "responses": {
                "200": {"description": "Metrics text"},
                "401": {"description": "Unauthorized"},
            },
        },
    },
    # Adresy usług monitorowania (Docker) – tylko w dokumentacji, nie są obsługiwane przez API
    f"{PREFIX}/observability/monitoring/grafana": {
        "get": {
            "summary": "Grafana",
            "description": "Zewnętrzny adres: http://localhost:3000 — dashboardy (metryki, trace'y). Logowanie: admin / admin.",
            "tags": ["Observability"],
            "responses": {
                "200": {
                    "description": "Usługa zewnętrzna – otwórz adres w przeglądarce."
                }
            },
        },
    },
    f"{PREFIX}/observability/monitoring/prometheus": {
        "get": {
            "summary": "Prometheus",
            "description": "Zewnętrzny adres: http://localhost:9090 — UI PromQL, targety: http://localhost:9090/targets",
            "tags": ["Observability"],
            "responses": {
                "200": {
                    "description": "Usługa zewnętrzna – otwórz adres w przeglądarce."
                }
            },
        },
    },
    f"{PREFIX}/observability/monitoring/alertmanager": {
        "get": {
            "summary": "Alertmanager",
            "description": "Zewnętrzny adres: http://localhost:9093 — zarządzanie alertami i powiadomieniami.",
            "tags": ["Observability"],
            "responses": {
                "200": {
                    "description": "Usługa zewnętrzna – otwórz adres w przeglądarce."
                }
            },
        },
    },
    f"{PREFIX}/observability/monitoring/tempo": {
        "get": {
            "summary": "Grafana Tempo",
            "description": "Zewnętrzny adres: http://localhost:3200 — backend trace'ów; dostęp z Grafany (Explore → Tempo).",
            "tags": ["Observability"],
            "responses": {
                "200": {
                    "description": "Usługa zewnętrzna – otwórz adres w przeglądarce."
                }
            },
        },
    },
    f"{PREFIX}/observability/monitoring/otel-collector": {
        "get": {
            "summary": "OpenTelemetry Collector",
            "description": "Zewnętrzne adresy: localhost:4317 (gRPC), localhost:4318 (HTTP) — odbiera trace'y z aplikacji (brak UI).",
            "tags": ["Observability"],
            "responses": {
                "200": {
                    "description": "Usługa zewnętrzna – używana wewnętrznie przez aplikację."
                }
            },
        },
    },
    f"{PREFIX}/auth/login": {
        "post": {
            "summary": "Log in",
            "description": "Authenticate with username and password. Sets session cookie. Optional android_id: for TABLET, RECEPTION, or ADMIN, updates that tablet device's last_seen_at (last login on device).",
            "tags": ["Auth"],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "username": {"type": "string"},
                                "password": {"type": "string"},
                                "android_id": {"type": "string"},
                            },
                            "required": ["username", "password"],
                        }
                    }
                },
            },
            "responses": {
                "200": {"description": "User and session expiry"},
                "401": {"description": "Invalid credentials"},
            },
        },
    },
    f"{PREFIX}/auth/logout": {
        "post": {
            "summary": "Log out",
            "description": "Invalidate session.",
            "tags": ["Auth"],
            "responses": {"200": {"description": "OK"}},
        },
    },
    f"{PREFIX}/auth/me": {
        "get": {
            "summary": "Current user",
            "description": "Returns authenticated user. Requires session.",
            "tags": ["Auth"],
            "responses": {
                "200": {"description": "User payload"},
                "401": {"description": "Authentication required"},
            },
        },
    },
    f"{PREFIX}/staff-users": {
        "get": {
            "summary": "List staff users",
            "description": "Paginated list. Admin only.",
            "tags": ["Staff users"],
            "parameters": [
                PAGE_Q,
                PAGE_SIZE_Q,
                {"name": "role", "in": "query", "schema": {"type": "string"}},
                {"name": "is_active", "in": "query", "schema": {"type": "boolean"}},
                {"name": "search", "in": "query", "schema": {"type": "string"}},
            ],
            "responses": {
                "200": {"description": "Items and pagination"},
                "401": {"description": "Authentication required"},
                "403": {"description": "Forbidden"},
            },
        },
        "post": {
            "summary": "Create staff user",
            "description": "Admin only.",
            "tags": ["Staff users"],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "201": {"description": "Created"},
                "400": {"description": "Validation error"},
                "401": {"description": "Authentication required"},
                "403": {"description": "Forbidden"},
                "409": {"description": "Username or email exists"},
            },
        },
    },
    f"{PREFIX}/staff-users/{{staff_user_id}}": {
        "get": {
            "summary": "Get staff user",
            "tags": ["Staff users"],
            "parameters": [
                {
                    "name": "staff_user_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "patch": {
            "summary": "Update staff user",
            "tags": ["Staff users"],
            "parameters": [
                {
                    "name": "staff_user_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "content": {"application/json": {"schema": {"type": "object"}}}
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
                "409": {"description": "Conflict"},
            },
        },
        "delete": {
            "summary": "Deactivate staff user",
            "tags": ["Staff users"],
            "parameters": [
                {
                    "name": "staff_user_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "Deactivated"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/doctor-text-templates": {
        "get": {
            "summary": "List doctor text templates",
            "tags": ["Doctor templates"],
            "parameters": [
                {
                    "name": "actor_user_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "template_locale",
                    "in": "query",
                    "schema": {"type": "string"},
                },
                {
                    "name": "include_inactive",
                    "in": "query",
                    "schema": {"type": "boolean"},
                },
            ],
            "responses": {"200": {"description": "Results"}},
        },
        "post": {
            "summary": "Create doctor text template",
            "tags": ["Doctor templates"],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "201": {"description": "Created"},
                "400": {"description": "Validation error"},
            },
        },
    },
    f"{PREFIX}/doctor-text-templates/{{template_id}}": {
        "get": {
            "summary": "Get doctor text template",
            "tags": ["Doctor templates"],
            "parameters": [
                {
                    "name": "template_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {
                    "description": "Template (name, template_body, lesion_group_favorites, etc.)"
                },
                "404": {"description": "Not found"},
            },
        },
        "patch": {
            "summary": "Update doctor text template",
            "tags": ["Doctor templates"],
            "parameters": [
                {
                    "name": "template_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/outbox-events": {
        "get": {
            "summary": "List outbox events",
            "tags": ["Outbox"],
            "parameters": [
                {"name": "status", "in": "query", "schema": {"type": "string"}},
                {"name": "event_type", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "retry_count_gte",
                    "in": "query",
                    "schema": {"type": "integer"},
                },
                LIST_LIMIT_Q,
            ],
            "responses": {"200": {"description": "Results and count"}},
        },
    },
    f"{PREFIX}/outbox-events/{{outbox_event_id}}/retry": {
        "post": {
            "summary": "Retry outbox event",
            "tags": ["Outbox"],
            "parameters": [
                {
                    "name": "outbox_event_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"reason": {"type": "string"}},
                        }
                    }
                }
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
                "409": {"description": "Conflict"},
            },
        },
    },
    f"{PREFIX}/operations/outbox/process": {
        "post": {
            "summary": "Process outbox batch",
            "tags": ["Operations"],
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"limit": {"type": "integer"}},
                        }
                    }
                }
            },
            "responses": {
                "202": {"description": "Accepted (processed, failed, dead_lettered)"}
            },
        },
    },
    f"{PREFIX}/operations/retention/run": {
        "post": {
            "summary": "Run retention cleanup",
            "tags": ["Operations"],
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "older_than_days": {"type": "integer"},
                                "dry_run": {"type": "boolean"},
                            },
                        }
                    }
                }
            },
            "responses": {
                "202": {
                    "description": "Per stream: befund + intake each with candidates, deleted, skipped_not_safe",
                },
            },
        },
    },
    f"{PREFIX}/audit-events": {
        "get": {
            "summary": "List audit events",
            "description": "ADMIN: full feed. DOCTOR: scoped. Pagination: page (default 1), page_size (default 20, max 100).",
            "tags": ["Operations"],
            "parameters": [
                {"name": "event_type", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "patient_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "medical_document_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "context_clinic_site_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "actor_user_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "outbox_event_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "from",
                    "in": "query",
                    "schema": {"type": "string", "format": "date-time"},
                },
                {
                    "name": "to",
                    "in": "query",
                    "schema": {"type": "string", "format": "date-time"},
                },
                PAGE_Q,
                PAGE_SIZE_Q,
            ],
            "responses": {
                "200": {"description": "items, pagination"},
                "401": {"description": "Authentication required"},
                "403": {"description": "Forbidden"},
            },
        },
    },
    f"{PREFIX}/intake-outbox-events": {
        "get": {
            "summary": "List intake outbox events",
            "description": "Events for intake PDF generation and HiDrive upload (GENERATE_INTAKE_PDF, HIDRIVE_UPLOAD_INTAKE_PDF). ADMIN, RECEPTION.",
            "tags": ["Intake – Outbox"],
            "parameters": [
                {"name": "status", "in": "query", "schema": {"type": "string"}},
                {"name": "event_type", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "retry_count_gte",
                    "in": "query",
                    "schema": {"type": "integer"},
                },
                LIST_LIMIT_Q,
            ],
            "responses": {"200": {"description": "results, count"}},
        },
    },
    f"{PREFIX}/intake-outbox-events/{{intake_outbox_event_id}}/retry": {
        "post": {
            "summary": "Retry intake outbox event",
            "description": "Move FAILED/DEAD_LETTER event back to PENDING. ADMIN, RECEPTION.",
            "tags": ["Intake – Outbox"],
            "parameters": [
                {
                    "name": "intake_outbox_event_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "200": {"description": "id, status, retry_count"},
                "404": {"description": "Not found"},
                "409": {"description": "Event not retryable"},
            },
        },
    },
    f"{PREFIX}/operations/intake-outbox/process": {
        "post": {
            "summary": "Process intake outbox batch",
            "description": "Process pending/failed intake outbox events (PDF generation, HiDrive upload). ADMIN only.",
            "tags": ["Intake – Outbox"],
            "requestBody": {
                "content": {"application/json": {"schema": {"type": "object"}}}
            },
            "responses": {"202": {"description": "processed, failed, dead_lettered"}},
        },
    },
    f"{PREFIX}/intake-documents": {
        "get": {
            "summary": "List intake document versions (PDF)",
            "description": "List generated intake PDF document versions. RECEPTION/ADMIN only; RECEPTION sees only documents from assigned clinic_sites. Query: queue_date (YYYY-MM-DD), pdf_generation_status (PENDING, IN_PROGRESS, COMPLETED, FAILED), patient_search, clinic_site_id, page (default 1), page_size (default 20, max 100).",
            "tags": ["Intake – Documents"],
            "parameters": [
                {
                    "name": "queue_date",
                    "in": "query",
                    "schema": {"type": "string", "format": "date"},
                },
                {
                    "name": "pdf_generation_status",
                    "in": "query",
                    "schema": {
                        "type": "string",
                        "enum": ["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"],
                    },
                },
                {"name": "patient_search", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "clinic_site_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                PAGE_Q,
                PAGE_SIZE_Q,
            ],
            "responses": {
                "200": {
                    "description": "items (id, version_no, pdf_generation_status, patient, queue_date, clinic_site_name, pdf_available, …), pagination"
                },
                "401": {"description": "Authentication required"},
                "403": {"description": "Forbidden (e.g. DOCTOR)"},
            },
        },
    },
    f"{PREFIX}/intake-documents/{{intake_document_version_id}}": {
        "get": {
            "summary": "Get intake document version detail",
            "description": "Detail of one intake document version. RECEPTION/ADMIN only; scope by clinic_site.",
            "tags": ["Intake – Documents"],
            "parameters": [
                {
                    "name": "intake_document_version_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {
                    "description": "Detail (id, version_no, pdf_generation_status, patient, queue_date, clinic_site_name, pdf_available, pdf_local_path, …)"
                },
                "401": {"description": "Authentication required"},
                "403": {"description": "Forbidden"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/intake-documents/{{intake_document_version_id}}/preview-pdf": {
        "get": {
            "summary": "Preview intake PDF",
            "description": "Returns the generated intake PDF file (Content-Disposition: inline). Only when pdf_generation_status is COMPLETED and file exists. RECEPTION/ADMIN only; scope by clinic_site.",
            "tags": ["Intake – Documents"],
            "parameters": [
                {
                    "name": "intake_document_version_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "application/pdf (inline)"},
                "401": {"description": "Authentication required"},
                "403": {"description": "Forbidden"},
                "404": {
                    "description": "Not found (out of scope, file missing, or status ≠ COMPLETED)"
                },
            },
        },
    },
    f"{PREFIX}/medical-documents": {
        "get": {
            "summary": "List medical documents",
            "description": (
                "Doctor work queue (DOCTOR, ADMIN, MANAGER). Paginated: page (default 1), "
                "page_size (default 20, max 100). Query `scope`: `all` (default), `mine`, "
                "`published_by_me`, or `in_revision` (published document with pending revision only)."
            ),
            "tags": ["Medical"],
            "parameters": [
                {"name": "status", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "queue_date",
                    "in": "query",
                    "schema": {"type": "string", "format": "date"},
                },
                {"name": "patient_search", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "scope",
                    "in": "query",
                    "schema": {
                        "type": "string",
                        "enum": ["all", "mine", "published_by_me", "in_revision"],
                        "default": "all",
                    },
                    "description": "Row filter for the work queue (see `list_medical_documents`).",
                },
                PAGE_Q,
                PAGE_SIZE_Q,
            ],
            "responses": {
                "200": {"description": "Items and pagination"},
                "401": {"description": "Authentication required"},
                "403": {"description": "Forbidden"},
            },
        },
        "post": {
            "summary": "Create medical document",
            "description": (
                "DOCTOR, ADMIN, or MANAGER. Links queue entry and intake form. "
                "Requires intake `form_status` **SUBMITTED** (not `REOPENED` — patient must finish edits first)."
            ),
            "tags": ["Medical"],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "queue_entry_id": {"type": "string", "format": "uuid"},
                                "intake_form_id": {"type": "string", "format": "uuid"},
                                "created_by_user_id": {
                                    "type": "string",
                                    "format": "uuid",
                                },
                            },
                        }
                    }
                },
            },
            "responses": {
                "201": {"description": "Created"},
                "400": {
                    "description": "Domain error (e.g. intake not **SUBMITTED** yet — `other.domain.intake_form_must_be_submitted`, or queue/intake mismatch)."
                },
                "404": {"description": "Queue entry or intake form not found"},
            },
        },
    },
    f"{PREFIX}/medical-documents/no-intake": {
        "post": {
            "summary": "Create medical document without digital intake",
            "description": (
                "DOCTOR, ADMIN, or MANAGER. Creates a medical document in paper mode "
                "(`source_type=PAPER_INTAKE`) after an ADMIN/MANAGER has created a "
                "`PaperIntakeAuthorization` for the queue entry. Atomically moves queue status "
                "to `PAPER_INTAKE_COMPLETED`. Requires `appointment_time` and enforces the "
                "3-hour guard after appointment time (same rule as authorization)."
            ),
            "tags": ["Medical"],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "queue_entry_id": {"type": "string", "format": "uuid"},
                                "created_by_user_id": {
                                    "type": "string",
                                    "format": "uuid",
                                },
                            },
                            "required": ["queue_entry_id"],
                        }
                    }
                },
            },
            "responses": {
                "201": {"description": "Created"},
                "400": {
                    "description": (
                        "Domain rules failed (e.g. queue not WAITING, missing "
                        "`appointment_time`, document already exists, 3-hour guard) — "
                        "`error_key` + `error` via `json_domain_error`. Or request body "
                        "schema validation — `error_key` `other.api.invalid_request_body` "
                        "with `details` (Pydantic)."
                    )
                },
                "401": {"description": "Authentication required"},
                "403": {
                    "description": (
                        "Forbidden — caller is not DOCTOR, ADMIN, or MANAGER "
                        "(`other.api.forbidden`)."
                    )
                },
                "404": {"description": "Queue entry not found"},
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}": {
        "get": {
            "summary": "Get medical document context",
            "description": (
                "Full document context for the doctor panel (DOCTOR, ADMIN, MANAGER): intake "
                "summary and current version payload. Top-level fields include `status`, "
                "`source_type` (`DIGITAL_INTAKE` or `PAPER_INTAKE`), `current_version_no`, "
                "`published_version_no` (last published version number; "
                "null until first publish), `has_pending_revision` (true when a PUBLISHED "
                "document has an in-progress DRAFT amendment), lock fields (`locked_by_user_id`, "
                "`locked_by_username`, `locked_at` — effective lock only, max 6h). "
                "`intake_form_id` is null for paper documents. For `source_type=PAPER_INTAKE`, "
                "`paper_intake_authorization` holds the manager authorization snapshot "
                "(`authorized_by_user_id`, `authorized_by_username`, `authorized_at` ISO string, "
                "`reason`) from audit metadata; null for digital intake. "
                "`intake_summary.patient` uses the same keys for digital intake and paper "
                "fallback (`id`, `first_name`, `last_name`, `date_of_birth` ISO string or null, "
                "`phone`, `email`); digital rows come from intake context, paper from "
                "`queue_entry.patient`."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
                {"name": "form_locale", "in": "query", "schema": {"type": "string"}},
            ],
            "responses": {
                "200": {
                    "description": "Context (intake, version, patient, revision flags, etc.)"
                },
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/preview-pdf": {
        "get": {
            "summary": "Preview PDF",
            "description": (
                "Returns PDF for a selected document version (DOCTOR, ADMIN, MANAGER). When "
                "external HiDrive PDFs are matched or already accepted, the response merges them "
                "with the Befund PDF. Query `source`: `published` (last published row), `draft` "
                "(latest DRAFT), or omit for default behaviour (published-only doc → published; "
                "published with pending revision → draft; legacy DRAFT-only doc → latest). "
                "Response headers `X-Befund-Preview-Source` and `X-Befund-Preview-Version-No` "
                "echo the resolved version. Content-Type: application/pdf."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "source",
                    "in": "query",
                    "schema": {"type": "string", "enum": ["published", "draft"]},
                    "description": "Optional; when invalid, API returns 400 (`other.api.preview_source_invalid`).",
                },
                {"name": "form_locale", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "authoring_locale",
                    "in": "query",
                    "schema": {"type": "string"},
                },
            ],
            "responses": {
                "200": {
                    "description": "PDF file (inline). May be Befund-only if merge failed or an attachment was unreadable.",
                    "headers": {
                        "X-Befund-Preview-Warning": {
                            "description": (
                                "Optional hint when merge failed, a HiDrive attachment was "
                                "invalid, or download failed (pipe-separated tokens); body is still a PDF."
                            ),
                            "schema": {"type": "string"},
                        }
                    },
                },
                "404": {"description": "Not found or no version to preview"},
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/external-pdfs": {
        "get": {
            "summary": "List external HiDrive PDF attachments",
            "description": (
                "DOCTOR, ADMIN, or MANAGER. Returns rows linked to the medical document "
                "(matched/rejected/etc.) from HiDrive /incoming flow."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
            ],
            "responses": {
                "200": {
                    "description": "JSON: items[{id, filename, status, hidrive_remote_path}]",
                },
                "404": {"description": "Medical document not found"},
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/external-pdfs/{{attachment_id}}/content": {
        "get": {
            "summary": "Download external PDF (inline)",
            "description": (
                "DOCTOR, ADMIN, or MANAGER. Streams the file from HiDrive on demand (no local cache). "
                "Content-Type: application/pdf."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "attachment_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
            ],
            "responses": {
                "200": {"description": "PDF file (inline)"},
                "404": {"description": "Document or attachment not found"},
                "410": {"description": "Attachment was rejected"},
                "422": {
                    "description": "Invalid or incomplete PDF (e.g. upload still in progress)",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"error": {"type": "string"}},
                            }
                        }
                    },
                },
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/external-pdfs/{{attachment_id}}/reject": {
        "post": {
            "summary": "Reject external PDF on HiDrive",
            "description": (
                "DOCTOR, ADMIN, or MANAGER. Renames the file on HiDrive with prefix rejected_ and sets "
                "attachment status to REJECTED."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "attachment_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
            ],
            "responses": {
                "200": {
                    "description": "JSON: {ok: true, status}",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "ok": {"type": "boolean"},
                                    "status": {"type": "string"},
                                },
                            }
                        }
                    },
                },
                "404": {"description": "Document or attachment not found"},
                "405": {"description": "Method not allowed"},
                "502": {"description": "HiDrive rename failed"},
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/versions": {
        "get": {
            "summary": "List document versions",
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {
                    "description": "Items (version_no, version_status, pdf_generation_status, etc.)"
                },
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/audit-trail": {
        "get": {
            "summary": "List audit events for document",
            "description": (
                "DOCTOR, ADMIN, or MANAGER. Pagination: page (default 1), page_size (default 20, max 100)."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
                PAGE_Q,
                PAGE_SIZE_Q,
            ],
            "responses": {
                "200": {"description": "items, pagination"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/retry-processing": {
        "post": {
            "summary": "Retry document processing",
            "description": (
                "Retry latest failed outbox step (e.g. PDF generation, HiDrive, SMS). "
                "ADMIN, MANAGER, or RECEPTION."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"reason": {"type": "string"}},
                        }
                    }
                }
            },
            "responses": {
                "200": {"description": "retried, outbox_event_id, event_type, status"},
                "404": {"description": "Not found"},
                "409": {"description": "Nothing to retry"},
            },
        },
    },
    f"{PREFIX}/medical-document-versions/{{version_id}}": {
        "get": {
            "summary": "Get document version",
            "description": "Single version by id (MedicalDocumentVersion.id) with full medical_payload.",
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "version_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "Version details"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/draft": {
        "put": {
            "summary": "Save draft",
            "description": (
                "DOCTOR, ADMIN, or MANAGER. Persists Befund payload. For a document already in "
                '**PUBLISHED** status, the client must send `"intent": "amend"` to start or '
                "continue a revision; otherwise the API returns **409** with "
                "`error_key` = `other.api.amend_intent_required`. While a revision is open, "
                "the document row stays `PUBLISHED` and `has_pending_revision` is true until "
                "publish or discard. Invalid `intent` strings (not `edit` or `amend`) yield **400** "
                "with `error_key` = `other.api.invalid_save_draft_intent`. ADMIN and MANAGER "
                "bypass the DRAFT edit-lock held by another user (same semantics as lock service)."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "200": {
                    "description": (
                        "Saved version plus document revision flags (`document_status`, "
                        "`has_pending_revision`, `published_version_no`)."
                    )
                },
                "400": {
                    "description": (
                        "Validation or domain error; body includes `error` and usually `error_key` "
                        "(e.g. `other.api.invalid_save_draft_intent`)."
                    ),
                    "content": {
                        "application/json": {"schema": _API_LOCALIZED_ERROR_SCHEMA}
                    },
                },
                "404": {"description": "Not found"},
                "409": {
                    "description": (
                        "Published document requires explicit revision intent (`intent=amend`); "
                        "`error_key` = `other.api.amend_intent_required`."
                    ),
                    "content": {
                        "application/json": {"schema": _API_LOCALIZED_ERROR_SCHEMA}
                    },
                },
                "423": {
                    "description": (
                        "Edit lock held by another user (DRAFT document only); JSON includes "
                        "`locked_by_username` (not the same shape as ApiLocalizedErrorBody)."
                    )
                },
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/discard-revision": {
        "post": {
            "summary": "Discard pending revision",
            "description": (
                "DOCTOR, ADMIN, or MANAGER. Deletes the latest **DRAFT** version on a **PUBLISHED** "
                "document that has `has_pending_revision=true`, clears the flag, and clears the "
                "edit lock. Returns **409** with `error_key` = `other.api.no_pending_revision_to_discard` "
                "when there is nothing to discard."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {
                    "description": "Pending revision discarded; document flags updated."
                },
                "404": {"description": "Medical document not found"},
                "409": {
                    "description": "No pending revision (`error_key`: `other.api.no_pending_revision_to_discard`).",
                    "content": {
                        "application/json": {"schema": _API_LOCALIZED_ERROR_SCHEMA}
                    },
                },
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/unlock": {
        "post": {
            "summary": "Release edit lock",
            "description": (
                "Clears edit lock when the caller holds the lock or has ADMIN/MANAGER oversight. "
                "Intended for page unload from the doctor panel."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "released: true"},
                "403": {"description": "Caller cannot release this lock"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/publish": {
        "post": {
            "summary": "Publish document",
            "description": (
                "DOCTOR, ADMIN, or MANAGER. Publishes the latest DRAFT (or completes a revision). "
                "DRAFT edit-lock rules match PUT …/draft (MANAGER/ADMIN may bypass another user's lock)."
            ),
            "tags": ["Medical"],
            "parameters": [
                {
                    "name": "medical_document_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "200": {"description": "Version"},
                "400": {"description": "Validation or domain error (e.g. no draft)"},
                "404": {"description": "Not found"},
                "409": {
                    "description": "Idempotency conflict (e.g. publish_request_id reused with different publish_locale)"
                },
                "423": {
                    "description": "Edit lock held by another user while document is DRAFT (same as PUT …/draft)."
                },
            },
        },
    },
    f"{PREFIX}/clinic-sites": {
        "get": {
            "summary": "List clinic sites",
            "tags": ["Reception – Dictionaries"],
            "parameters": [
                {"name": "is_active", "in": "query", "schema": {"type": "boolean"}},
                {"name": "search", "in": "query", "schema": {"type": "string"}},
                LIST_LIMIT_Q,
            ],
            "responses": {"200": {"description": "Items"}},
        },
        "post": {
            "summary": "Create clinic site",
            "tags": ["Reception – Dictionaries"],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {"201": {"description": "Created"}},
        },
    },
    f"{PREFIX}/clinic-sites/{{clinic_site_id}}": {
        "get": {
            "summary": "Get clinic site",
            "tags": ["Reception – Dictionaries"],
            "parameters": [
                {
                    "name": "clinic_site_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "patch": {
            "summary": "Update clinic site",
            "tags": ["Reception – Dictionaries"],
            "parameters": [
                {
                    "name": "clinic_site_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "content": {"application/json": {"schema": {"type": "object"}}}
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "delete": {
            "summary": "Deactivate clinic site",
            "tags": ["Reception – Dictionaries"],
            "parameters": [
                {
                    "name": "clinic_site_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/consulting-rooms": {
        "get": {
            "summary": "List consulting rooms",
            "tags": ["Reception – Dictionaries"],
            "parameters": [
                {
                    "name": "clinic_site_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {"name": "is_active", "in": "query", "schema": {"type": "boolean"}},
                {"name": "search", "in": "query", "schema": {"type": "string"}},
                LIST_LIMIT_Q,
            ],
            "responses": {"200": {"description": "Items"}},
        },
        "post": {
            "summary": "Create consulting room",
            "tags": ["Reception – Dictionaries"],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {"201": {"description": "Created"}},
        },
    },
    f"{PREFIX}/consulting-rooms/{{consulting_room_id}}": {
        "get": {
            "summary": "Get consulting room",
            "tags": ["Reception – Dictionaries"],
            "parameters": [
                {
                    "name": "consulting_room_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "patch": {
            "summary": "Update consulting room",
            "tags": ["Reception – Dictionaries"],
            "parameters": [
                {
                    "name": "consulting_room_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "content": {"application/json": {"schema": {"type": "object"}}}
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "delete": {
            "summary": "Deactivate consulting room",
            "tags": ["Reception – Dictionaries"],
            "parameters": [
                {
                    "name": "consulting_room_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/imports/batches": {
        "get": {
            "summary": "List import batches",
            "tags": ["Reception – Imports"],
            "parameters": [LIST_LIMIT_Q],
            "responses": {"200": {"description": "Items"}},
        },
    },
    f"{PREFIX}/imports/batches/{{batch_id}}": {
        "get": {
            "summary": "Get import batch",
            "tags": ["Reception – Imports"],
            "parameters": [
                {
                    "name": "batch_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/imports/batches/{{batch_id}}/errors": {
        "get": {
            "summary": "List import batch errors",
            "tags": ["Reception – Imports"],
            "parameters": [
                {
                    "name": "batch_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "Items"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/patients": {
        "get": {
            "summary": "List patients",
            "tags": ["Reception – Patients"],
            "parameters": [
                {"name": "search", "in": "query", "schema": {"type": "string"}},
                {"name": "last_name", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "date_of_birth",
                    "in": "query",
                    "schema": {"type": "string", "format": "date"},
                },
                {"name": "phone", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "doctolib_patient_id",
                    "in": "query",
                    "schema": {"type": "string"},
                },
                {"name": "is_active", "in": "query", "schema": {"type": "boolean"}},
                PAGE_Q,
                PAGE_SIZE_Q,
            ],
            "responses": {"200": {"description": "Items and pagination"}},
        },
        "post": {
            "summary": "Create or update patient (manual)",
            "tags": ["Reception – Patients"],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "200": {"description": "Patient"},
                "201": {"description": "Created"},
            },
        },
    },
    f"{PREFIX}/patients/{{patient_id}}/anonymize": {
        "post": {
            "summary": "Anonymize patient (ADMIN, RODO Art. 17)",
            "tags": ["Reception – Patients"],
            "parameters": [
                {
                    "name": "patient_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
            ],
            "responses": {
                "200": {"description": "Patient anonymized"},
                "404": {"description": "Not found"},
                "422": {"description": "e.g. active queue entries"},
            },
        },
    },
    f"{PREFIX}/patients/{{patient_id}}": {
        "get": {
            "summary": "Get patient",
            "tags": ["Reception – Patients"],
            "parameters": [
                {
                    "name": "patient_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "patch": {
            "summary": "Update patient",
            "tags": ["Reception – Patients"],
            "parameters": [
                {
                    "name": "patient_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "content": {"application/json": {"schema": {"type": "object"}}}
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "delete": {
            "summary": "Deactivate patient",
            "tags": ["Reception – Patients"],
            "parameters": [
                {
                    "name": "patient_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/daily-queues": {
        "get": {
            "summary": "List daily queues",
            "tags": ["Reception – Queues"],
            "parameters": [
                {
                    "name": "queue_date",
                    "in": "query",
                    "schema": {"type": "string", "format": "date"},
                },
                {
                    "name": "clinic_site_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "consulting_room_id",
                    "in": "query",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {"name": "shift_code", "in": "query", "schema": {"type": "string"}},
                {"name": "status", "in": "query", "schema": {"type": "string"}},
                LIST_LIMIT_Q,
            ],
            "responses": {"200": {"description": "Items"}},
        },
        "post": {
            "summary": "Create daily queue",
            "tags": ["Reception – Queues"],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {"201": {"description": "Created"}},
        },
    },
    f"{PREFIX}/daily-queues/{{daily_queue_id}}": {
        "get": {
            "summary": "Get daily queue",
            "tags": ["Reception – Queues"],
            "parameters": [
                {
                    "name": "daily_queue_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "patch": {
            "summary": "Update daily queue",
            "tags": ["Reception – Queues"],
            "parameters": [
                {
                    "name": "daily_queue_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "content": {"application/json": {"schema": {"type": "object"}}}
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/daily-queues/{{daily_queue_id}}/entries": {
        "get": {
            "summary": "List queue entries",
            "tags": ["Reception – Queues"],
            "parameters": [
                {
                    "name": "daily_queue_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
                LIST_LIMIT_Q,
            ],
            "responses": {
                "200": {"description": "Items"},
                "404": {"description": "Not found"},
            },
        },
        "post": {
            "summary": "Create queue entry",
            "tags": ["Reception – Queues"],
            "parameters": [
                {
                    "name": "daily_queue_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "201": {"description": "Created"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/queue-entries/{{queue_entry_id}}": {
        "get": {
            "summary": "Get queue entry",
            "tags": ["Reception – Queues"],
            "parameters": [
                {
                    "name": "queue_entry_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "patch": {
            "summary": "Update queue entry",
            "tags": ["Reception – Queues"],
            "parameters": [
                {
                    "name": "queue_entry_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "content": {"application/json": {"schema": {"type": "object"}}}
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/queue-entries/{{queue_entry_id}}/paper-intake-authorization": {
        "post": {
            "summary": "Authorize paper intake path",
            "description": (
                "ADMIN or MANAGER only. Creates `PaperIntakeAuthorization` for a WAITING queue "
                "entry (does not change `entry_status`). Body: `reason` (10–500 chars). "
                "Same business rules as internal `authorize_paper_intake` (appointment_time + "
                "3h, no SUBMITTED digital intake, no existing document, no duplicate auth). "
                "Clinic scope applies like other queue-entry mutations."
            ),
            "tags": ["Reception – Queues", "Medical"],
            "parameters": [
                {
                    "name": "queue_entry_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "201": {
                    "description": (
                        "Created. Body: `paper_intake_authorization_id`, `queue_entry_id`, "
                        "`authorized_at` (ISO)."
                    )
                },
                "400": {"description": "Domain or validation error"},
                "401": {"description": "Authentication required"},
                "403": {"description": "Forbidden (role or clinic scope)"},
                "404": {"description": "Queue entry not found"},
            },
        },
        "delete": {
            "summary": "Revoke paper intake authorization",
            "description": (
                "ADMIN or MANAGER only. Removes active authorization when no medical document "
                "exists yet for the queue entry. Body: `reason` (10–500 chars) recorded on audit."
            ),
            "tags": ["Reception – Queues", "Medical"],
            "parameters": [
                {
                    "name": "queue_entry_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "200": {
                    "description": "Revoked. Body: `queue_entry_id`, `revoked`: true"
                },
                "400": {"description": "Domain or validation error"},
                "401": {"description": "Authentication required"},
                "403": {"description": "Forbidden (role or clinic scope)"},
                "404": {"description": "Queue entry not found"},
            },
        },
    },
    f"{PREFIX}/queue-entries/{{queue_entry_id}}/sessions": {
        "post": {
            "summary": "Create tablet session",
            "description": "Creates a session for the intake form on a tablet. No token; tablet uses session cookie. Creator is the authenticated user. Allowed role: TABLET (or RECEPTION, ADMIN). Request body: form_locale (default de-DE), expires_in_minutes (default 120, max 480), optional tablet_device_id, optional android_id (for auto-registering the device).",
            "tags": ["Reception – Queues"],
            "parameters": [
                {
                    "name": "queue_entry_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "201": {
                    "description": "Session created. Body: session_id, expires_at (ISO), intake_form_id. No token."
                },
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/tablet-devices": {
        "get": {
            "summary": "List tablet devices",
            "description": "Items have id, android_id, is_active, last_seen_at (last tablet-area login for that android_id via /tablet/login or /auth/login with android_id, or manual POST …/heartbeat). Query: is_active, search (by android_id), limit (default 20, max 100).",
            "tags": ["Reception – Devices"],
            "parameters": [
                {"name": "is_active", "in": "query", "schema": {"type": "boolean"}},
                {
                    "name": "search",
                    "in": "query",
                    "schema": {
                        "type": "string",
                        "description": "Filter by android_id (substring)",
                    },
                },
                LIST_LIMIT_Q,
            ],
            "responses": {"200": {"description": "Items"}},
        },
        "post": {
            "summary": "Create tablet device",
            "description": "Body: android_id (required), is_active (default true). No name or device_code.",
            "tags": ["Reception – Devices"],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "201": {"description": "Created (id, android_id, is_active)"}
            },
        },
    },
    f"{PREFIX}/tablet-devices/{{tablet_device_id}}": {
        "get": {
            "summary": "Get tablet device",
            "description": "Returns id, android_id, is_active, last_seen_at (last login on device or heartbeat).",
            "tags": ["Reception – Devices"],
            "parameters": [
                {
                    "name": "tablet_device_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "patch": {
            "summary": "Update tablet device",
            "description": "Body: optional android_id, optional is_active.",
            "tags": ["Reception – Devices"],
            "parameters": [
                {
                    "name": "tablet_device_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "content": {"application/json": {"schema": {"type": "object"}}}
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
        "delete": {
            "summary": "Deactivate tablet device",
            "tags": ["Reception – Devices"],
            "parameters": [
                {
                    "name": "tablet_device_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/tablet-devices/{{tablet_device_id}}/heartbeat": {
        "post": {
            "summary": "Tablet heartbeat",
            "description": "Sets last_seen_at to now (operational refresh; same field as last login time from tablet auth). RECEPTION/ADMIN only.",
            "tags": ["Reception – Devices"],
            "parameters": [
                {
                    "name": "tablet_device_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "last_seen_at"},
                "404": {"description": "Not found"},
            },
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}": {
        "get": {
            "summary": "Get intake form context",
            "description": "Context for tablet: patient (read-only), consents, anamnesis questions with options and current answer, body_map, form status. `form_status` is one of `IN_PROGRESS`, `REOPENED` (reopened by reception/admin for patient to edit again), or `SUBMITTED`. TABLET restricted to today's queues.",
            "tags": ["Intake"],
            "parameters": [
                {
                    "name": "intake_form_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                },
                {"name": "form_locale", "in": "query", "schema": {"type": "string"}},
            ],
            "responses": {
                "200": {
                    "description": "Context (patient, consents, anamnesis_questions, body_map_data, form_status, has_signature)"
                },
                "404": {"description": "Not found"},
            },
        },
        "patch": {
            "summary": "Update body map",
            "description": "Update body_map_schema_version and body_map_data (list of points: x, y in [0,1], side front|back, optional label).",
            "tags": ["Intake"],
            "parameters": [
                {
                    "name": "intake_form_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "200": {
                    "description": "intake_form_id, body_map_schema_version, body_map_data"
                },
                "404": {"description": "Not found"},
                "409": {
                    "description": "State transition not allowed — body map edits only when `form_status` is `IN_PROGRESS` or `REOPENED` (see `error_key` / domain message)."
                },
            },
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}/anamnesis": {
        "put": {
            "summary": "Update anamnesis payload",
            "tags": ["Intake"],
            "parameters": [
                {
                    "name": "intake_form_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "anamnesis_schema_version": {"type": "integer"},
                                "answers": {"type": "array"},
                            },
                        }
                    }
                },
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
                "409": {
                    "description": "State transition not allowed — anamnesis edits only when `form_status` is `IN_PROGRESS` or `REOPENED` (see `error_key`)."
                },
            },
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}/consents": {
        "put": {
            "summary": "Update intake form consents",
            "description": "Replace consent acceptance set. Body: consents[] with consent_definition_id, accepted.",
            "tags": ["Intake"],
            "parameters": [
                {
                    "name": "intake_form_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "200": {"description": "intake_form_id, consents"},
                "404": {"description": "Not found"},
                "409": {
                    "description": "State transition not allowed — consents editable only when `form_status` is `IN_PROGRESS` or `REOPENED`, and consent definitions must be active for the date (see `error_key`)."
                },
            },
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}/signature": {
        "post": {
            "summary": "Upload signature",
            "description": "Base64-encoded image (e.g. data:image/png;base64,...). Max 2MB.",
            "tags": ["Intake"],
            "parameters": [
                {
                    "name": "intake_form_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "responses": {
                "200": {"description": "signature_file_path, signature_sha256"},
                "400": {"description": "Invalid signature"},
                "404": {"description": "Not found"},
                "409": {
                    "description": "State transition not allowed — signature upload only when `form_status` is `IN_PROGRESS` or `REOPENED` (see `error_key`)."
                },
                "413": {"description": "Payload too large"},
            },
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}/submit": {
        "post": {
            "summary": "Submit intake form",
            "tags": ["Intake"],
            "parameters": [
                {
                    "name": "intake_form_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "submitted_by_user_id": {
                                    "type": "string",
                                    "format": "uuid",
                                }
                            },
                        }
                    }
                },
            },
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not found"},
                "400": {
                    "description": "Validation or business rule (e.g. missing consents/anamnesis/signature); may include `error_key`."
                },
            },
        },
    },
    f"{PREFIX}/patient-results/request-otp": {
        "post": {
            "summary": "Request OTP",
            "description": "Request OTP for patient results portal. Sends SMS if patient exists (phone + date_of_birth). CAPTCHA required. No auth.",
            "tags": ["Patient results"],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "phone": {"type": "string"},
                                "date_of_birth": {
                                    "type": "string",
                                    "format": "date",
                                    "description": "YYYY-MM-DD",
                                },
                                "captcha_token": {"type": "string"},
                            },
                            "required": ["phone", "date_of_birth", "captcha_token"],
                        }
                    }
                },
            },
            "responses": {
                "200": {"description": "OK (always, to prevent enumeration)"},
                "400": {"description": "Invalid input or CAPTCHA failed"},
            },
        },
    },
    f"{PREFIX}/patient-results/verify-otp": {
        "post": {
            "summary": "Verify OTP",
            "description": "Verify OTP code and establish patient results session. Sets session cookie for documents/download. No auth.",
            "tags": ["Patient results"],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "phone": {"type": "string"},
                                "date_of_birth": {
                                    "type": "string",
                                    "format": "date",
                                    "description": "YYYY-MM-DD",
                                },
                                "otp_code": {"type": "string"},
                            },
                            "required": ["phone", "date_of_birth", "otp_code"],
                        }
                    }
                },
            },
            "responses": {
                "200": {"description": "OK, session cookie set"},
                "400": {"description": "Invalid or expired code"},
            },
        },
    },
    f"{PREFIX}/patient-results/documents": {
        "get": {
            "summary": "List documents",
            "description": "List published documents for the logged-in patient. Requires patient_results session (from verify-otp).",
            "tags": ["Patient results"],
            "responses": {
                "200": {
                    "description": "items: [{version_id, document_id, queue_date, published_at}]"
                },
                "401": {"description": "Session required"},
            },
        },
    },
    f"{PREFIX}/patient-results/documents/{{version_id}}/download": {
        "get": {
            "summary": "Download PDF",
            "description": "Download Befund PDF for a version. Requires patient_results session.",
            "tags": ["Patient results"],
            "parameters": [
                {
                    "name": "version_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {"description": "PDF file"},
                "401": {"description": "Session required"},
                "404": {"description": "Not found or unavailable"},
            },
        },
    },
}


def _paths_with_pydantic_refs() -> dict:
    """Build paths from COGITO_PATHS, injecting $ref request/response schemas from Pydantic where registered."""
    paths: dict[str, Any] = {}
    for path_key, operations in COGITO_PATHS.items():
        paths[path_key] = {}
        for method, spec in operations.items():  # type: ignore[attr-defined]
            op = deepcopy(spec)
            body_schema = get_request_body_schema_for(path_key, method)
            if (
                body_schema is not None
                and "requestBody" in op
                and "content" in op["requestBody"]
            ):
                op["requestBody"]["content"]["application/json"] = {
                    "schema": body_schema
                }
            for status in ("200", "201"):
                response_schema = get_response_schema_for(path_key, method, status)
                if (
                    response_schema is not None
                    and "responses" in op
                    and status in op["responses"]
                ):
                    op["responses"][status]["content"] = {
                        "application/json": {"schema": response_schema}
                    }
            # Require login for all operations except NO_AUTH_OPERATIONS (Swagger UI shows lock icon).
            if (path_key, method) in NO_AUTH_OPERATIONS:
                op["security"] = []
            else:
                op["security"] = [{SECURITY_SCHEME_SESSION: []}]
            paths[path_key][method] = op
    return paths


def cogito_extend_schema(schema, *args, **kwargs):
    """POSTPROCESSING_HOOK: inject Cogitomedica API v1 paths into the OpenAPI schema."""
    if schema is None:
        return build_cogito_openapi_schema()
    if "paths" not in schema:
        schema["paths"] = {}
    paths = _paths_with_pydantic_refs()
    for path_key, operations in paths.items():
        if path_key not in schema["paths"]:
            schema["paths"][path_key] = {}
        for method, spec in operations.items():
            schema["paths"][path_key][method] = spec
    if "components" not in schema:
        schema["components"] = {}
    schema["components"].setdefault("schemas", {}).update(get_components_schemas())
    return schema


def build_cogito_openapi_schema() -> dict:
    """Build full OpenAPI 3.0 schema for Cogitomedica API."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Cogitomedica API",
            "description": "OpenAPI schema for Cogitomedica backend. All API v1 endpoints are documented.",
            "version": "1.0.0",
        },
        "servers": [
            {
                "url": "/",
                "description": "Relative to current host (e.g. http://127.0.0.1:8000)",
            }
        ],
        "paths": _paths_with_pydantic_refs(),
        "components": {
            "schemas": get_components_schemas(),
            "securitySchemes": {
                SECURITY_SCHEME_SESSION: {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "sessionid",
                    "description": "Wymagane logowanie (sesja Django). Zaloguj się przez POST /api/v1/auth/login, aby wywoływać chronione endpointy.",
                },
            },
        },
    }


@require_GET
def cogito_openapi_schema_view(request):
    """Serve OpenAPI 3.0 schema as JSON for Swagger UI / ReDoc."""
    schema = build_cogito_openapi_schema()
    return JsonResponse(schema, json_dumps_params={"indent": 0})
