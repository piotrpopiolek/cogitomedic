from __future__ import annotations

import logging
from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from pydantic import ValidationError

from apps.core.api_utils import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    json_domain_error,
    json_error,
    json_pydantic_validation_error,
    read_json_body,
    require_auth,
    require_user_role,
    safe_parse_positive_int,
)
from apps.core.http_utils import get_client_ip
from apps.core.exceptions import (
    DomainError,
    IdempotencyConflictError,
    InvalidRequestBodyEncoding,
)
from apps.medical.api_schemas import (
    CreateMedicalDocumentRequest,
    CreateMedicalDocumentWithoutIntakeRequest,
    PaperIntakeAuthorizationRequest,
    DoctorTemplateCreateRequest,
    DoctorTemplateListQuery,
    DoctorTemplateUpdateRequest,
    PublishMedicalDocumentRequest,
    RetryProcessingRequest,
    SaveDraftMedicalDocumentRequest,
)
from apps.medical.external_pdf_service import (
    ExternalPdfCorruptError,
    download_external_pdf,
    reject_external_pdf,
)
from apps.medical.pdf_builder import (
    build_merged_preview_pdf_bytes,
)
from apps.medical.medical_payload_schemas import validate_medical_payload_v1
from apps.core.translation_service import resolve_other_message
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
)
from apps.reception.models import QueueEntry
from apps.medical.services import (
    _is_admin_or_manager_medical_oversight,
    assigned_doctor_audit_metadata,
    authorize_paper_intake,
    check_doctor_document_access,
    check_doctor_queue_entry_access,
    create_external_upload_medical_document,
    create_medical_document_without_intake,
    create_or_get_medical_document,
    discard_pending_revision,
    get_document_lock_state,
    get_medical_document_context,
    latest_retryable_outbox_event,
    latest_version_processing_error_message,
    list_medical_documents,
    outbox_event_stage_status,
    parse_medical_documents_list_params,
    publish_document_version,
    refresh_document_lock,
    release_document_lock,
    revoke_document_version,
    revoke_paper_intake_authorization,
    retry_latest_document_processing,
    save_draft_document_version,
    select_external_upload_attachment_for_draft,
    upload_external_pdf_to_incoming,
)
from apps.medical.template_services import (
    TemplateListFilters,
    TemplateNotFoundError,
    TemplatePermissionError,
    create_template,
    get_template,
    list_templates,
    update_template,
)
from apps.operations.api_views import _serialize_audit_event
from apps.operations.models import AuditEvent
from apps.operations.services import create_audit_event

logger = logging.getLogger(__name__)


class _MedicalDocumentEditLocked(Exception):
    """Raised inside ``transaction.atomic`` to roll back and return HTTP 423."""

    __slots__ = ("locked_by_username",)

    def __init__(self, locked_by_username: str | None) -> None:
        super().__init__()
        self.locked_by_username = locked_by_username


def _json_document_locked(
    request: HttpRequest, locked_by_username: str | None
) -> JsonResponse:
    holder = locked_by_username or "—"
    default = "This document is being edited by {username}. Please try again later."
    msg = resolve_other_message(
        request,
        "doctor.document_locked_error",
        default,
        username=holder,
    )
    return JsonResponse(
        {"error": msg, "locked_by_username": locked_by_username},
        status=423,
    )


def _serialize_medical_document_list_item(doc) -> dict:
    """Serialize one medical document for list response; doc has prefetched versions (ordered -version_no)."""
    versions = list(doc.versions.all())
    latest = versions[0] if versions else None
    events_by_type = (
        {e.event_type: e for e in latest.outbox_events.all()} if latest else {}
    )
    patient = doc.queue_entry.patient
    queue = doc.queue_entry.daily_queue
    lock_eff, lock_name, lock_at = get_document_lock_state(doc)
    return {
        "id": str(doc.id),
        "queue_entry_id": str(doc.queue_entry_id),
        "status": doc.status,
        "current_version_no": doc.current_version_no,
        "last_published_at": (
            doc.last_published_at.isoformat() if doc.last_published_at else None
        ),
        "queue_date": queue.queue_date.isoformat(),
        "patient": {
            "id": str(patient.id),
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "date_of_birth": patient.date_of_birth.isoformat(),
        },
        "locked_by_username": lock_name if lock_eff else None,
        "locked_at": lock_at.isoformat() if lock_eff and lock_at else None,
        "pdf_generation_status": latest.pdf_generation_status if latest else None,
        "hidrive_sent": latest.hidrive_sent if latest else False,
        "sms_sent": latest.sms_sent if latest else False,
        "hidrive_status": (
            outbox_event_stage_status(
                events_by_type.get("HIDRIVE_UPLOAD"),
                completed=bool(latest and latest.hidrive_sent),
            )
            if latest
            else None
        ),
        "sms_status": (
            outbox_event_stage_status(
                events_by_type.get("SMS_SEND"),
                completed=bool(latest and latest.sms_sent),
            )
            if latest
            else None
        ),
        "processing_error_message": (
            latest_version_processing_error_message(latest) if latest else None
        ),
        "can_retry_processing": (
            latest_retryable_outbox_event(latest) is not None if latest else False
        ),
    }


