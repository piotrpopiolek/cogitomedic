from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from pydantic import ValidationError

from apps.core.api_utils import (
    get_scoped_clinic_site_ids,
    get_tablet_scope_clinic_site_ids,
    json_domain_error,
    json_error,
    resolve_list_limit_query,
    read_json_body,
    require_auth,
    require_user_role,
)
from apps.core.exceptions import (
    DomainError,
    InvalidRequestBodyEncoding,
    StateTransitionError,
)
from apps.reception.api_schemas import (
    CreateDailyQueueRequest,
    CreateQueueEntryRequest,
    CreateQueueEntrySessionRequest,
    UpdateDailyQueueRequest,
    UpdateQueueEntryRequest,
)
from apps.reception.models import DailyQueue, QueueEntry
from apps.reception.services import (
    NOT_PROVIDED,
    create_daily_queue,
    create_queue_entry,
    get_or_create_tablet_device_by_android_id,
    issue_tablet_session_latest_wins,
    update_daily_queue,
    update_queue_entry,
)


def _queue_entry_domain_error_response(exc: DomainError) -> JsonResponse:
    """Same DomainError key → same HTTP status on POST create and PATCH."""
    key = exc.api_message_key or ""
    if key in {
        "other.domain.queue_entry_process_type_exists",
        "other.domain.queue_closed_cannot_add_patient",
    }:
        status = 409
    elif key in {
        "other.domain.ausfallhonorar_role_required",
        "other.domain.telederm_intake_disabled",
    }:
        status = 403
    else:
        status = 400
    return json_domain_error(exc, status=status)


def _pydantic_validation_error_response(exc: ValidationError) -> JsonResponse:
    """HTTP 400; omit ctx so field-validator ValueError is JSON-serializable."""
    return JsonResponse(
        {
            "error": "Validation error.",
            "details": exc.errors(include_url=False, include_context=False),
        },
        status=400,
    )


def _serialize_queue(q: DailyQueue) -> dict:
    return {
        "id": str(q.id),
        "queue_date": q.queue_date.isoformat(),
        "clinic_site_id": str(q.clinic_site_id),
        "consulting_room_id": str(q.consulting_room_id),
        "assigned_doctor_id": (
            str(q.assigned_doctor_id) if q.assigned_doctor_id else None
        ),
        "shift_code": q.shift_code,
        "source": q.source,
        "status": q.status,
        "created_at": q.created_at.isoformat(),
        "updated_at": q.updated_at.isoformat(),
    }


def _serialize_entry(e: QueueEntry) -> dict:
    return {
        "id": str(e.id),
        "daily_queue_id": str(e.daily_queue_id),
        "patient_id": str(e.patient_id),
        "entry_status": e.entry_status,
        "process_type": e.process_type,
        "position_no": e.position_no,
        "visit_external_id": e.visit_external_id,
        "appointment_time": (
            e.appointment_time.isoformat() if e.appointment_time else None
        ),
        "notes": e.notes,
        "ausfallhonorar": e.ausfallhonorar,
        "created_at": e.created_at.isoformat(),
        "updated_at": e.updated_at.isoformat(),
    }


@require_auth
def daily_queues_view(request: HttpRequest) -> JsonResponse:
    allowed = (
        {"RECEPTION", "ADMIN", "TABLET", "DOCTOR"}
        if request.method == "GET"
        else {"RECEPTION", "ADMIN"}
    )
    role_error = require_user_role(request, allowed_roles=allowed)
    if role_error:
        return role_error
    if request.method == "GET":
        qs = DailyQueue.objects.all().order_by(
            "-queue_date", "clinic_site_id", "consulting_room_id"
        )
        queue_date = request.GET.get("queue_date")
        is_tablet = request.user.is_tablet
        if is_tablet:
            today = timezone.now().date()
            if queue_date and queue_date != today.isoformat():
                return json_error("other.api.tablet_queues_today_only", status=403)
            queue_date = today.isoformat()

        scope_ids = get_tablet_scope_clinic_site_ids(request)
        if scope_ids is None:
            scope_ids = get_scoped_clinic_site_ids(request.user)
        if scope_ids is not None:
            if not scope_ids:
                return JsonResponse({"items": []})
            qs = qs.filter(clinic_site_id__in=scope_ids)
        if request.user.is_doctor:
            qs = qs.filter(assigned_doctor_id=request.user.id)

        if queue_date:
            qs = qs.filter(queue_date=queue_date)
        clinic_site_id = request.GET.get("clinic_site_id")
        if clinic_site_id:
            qs = qs.filter(clinic_site_id=clinic_site_id)
        consulting_room_id = request.GET.get("consulting_room_id")
        if consulting_room_id:
            qs = qs.filter(consulting_room_id=consulting_room_id)
        shift_code = request.GET.get("shift_code")
        if shift_code:
            qs = qs.filter(shift_code=shift_code)
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        limit = resolve_list_limit_query(request.GET.get("limit"))
        if isinstance(limit, JsonResponse):
            return limit
        items = [_serialize_queue(q) for q in qs[:limit]]
        return JsonResponse({"items": items})
    if request.method == "POST":
        try:
            body = CreateDailyQueueRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("other.api.invalid_json_payload", status=400)
        except InvalidRequestBodyEncoding as exc:
            return json_domain_error(exc)
        except ValidationError as exc:
            return _pydantic_validation_error_response(exc)
        scope_ids = get_scoped_clinic_site_ids(request.user)
        if scope_ids is not None and str(body.clinic_site_id) not in {
            str(sid) for sid in scope_ids
        }:
            return json_error("other.api.clinic_site_not_in_scope", status=403)
        try:
            queue = create_daily_queue(
                queue_date=body.queue_date,
                clinic_site_id=body.clinic_site_id,
                consulting_room_id=body.consulting_room_id,
                assigned_doctor_id=body.assigned_doctor_id,
                shift_code=body.shift_code,
                created_by_user_id=request.user.id,
                source=body.source,
            )
        except ObjectDoesNotExist:
            return json_error(
                "other.api.clinic_site_or_consulting_room_not_found", status=404
            )
        except (DomainError, StateTransitionError) as exc:
            if "Duplicate queue" in str(exc):
                return json_error("other.api.duplicate_queue_slot", status=409)
            return json_domain_error(exc, status=400)
        except IntegrityError:
            return json_error("other.api.duplicate_queue_slot", status=409)
        return JsonResponse(_serialize_queue(queue), status=201)
    return json_error("other.api.method_not_allowed", status=405)


