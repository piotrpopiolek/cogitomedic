"""
Generate OpenAPI 3.0 component schemas from Pydantic models.

Pydantic v2 model_json_schema() returns JSON Schema with $defs; OpenAPI 3.0
uses components/schemas and #/components/schemas/Name refs. This module
flattens $defs into components.schemas and rewrites $refs for use in the
Cogitomedica OpenAPI schema.
"""
from __future__ import annotations

from typing import Any

# Ref prefix used in the final OpenAPI document
COMPONENTS_REF_PREFIX = "#/components/schemas/"
PYDANTIC_DEFS_PREFIX = "#/$defs/"


def _rewrite_refs(obj: Any, ref_prefix: str) -> Any:
    """Recursively replace #/$defs/X with ref_prefix + X in $ref values."""
    if isinstance(obj, dict):
        if "$ref" in obj and isinstance(obj["$ref"], str):
            ref = obj["$ref"]
            if ref.startswith(PYDANTIC_DEFS_PREFIX):
                name = ref[len(PYDANTIC_DEFS_PREFIX) :]
                return {"$ref": ref_prefix + name}
        return {k: _rewrite_refs(v, ref_prefix) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rewrite_refs(item, ref_prefix) for item in obj]
    return obj


def pydantic_to_openapi_schema(
    schema: dict[str, Any],
    *,
    ref_prefix: str = COMPONENTS_REF_PREFIX,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """
    Convert Pydantic model_json_schema() output for OpenAPI 3.0 components.

    Returns:
        (root_schema, definitions): root_schema is the request/response schema
        (often a $ref); definitions is a name -> schema dict to merge into
        components.schemas. All $refs are rewritten to ref_prefix.
    """
    schema = dict(schema)
    defs = schema.pop("$defs", {})

    # Rewrite refs in definitions first (they may reference each other)
    defs_rewritten = {
        name: _rewrite_refs(defn, ref_prefix) for name, defn in defs.items()
    }

    # Root: either a $ref or an inline object
    root = _rewrite_refs(schema, ref_prefix)

    # If root is a single $ref, the referenced name is the main model
    if set(root.keys()) == {"$ref"} and root["$ref"].startswith(ref_prefix):
        main_name = root["$ref"][len(ref_prefix) :]
        # Ensure main model is in definitions (Pydantic often puts it in $defs)
        if main_name not in defs_rewritten and main_name in defs:
            defs_rewritten[main_name] = _rewrite_refs(defs[main_name], ref_prefix)
    return root, defs_rewritten


def build_components_schemas(
    model_classes: list[type],
) -> dict[str, dict[str, Any]]:
    """
    Build OpenAPI 3.0 components.schemas from a list of Pydantic model classes.

    Nested models (from $defs) are merged into the same components.schemas dict
    with unique names. Caller should set openapi_doc["components"] = {"schemas": result}.
    """
    from pydantic import BaseModel

    all_schemas: dict[str, dict[str, Any]] = {}

    for model in model_classes:
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            continue
        raw = model.model_json_schema()
        root, defs = pydantic_to_openapi_schema(raw)
        # Root may be $ref to model.__name__; ensure it's in defs
        root_name = model.__name__
        if set(root.keys()) == {"$ref"} and root["$ref"].endswith(root_name):
            # Merge defs (root model + nested)
            for name, s in defs.items():
                if name not in all_schemas:
                    all_schemas[name] = s
        else:
            # Root is inline schema (no $ref)
            all_schemas[root_name] = root
            for name, s in defs.items():
                if name not in all_schemas:
                    all_schemas[name] = s

    return all_schemas


def get_request_schema_ref(model_class: type) -> dict[str, Any]:
    """
    Return OpenAPI request body schema that references the component for this model.

    Use in paths[path][method]["requestBody"]["content"]["application/json"]["schema"].
    """
    return {"$ref": f"{COMPONENTS_REF_PREFIX}{model_class.__name__}"}


def _get_request_model_registry() -> list[type]:
    """All Pydantic models used as API request/query bodies (for components.schemas)."""
    from apps.intake.api_schemas import (
        AnamnesisAnswerPayload,
        SubmitIntakeFormRequest,
        UpdateAnamnesisPayloadRequest,
    )
    from apps.medical.api_schemas import (
        CreateMedicalDocumentRequest,
        DoctorTemplateCreateRequest,
        DoctorTemplateUpdateRequest,
        PublishMedicalDocumentRequest,
        SaveDraftMedicalDocumentRequest,
    )
    from apps.outbox.api_schemas import (
        ProcessOutboxRequest,
        RetentionRunRequest,
        RetryOutboxEventRequest,
    )
    from apps.reception.api_schemas import (
        CreateClinicSiteRequest,
        CreateConsultingRoomRequest,
        CreateDailyQueueRequest,
        CreatePatientRequest,
        CreateQueueEntryRequest,
        CreateQueueEntrySessionRequest,
        CreateTabletDeviceRequest,
        MergePatientRequest,
        UpdateClinicSiteRequest,
        UpdateConsultingRoomRequest,
        UpdateDailyQueueRequest,
        UpdatePatientRequest,
        UpdateQueueEntryRequest,
        UpdateTabletDeviceRequest,
    )
    from apps.users.api_schemas import (
        AuthLoginRequest,
        CreateStaffUserRequest,
        UpdateStaffUserRequest,
    )

    return [
        # Auth
        AuthLoginRequest,
        # Staff users
        CreateStaffUserRequest,
        UpdateStaffUserRequest,
        # Doctor templates
        DoctorTemplateCreateRequest,
        DoctorTemplateUpdateRequest,
        # Outbox / operations
        ProcessOutboxRequest,
        RetryOutboxEventRequest,
        RetentionRunRequest,
        # Medical
        CreateMedicalDocumentRequest,
        SaveDraftMedicalDocumentRequest,
        PublishMedicalDocumentRequest,
        # Intake (AnamnesisAnswerPayload is nested in UpdateAnamnesisPayloadRequest)
        AnamnesisAnswerPayload,
        UpdateAnamnesisPayloadRequest,
        SubmitIntakeFormRequest,
        # Reception
        CreateQueueEntrySessionRequest,
        CreateDailyQueueRequest,
        UpdateDailyQueueRequest,
        CreateQueueEntryRequest,
        UpdateQueueEntryRequest,
        CreateTabletDeviceRequest,
        UpdateTabletDeviceRequest,
        CreateClinicSiteRequest,
        UpdateClinicSiteRequest,
        CreateConsultingRoomRequest,
        UpdateConsultingRoomRequest,
        CreatePatientRequest,
        UpdatePatientRequest,
        MergePatientRequest,
    ]


def get_components_schemas() -> dict[str, dict[str, Any]]:
    """
    Build components.schemas from all registered Pydantic request/body models.

    Safe to call from build_cogito_openapi_schema(); uses lazy app imports.
    """
    return build_components_schemas(_get_request_model_registry())


# Map (path, method) -> Pydantic model for requestBody. Paths must match COGITO_PATHS keys.
def _request_body_model_map() -> dict[tuple[str, str], type]:
    """(path, method) -> request body model class. Used to inject $ref into paths."""
    from apps.intake.api_schemas import SubmitIntakeFormRequest, UpdateAnamnesisPayloadRequest
    from apps.medical.api_schemas import (
        CreateMedicalDocumentRequest,
        DoctorTemplateCreateRequest,
        DoctorTemplateUpdateRequest,
        PublishMedicalDocumentRequest,
        SaveDraftMedicalDocumentRequest,
    )
    from apps.outbox.api_schemas import ProcessOutboxRequest, RetentionRunRequest, RetryOutboxEventRequest
    from apps.reception.api_schemas import (
        CreateClinicSiteRequest,
        CreateConsultingRoomRequest,
        CreateDailyQueueRequest,
        CreatePatientRequest,
        CreateQueueEntryRequest,
        CreateQueueEntrySessionRequest,
        CreateTabletDeviceRequest,
        MergePatientRequest,
        UpdateClinicSiteRequest,
        UpdateConsultingRoomRequest,
        UpdateDailyQueueRequest,
        UpdatePatientRequest,
        UpdateQueueEntryRequest,
        UpdateTabletDeviceRequest,
    )
    from apps.users.api_schemas import AuthLoginRequest, CreateStaffUserRequest, UpdateStaffUserRequest

    P = "/api/v1"
    return {
        (f"{P}/auth/login", "post"): AuthLoginRequest,
        (f"{P}/staff-users", "post"): CreateStaffUserRequest,
        (f"{P}/staff-users/{{staff_user_id}}", "patch"): UpdateStaffUserRequest,
        (f"{P}/doctor-text-templates", "post"): DoctorTemplateCreateRequest,
        (f"{P}/doctor-text-templates/{{template_id}}", "patch"): DoctorTemplateUpdateRequest,
        (f"{P}/outbox-events/{{outbox_event_id}}/retry", "post"): RetryOutboxEventRequest,
        (f"{P}/operations/outbox/process", "post"): ProcessOutboxRequest,
        (f"{P}/operations/retention/run", "post"): RetentionRunRequest,
        (f"{P}/medical-documents", "post"): CreateMedicalDocumentRequest,
        (f"{P}/medical-documents/{{medical_document_id}}/draft", "put"): SaveDraftMedicalDocumentRequest,
        (f"{P}/medical-documents/{{medical_document_id}}/publish", "post"): PublishMedicalDocumentRequest,
        (f"{P}/clinic-sites", "post"): CreateClinicSiteRequest,
        (f"{P}/clinic-sites/{{clinic_site_id}}", "patch"): UpdateClinicSiteRequest,
        (f"{P}/consulting-rooms", "post"): CreateConsultingRoomRequest,
        (f"{P}/consulting-rooms/{{consulting_room_id}}", "patch"): UpdateConsultingRoomRequest,
        (f"{P}/patients", "post"): CreatePatientRequest,
        (f"{P}/patients/{{patient_id}}", "patch"): UpdatePatientRequest,
        (f"{P}/patients/{{patient_id}}/merge", "post"): MergePatientRequest,
        (f"{P}/daily-queues", "post"): CreateDailyQueueRequest,
        (f"{P}/daily-queues/{{daily_queue_id}}", "patch"): UpdateDailyQueueRequest,
        (f"{P}/daily-queues/{{daily_queue_id}}/entries", "post"): CreateQueueEntryRequest,
        (f"{P}/queue-entries/{{queue_entry_id}}", "patch"): UpdateQueueEntryRequest,
        (f"{P}/queue-entries/{{queue_entry_id}}/sessions", "post"): CreateQueueEntrySessionRequest,
        (f"{P}/tablet-devices", "post"): CreateTabletDeviceRequest,
        (f"{P}/tablet-devices/{{tablet_device_id}}", "patch"): UpdateTabletDeviceRequest,
        (f"{P}/intake-forms/{{intake_form_id}}/anamnesis", "put"): UpdateAnamnesisPayloadRequest,
        (f"{P}/intake-forms/{{intake_form_id}}/submit", "post"): SubmitIntakeFormRequest,
    }


def get_request_body_schema_for(path: str, method: str) -> dict[str, Any] | None:
    """
    Return OpenAPI schema dict for request body ($ref to component) if this path+method
    has a registered Pydantic model; otherwise None.
    """
    m = _request_body_model_map().get((path, method.lower()))
    return get_request_schema_ref(m) if m else None