@require_auth
def medical_documents_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method == "GET":
        list_params = parse_medical_documents_list_params(request.GET)
        items, total = list_medical_documents(
            **list_params,
            user=request.user,
        )
        create_audit_event(
            event_type="MEDICAL_DOCUMENTS_LISTED",
            actor_user_id=request.user.id,
            metadata={
                "client_ip": get_client_ip(request),
                "page": list_params["page"],
                "page_size": list_params["page_size"],
                "total": total,
                "item_count": len(items),
            },
        )
        return JsonResponse(
            {
                "items": [_serialize_medical_document_list_item(d) for d in items],
                "pagination": {
                    "page": list_params["page"],
                    "page_size": list_params["page_size"],
                    "total": total,
                },
            },
            status=200,
        )
    if request.method == "POST":
        try:
            body = CreateMedicalDocumentRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("other.api.invalid_json_payload", status=400)
        except InvalidRequestBodyEncoding as exc:
            return json_domain_error(exc)
        except ValidationError as exc:
            return json_pydantic_validation_error(exc)

        try:
            entry = QueueEntry.objects.select_related("daily_queue").get(
                id=body.queue_entry_id
            )
            check_doctor_queue_entry_access(entry, request.user)
            document = create_or_get_medical_document(
                queue_entry_id=body.queue_entry_id,
                intake_form_id=body.intake_form_id,
                created_by_user_id=request.user.id,
            )
        except ObjectDoesNotExist:
            return json_error("other.api.queue_entry_or_intake_not_found", status=404)
        except DomainError as exc:
            return json_domain_error(exc, status=400)
        return JsonResponse(
            {
                "medical_document_id": str(document.id),
                "queue_entry_id": str(document.queue_entry_id),
                "status": document.status,
            },
            status=201,
        )
    return json_error("other.api.method_not_allowed", status=405)


@require_auth
def medical_documents_no_intake_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        body = CreateMedicalDocumentWithoutIntakeRequest.model_validate(
            read_json_body(request)
        )
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return json_pydantic_validation_error(exc)

    try:
        entry = QueueEntry.objects.select_related("daily_queue").get(
            id=body.queue_entry_id
        )
        check_doctor_queue_entry_access(entry, request.user)
        document = create_medical_document_without_intake(
            queue_entry_id=body.queue_entry_id,
            created_by_user_id=request.user.id,
        )
    except ObjectDoesNotExist:
        return json_error("other.api.queue_entry_not_found", status=404)
    except DomainError as exc:
        return json_domain_error(exc, status=400)

    return JsonResponse(
        {
            "medical_document_id": str(document.id),
            "queue_entry_id": str(document.queue_entry_id),
            "status": document.status,
            "source_type": document.source_type,
        },
        status=201,
    )


def _external_upload_error_status(exc: DomainError) -> int:
    key = exc.api_message_key or ""
    if key == "other.domain.external_upload_file_too_large":
        return 413
    if key == "other.domain.external_upload_invalid_content_type":
        return 415
    if key in {
        "other.api.queue_entry_not_found",
        "other.api.queue_entry_or_intake_not_found",
        "other.api.medical_document_not_found",
        "other.api.staff_user_not_found",
    }:
        return 404
    if key == "other.api.server_error":
        return 502
    if key in {
        "other.domain.external_upload_staff_role_required",
        "other.domain.external_upload_select_attachment_invalid_role",
        "other.domain.external_upload_create_document_invalid_role",
    }:
        return 403
    if key in {
        "other.domain.external_upload_not_pdf",
        "other.domain.external_upload_invalid_or_empty_pdf",
        "other.domain.external_upload_intake_not_ready",
        "other.domain.external_upload_not_external_source",
        "other.domain.external_upload_attachment_not_found",
        "other.domain.external_upload_attachment_invalid_status",
        "other.domain.external_upload_attachment_path_invalid",
        "other.domain.external_upload_no_active_draft",
        "other.domain.medical_document_source_type_mismatch",
    }:
        return 422
    return 400


