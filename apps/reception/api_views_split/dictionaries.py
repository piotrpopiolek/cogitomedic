from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import json_error, read_json_body, require_auth
from apps.core.exceptions import DomainError
from apps.reception.api_schemas import (
    CreateClinicSiteRequest,
    CreateConsultingRoomRequest,
    UpdateClinicSiteRequest,
    UpdateConsultingRoomRequest,
)
from apps.reception.models import ClinicSite, ConsultingRoom
from apps.reception.services import (
    create_clinic_site,
    create_consulting_room,
    deactivate_clinic_site,
    deactivate_consulting_room,
    update_clinic_site,
    update_consulting_room,
)

from .common import parse_bool_query, parse_list_limit, parse_positive_int


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


@require_auth
@csrf_exempt
def clinic_sites_view(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = ClinicSite.objects.all().order_by("code")
        is_active_raw = request.GET.get("is_active")
        if is_active_raw is not None:
            is_active = parse_bool_query(is_active_raw)
            if is_active is None:
                return json_error("Invalid is_active query parameter.", status=400)
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
        try:
            limit = parse_list_limit(request.GET.get("limit"))
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
            site = create_clinic_site(code=body.code, name=body.name, is_active=body.is_active)
        except IntegrityError:
            return json_error("Clinic site code already exists.", status=409)
        return JsonResponse(_serialize_clinic_site(site), status=201)

    return json_error("Method not allowed.", status=405)


@require_auth
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
        try:
            site = deactivate_clinic_site(clinic_site_id=clinic_site_id)
        except ObjectDoesNotExist:
            return json_error("Clinic site not found.", status=404)
        return JsonResponse(_serialize_clinic_site(site))

    try:
        body = UpdateClinicSiteRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        site = update_clinic_site(
            clinic_site_id=clinic_site_id,
            code=body.code,
            name=body.name,
            is_active=body.is_active,
        )
    except ObjectDoesNotExist:
        return json_error("Clinic site not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    except IntegrityError:
        return json_error("Clinic site code already exists.", status=409)
    return JsonResponse(_serialize_clinic_site(site))


@require_auth
@csrf_exempt
def consulting_rooms_view(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = ConsultingRoom.objects.all().order_by("clinic_site_id", "code")
        clinic_site_id = request.GET.get("clinic_site_id")
        if clinic_site_id:
            qs = qs.filter(clinic_site_id=clinic_site_id)
        is_active_raw = request.GET.get("is_active")
        if is_active_raw is not None:
            is_active = parse_bool_query(is_active_raw)
            if is_active is None:
                return json_error("Invalid is_active query parameter.", status=400)
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
        try:
            limit = parse_list_limit(request.GET.get("limit"))
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
            room = create_consulting_room(
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


@require_auth
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
        try:
            room = deactivate_consulting_room(consulting_room_id=consulting_room_id)
        except ObjectDoesNotExist:
            return json_error("Consulting room not found.", status=404)
        return JsonResponse(_serialize_consulting_room(room))

    try:
        body = UpdateConsultingRoomRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        room = update_consulting_room(
            consulting_room_id=consulting_room_id,
            clinic_site_id=body.clinic_site_id,
            code=body.code,
            name=body.name,
            is_active=body.is_active,
        )
    except ObjectDoesNotExist:
        return json_error("Clinic site or consulting room not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    except IntegrityError:
        return json_error("Consulting room code already exists for this clinic site.", status=409)
    return JsonResponse(_serialize_consulting_room(room))
