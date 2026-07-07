"""Canonical English fallbacks for API / domain message keys (DB categories: other, doctor, …)."""

from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "translation_data"


def _en_map_from_translation_json(filename: str) -> dict[str, str]:
    path = _DATA_DIR / filename
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v["en"] for k, v in raw.items() if isinstance(v, dict) and "en" in v}


_DOCTOR_PUBLISH_VALIDATION_KEYS = (
    "doctor.msg_validation_examination_scope_required",
    "doctor.msg_validation_final_assessment_required",
    "doctor.msg_validation_fitzpatrick_required",
    "doctor.msg_validation_overall_assessment_required",
    "doctor.msg_validation_recommendations_required",
)


def _doctor_publish_validation_en() -> dict[str, str]:
    doc = json.loads((_DATA_DIR / "doctor_ui.json").read_text(encoding="utf-8"))
    return {k: doc[k]["en"] for k in _DOCTOR_PUBLISH_VALIDATION_KEYS}


API_ERROR_KEY_DEFAULT_EN: dict[str, str] = {
    "other.api.actor_mismatch": "Actor mismatch.",
    "other.api.actor_user_not_found": "Actor user not found.",
    "other.api.authentication_required": "Authentication required.",
    "other.api.captcha_verification_failed": "CAPTCHA verification failed.",
    "other.api.clinic_site_code_already_exists": "Clinic site code already exists.",
    "other.api.clinic_site_not_found": "Clinic site not found.",
    "other.api.clinic_site_not_in_scope": "Clinic site is not in your assigned scope.",
    "other.api.clinic_site_or_consulting_room_not_found": "Clinic site or consulting room not found.",
    "other.api.consulting_room_code_exists": "Consulting room code already exists for this clinic site.",
    "other.api.consulting_room_not_found": "Consulting room not found.",
    "other.api.consulting_room_not_in_scope": "Consulting room is not in your assigned scope.",
    "other.api.daily_queue_not_found": "Daily queue not found.",
    "other.api.daily_queue_not_in_scope": "Daily queue is not in your assigned scope.",
    "other.api.date_of_birth_format": "date_of_birth must be YYYY-MM-DD.",
    "other.api.date_of_birth_required": "date_of_birth is required.",
    "other.api.doctor_entries_own_queues": "Doctor can only access entries from own queues.",
    "other.api.doctor_own_assigned_queues": "Doctor can only access own assigned queues.",
    "other.api.doctor_own_queues": "Doctor can only access own queues.",
    "other.api.document_not_found": "Document not found or unavailable.",
    "other.api.document_retention_expired": "Your results are no longer available online. Please contact the clinic.",
    "other.api.duplicate_queue_slot": "Duplicate queue for this date/site/room/shift.",
    "other.api.duplicate_visit_external_id": "Duplicate visit_external_id in this queue.",
    "other.api.forbidden": "Forbidden.",
    "other.api.import_batch_not_found": "Import batch not found.",
    "other.api.intake_document_not_found": "Intake document not found.",
    "other.api.intake_form_not_found": "Intake form not found.",
    "other.api.intake_outbox_event_not_found": "Intake outbox event not found.",
    "other.api.invalid_credentials": "Invalid credentials.",
    "other.api.invalid_form_locale_format": "Invalid form_locale format.",
    "other.api.invalid_is_active": "Invalid is_active query parameter.",
    "other.api.invalid_limit": "Invalid limit query parameter. Allowed values: 10, 20, 50, 100.",
    "other.api.invalid_page_size": "Invalid page_size query parameter. Allowed values: 10, 20, 50, 100.",
    "other.api.invalid_json_body": "Invalid JSON body.",
    "other.api.invalid_json_payload": "Invalid JSON payload.",
    "other.api.invalid_or_expired_code": "Invalid or expired code.",
    "other.api.invalid_request_encoding": "Request body is not valid UTF-8.",
    "other.api.invalid_request_body": (
        "Request body does not match the expected schema."
    ),
    "other.api.invalid_role_query": "Invalid role query parameter.",
    "other.api.invalid_save_draft_intent": (
        "Invalid intent for PUT …/draft. Allowed values: edit, amend."
    ),
    "other.api.medical_document_not_found": "Medical document not found.",
    "other.api.external_pdf_rejected": "This external PDF was already rejected.",
    "other.api.external_pdf_reject_failed": "Could not reject the file on HiDrive.",
    "other.api.medical_document_version_not_found": "Medical document version not found.",
    "other.api.amend_intent_required": (
        "This document is already published. To make changes, confirm starting a "
        "revision (intent=amend)."
    ),
    "other.api.no_pending_revision_to_discard": (
        "No pending revision to discard for this document."
    ),
    "other.api.preview_source_invalid": (
        "Invalid preview source. Allowed values: published, draft."
    ),
    "other.api.medical_payload_schema_mismatch": (
        "medical_payload.schema_version must match medical_payload_schema_version."
    ),
    "other.api.method_not_allowed": "Method not allowed.",
    "other.api.method_not_allowed_for_role": "Method not allowed for this role.",
    "other.api.no_draft_before_publish": (
        "No draft version available. Save a draft (PUT .../draft) with validated payload before publishing."
    ),
    "other.api.no_version_to_preview": "No version to preview. Save a draft first.",
    "other.api.external_upload_attachment_missing": (
        "The referenced external PDF attachment no longer exists for this document version."
    ),
    "other.api.only_admin_create_clinic_site": "Only Admin can create clinic sites.",
    "other.api.only_admin_create_consulting_room": "Only Admin can create consulting rooms.",
    "other.api.only_admin_update_clinic_site": "Only Admin can update or deactivate clinic sites.",
    "other.api.only_admin_update_consulting_room": "Only Admin can update or deactivate consulting rooms.",
    "other.api.only_reception_admin_update_queue": "Only Reception or Admin can update daily queue.",
    "other.api.otp_code_required": "The OTP code is required.",
    "other.api.outbox_event_not_found": "Outbox event not found.",
    "other.api.patient_not_found": "Patient not found.",
    "other.api.patient_uniqueness_conflict": "Patient uniqueness conflict.",
    "other.api.pdf_file_not_found": "PDF file not found.",
    "other.api.pdf_not_generated": "PDF not yet generated or unavailable.",
    "other.api.phone_required": "phone is required.",
    "other.api.publish_request_id_locale_conflict": "publish_request_id already used with different publish_locale.",
    "other.api.publish_request_id_required": "publish_request_id is required for publish.",
    "other.api.provide_entry_status_or_notes": "Provide entry_status and/or notes.",
    "other.api.provide_field_to_update": "Provide at least one field to update.",
    "other.api.queue_entry_not_found": "Queue entry not found.",
    "other.api.queue_entry_not_in_scope": "Queue entry is not in your assigned scope.",
    "other.api.queue_entry_or_intake_not_found": "Queue entry or intake form not found.",
    "other.api.queue_entry_or_tablet_not_found": "Queue entry or tablet device not found.",
    "other.api.queue_or_patient_not_found": "Queue or patient not found.",
    "other.api.request_body_too_large": "Request body exceeds maximum size ({max_bytes} bytes).",
    "other.api.retry_count_gte_integer": "retry_count_gte must be an integer.",
    "other.api.session_otp_required": "Session required. Please verify OTP first.",
    "other.api.staff_user_not_found": "Staff user not found.",
    "other.api.tablet_android_id_exists": "Tablet device with this android_id already exists.",
    "other.api.tablet_device_not_found": "Tablet device not found.",
    "other.api.tablet_entries_today_only": "Tablet role can only access entries of today's queues.",
    "other.api.tablet_queues_today_only": "Tablet role can only access queues for today.",
    "other.api.template_not_found": "Template not found.",
    "other.api.too_many_requests": "Too many requests. Try again later.",
    "other.api.unauthorized": "Unauthorized.",
    "other.api.username_or_email_exists": "Username or email already exists.",
}

OTHER_DOMAIN_KEY_DEFAULT_EN: dict[str, str] = _en_map_from_translation_json(
    "other_domain.json"
)

OTHER_I18N_KEY_DEFAULT_EN: dict[str, str] = {
    **API_ERROR_KEY_DEFAULT_EN,
    **OTHER_DOMAIN_KEY_DEFAULT_EN,
    **_doctor_publish_validation_en(),
}