@require_auth
def medical_external_upload_upload_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"RECEPTION", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)

    raw_queue_entry_id = (request.POST.get("queue_entry_id") or "").strip()
    uploaded_file = request.FILES.get("file")
    if not raw_queue_entry_id or uploaded_file is None:
        return json_error("other.api.invalid_request_body", status=400)
    try:
        queue_entry_id = UUID(raw_queue_entry_id)
    except ValueError:
        return json_error("other.api.invalid_request_body", status=400)

    try:
        document = create_external_upload_medical_document(
            queue_entry_id=queue_entry_id,
            created_by_user_id=request.user.id,
        )
        attachment = upload_external_pdf_to_incoming(
            medical_document_id=document.id,
            uploaded_file=uploaded_file,
            actor_user_id=request.user.id,
        )
        draft_version = select_external_upload_attachment_for_draft(
            medical_document_id=document.id,
            attachment_id=attachment.id,
            actor_user_id=request.user.id,
        )
    except DomainError as exc:
        return json_domain_error(exc, status=_external_upload_error_status(exc))

    return JsonResponse(
        {
            "document_id": str(document.id),
            "draft_version_id": str(draft_version.id),
            "attachment_id": str(attachment.id),
            "hidrive_remote_path": attachment.hidrive_remote_path,
            "size_bytes": int(uploaded_file.size or 0),
            "original_filename": attachment.original_filename,
        },
        status=201,
    )


@require_auth
def queue_entry_paper_intake_authorization_view(
    request: HttpRequest, queue_entry_id: UUID
) -> JsonResponse:
    """ADMIN/MANAGER: POST to authorize, DELETE to revoke (body ``reason`` in both cases).

    No clinic-site scope gate (same oversight model as ``/admin/paper-intake/`` HTML hub
    and entry page): only role checks; business rules live in ``authorize_paper_intake`` /
    ``revoke_paper_intake_authorization``. Other queue-entry HTTP handlers may still return
    ``other.api.queue_entry_not_in_scope`` for scoped staff; this view intentionally does not.
    """
    role_error = require_user_role(request, allowed_roles={"ADMIN", "MANAGER"})
    if role_error:
        return role_error
    if request.method not in ("POST", "DELETE"):
        return json_error("other.api.method_not_allowed", status=405)
    if not QueueEntry.objects.filter(id=queue_entry_id).exists():
        return json_error("other.api.queue_entry_not_found", status=404)

    try:
        body = PaperIntakeAuthorizationRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return json_pydantic_validation_error(exc)

    if request.method == "POST":
        try:
            authorization = authorize_paper_intake(
                queue_entry_id=queue_entry_id,
                authorized_by_user_id=request.user.id,
                reason=body.reason,
            )
        except DomainError as exc:
            return json_domain_error(exc, status=400)
        return JsonResponse(
            {
                "paper_intake_authorization_id": str(authorization.id),
                "queue_entry_id": str(authorization.queue_entry_id),
                "authorized_at": authorization.authorized_at.isoformat(),
            },
            status=201,
        )

    try:
        revoke_paper_intake_authorization(
            queue_entry_id=queue_entry_id,
            revoked_by_user_id=request.user.id,
            reason=body.reason,
        )
    except DomainError as exc:
        return json_domain_error(exc, status=400)
    return JsonResponse(
        {"queue_entry_id": str(queue_entry_id), "revoked": True},
        status=200,
    )


@require_auth
def medical_document_detail_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    """GET full document context: intake summary + current version (for doctor panel)."""
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    form_locale = (request.GET.get("form_locale") or "de-DE")[:10]
    try:
        context = get_medical_document_context(
            medical_document_id=medical_document_id,
            form_locale=form_locale,
            user=request.user,
        )
    except DomainError as exc:
        return json_domain_error(exc, status=422)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)
    doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
        id=medical_document_id
    )
    create_audit_event(
        event_type="MEDICAL_DOCUMENT_VIEWED",
        actor_user_id=request.user.id,
        patient_id=doc.queue_entry.patient_id,
        medical_document_id=doc.id,
        context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            **assigned_doctor_audit_metadata(doc),
        },
    )
    return JsonResponse(context, status=200)


