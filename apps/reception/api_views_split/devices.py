from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import (
    json_error,
    parse_bool_query,
    parse_list_limit,
    read_json_body,
    require_auth,
    require_user_role,
)
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding
from apps.reception.api_schemas import CreateTabletDeviceRequest, UpdateTabletDeviceRequest
from apps.reception.models import TabletDevice
from apps.reception.services import (
    create_tablet_device,
    deactivate_tablet_device,
    mark_tablet_heartbeat,
    update_tablet_device,
)



def _serialize_tablet_device(device: TabletDevice) -> dict:
    return {
        "id": str(device.id),
        "android_id": device.android_id,
        "is_active": device.is_active,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "created_at": device.created_at.isoformat(),
    }


@require_auth
@csrf_exempt
def tablet_devices_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method == "GET":
        qs = TabletDevice.objects.all().order_by("android_id")
        is_active = parse_bool_query(request.GET.get("is_active"))
        if request.GET.get("is_active") is not None and is_active is None:
            return json_error("Invalid is_active query parameter.", status=400)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(android_id__icontains=search)
        limit = parse_list_limit(request.GET.get("limit"))
        return JsonResponse({"items": [_serialize_tablet_device(device) for device in qs[:limit]]})

    if request.method == "POST":
        try:
            body = CreateTabletDeviceRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except InvalidRequestBodyEncoding:
            return json_error("Invalid request encoding.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            device = create_tablet_device(android_id=body.android_id, is_active=body.is_active)
        except IntegrityError:
            return json_error("Tablet device with this android_id already exists.", status=409)
        return JsonResponse(_serialize_tablet_device(device), status=201)

    return json_error("Method not allowed.", status=405)


@require_auth
@csrf_exempt
def tablet_device_detail_view(request: HttpRequest, tablet_device_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("Method not allowed.", status=405)
    try:
        device = TabletDevice.objects.get(id=tablet_device_id)
    except ObjectDoesNotExist:
        return json_error("Tablet device not found.", status=404)
    if request.method == "GET":
        return JsonResponse(_serialize_tablet_device(device))
    if request.method == "DELETE":
        try:
            device = deactivate_tablet_device(tablet_device_id=tablet_device_id)
        except ObjectDoesNotExist:
            return json_error("Tablet device not found.", status=404)
        return JsonResponse(_serialize_tablet_device(device))

    try:
        body = UpdateTabletDeviceRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        device = update_tablet_device(
            tablet_device_id=tablet_device_id,
            android_id=body.android_id,
            is_active=body.is_active,
        )
    except ObjectDoesNotExist:
        return json_error("Tablet device not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    except IntegrityError:
        return json_error("Tablet device with this android_id already exists.", status=409)
    return JsonResponse(_serialize_tablet_device(device))


@require_auth
@csrf_exempt
def tablet_device_heartbeat_view(request: HttpRequest, tablet_device_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        device = mark_tablet_heartbeat(tablet_device_id=tablet_device_id)
    except ObjectDoesNotExist:
        return json_error("Tablet device not found.", status=404)
    return JsonResponse({"last_seen_at": device.last_seen_at.isoformat()})