@require_auth
def daily_queue_detail_view(request: HttpRequest, daily_queue_id: UUID) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"RECEPTION", "ADMIN", "DOCTOR"}
    )
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH"):
        return json_error("other.api.method_not_allowed", status=405)
    try:
        queue = DailyQueue.objects.get(id=daily_queue_id)
    except ObjectDoesNotExist:
        return json_error("other.api.daily_queue_not_found", status=404)
    scope_ids = get_scoped_clinic_site_ids(request.user)
    if scope_ids is not None and queue.clinic_site_id not in scope_ids:
        return json_error("other.api.daily_queue_not_in_scope", status=403)
    if request.user.is_doctor and queue.assigned_doctor_id != request.user.id:
        return json_error("other.api.doctor_own_assigned_queues", status=403)
    if request.method == "GET":
        return JsonResponse(_serialize_queue(queue))
    if request.user.is_doctor:
        return json_error("other.api.only_reception_admin_update_queue", status=403)
    try:
        raw = read_json_body(request)
        body = UpdateDailyQueueRequest.model_validate(raw)
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return _pydantic_validation_error_response(exc)
    try:
        queue = update_daily_queue(
            daily_queue_id,
            status=body.status,
            assigned_doctor_id=(
                body.assigned_doctor_id if "assigned_doctor_id" in raw else NOT_PROVIDED
            ),
        )
    except ObjectDoesNotExist:
        return json_error("other.api.daily_queue_not_found", status=404)
    except DomainError as exc:
        return json_domain_error(exc, status=400)
    return JsonResponse(_serialize_queue(queue))


@require_auth
def daily_queue_entries_view(
    request: HttpRequest, daily_queue_id: UUID
) -> JsonResponse:
    allowed = (
        {"RECEPTION", "ADMIN", "TABLET", "DOCTOR"}
        if request.method == "GET"
        else {"RECEPTION", "ADMIN"}
    )
    role_error = require_user_role(request, allowed_roles=allowed)
    if role_error:
        return role_error
    if request.method not in ("GET", "POST"):
        return json_error("other.api.method_not_allowed", status=405)
    try:
        queue = DailyQueue.objects.get(id=daily_queue_id)
    except ObjectDoesNotExist:
        return json_error("other.api.daily_queue_not_found", status=404)

    scope_ids = get_tablet_scope_clinic_site_ids(request)
    if scope_ids is None:
        scope_ids = get_scoped_clinic_site_ids(request.user)
    if scope_ids is not None and queue.clinic_site_id not in scope_ids:
        return json_error("other.api.daily_queue_not_in_scope", status=403)
    if request.user.is_tablet and queue.queue_date != timezone.now().date():
        return json_error("other.api.tablet_entries_today_only", status=403)

    if request.user.is_doctor and queue.assigned_doctor_id != request.user.id:
        return json_error("other.api.doctor_own_queues", status=403)

    if request.method == "GET":
        qs = (
            QueueEntry.objects.filter(daily_queue_id=daily_queue_id)
            .select_related("patient")
            .order_by("position_no")
        )
        entry_status = request.GET.get("entry_status")
        if entry_status:
            qs = qs.filter(entry_status=entry_status)
        patient_id = request.GET.get("patient_id")
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        ordering = request.GET.get("ordering", "position_no")
        if ordering.lstrip("-") == "position_no":
            qs = qs.order_by(ordering)
        limit = resolve_list_limit_query(request.GET.get("limit"))
        if isinstance(limit, JsonResponse):
            return limit
        items = [_serialize_entry(e) for e in qs[:limit]]
        return JsonResponse({"items": items})
    try:
        body = CreateQueueEntryRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return _pydantic_validation_error_response(exc)
    try:
        entry = create_queue_entry(
            daily_queue_id=daily_queue_id,
            patient_id=body.patient_id,
            created_by_user_id=request.user.id,
            appointment_time=body.appointment_time,
            visit_external_id=body.visit_external_id,
            notes=body.notes,
            process_type=body.process_type,
        )
    except ObjectDoesNotExist:
        return json_error("other.api.queue_or_patient_not_found", status=404)
    except StateTransitionError as exc:
        return json_domain_error(exc, status=409)
    except DomainError as exc:
        return _queue_entry_domain_error_response(exc)
    except IntegrityError:
        return json_error("other.api.duplicate_visit_external_id", status=409)
    return JsonResponse(_serialize_entry(entry), status=201)