@require_auth
def medical_document_preview_pdf_view(
    request: HttpRequest, medical_document_id: UUID
) -> HttpResponse:
    """GET: return PDF preview for a document.

    - ``?source=published``: render the currently published version. Returns
      404 if the document has no published version.
    - ``?source=draft``: render the pending DRAFT version (latest by
      ``version_no``). Returns 404 if there is no DRAFT.
    - Default (no ``source``):
      - PUBLISHED + no pending revision → published version
      - PUBLISHED + pending revision → draft version
      - DRAFT → latest version (legacy behaviour)

    Statuses are never mutated here – previewing must be a pure read.
    """
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)

    source = (request.GET.get("source") or "").strip().lower()
    if source and source not in ("published", "draft"):
        return json_error("other.api.preview_source_invalid", status=400)

    base_qs = MedicalDocumentVersion.objects.filter(
        medical_document_id=medical_document_id
    ).select_related(
        "medical_document",
        "medical_document__queue_entry",
        "medical_document__queue_entry__patient",
        "medical_document__created_by_user",
        "medical_document__updated_by_user",
        "published_by_user",
    )

    if not source:
        if doc.status == MedicalDocStatus.PUBLISHED and not doc.has_pending_revision:
            source = "published"
        elif doc.status == MedicalDocStatus.PUBLISHED and doc.has_pending_revision:
            source = "draft"
        else:
            source = "draft"  # legacy DRAFT-only flow → latest is DRAFT

    if source == "published":
        version = (
            base_qs.filter(
                version_status=DocVersionStatus.PUBLISHED,
            )
            .order_by("-version_no")
            .first()
        )
    else:
        version = (
            base_qs.filter(
                version_status=DocVersionStatus.DRAFT,
            )
            .order_by("-version_no")
            .first()
        )
        # Fallback for legacy data: no DRAFT row but document is DRAFT –
        # take whatever latest version exists so the doctor can still preview.
        if version is None and doc.status == MedicalDocStatus.DRAFT:
            version = base_qs.order_by("-version_no").first()

    if not version:
        return json_error("other.api.no_version_to_preview", status=404)

    form_locale = (
        request.GET.get("form_locale") or request.GET.get("authoring_locale") or ""
    ).strip()[:10]
    authoring_locale_override = form_locale if form_locale else None
    pdf_bytes, preview_warn = build_merged_preview_pdf_bytes(
        version, authoring_locale_override=authoring_locale_override
    )
    create_audit_event(
        event_type="MEDICAL_DOCUMENT_PDF_PREVIEWED",
        actor_user_id=request.user.id,
        patient_id=doc.queue_entry.patient_id,
        medical_document_id=doc.id,
        context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            "version_no": version.version_no,
            "source": source,
            "document_status": doc.status,
            "has_pending_revision": doc.has_pending_revision,
            **assigned_doctor_audit_metadata(doc),
        },
    )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="befund-preview.pdf"'
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Befund-Preview-Source"] = source
    response["X-Befund-Preview-Version-No"] = str(version.version_no)
    if preview_warn:
        response["X-Befund-Preview-Warning"] = preview_warn
    return response


@require_auth
def medical_document_versions_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    """GET: list versions of a medical document."""
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)

    versions = (
        MedicalDocumentVersion.objects.filter(medical_document_id=medical_document_id)
        .order_by("-version_no")
        .values(
            "id",
            "version_no",
            "version_status",
            "pdf_generation_status",
            "published_at",
            "revoked_at",
            "hidrive_sent",
            "sms_sent",
        )
    )
    items = [
        {
            "id": str(v["id"]),
            "version_no": v["version_no"],
            "version_status": v["version_status"],
            "pdf_generation_status": v["pdf_generation_status"],
            "published_at": (
                v["published_at"].isoformat() if v["published_at"] else None
            ),
            "revoked_at": v["revoked_at"].isoformat() if v["revoked_at"] else None,
            "hidrive_sent": v["hidrive_sent"],
            "sms_sent": v["sms_sent"],
        }
        for v in versions
    ]
    create_audit_event(
        event_type="MEDICAL_DOCUMENT_VERSIONS_LISTED",
        actor_user_id=request.user.id,
        patient_id=doc.queue_entry.patient_id,
        medical_document_id=doc.id,
        context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            "version_count": len(items),
            **assigned_doctor_audit_metadata(doc),
        },
    )
    return JsonResponse({"items": items}, status=200)


