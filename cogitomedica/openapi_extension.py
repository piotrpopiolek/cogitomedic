"""
OpenAPI schema for Cogitomedica API v1.

API uses Django view functions (not DRF), so drf-spectacular does not auto-discover them.
We serve the full schema from cogito_openapi_schema_view so /api/docs works without DRF views.

Request/response body schemas are generated from Pydantic models (openapi_schemas) so the
documentation stays in sync with api_schemas in each app.
"""
from __future__ import annotations

from copy import deepcopy

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from cogitomedica.openapi_schemas import (
    get_components_schemas,
    get_request_body_schema_for,
    get_response_schema_for,
)

PREFIX = "/api/v1"

# Operations that do not require authentication (no lock icon in Swagger UI).
NO_AUTH_OPERATIONS = {
    (f"{PREFIX}/observability/health", "get"),
    (f"{PREFIX}/observability/metrics", "get"),
    (f"{PREFIX}/observability/monitoring/grafana", "get"),
    (f"{PREFIX}/observability/monitoring/prometheus", "get"),
    (f"{PREFIX}/observability/monitoring/alertmanager", "get"),
    (f"{PREFIX}/observability/monitoring/tempo", "get"),
    (f"{PREFIX}/observability/monitoring/otel-collector", "get"),
    (f"{PREFIX}/auth/login", "post"),
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
            "responses": {"200": {"description": "OK or degraded"}, "503": {"description": "Service unavailable"}},
        },
    },
    f"{PREFIX}/observability/metrics": {
        "get": {
            "summary": "Prometheus metrics",
            "description": "Eksport metryk w formacie Prometheus. Wymaga nagłówka `Authorization: Bearer <PROMETHEUS_METRICS_TOKEN>` lub zalogowanej sesji z rolą ADMIN.",
            "tags": ["Observability"],
            "responses": {"200": {"description": "Metrics text"}, "401": {"description": "Unauthorized"}},
        },
    },
    # Adresy usług monitorowania (Docker) – tylko w dokumentacji, nie są obsługiwane przez API
    f"{PREFIX}/observability/monitoring/grafana": {
        "get": {
            "summary": "Grafana",
            "description": "Zewnętrzny adres: http://localhost:3000 — dashboardy (metryki, trace'y). Logowanie: admin / admin.",
            "tags": ["Observability"],
            "responses": {"200": {"description": "Usługa zewnętrzna – otwórz adres w przeglądarce."}},
        },
    },
    f"{PREFIX}/observability/monitoring/prometheus": {
        "get": {
            "summary": "Prometheus",
            "description": "Zewnętrzny adres: http://localhost:9090 — UI PromQL, targety: http://localhost:9090/targets",
            "tags": ["Observability"],
            "responses": {"200": {"description": "Usługa zewnętrzna – otwórz adres w przeglądarce."}},
        },
    },
    f"{PREFIX}/observability/monitoring/alertmanager": {
        "get": {
            "summary": "Alertmanager",
            "description": "Zewnętrzny adres: http://localhost:9093 — zarządzanie alertami i powiadomieniami.",
            "tags": ["Observability"],
            "responses": {"200": {"description": "Usługa zewnętrzna – otwórz adres w przeglądarce."}},
        },
    },
    f"{PREFIX}/observability/monitoring/tempo": {
        "get": {
            "summary": "Grafana Tempo",
            "description": "Zewnętrzny adres: http://localhost:3200 — backend trace'ów; dostęp z Grafany (Explore → Tempo).",
            "tags": ["Observability"],
            "responses": {"200": {"description": "Usługa zewnętrzna – otwórz adres w przeglądarce."}},
        },
    },
    f"{PREFIX}/observability/monitoring/otel-collector": {
        "get": {
            "summary": "OpenTelemetry Collector",
            "description": "Zewnętrzne adresy: localhost:4317 (gRPC), localhost:4318 (HTTP) — odbiera trace'y z aplikacji (brak UI).",
            "tags": ["Observability"],
            "responses": {"200": {"description": "Usługa zewnętrzna – używana wewnętrznie przez aplikację."}},
        },
    },
    f"{PREFIX}/auth/login": {
        "post": {
            "summary": "Log in",
            "description": "Authenticate with username and password. Sets session cookie.",
            "tags": ["Auth"],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"username": {"type": "string"}, "password": {"type": "string"}}, "required": ["username", "password"]}}}},
            "responses": {"200": {"description": "User and session expiry"}, "401": {"description": "Invalid credentials"}},
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
            "responses": {"200": {"description": "User payload"}, "401": {"description": "Authentication required"}},
        },
    },
    f"{PREFIX}/staff-users": {
        "get": {
            "summary": "List staff users",
            "description": "Paginated list. Admin only.",
            "tags": ["Staff users"],
            "parameters": [{"name": "page", "in": "query", "schema": {"type": "integer"}}, {"name": "page_size", "in": "query", "schema": {"type": "integer"}}, {"name": "role", "in": "query", "schema": {"type": "string"}}, {"name": "is_active", "in": "query", "schema": {"type": "boolean"}}, {"name": "search", "in": "query", "schema": {"type": "string"}}],
            "responses": {"200": {"description": "Items and pagination"}, "401": {"description": "Authentication required"}, "403": {"description": "Forbidden"}},
        },
        "post": {
            "summary": "Create staff user",
            "description": "Admin only.",
            "tags": ["Staff users"],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"201": {"description": "Created"}, "400": {"description": "Validation error"}, "401": {"description": "Authentication required"}, "403": {"description": "Forbidden"}, "409": {"description": "Username or email exists"}},
        },
    },
    f"{PREFIX}/staff-users/{{staff_user_id}}": {
        "get": {"summary": "Get staff user", "tags": ["Staff users"], "parameters": [{"name": "staff_user_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "patch": {"summary": "Update staff user", "tags": ["Staff users"], "parameters": [{"name": "staff_user_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}, "409": {"description": "Conflict"}},
        },
        "delete": {"summary": "Deactivate staff user", "tags": ["Staff users"], "parameters": [{"name": "staff_user_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "Deactivated"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/doctor-text-templates": {
        "get": {
            "summary": "List doctor text templates",
            "tags": ["Doctor templates"],
            "parameters": [{"name": "actor_user_id", "in": "query", "schema": {"type": "string", "format": "uuid"}}, {"name": "template_locale", "in": "query", "schema": {"type": "string"}}, {"name": "include_inactive", "in": "query", "schema": {"type": "boolean"}}],
            "responses": {"200": {"description": "Results"}},
        },
        "post": {
            "summary": "Create doctor text template",
            "tags": ["Doctor templates"],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"201": {"description": "Created"}, "400": {"description": "Validation error"}},
        },
    },
    f"{PREFIX}/doctor-text-templates/{{template_id}}": {
        "get": {
            "summary": "Get doctor text template",
            "tags": ["Doctor templates"],
            "parameters": [{"name": "template_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "responses": {"200": {"description": "Template (name, template_body, lesion_group_favorites, etc.)"}, "404": {"description": "Not found"}},
        },
        "patch": {
            "summary": "Update doctor text template",
            "tags": ["Doctor templates"],
            "parameters": [{"name": "template_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/outbox-events": {
        "get": {
            "summary": "List outbox events",
            "tags": ["Outbox"],
            "parameters": [{"name": "status", "in": "query", "schema": {"type": "string"}}, {"name": "event_type", "in": "query", "schema": {"type": "string"}}, {"name": "retry_count_gte", "in": "query", "schema": {"type": "integer"}}, {"name": "limit", "in": "query", "schema": {"type": "integer"}}],
            "responses": {"200": {"description": "Results and count"}},
        },
    },
    f"{PREFIX}/outbox-events/{{outbox_event_id}}/retry": {
        "post": {
            "summary": "Retry outbox event",
            "tags": ["Outbox"],
            "parameters": [{"name": "outbox_event_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"reason": {"type": "string"}}}}}},
            "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}, "409": {"description": "Conflict"}},
        },
    },
    f"{PREFIX}/operations/outbox/process": {
        "post": {
            "summary": "Process outbox batch",
            "tags": ["Operations"],
            "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"limit": {"type": "integer"}}}}}},
            "responses": {"202": {"description": "Accepted (processed, failed, dead_lettered)"}},
        },
    },
    f"{PREFIX}/operations/retention/run": {
        "post": {
            "summary": "Run retention cleanup",
            "tags": ["Operations"],
            "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"older_than_days": {"type": "integer"}, "dry_run": {"type": "boolean"}}}}}},
            "responses": {"202": {"description": "Candidates, deleted, skipped"}},
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
                {"name": "retry_count_gte", "in": "query", "schema": {"type": "integer"}},
                {"name": "limit", "in": "query", "schema": {"type": "integer"}},
            ],
            "responses": {"200": {"description": "results, count"}},
        },
    },
    f"{PREFIX}/intake-outbox-events/{{intake_outbox_event_id}}/retry": {
        "post": {
            "summary": "Retry intake outbox event",
            "description": "Move FAILED/DEAD_LETTER event back to PENDING. ADMIN, RECEPTION.",
            "tags": ["Intake – Outbox"],
            "parameters": [{"name": "intake_outbox_event_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "id, status, retry_count"}, "404": {"description": "Not found"}, "409": {"description": "Event not retryable"}},
        },
    },
    f"{PREFIX}/operations/intake-outbox/process": {
        "post": {
            "summary": "Process intake outbox batch",
            "description": "Process pending/failed intake outbox events (PDF generation, HiDrive upload). ADMIN only.",
            "tags": ["Intake – Outbox"],
            "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"202": {"description": "processed, failed, dead_lettered"}},
        },
    },
    f"{PREFIX}/medical-documents": {
        "get": {
            "summary": "List medical documents",
            "description": "Doctor work queue. Filtered by consulting room of the current user. Paginated.",
            "tags": ["Medical"],
            "parameters": [
                {"name": "status", "in": "query", "schema": {"type": "string"}},
                {"name": "queue_date", "in": "query", "schema": {"type": "string", "format": "date"}},
                {"name": "patient_search", "in": "query", "schema": {"type": "string"}},
                {"name": "page", "in": "query", "schema": {"type": "integer"}},
                {"name": "page_size", "in": "query", "schema": {"type": "integer"}},
            ],
            "responses": {"200": {"description": "Items and pagination"}, "401": {"description": "Authentication required"}, "403": {"description": "Forbidden"}},
        },
        "post": {
            "summary": "Create medical document",
            "description": "Doctor or Admin. Links queue entry and intake form.",
            "tags": ["Medical"],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"queue_entry_id": {"type": "string", "format": "uuid"}, "intake_form_id": {"type": "string", "format": "uuid"}, "created_by_user_id": {"type": "string", "format": "uuid"}}}}}},
            "responses": {"201": {"description": "Created"}, "404": {"description": "Queue entry or intake form not found"}},
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}": {
        "get": {
            "summary": "Get medical document context",
            "description": "Full document context for doctor panel: intake summary and current version (draft or published).",
            "tags": ["Medical"],
            "parameters": [
                {"name": "medical_document_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                {"name": "form_locale", "in": "query", "schema": {"type": "string"}},
            ],
            "responses": {"200": {"description": "Context (intake, version, patient, etc.)"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/preview-pdf": {
        "get": {
            "summary": "Preview PDF",
            "description": "Returns PDF of the latest saved version (draft or published). Content-Type: application/pdf.",
            "tags": ["Medical"],
            "parameters": [
                {"name": "medical_document_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                {"name": "form_locale", "in": "query", "schema": {"type": "string"}},
                {"name": "authoring_locale", "in": "query", "schema": {"type": "string"}},
            ],
            "responses": {"200": {"description": "PDF file (inline)"}, "404": {"description": "Not found or no version to preview"}},
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/versions": {
        "get": {
            "summary": "List document versions",
            "tags": ["Medical"],
            "parameters": [{"name": "medical_document_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "responses": {"200": {"description": "Items (version_no, version_status, pdf_generation_status, etc.)"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/retry-processing": {
        "post": {
            "summary": "Retry document processing",
            "description": "Retry latest failed outbox step (e.g. PDF generation, HiDrive, SMS). ADMIN or RECEPTION.",
            "tags": ["Medical"],
            "parameters": [{"name": "medical_document_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"reason": {"type": "string"}}}}}},
            "responses": {"200": {"description": "retried, outbox_event_id, event_type, status"}, "404": {"description": "Not found"}, "409": {"description": "Nothing to retry"}},
        },
    },
    f"{PREFIX}/medical-document-versions/{{version_id}}": {
        "get": {
            "summary": "Get document version",
            "description": "Single version by id (MedicalDocumentVersion.id) with full medical_payload.",
            "tags": ["Medical"],
            "parameters": [{"name": "version_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "responses": {"200": {"description": "Version details"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/draft": {
        "put": {
            "summary": "Save draft",
            "tags": ["Medical"],
            "parameters": [{"name": "medical_document_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "Version"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/medical-documents/{{medical_document_id}}/publish": {
        "post": {
            "summary": "Publish document",
            "tags": ["Medical"],
            "parameters": [{"name": "medical_document_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "Version"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/clinic-sites": {
        "get": {"summary": "List clinic sites", "tags": ["Reception – Dictionaries"], "parameters": [{"name": "is_active", "in": "query", "schema": {"type": "boolean"}}, {"name": "search", "in": "query", "schema": {"type": "string"}}, {"name": "limit", "in": "query", "schema": {"type": "integer"}}], "responses": {"200": {"description": "Items"}},
        },
        "post": {"summary": "Create clinic site", "tags": ["Reception – Dictionaries"], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"201": {"description": "Created"}},
        },
    },
    f"{PREFIX}/clinic-sites/{{clinic_site_id}}": {
        "get": {"summary": "Get clinic site", "tags": ["Reception – Dictionaries"], "parameters": [{"name": "clinic_site_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "patch": {"summary": "Update clinic site", "tags": ["Reception – Dictionaries"], "parameters": [{"name": "clinic_site_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "delete": {"summary": "Deactivate clinic site", "tags": ["Reception – Dictionaries"], "parameters": [{"name": "clinic_site_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/consulting-rooms": {
        "get": {"summary": "List consulting rooms", "tags": ["Reception – Dictionaries"], "parameters": [{"name": "clinic_site_id", "in": "query", "schema": {"type": "string", "format": "uuid"}}, {"name": "is_active", "in": "query", "schema": {"type": "boolean"}}, {"name": "search", "in": "query", "schema": {"type": "string"}}, {"name": "limit", "in": "query", "schema": {"type": "integer"}}], "responses": {"200": {"description": "Items"}},
        },
        "post": {"summary": "Create consulting room", "tags": ["Reception – Dictionaries"], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"201": {"description": "Created"}},
        },
    },
    f"{PREFIX}/consulting-rooms/{{consulting_room_id}}": {
        "get": {"summary": "Get consulting room", "tags": ["Reception – Dictionaries"], "parameters": [{"name": "consulting_room_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "patch": {"summary": "Update consulting room", "tags": ["Reception – Dictionaries"], "parameters": [{"name": "consulting_room_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "delete": {"summary": "Deactivate consulting room", "tags": ["Reception – Dictionaries"], "parameters": [{"name": "consulting_room_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/patients": {
        "get": {"summary": "List patients", "tags": ["Reception – Patients"], "parameters": [{"name": "search", "in": "query", "schema": {"type": "string"}}, {"name": "last_name", "in": "query", "schema": {"type": "string"}}, {"name": "date_of_birth", "in": "query", "schema": {"type": "string", "format": "date"}}, {"name": "phone", "in": "query", "schema": {"type": "string"}}, {"name": "identity_status", "in": "query", "schema": {"type": "string"}}, {"name": "doctolib_patient_id", "in": "query", "schema": {"type": "string"}}, {"name": "is_active", "in": "query", "schema": {"type": "boolean"}}, {"name": "page", "in": "query", "schema": {"type": "integer"}}, {"name": "page_size", "in": "query", "schema": {"type": "integer"}}], "responses": {"200": {"description": "Items and pagination"}},
        },
        "post": {"summary": "Create or update patient (manual)", "tags": ["Reception – Patients"], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "Patient"}, "201": {"description": "Created"}},
        },
    },
    f"{PREFIX}/patients/{{patient_id}}": {
        "get": {"summary": "Get patient", "tags": ["Reception – Patients"], "parameters": [{"name": "patient_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "patch": {"summary": "Update patient", "tags": ["Reception – Patients"], "parameters": [{"name": "patient_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "delete": {"summary": "Deactivate patient", "tags": ["Reception – Patients"], "parameters": [{"name": "patient_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/patients/{{patient_id}}/contact-history": {
        "get": {
            "summary": "Patient contact history",
            "tags": ["Reception – Patients"],
            "parameters": [{"name": "patient_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}, {"name": "page", "in": "query", "schema": {"type": "integer"}}, {"name": "page_size", "in": "query", "schema": {"type": "integer"}}],
            "responses": {"200": {"description": "Items and pagination"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/patients/{{patient_id}}/merge": {
        "post": {
            "summary": "Merge temporary patient into confirmed",
            "tags": ["Reception – Patients"],
            "parameters": [{"name": "patient_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"target_patient_id": {"type": "string", "format": "uuid"}, "source_action": {"type": "string"}, "reason": {"type": "string"}, "actor_user_id": {"type": "string", "format": "uuid"}}}}}},
            "responses": {"200": {"description": "Merge result"}, "404": {"description": "Not found"}, "409": {"description": "Conflict"}, "422": {"description": "Unprocessable"}},
        },
    },
    f"{PREFIX}/daily-queues": {
        "get": {"summary": "List daily queues", "tags": ["Reception – Queues"], "parameters": [{"name": "queue_date", "in": "query", "schema": {"type": "string", "format": "date"}}, {"name": "clinic_site_id", "in": "query", "schema": {"type": "string", "format": "uuid"}}, {"name": "consulting_room_id", "in": "query", "schema": {"type": "string", "format": "uuid"}}, {"name": "shift_code", "in": "query", "schema": {"type": "string"}}, {"name": "status", "in": "query", "schema": {"type": "string"}}, {"name": "limit", "in": "query", "schema": {"type": "integer"}}], "responses": {"200": {"description": "Items"}},
        },
        "post": {"summary": "Create daily queue", "tags": ["Reception – Queues"], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"201": {"description": "Created"}},
        },
    },
    f"{PREFIX}/daily-queues/{{daily_queue_id}}": {
        "get": {"summary": "Get daily queue", "tags": ["Reception – Queues"], "parameters": [{"name": "daily_queue_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "patch": {"summary": "Update daily queue", "tags": ["Reception – Queues"], "parameters": [{"name": "daily_queue_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/daily-queues/{{daily_queue_id}}/entries": {
        "get": {"summary": "List queue entries", "tags": ["Reception – Queues"], "parameters": [{"name": "daily_queue_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}, {"name": "limit", "in": "query", "schema": {"type": "integer"}}], "responses": {"200": {"description": "Items"}, "404": {"description": "Not found"}},
        },
        "post": {"summary": "Create queue entry", "tags": ["Reception – Queues"], "parameters": [{"name": "daily_queue_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"201": {"description": "Created"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/queue-entries/{{queue_entry_id}}": {
        "get": {"summary": "Get queue entry", "tags": ["Reception – Queues"], "parameters": [{"name": "queue_entry_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "patch": {"summary": "Update queue entry", "tags": ["Reception – Queues"], "parameters": [{"name": "queue_entry_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/queue-entries/{{queue_entry_id}}/sessions": {
        "post": {
            "summary": "Create tablet session",
            "description": "Creates a session for the intake form on a tablet. No token; tablet uses session cookie. Creator is the authenticated user. Allowed role: TABLET (or RECEPTION, ADMIN). Request body: form_locale (default de-DE), expires_in_minutes (default 120, max 480), optional tablet_device_id, optional android_id (for auto-registering the device).",
            "tags": ["Reception – Queues"],
            "parameters": [{"name": "queue_entry_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"201": {"description": "Session created. Body: session_id, expires_at (ISO), intake_form_id. No token."}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/tablet-devices": {
        "get": {"summary": "List tablet devices", "description": "Items have id, android_id, is_active, last_seen_at. Query: is_active, search (by android_id), limit.", "tags": ["Reception – Devices"], "parameters": [{"name": "is_active", "in": "query", "schema": {"type": "boolean"}}, {"name": "search", "in": "query", "schema": {"type": "string", "description": "Filter by android_id (substring)"}}, {"name": "limit", "in": "query", "schema": {"type": "integer"}}], "responses": {"200": {"description": "Items"}},
        },
        "post": {"summary": "Create tablet device", "description": "Body: android_id (required), is_active (default true). No name or device_code.", "tags": ["Reception – Devices"], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"201": {"description": "Created (id, android_id, is_active)"}},
        },
    },
    f"{PREFIX}/tablet-devices/{{tablet_device_id}}": {
        "get": {"summary": "Get tablet device", "description": "Returns id, android_id, is_active, last_seen_at.", "tags": ["Reception – Devices"], "parameters": [{"name": "tablet_device_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "patch": {"summary": "Update tablet device", "description": "Body: optional android_id, optional is_active.", "tags": ["Reception – Devices"], "parameters": [{"name": "tablet_device_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
        "delete": {"summary": "Deactivate tablet device", "tags": ["Reception – Devices"], "parameters": [{"name": "tablet_device_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}], "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/tablet-devices/{{tablet_device_id}}/heartbeat": {
        "post": {
            "summary": "Tablet heartbeat",
            "tags": ["Reception – Devices"],
            "parameters": [{"name": "tablet_device_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "responses": {"200": {"description": "last_seen_at"}, "404": {"description": "Not found"}},
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}": {
        "get": {
            "summary": "Get intake form context",
            "description": "Context for tablet: patient (read-only), consents, anamnesis questions with options and current answer, body_map, form status. TABLET restricted to today's queues.",
            "tags": ["Intake"],
            "parameters": [{"name": "intake_form_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}, {"name": "form_locale", "in": "query", "schema": {"type": "string"}}],
            "responses": {"200": {"description": "Context (patient, consents, anamnesis_questions, body_map_data, form_status, has_signature)"}, "404": {"description": "Not found"}},
        },
        "patch": {
            "summary": "Update body map",
            "description": "Update body_map_schema_version and body_map_data (list of points: x, y in [0,1], side front|back, optional label).",
            "tags": ["Intake"],
            "parameters": [{"name": "intake_form_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "intake_form_id, body_map_schema_version, body_map_data"}, "404": {"description": "Not found"}, "409": {"description": "Form not IN_PROGRESS"}},
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}/anamnesis": {
        "put": {
            "summary": "Update anamnesis payload",
            "tags": ["Intake"],
            "parameters": [{"name": "intake_form_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"anamnesis_schema_version": {"type": "integer"}, "answers": {"type": "array"}}}}}},
            "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}, "409": {"description": "Conflict"}},
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}/consents": {
        "put": {
            "summary": "Update intake form consents",
            "description": "Replace consent acceptance set. Body: consents[] with consent_definition_id, accepted.",
            "tags": ["Intake"],
            "parameters": [{"name": "intake_form_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "intake_form_id, consents"}, "404": {"description": "Not found"}, "409": {"description": "Form not IN_PROGRESS or consent not active"}},
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}/signature": {
        "post": {
            "summary": "Upload signature",
            "description": "Base64-encoded image (e.g. data:image/png;base64,...). Max 2MB.",
            "tags": ["Intake"],
            "parameters": [{"name": "intake_form_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "signature_file_path, signature_sha256"}, "400": {"description": "Invalid signature"}, "404": {"description": "Not found"}, "409": {"description": "Form already submitted"}, "413": {"description": "Payload too large"}},
        },
    },
    f"{PREFIX}/intake-forms/{{intake_form_id}}/submit": {
        "post": {
            "summary": "Submit intake form",
            "tags": ["Intake"],
            "parameters": [{"name": "intake_form_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"submitted_by_user_id": {"type": "string", "format": "uuid"}}}}}},
            "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}, "400": {"description": "Validation error"}},
        },
    },
}


def _paths_with_pydantic_refs() -> dict:
    """Build paths from COGITO_PATHS, injecting $ref request/response schemas from Pydantic where registered."""
    paths = {}
    for path_key, operations in COGITO_PATHS.items():
        paths[path_key] = {}
        for method, spec in operations.items():
            op = deepcopy(spec)
            body_schema = get_request_body_schema_for(path_key, method)
            if body_schema is not None and "requestBody" in op and "content" in op["requestBody"]:
                op["requestBody"]["content"]["application/json"] = {"schema": body_schema}
            for status in ("200", "201"):
                response_schema = get_response_schema_for(path_key, method, status)
                if response_schema is not None and "responses" in op and status in op["responses"]:
                    op["responses"][status]["content"] = {"application/json": {"schema": response_schema}}
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
        "servers": [{"url": "/", "description": "Relative to current host (e.g. http://127.0.0.1:8000)"}],
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