@require_auth
def queue_entry_detail_view(request: HttpRequest, queue_entry_id: UUID) -> JsonResponse:
    if request.method == "GET":
        allowed = {"RECEPTION", "ADMIN", "DOCTOR", "MANAGER"}
    elif request.method == "PATCH":
        allowed = {"RECEPTION", "ADMIN", "MANAGER"}
    else:
        allowed = {"RECEPTION", "ADMIN"}
    role_error = require_user_role(request, allowed_roles=allowed)
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("other.api.method_not_allowed", status=405)
    try:
        entry = QueueEntry.objects.select_related("daily_queue").get(id=queue_entry_id)
    except ObjectDoesNotExist:
        return json_error("other.api.queue_entry_not_found", status=404)

    scope_ids = get_scoped_clinic_site_ids(request.user)
    if scope_ids is not None and entry.daily_queue.clinic_site_id not in scope_ids:
        return json_error("other.api.queue_entry_not_in_scope", status=403)
    if (
        request.user.is_doctor
        and entry.daily_queue.assigned_doctor_id != request.user.id
    ):
        return json_error("other.api.doctor_entries_own_queues", status=403)

    if request.method == "GET":
        return JsonResponse(_serialize_entry(entry))
    if request.method == "DELETE":
        try:
            entry = update_queue_entry(
                queue_entry_id,
                entry_status="CANCELLED",
                actor_user_id=request.user.id,
            )
        except ObjectDoesNotExist:
            return json_error("other.api.queue_entry_not_found", status=404)
        except DomainError as exc:
            return json_domain_error(exc, status=400)
        return JsonResponse(_serialize_entry(entry))
    try:
        body = UpdateQueueEntryRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return _pydantic_validation_error_response(exc)
    if body.entry_status is None and body.notes is None and body.ausfallhonorar is None:
        return json_error("other.api.provide_entry_status_or_notes", status=400)
    try:
        entry = update_queue_entry(
            queue_entry_id,
            entry_status=body.entry_status,
            notes=body.notes,
            ausfallhonorar=body.ausfallhonorar,
            actor_user_id=request.user.id,
        )
    except ObjectDoesNotExist:
        return json_error("other.api.queue_entry_not_found", status=404)
    except DomainError as exc:
        return _queue_entry_domain_error_response(exc)
    return JsonResponse(_serialize_entry(entry))


@require_auth
def queue_entry_sessions_view(
    request: HttpRequest, queue_entry_id: UUID
) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"RECEPTION", "ADMIN", "TABLET"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        entry = QueueEntry.objects.select_related("daily_queue").get(id=queue_entry_id)
    except ObjectDoesNotExist:
        return json_error("other.api.queue_entry_not_found", status=404)
    scope_ids = get_tablet_scope_clinic_site_ids(request)
    if scope_ids is None:
        scope_ids = get_scoped_clinic_site_ids(request.user)
    if scope_ids is not None and entry.daily_queue.clinic_site_id not in scope_ids:
        return json_error("other.api.queue_entry_not_in_scope", status=403)
    try:
        body = CreateQueueEntrySessionRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return _pydantic_validation_error_response(exc)
    tablet_device_id = body.tablet_device_id
    if tablet_device_id is None and body.android_id:
        device, _ = get_or_create_tablet_device_by_android_id(
            android_id=body.android_id
        )
        tablet_device_id = device.id
    try:
        issued = issue_tablet_session_latest_wins(
            queue_entry_id=queue_entry_id,
            created_by_user_id=request.user.id,
            form_locale=body.form_locale,
            expires_in_minutes=body.expires_in_minutes,
            tablet_device_id=tablet_device_id,
        )
    except ObjectDoesNotExist:
        return json_error("other.api.queue_entry_or_tablet_not_found", status=404)
    except DomainError as exc:
        return json_domain_error(exc, status=400)
    return JsonResponse(
        {
            "session_id": str(issued.session_id),
            "expires_at": issued.expires_at.isoformat(),
            "intake_form_id": str(issued.intake_form_id),
        },
        status=201,
    )