@require_auth
def medical_document_draft_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "PUT":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        body = SaveDraftMedicalDocumentRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return json_pydantic_validation_error(exc)

    if body.medical_payload.schema_version != body.medical_payload_schema_version:
        return json_error("other.api.medical_payload_schema_mismatch", status=400)

    payload_dict = body.medical_payload.model_dump()
    if body.medical_payload_schema_version == 1:
        try:
            payload_dict = validate_medical_payload_v1(payload_dict)
        except ValidationError as exc:
            details = [
                {"type": e.get("type"), "loc": e.get("loc"), "msg": e.get("msg")}
                for e in exc.errors()
            ]
            return JsonResponse(
                {"error": "Invalid medical_payload (v1).", "details": details},
                status=400,
            )

    try:
        with transaction.atomic():
            # Do not select_related("locked_by_user") here: PostgreSQL rejects
            # FOR UPDATE on the nullable side of an outer join.
            doc = (
                MedicalDocument.objects.select_for_update()
                .select_related(
                    "queue_entry__daily_queue",
                )
                .get(id=medical_document_id)
            )
            check_doctor_document_access(doc, request.user)
            if doc.status == MedicalDocStatus.DRAFT:
                eff, holder_name, _ = get_document_lock_state(doc)
                if (
                    eff
                    and doc.locked_by_user_id != request.user.id
                    and not _is_admin_or_manager_medical_oversight(request.user)
                ):
                    raise _MedicalDocumentEditLocked(holder_name)

            version = save_draft_document_version(
                medical_document_id=medical_document_id,
                updated_by_user_id=request.user.id,
                medical_payload_schema_version=body.medical_payload_schema_version,
                medical_payload=payload_dict,
                diagnosis_code=body.diagnosis_code,
                procedure_code=body.procedure_code,
                intent=body.intent,
            )
            doc.refresh_from_db()

            if doc.status == MedicalDocStatus.DRAFT:
                if not refresh_document_lock(
                    medical_document_id=medical_document_id, user=request.user
                ):
                    doc_after = MedicalDocument.objects.select_related(
                        "locked_by_user"
                    ).get(id=medical_document_id)
                    _, holder2, _ = get_document_lock_state(doc_after)
                    raise _MedicalDocumentEditLocked(holder2)
    except _MedicalDocumentEditLocked as exc:
        return _json_document_locked(request, exc.locked_by_username)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)
    except DomainError as exc:
        # 409 specifically for the amend-intent guardrail so the UI can show a
        # confirmation modal instead of a generic validation toast.
        if exc.api_message_key == "other.api.amend_intent_required":
            return json_domain_error(exc, status=409)
        return json_domain_error(exc, status=400)

    return JsonResponse(
        {
            "medical_document_version_id": str(version.id),
            "version_no": version.version_no,
            "version_status": version.version_status,
            "document_status": doc.status,
            "has_pending_revision": doc.has_pending_revision,
            "published_version_no": doc.published_version_no,
        },
        status=200,
    )


@require_auth
def medical_document_discard_revision_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    """POST: discard a pending DRAFT revision on a PUBLISHED document.

    Returns 200 with cleared state, 404 if the document is unknown, 409 if
    there is no pending revision to discard.
    """
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)

    try:
        doc = discard_pending_revision(
            medical_document_id=medical_document_id,
            actor_user_id=request.user.id,
        )
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)
    except DomainError as exc:
        if exc.api_message_key == "other.api.no_pending_revision_to_discard":
            return json_domain_error(exc, status=409)
        return json_domain_error(exc, status=400)

    return JsonResponse(
        {
            "discarded": True,
            "document_id": str(doc.id),
            "status": doc.status,
            "current_version_no": doc.current_version_no,
            "published_version_no": doc.published_version_no,
            "has_pending_revision": doc.has_pending_revision,
        },
        status=200,
    )


@require_auth
def medical_document_unlock_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    """POST: release edit lock (session holder or admin). Used on page unload from doctor panel."""
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)
    try:
        released = release_document_lock(
            medical_document_id=medical_document_id, user=request.user
        )
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)
    if not released:
        return JsonResponse(
            {
                "released": False,
                "error": resolve_other_message(
                    request,
                    "doctor.document_unlock_forbidden",
                    "You cannot release this document lock.",
                ),
            },
            status=403,
        )
    return JsonResponse({"released": True}, status=200)


