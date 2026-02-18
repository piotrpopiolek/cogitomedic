from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import json_error, read_json_body
from apps.core.exceptions import DomainError, StateTransitionError
from apps.reception.api_schemas import (
    CreateClinicSiteRequest,
    CreateConsultingRoomRequest,
    CreateDailyQueueRequest,
    CreateQueueEntryRequest,
    CreateQueueEntrySessionRequest,
    CreateTabletDeviceRequest,
    UpdateClinicSiteRequest,
    UpdateConsultingRoomRequest,
    UpdateDailyQueueRequest,
    UpdateQueueEntryRequest,
    UpdateTabletDeviceRequest,
)
from apps.reception.models import ClinicSite, ConsultingRoom, DailyQueue, QueueEntry, TabletDevice
from apps.reception.services import (
    create_daily_queue,
    create_queue_entry,
    issue_tablet_session_token_latest_wins,
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


def _serialize_tablet_device(device: TabletDevice) -> dict:
    return {
        "id": str(device.id),
        "name": device.name,
        "device_code": device.device_code,
        "is_active": device.is_active,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "created_at": device.created_at.isoformat(),
    }


def _parse_bool_query(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def _serialize_clinic_site(site: ClinicSite) -> dict:
    return {
        "id": str(site.id),
        "code": site.code,
        "name": site.name,
        "is_active": site.is_active,
        "created_at": site.created_at.isoformat(),
    }


def _serialize_consulting_room(room: ConsultingRoom) -> dict:
    return {
        "id": str(room.id),
        "clinic_site_id": str(room.clinic_site_id),
        "code": room.code,
        "name": room.name,
        "is_active": room.is_active,
        "created_at": room.created_at.isoformat(),
    }


@csrf_exempt
def clinic_sites_view(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = ClinicSite.objects.all().order_by("code")
        is_active_raw = request.GET.get("is_active")
        if is_active_raw is not None:
            is_active = _parse_bool_query(is_active_raw)
            if is_active is None:
                return json_error("Invalid is_active query parameter.", status=400)
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
        return JsonResponse({"items": [_serialize_clinic_site(site) for site in qs]})

    if request.method == "POST":
        try:
            body = CreateClinicSiteRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            site = ClinicSite.objects.create(
                code=body.code,
                name=body.name,
                is_active=body.is_active,
            )
        except IntegrityError:
            return json_error("Clinic site code already exists.", status=409)
        return JsonResponse(_serialize_clinic_site(site), status=201)

    return json_error("Method not allowed.", status=405)


@csrf_exempt
def clinic_site_detail_view(request: HttpRequest, clinic_site_id: UUID) -> JsonResponse:
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("Method not allowed.", status=405)

    try:
        site = ClinicSite.objects.get(id=clinic_site_id)
    except ObjectDoesNotExist:
        return json_error("Clinic site not found.", status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_clinic_site(site))

    if request.method == "DELETE":
        if site.is_active:
            site.is_active = False
            site.save(update_fields=["is_active"])
        return JsonResponse(_serialize_clinic_site(site))

    try:
        body = UpdateClinicSiteRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    update_fields: list[str] = []
    if body.code is not None:
        site.code = body.code
        update_fields.append("code")
    if body.name is not None:
        site.name = body.name
        update_fields.append("name")
    if body.is_active is not None:
        site.is_active = body.is_active
        update_fields.append("is_active")
    if not update_fields:
        return json_error("Provide at least one field to update.", status=400)
    try:
        site.save(update_fields=update_fields)
    except IntegrityError:
        return json_error("Clinic site code already exists.", status=409)
    return JsonResponse(_serialize_clinic_site(site))


@csrf_exempt
def consulting_rooms_view(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = ConsultingRoom.objects.all().order_by("clinic_site_id", "code")
        clinic_site_id = request.GET.get("clinic_site_id")
        if clinic_site_id:
            qs = qs.filter(clinic_site_id=clinic_site_id)
        is_active_raw = request.GET.get("is_active")
        if is_active_raw is not None:
            is_active = _parse_bool_query(is_active_raw)
            if is_active is None:
                return json_error("Invalid is_active query parameter.", status=400)
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
        return JsonResponse({"items": [_serialize_consulting_room(room) for room in qs]})

    if request.method == "POST":
        try:
            body = CreateConsultingRoomRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            ClinicSite.objects.get(id=body.clinic_site_id)
            room = ConsultingRoom.objects.create(
                clinic_site_id=body.clinic_site_id,
                code=body.code,
                name=body.name,
                is_active=body.is_active,
            )
        except ObjectDoesNotExist:
            return json_error("Clinic site not found.", status=404)
        except IntegrityError:
            return json_error("Consulting room code already exists for this clinic site.", status=409)
        return JsonResponse(_serialize_consulting_room(room), status=201)

    return json_error("Method not allowed.", status=405)


@csrf_exempt
def consulting_room_detail_view(request: HttpRequest, consulting_room_id: UUID) -> JsonResponse:
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("Method not allowed.", status=405)

    try:
        room = ConsultingRoom.objects.get(id=consulting_room_id)
    except ObjectDoesNotExist:
        return json_error("Consulting room not found.", status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_consulting_room(room))

    if request.method == "DELETE":
        if room.is_active:
            room.is_active = False
            room.save(update_fields=["is_active"])
        return JsonResponse(_serialize_consulting_room(room))

    try:
        body = UpdateConsultingRoomRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    update_fields: list[str] = []
    if body.clinic_site_id is not None:
        try:
            ClinicSite.objects.get(id=body.clinic_site_id)
        except ObjectDoesNotExist:
            return json_error("Clinic site not found.", status=404)
        room.clinic_site_id = body.clinic_site_id
        update_fields.append("clinic_site")
    if body.code is not None:
        room.code = body.code
        update_fields.append("code")
    if body.name is not None:
        room.name = body.name
        update_fields.append("name")
    if body.is_active is not None:
        room.is_active = body.is_active
        update_fields.append("is_active")
    if not update_fields:
        return json_error("Provide at least one field to update.", status=400)
    try:
        room.save(update_fields=update_fields)
    except IntegrityError:
        return json_error("Consulting room code already exists for this clinic site.", status=409)
    return JsonResponse(_serialize_consulting_room(room))


@csrf_exempt
def daily_queues_view(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = DailyQueue.objects.all().order_by("-queue_date", "clinic_site_id", "consulting_room_id")
        queue_date = request.GET.get("queue_date")
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
        items = [_serialize_queue(q) for q in qs]
        return JsonResponse({"items": items})
    if request.method == "POST":
        try:
            body = CreateDailyQueueRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            queue = create_daily_queue(
                queue_date=body.queue_date,
                clinic_site_id=body.clinic_site_id,
                consulting_room_id=body.consulting_room_id,
                shift_code=body.shift_code,
                created_by_user_id=body.created_by_user_id,
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


@csrf_exempt
def daily_queue_detail_view(request: HttpRequest, daily_queue_id: UUID) -> JsonResponse:
    if request.method not in ("GET", "PATCH"):
        return json_error("Method not allowed.", status=405)
    try:
        queue = DailyQueue.objects.get(id=daily_queue_id)
    except ObjectDoesNotExist:
        return json_error("Daily queue not found.", status=404)
    if request.method == "GET":
        return JsonResponse(_serialize_queue(queue))
    # PATCH
    try:
        body = UpdateDailyQueueRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        queue = update_daily_queue_status(daily_queue_id, status=body.status)
    except ObjectDoesNotExist:
        return json_error("Daily queue not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    return JsonResponse(_serialize_queue(queue))


@csrf_exempt
def daily_queue_entries_view(request: HttpRequest, daily_queue_id: UUID) -> JsonResponse:
    if request.method not in ("GET", "POST"):
        return json_error("Method not allowed.", status=405)
    try:
        DailyQueue.objects.get(id=daily_queue_id)
    except ObjectDoesNotExist:
        return json_error("Daily queue not found.", status=404)
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
        items = [_serialize_entry(e) for e in qs]
        return JsonResponse({"items": items})
    # POST
    try:
        body = CreateQueueEntryRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        entry = create_queue_entry(
            daily_queue_id=daily_queue_id,
            patient_id=body.patient_id,
            created_by_user_id=body.created_by_user_id,
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


@csrf_exempt
def queue_entry_detail_view(request: HttpRequest, queue_entry_id: UUID) -> JsonResponse:
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("Method not allowed.", status=405)
    try:
        entry = QueueEntry.objects.get(id=queue_entry_id)
    except ObjectDoesNotExist:
        return json_error("Queue entry not found.", status=404)
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
    # PATCH
    try:
        body = UpdateQueueEntryRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    if body.entry_status is None and body.notes is None:
        return json_error("Provide entry_status and/or notes.", status=400)
    try:
        entry = update_queue_entry(
            queue_entry_id,
            entry_status=body.entry_status,
            notes=body.notes,
        )
    except ObjectDoesNotExist:
        return json_error("Queue entry not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    return JsonResponse(_serialize_entry(entry))


@csrf_exempt
def tablet_devices_view(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = TabletDevice.objects.all().order_by("name")
        is_active_raw = request.GET.get("is_active")
        if is_active_raw is not None:
            is_active = _parse_bool_query(is_active_raw)
            if is_active is None:
                return json_error("Invalid is_active query parameter.", status=400)
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(device_code__icontains=search))
        return JsonResponse({"items": [_serialize_tablet_device(device) for device in qs]})

    if request.method == "POST":
        try:
            body = CreateTabletDeviceRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            device = TabletDevice.objects.create(
                name=body.name,
                device_code=body.device_code,
                is_active=body.is_active,
            )
        except IntegrityError:
            return json_error("Tablet device with this name or code already exists.", status=409)
        return JsonResponse(_serialize_tablet_device(device), status=201)

    return json_error("Method not allowed.", status=405)


@csrf_exempt
def tablet_device_detail_view(request: HttpRequest, tablet_device_id: UUID) -> JsonResponse:
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("Method not allowed.", status=405)

    try:
        device = TabletDevice.objects.get(id=tablet_device_id)
    except ObjectDoesNotExist:
        return json_error("Tablet device not found.", status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_tablet_device(device))

    if request.method == "DELETE":
        if device.is_active:
            device.is_active = False
            device.save(update_fields=["is_active"])
        return JsonResponse(_serialize_tablet_device(device))

    try:
        body = UpdateTabletDeviceRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    update_fields: list[str] = []
    if body.name is not None:
        device.name = body.name
        update_fields.append("name")
    if body.device_code is not None:
        device.device_code = body.device_code
        update_fields.append("device_code")
    if body.is_active is not None:
        device.is_active = body.is_active
        update_fields.append("is_active")
    if not update_fields:
        return json_error("Provide at least one field to update.", status=400)
    try:
        device.save(update_fields=update_fields)
    except IntegrityError:
        return json_error("Tablet device with this name or code already exists.", status=409)
    return JsonResponse(_serialize_tablet_device(device))


@csrf_exempt
def tablet_device_heartbeat_view(request: HttpRequest, tablet_device_id: UUID) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        device = TabletDevice.objects.get(id=tablet_device_id)
    except ObjectDoesNotExist:
        return json_error("Tablet device not found.", status=404)

    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])
    return JsonResponse({"last_seen_at": device.last_seen_at.isoformat()})


@csrf_exempt
def queue_entry_sessions_view(request: HttpRequest, queue_entry_id: UUID) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        body = CreateQueueEntrySessionRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        issued = issue_tablet_session_token_latest_wins(
            queue_entry_id=queue_entry_id,
            created_by_user_id=body.created_by_user_id,
            form_locale=body.form_locale,
            expires_in_minutes=body.expires_in_minutes,
            tablet_device_id=body.tablet_device_id,
        )
    except ObjectDoesNotExist:
        return json_error("Queue entry or tablet device not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)

    return JsonResponse(
        {
            "token": issued.token_plain,
            "session_id": str(issued.session_id),
            "expires_at": issued.expires_at.isoformat(),
        },
        status=201,
    )
