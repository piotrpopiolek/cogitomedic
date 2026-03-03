from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from pydantic import ValidationError

from apps.core.api_utils import json_error, parse_list_limit, read_json_body, require_auth, require_user_role
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding, StateTransitionError
from apps.reception.api_schemas import (
    CreateDailyQueueRequest,
    CreateQueueEntryRequest,
    CreateQueueEntrySessionRequest,
    UpdateDailyQueueRequest,
    UpdateQueueEntryRequest,
)
from apps.reception.models import DailyQueue, QueueEntry
from apps.reception.services import (
    create_daily_queue,
    create_queue_entry,
    get_or_create_tablet_device_by_android_id,
    issue_tablet_session_latest_wins,
    update_daily_queue_status,
    update_queue_entry,
)



def _serialize_queue(q: DailyQueue) -> dict:
    return {
        "id": str(q.id),
        "queue_date": q.queue_date.isoformat(),
        "clinic_site_id": str(q.clinic_site_id),
        "consulting_room_id": str(q.consulting_room_id),
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
        "position_no": e.position_no,
        "visit_external_id": e.visit_external_id,
        "appointment_time": e.appointment_time.isoformat() if e.appointment_time else None,
        "notes": e.notes,
        "created_at": e.created_at.isoformat(),
        "updated_at": e.updated_at.isoformat(),
    }


@require_auth
def daily_queues_view(request: HttpRequest) -> JsonResponse:
    allowed = {"RECEPTION", "ADMIN", "TABLET", "DOCTOR"} if request.method == "GET" else {"RECEPTION", "ADMIN"}
    role_error = require_user_role(request, allowed_roles=allowed)
    if role_error:
        return role_error
    if request.method == "GET":
        qs = DailyQueue.objects.all().order_by("-queue_date", "clinic_site_id", "consulting_room_id")
        queue_date = request.GET.get("queue_date")
        is_tablet = getattr(request.user, "role", None) == "TABLET"
        if is_tablet:
            today = timezone.now().date()
            if queue_date and queue_date != today.isoformat():
                return json_error("TABLET role can only access queues for today.", status=403)
            queue_date = today.isoformat()
            
        if getattr(request.user, "role", None) == "DOCTOR":
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
        limit = parse_list_limit(request.GET.get("limit"))
        items = [_serialize_queue(q) for q in qs[:limit]]
        return JsonResponse({"items": items})
    if request.method == "POST":
        try:
            body = CreateDailyQueueRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except InvalidRequestBodyEncoding:
            return json_error("Invalid request encoding.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            queue = create_daily_queue(
                queue_date=body.queue_date,
                clinic_site_id=body.clinic_site_id,
                consulting_room_id=body.consulting_room_id,
                shift_code=body.shift_code,
                created_by_user_id=request.user.id,
                source=body.source,
            )
        except ObjectDoesNotExist:
            return json_error("Clinic site or consulting room not found.", status=404)
        except (DomainError, StateTransitionError) as exc:
            if "Duplicate queue" in str(exc):
                return json_error("Duplicate queue for this date/site/room/shift.", status=409)
            return json_error(str(exc), status=400)
        return JsonResponse(_serialize_queue(queue), status=201)
    return json_error("Method not allowed.", status=405)