@require_auth
def medical_document_publish_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        body = PublishMedicalDocumentRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return json_pydantic_validation_error(exc)

    try:
        with transaction.atomic():
            doc = (
                MedicalDocument.objects.select_for_update()
                .select_related("queue_entry__daily_queue")
                .get(id=medical_document_id)
            )
            check_doctor_document_access(doc, request.user)

            if doc.status == MedicalDocStatus.DRAFT:
                eff, holder_name, _ = get_document_lock_state(doc)
                if (
                    eff
                    and doc.locked_by_user_id != request.user.id
                    and not _is_admin_or_manager_medical_oversight(request.user)
                ):
                    raise _MedicalDocumentEditLocked(holder_name)

            version = publish_document_version(
                medical_document_id=medical_document_id,
                publish_request_id=body.publish_request_id,
                published_by_user_id=request.user.id,
                publish_locale=body.publish_locale,
                resend_sms=body.resend_sms,
            )
    except _MedicalDocumentEditLocked as exc:
        return _json_document_locked(request, exc.locked_by_username)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)
    except IdempotencyConflictError as exc:
        return json_domain_error(exc, status=409)
    except DomainError as exc:
        return json_domain_error(exc, status=400)

    return JsonResponse(
        {
            "medical_document_version_id": str(version.id),
            "version_no": version.version_no,
            "version_status": version.version_status,
            "publish_request_id": (
                str(version.publish_request_id) if version.publish_request_id else None
            ),
            "publish_locale": version.publish_locale,
        },
        status=200,
    )


@require_auth
def medical_document_version_detail_view(
    request: HttpRequest, version_id: UUID
) -> JsonResponse:
    """GET: single medical document version by id (MedicalDocumentVersion.id)."""
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        version = MedicalDocumentVersion.objects.select_related(
            "medical_document", "medical_document__queue_entry__daily_queue"
        ).get(id=version_id)
        check_doctor_document_access(version.medical_document, request.user)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_version_not_found", status=404)
    mdoc = version.medical_document
    create_audit_event(
        event_type="MEDICAL_DOCUMENT_VERSION_VIEWED",
        actor_user_id=request.user.id,
        patient_id=mdoc.queue_entry.patient_id,
        medical_document_id=mdoc.id,
        context_clinic_site_id=mdoc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            "medical_document_version_id": str(version.id),
            "version_no": version.version_no,
            **assigned_doctor_audit_metadata(mdoc),
        },
    )
    return JsonResponse(
        {
            "id": str(version.id),
            "medical_document_id": str(version.medical_document_id),
            "version_no": version.version_no,
            "version_status": version.version_status,
            "medical_payload_schema_version": version.medical_payload_schema_version,
            "medical_payload": version.medical_payload,
            "diagnosis_code": version.diagnosis_code,
            "procedure_code": version.procedure_code,
            "pdf_generation_status": version.pdf_generation_status,
            "hidrive_sent": version.hidrive_sent,
            "hidrive_sent_at": (
                version.hidrive_sent_at.isoformat() if version.hidrive_sent_at else None
            ),
            "sms_sent": version.sms_sent,
            "sms_sent_at": (
                version.sms_sent_at.isoformat() if version.sms_sent_at else None
            ),
            "published_at": (
                version.published_at.isoformat() if version.published_at else None
            ),
            "revoked_at": (
                version.revoked_at.isoformat() if version.revoked_at else None
            ),
            "publish_request_id": (
                str(version.publish_request_id) if version.publish_request_id else None
            ),
            "publish_locale": version.publish_locale,
            "created_at": version.created_at.isoformat(),
        },
        status=200,
    )


@require_auth
def medical_document_retry_processing_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"ADMIN", "MANAGER", "RECEPTION"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        body = RetryProcessingRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return json_pydantic_validation_error(exc)

    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
        retried = retry_latest_document_processing(
            medical_document_id=medical_document_id,
            actor=request.user,
            reason=body.reason,
        )
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)
    except DomainError as exc:
        return json_domain_error(exc, status=409)

    return JsonResponse(
        {
            "retried": True,
            "outbox_event_id": str(retried.id),
            "event_type": retried.event_type,
            "status": retried.status,
        },
        status=200,
    )


@require_auth
def medical_document_revoke_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    """POST: Revoke the current published version. Patient loses access in ergebnisse portal."""
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
        version = revoke_document_version(
            medical_document_id=medical_document_id,
            revoked_by_user_id=request.user.id,
        )
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)
    except DomainError as exc:
        return json_domain_error(exc, status=400)
    return JsonResponse(
        {
            "medical_document_version_id": str(version.id),
            "version_no": version.version_no,
            "revoked_at": (
                version.revoked_at.isoformat() if version.revoked_at else None
            ),
        },
        status=200,
    )


