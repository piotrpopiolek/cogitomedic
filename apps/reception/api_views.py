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
    CreatePatientRequest,
    MergePatientRequest,
    UpdateClinicSiteRequest,
    UpdateConsultingRoomRequest,
    UpdateDailyQueueRequest,
    UpdatePatientRequest,
    UpdateQueueEntryRequest,
    UpdateTabletDeviceRequest,
)
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientContactHistory,
    QueueEntry,
    TabletDevice,
)
from apps.reception.services import (
    InvalidSourceActionError,
    SourceNotTemporaryError,
    TargetNotConfirmedError,
    create_or_update_patient_manual,
    create_daily_queue,
    create_queue_entry,
    issue_tablet_session_token_latest_wins,
    merge_temporary_patient_into_confirmed,
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


def _serialize_patient(patient: Patient) -> dict:
    return {
        "id": str(patient.id),
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "date_of_birth": patient.date_of_birth.isoformat(),
        "phone": patient.phone,
        "email": patient.email,
        "doctolib_patient_id": patient.doctolib_patient_id,
        "identity_status": patient.identity_status,
        "identity_alert_created_at": (
            patient.identity_alert_created_at.isoformat() if patient.identity_alert_created_at else None
        ),
        "identity_resolution_due_at": (
            patient.identity_resolution_due_at.isoformat() if patient.identity_resolution_due_at else None
        ),
        "street": patient.street,
        "city": patient.city,
        "postal_code": patient.postal_code,
        "country_code": patient.country_code,
        "external_source": patient.external_source,
        "external_source_id": patient.external_source_id,
        "is_active": patient.is_active,
        "created_at": patient.created_at.isoformat(),
        "updated_at": patient.updated_at.isoformat(),
    }


def _serialize_contact_history(item: PatientContactHistory) -> dict:
    return {
        "id": str(item.id),
        "phone": item.phone,
        "email": item.email,
        "changed_at": item.changed_at.isoformat(),
        "changed_by_user_id": str(item.changed_by_user_id) if item.changed_by_user_id else None,
        "reason": item.reason,
    }


def _parse_positive_int(value: str, *, default: int, minimum: int = 1, maximum: int = 100) -> int:
    if not value:
        return default
    parsed = int(value)
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


@csrf_exempt
def patients_view(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = Patient.objects.all().order_by("-created_at")
        search = request.GET.get("search")
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        last_name = request.GET.get("last_name")
        if last_name:
            qs = qs.filter(last_name__icontains=last_name)
        date_of_birth = request.GET.get("date_of_birth")
        if date_of_birth:
            qs = qs.filter(date_of_birth=date_of_birth)
        phone = request.GET.get("phone")
        if phone:
            qs = qs.filter(phone__icontains=phone)
        identity_status = request.GET.get("identity_status")
        if identity_status:
            qs = qs.filter(identity_status=identity_status)
        doctolib_patient_id = request.GET.get("doctolib_patient_id")
        if doctolib_patient_id:
            qs = qs.filter(doctolib_patient_id=doctolib_patient_id)
        is_active_raw = request.GET.get("is_active")
        if is_active_raw is not None:
            is_active = _parse_bool_query(is_active_raw)
            if is_active is None:
                return json_error("Invalid is_active query parameter.", status=400)
            qs = qs.filter(is_active=is_active)
        try:
            page = _parse_positive_int(request.GET.get("page", "1"), default=1, maximum=10_000)
            page_size = _parse_positive_int(request.GET.get("page_size", "20"), default=20, maximum=200)
        except ValueError:
            return json_error("Invalid pagination parameters.", status=400)
        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        items = [_serialize_patient(patient) for patient in qs[start:end]]
        return JsonResponse(
            {
                "items": items,
                "pagination": {"page": page, "page_size": page_size, "total": total},
            }
        )

    if request.method == "POST":
        try:
            body = CreatePatientRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            patient = create_or_update_patient_manual(
                first_name=body.first_name,
                last_name=body.last_name,
                date_of_birth=body.date_of_birth,
                phone=body.phone,
                email=body.email,
                doctolib_patient_id=body.doctolib_patient_id,
                created_or_updated_by_user_id=body.created_by_user_id,
            )
            update_fields = ["updated_at"]
            patient.street = body.street
            update_fields.append("street")
            patient.city = body.city
            update_fields.append("city")
            patient.postal_code = body.postal_code
            update_fields.append("postal_code")
            patient.country_code = body.country_code
            update_fields.append("country_code")
            patient.external_source = body.external_source
            update_fields.append("external_source")
            patient.external_source_id = body.external_source_id
            update_fields.append("external_source_id")
            patient.save(update_fields=update_fields)
        except IntegrityError:
            return json_error("Patient uniqueness conflict.", status=409)
        except DomainError as exc:
            return json_error(str(exc), status=400)

        return JsonResponse(
            {
                "patient": _serialize_patient(patient),
                "identity_alert": {
                    "created": patient.identity_status == "TEMPORARY",
                    "due_at": (
                        patient.identity_resolution_due_at.isoformat()
                        if patient.identity_resolution_due_at
                        else None
                    ),
                },
            },
            status=201,
        )

    return json_error("Method not allowed.", status=405)


@csrf_exempt
def patient_detail_view(request: HttpRequest, patient_id: UUID) -> JsonResponse:
    if request.method not in ("GET", "PATCH"):
        return json_error("Method not allowed.", status=405)
    try:
        patient = Patient.objects.get(id=patient_id)
    except ObjectDoesNotExist:
        return json_error("Patient not found.", status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_patient(patient))

    try:
        body = UpdatePatientRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    fields_set = body.model_fields_set
    if not fields_set:
        return json_error("Provide at least one field to update.", status=400)
    identity_or_contact_fields = {
        "first_name",
        "last_name",
        "date_of_birth",
        "phone",
        "email",
        "doctolib_patient_id",
    }
    if identity_or_contact_fields.intersection(fields_set) and body.changed_by_user_id is None:
        return json_error("changed_by_user_id is required for identity/contact updates.", status=400)

    old_phone = patient.phone
    old_email = patient.email

    try:
        # Reuse domain service to preserve temporary/confirmed identity logic.
        if any(
            field in fields_set
            for field in ["first_name", "last_name", "date_of_birth", "phone", "email", "doctolib_patient_id"]
        ):
            actor_user_id = body.changed_by_user_id
            if actor_user_id is None:
                return json_error("changed_by_user_id is required for identity/contact updates.", status=400)
            patient = create_or_update_patient_manual(
                patient_id=patient.id,
                first_name=body.first_name if "first_name" in fields_set else patient.first_name,
                last_name=body.last_name if "last_name" in fields_set else patient.last_name,
                date_of_birth=body.date_of_birth if "date_of_birth" in fields_set else patient.date_of_birth,
                phone=body.phone if "phone" in fields_set else patient.phone,
                email=body.email if "email" in fields_set else patient.email,
                doctolib_patient_id=(
                    body.doctolib_patient_id if "doctolib_patient_id" in fields_set else patient.doctolib_patient_id
                ),
                created_or_updated_by_user_id=actor_user_id,
            )
        update_fields: list[str] = ["updated_at"]
        if "street" in fields_set:
            patient.street = body.street
            update_fields.append("street")
        if "city" in fields_set:
            patient.city = body.city
            update_fields.append("city")
        if "postal_code" in fields_set:
            patient.postal_code = body.postal_code
            update_fields.append("postal_code")
        if "country_code" in fields_set:
            patient.country_code = body.country_code
            update_fields.append("country_code")
        if "external_source" in fields_set:
            patient.external_source = body.external_source
            update_fields.append("external_source")
        if "external_source_id" in fields_set:
            patient.external_source_id = body.external_source_id
            update_fields.append("external_source_id")
        if "is_active" in fields_set and body.is_active is not None:
            patient.is_active = body.is_active
            update_fields.append("is_active")
        if len(update_fields) > 1:
            patient.save(update_fields=update_fields)
    except IntegrityError:
        return json_error("Patient uniqueness conflict.", status=409)
    except DomainError as exc:
        return json_error(str(exc), status=400)

    if patient.phone != old_phone or patient.email != old_email:
        PatientContactHistory.objects.create(
            patient=patient,
            phone=old_phone,
            email=old_email,
            changed_by_user_id=body.changed_by_user_id,
            reason=body.change_reason,
        )
    return JsonResponse(_serialize_patient(patient))


@csrf_exempt
def patient_contact_history_view(request: HttpRequest, patient_id: UUID) -> JsonResponse:
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    try:
        Patient.objects.get(id=patient_id)
    except ObjectDoesNotExist:
        return json_error("Patient not found.", status=404)

    try:
        page = _parse_positive_int(request.GET.get("page", "1"), default=1, maximum=10_000)
        page_size = _parse_positive_int(request.GET.get("page_size", "20"), default=20, maximum=200)
    except ValueError:
        return json_error("Invalid pagination parameters.", status=400)

    qs = PatientContactHistory.objects.filter(patient_id=patient_id).order_by("-changed_at")
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = [_serialize_contact_history(item) for item in qs[start:end]]
    return JsonResponse({"items": items, "pagination": {"page": page, "page_size": page_size, "total": total}})


@csrf_exempt
def patient_merge_view(request: HttpRequest, patient_id: UUID) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        body = MergePatientRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        result = merge_temporary_patient_into_confirmed(
            source_patient_id=patient_id,
            target_patient_id=body.target_patient_id,
            source_action=body.source_action,
            reason=body.reason,
            actor_user_id=body.actor_user_id,
        )
    except ObjectDoesNotExist:
        return json_error("Patient not found.", status=404)
    except StateTransitionError as exc:
        return json_error(str(exc), status=409)
    except (SourceNotTemporaryError, TargetNotConfirmedError) as exc:
        return json_error(str(exc), status=422)
    except InvalidSourceActionError as exc:
        return json_error(str(exc), status=400)
    except DomainError as exc:
        return json_error(str(exc), status=400)

    return JsonResponse(
        {
            "merged": result.merged,
            "source_patient_id": str(result.source_patient_id),
            "target_patient_id": str(result.target_patient_id),
            "moved_entities": {
                "queue_entries": result.moved_queue_entries,
                "intake_forms": result.moved_intake_forms,
                "medical_documents": result.moved_medical_documents,
            },
            "identity_alert_closed": result.identity_alert_closed,
        }
    )


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
        try:
            limit = _parse_positive_int(request.GET.get("limit", "100"), default=100, maximum=100)
        except ValueError:
            return json_error("Invalid limit parameter.", status=400)
        return JsonResponse({"items": [_serialize_clinic_site(site) for site in qs[:limit]]})

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
        try:
            limit = _parse_positive_int(request.GET.get("limit", "100"), default=100, maximum=100)
        except ValueError:
            return json_error("Invalid limit parameter.", status=400)
        return JsonResponse({"items": [_serialize_consulting_room(room) for room in qs[:limit]]})

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
        try:
            limit = _parse_positive_int(request.GET.get("limit", "100"), default=100, maximum=100)
        except ValueError:
            return json_error("Invalid limit parameter.", status=400)
        items = [_serialize_queue(q) for q in qs[:limit]]
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
        try:
            limit = _parse_positive_int(request.GET.get("limit", "100"), default=100, maximum=100)
        except ValueError:
            return json_error("Invalid limit parameter.", status=400)
        items = [_serialize_entry(e) for e in qs[:limit]]
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
        try:
            limit = _parse_positive_int(request.GET.get("limit", "100"), default=100, maximum=100)
        except ValueError:
            return json_error("Invalid limit parameter.", status=400)
        return JsonResponse({"items": [_serialize_tablet_device(device) for device in qs[:limit]]})

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