@require_auth
def daily_queue_detail_view(request: HttpRequest, daily_queue_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH"):
        return json_error("Method not allowed.", status=405)
    try:
        queue = DailyQueue.objects.get(id=daily_queue_id)
    except ObjectDoesNotExist:
        return json_error("Daily queue not found.", status=404)
    if request.method == "GET":
        return JsonResponse(_serialize_queue(queue))
    try:
        body = UpdateDailyQueueRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        queue = update_daily_queue_status(daily_queue_id, status=body.status)
    except ObjectDoesNotExist:
        return json_error("Daily queue not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    return JsonResponse(_serialize_queue(queue))


@require_auth
def daily_queue_entries_view(request: HttpRequest, daily_queue_id: UUID) -> JsonResponse:
    allowed = {"RECEPTION", "ADMIN", "TABLET", "DOCTOR"} if request.method == "GET" else {"RECEPTION", "ADMIN"}
    role_error = require_user_role(request, allowed_roles=allowed)
    if role_error:
        return role_error
    if request.method not in ("GET", "POST"):
        return json_error("Method not allowed.", status=405)
    try:
        queue = DailyQueue.objects.get(id=daily_queue_id)
    except ObjectDoesNotExist:
        return json_error("Daily queue not found.", status=404)
        
    if getattr(request.user, "role", None) == "TABLET" and queue.queue_date != timezone.now().date():
        return json_error("TABLET role can only access entries of today's queues.", status=403)
        
    if getattr(request.user, "role", None) == "DOCTOR" and queue.assigned_doctor_id != request.user.id:
        return json_error("DOCTOR can only access own queues.", status=403)
        
    if request.method == "GET":
        qs = QueueEntry.objects.filter(daily_queue_id=daily_queue_id).select_related("patient").order_by("position_no")
        entry_status = request.GET.get("entry_status")
        if entry_status:
            qs = qs.filter(entry_status=entry_status)
        patient_id = request.GET.get("patient_id")
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        ordering = request.GET.get("ordering", "position_no")
        if ordering.lstrip("-") == "position_no":
            qs = qs.order_by(ordering)
        limit = parse_list_limit(request.GET.get("limit"))
        items = [_serialize_entry(e) for e in qs[:limit]]
        return JsonResponse({"items": items})
    try:
        body = CreateQueueEntryRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        entry = create_queue_entry(
            daily_queue_id=daily_queue_id,
            patient_id=body.patient_id,
            created_by_user_id=request.user.id,
            appointment_time=body.appointment_time,
            visit_external_id=body.visit_external_id,
            notes=body.notes,
        )
    except ObjectDoesNotExist:
        return json_error("Queue or patient not found.", status=404)
    except StateTransitionError as exc:
        return json_error(str(exc), status=409)
    except IntegrityError:
        return json_error("Duplicate visit_external_id in this queue.", status=409)
    return JsonResponse(_serialize_entry(entry), status=201)


@require_auth
def queue_entry_detail_view(request: HttpRequest, queue_entry_id: UUID) -> JsonResponse:
    allowed = {"RECEPTION", "ADMIN", "DOCTOR"} if request.method == "GET" else {"RECEPTION", "ADMIN"}
    role_error = require_user_role(request, allowed_roles=allowed)
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("Method not allowed.", status=405)
    try:
        entry = QueueEntry.objects.select_related("daily_queue").get(id=queue_entry_id)
    except ObjectDoesNotExist:
        return json_error("Queue entry not found.", status=404)
        
    if getattr(request.user, "role", None) == "DOCTOR" and entry.daily_queue.assigned_doctor_id != request.user.id:
        return json_error("DOCTOR can only access entries from own queues.", status=403)
        
    if request.method == "GET":
        return JsonResponse(_serialize_entry(entry))
    if request.method == "DELETE":
        try:
            entry = update_queue_entry(queue_entry_id, entry_status="CANCELLED")
        except ObjectDoesNotExist:
            return json_error("Queue entry not found.", status=404)
        except DomainError as exc:
            return json_error(str(exc), status=400)
        return JsonResponse(_serialize_entry(entry))
    try:
        body = UpdateQueueEntryRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    if body.entry_status is None and body.notes is None:
        return json_error("Provide entry_status and/or notes.", status=400)
    try:
        entry = update_queue_entry(queue_entry_id, entry_status=body.entry_status, notes=body.notes)
    except ObjectDoesNotExist:
        return json_error("Queue entry not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    return JsonResponse(_serialize_entry(entry))


@require_auth
def queue_entry_sessions_view(request: HttpRequest, queue_entry_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "TABLET"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = CreateQueueEntrySessionRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    tablet_device_id = body.tablet_device_id
    if tablet_device_id is None and body.android_id:
        device, _ = get_or_create_tablet_device_by_android_id(android_id=body.android_id)
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
        return json_error("Queue entry or tablet device not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    return JsonResponse(
        {
            "session_id": str(issued.session_id),
            "expires_at": issued.expires_at.isoformat(),
            "intake_form_id": str(issued.intake_form_id),
        },
        status=201,
    )