@require_auth
def doctor_text_templates_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method == "GET":
        try:
            query = DoctorTemplateListQuery.model_validate(
                {
                    "template_locale": request.GET.get("template_locale"),
                    "include_inactive": request.GET.get(
                        "include_inactive", "false"
                    ).lower()
                    == "true",
                }
            )
        except ValidationError as exc:
            return json_pydantic_validation_error(exc)

        try:
            templates = list_templates(
                filters=TemplateListFilters(
                    actor_user_id=request.user.id,
                    template_locale=query.template_locale,
                    include_inactive=query.include_inactive,
                )
            )
        except ObjectDoesNotExist:
            return json_error("other.api.actor_user_not_found", status=404)
        except DomainError as exc:
            return json_domain_error(exc, status=400)

        return JsonResponse(
            {
                "results": [
                    {
                        "id": str(template.id),
                        "name": template.name,
                        "template_locale": template.template_locale,
                        "template_body": template.template_body,
                        "lesion_group_favorites": template.lesion_group_favorites or [],
                        "is_global": template.is_global,
                        "clinic_site_id": (
                            str(template.clinic_site_id)
                            if template.clinic_site_id
                            else None
                        ),
                        "is_active": template.is_active,
                        "owner_user_id": (
                            str(template.owner_user_id)
                            if template.owner_user_id
                            else None
                        ),
                    }
                    for template in templates
                ]
            },
            status=200,
        )

    if request.method == "POST":
        try:
            body = DoctorTemplateCreateRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("other.api.invalid_json_payload", status=400)
        except InvalidRequestBodyEncoding as exc:
            return json_domain_error(exc)
        except ValidationError as exc:
            return json_pydantic_validation_error(exc)

        try:
            template = create_template(
                actor_user_id=request.user.id,
                name=body.name,
                template_locale=body.template_locale,
                template_body=body.template_body,
                lesion_group_favorites=[
                    p.model_dump(mode="json") for p in body.lesion_group_favorites
                ],
                is_global=body.is_global,
                clinic_site_id=body.clinic_site_id,
                is_active=body.is_active,
            )
        except ObjectDoesNotExist:
            return json_error("other.api.actor_user_not_found", status=404)
        except TemplatePermissionError as exc:
            return json_domain_error(exc, status=400)
        except DomainError as exc:
            return json_domain_error(exc, status=400)

        return JsonResponse(
            {
                "id": str(template.id),
                "name": template.name,
                "template_locale": template.template_locale,
                "template_body": template.template_body,
                "lesion_group_favorites": template.lesion_group_favorites or [],
                "is_global": template.is_global,
                "clinic_site_id": (
                    str(template.clinic_site_id) if template.clinic_site_id else None
                ),
                "is_active": template.is_active,
            },
            status=201,
        )

    return json_error("other.api.method_not_allowed", status=405)


@require_auth
def doctor_text_template_detail_view(
    request: HttpRequest, template_id: UUID
) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method == "GET":
        try:
            template = get_template(
                template_id=template_id, actor_user_id=request.user.id
            )
        except TemplateNotFoundError:
            return json_error("other.api.template_not_found", status=404)
        return JsonResponse(
            {
                "id": str(template.id),
                "name": template.name,
                "template_locale": template.template_locale,
                "template_body": template.template_body,
                "lesion_group_favorites": template.lesion_group_favorites or [],
                "is_global": template.is_global,
                "clinic_site_id": (
                    str(template.clinic_site_id) if template.clinic_site_id else None
                ),
                "is_active": template.is_active,
                "owner_user_id": (
                    str(template.owner_user_id) if template.owner_user_id else None
                ),
            },
            status=200,
        )
    if request.method != "PATCH":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        body = DoctorTemplateUpdateRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return json_pydantic_validation_error(exc)

    try:
        template = update_template(
            template_id=template_id,
            actor_user_id=request.user.id,
            name=body.name,
            template_locale=body.template_locale,
            template_body=body.template_body,
            lesion_group_favorites=(
                [p.model_dump(mode="json") for p in body.lesion_group_favorites]
                if body.lesion_group_favorites is not None
                else None
            ),
            is_active=body.is_active,
        )
    except ObjectDoesNotExist:
        return json_error("other.api.actor_user_not_found", status=404)
    except TemplateNotFoundError as exc:
        return json_domain_error(exc, status=404)
    except TemplatePermissionError as exc:
        return json_domain_error(exc, status=400)
    except DomainError as exc:
        return json_domain_error(exc, status=400)

    return JsonResponse(
        {
            "id": str(template.id),
            "name": template.name,
            "template_locale": template.template_locale,
            "template_body": template.template_body,
            "lesion_group_favorites": template.lesion_group_favorites or [],
            "is_global": template.is_global,
            "is_active": template.is_active,
        },
        status=200,
    )


@require_auth
def medical_document_audit_trail_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)

    page = safe_parse_positive_int(request.GET.get("page"), default=1, maximum=10_000)
    page_size = safe_parse_positive_int(
        request.GET.get("page_size"),
        default=DEFAULT_LIST_LIMIT,
        maximum=MAX_LIST_LIMIT,
    )
    qs = AuditEvent.objects.filter(medical_document_id=medical_document_id).order_by(
        "-event_time"
    )
    total = qs.count()
    start = (page - 1) * page_size
    events = list(qs[start : start + page_size])
    items = [_serialize_audit_event(event) for event in events]
    return JsonResponse(
        {
            "items": items,
            "pagination": {"page": page, "page_size": page_size, "total": total},
        },
        status=200,
    )


@require_auth
def medical_document_external_pdfs_view(
    request: HttpRequest, medical_document_id: UUID
) -> JsonResponse:
    """GET: list external HiDrive PDF attachments for this document."""
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)

    items = [
        {
            "id": str(a.id),
            "filename": a.original_filename,
            "status": a.status,
            "hidrive_remote_path": a.hidrive_remote_path,
        }
        for a in ExternalPdfAttachment.objects.filter(
            medical_document_id=medical_document_id
        ).order_by("original_filename", "created_at")
    ]
    return JsonResponse({"items": items}, status=200)


@require_auth
@xframe_options_sameorigin
def medical_document_external_pdf_content_view(
    request: HttpRequest, medical_document_id: UUID, attachment_id: UUID
) -> HttpResponse:
    """GET: stream external PDF from HiDrive (on-demand, no disk cache).

    Same-origin framing is allowed so the doctor panel can show this URL in an
    ``iframe`` (blob: URLs break multi-page PDF in some browsers).
    """
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
        att = ExternalPdfAttachment.objects.get(
            id=attachment_id, medical_document_id=medical_document_id
        )
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)

    if att.status == ExternalPdfStatus.REJECTED:
        return json_error("other.api.external_pdf_rejected", status=410)
    try:
        data = download_external_pdf(att)
    except ExternalPdfCorruptError:
        return JsonResponse(
            {
                "error": resolve_other_message(
                    request,
                    "doctor.external_pdf_upload_in_progress",
                    "",
                )
            },
            status=422,
        )
    except Exception:
        logger.exception(
            "download_external_pdf failed: attachment=%s path=%s",
            att.id,
            att.hidrive_remote_path,
        )
        return JsonResponse(
            {
                "error": resolve_other_message(
                    request,
                    "doctor.external_pdf_gate_hidrive_error",
                    "",
                )
            },
            status=502,
        )
    safe_name = (att.original_filename or "external.pdf").replace('"', "")
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{safe_name}"'
    response["Cache-Control"] = "no-store, max-age=0"
    return response


@require_auth
def medical_document_external_pdf_reject_view(
    request: HttpRequest, medical_document_id: UUID, attachment_id: UUID
) -> JsonResponse:
    """POST: reject external PDF (rename on HiDrive + REJECTED)."""
    role_error = require_user_role(
        request, allowed_roles={"DOCTOR", "ADMIN", "MANAGER"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document_id
        )
        check_doctor_document_access(doc, request.user)
        att = ExternalPdfAttachment.objects.get(
            id=attachment_id, medical_document_id=medical_document_id
        )
    except ObjectDoesNotExist:
        return json_error("other.api.medical_document_not_found", status=404)

    if att.status == ExternalPdfStatus.REJECTED:
        return JsonResponse({"ok": True, "status": att.status}, status=200)
    try:
        reject_external_pdf(att)
    except Exception:
        logger.exception(
            "reject_external_pdf failed: attachment=%s path=%s",
            att.id,
            att.hidrive_remote_path,
        )
        return json_error("other.api.external_pdf_reject_failed", status=502)
    create_audit_event(
        event_type="EXTERNAL_PDF_REJECTED",
        actor_user_id=request.user.id,
        patient_id=doc.queue_entry.patient_id,
        medical_document_id=doc.id,
        context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "external_pdf_attachment_id": str(att.id),
            "hidrive_remote_path": att.hidrive_remote_path,
        },
    )
    return JsonResponse({"ok": True, "status": att.status}, status=200)
