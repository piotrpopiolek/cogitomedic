from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse
from pydantic import ValidationError

from apps.core.api_utils import (
    get_scoped_clinic_site_ids,
    json_domain_error,
    json_error,
    parse_bool_query,
    parse_list_limit,
    read_json_body,
    require_auth,
    require_user_role,
)
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding
from apps.reception.api_schemas import (
    CreateTabletDeviceRequest,
    UpdateTabletDeviceRequest,
)
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
        "last_seen_at": (
            device.last_seen_at.isoformat() if device.last_seen_at else None
        ),
        "created_at": device.created_at.isoformat(),
        "clinic_site_id": str(device.clinic_site_id) if device.clinic_site_id else None,
    }


def _is_device_in_scope(
    *, device: TabletDevice, scoped_clinic_site_ids: list[UUID] | None
) -> bool:
    if scoped_clinic_site_ids is None:
        return True
    return bool(
        device.clinic_site_id and device.clinic_site_id in scoped_clinic_site_ids
    )


@require_auth
def tablet_devices_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method == "GET":
        qs = TabletDevice.objects.all().order_by("android_id")
        scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
        if scoped_clinic_site_ids is not None:
            qs = qs.filter(clinic_site_id__in=scoped_clinic_site_ids)
        is_active = parse_bool_query(request.GET.get("is_active"))
        if request.GET.get("is_active") is not None and is_active is None:
            return json_error("other.api.invalid_is_active", status=400)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(android_id__icontains=search)
        limit = parse_list_limit(request.GET.get("limit"))
        return JsonResponse(
            {"items": [_serialize_tablet_device(device) for device in qs[:limit]]}
        )

    if request.method == "POST":
        try:
            body = CreateTabletDeviceRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("other.api.invalid_json_payload", status=400)
        except InvalidRequestBodyEncoding as exc:
            return json_domain_error(exc)
        except ValidationError as exc:
            return JsonResponse(
                {"error": "Validation error.", "details": exc.errors()}, status=400
            )
        scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
        if (
            scoped_clinic_site_ids is not None
            and body.clinic_site_id is not None
            and body.clinic_site_id not in scoped_clinic_site_ids
        ):
            return json_error("other.api.clinic_site_not_found", status=404)
        try:
            device = create_tablet_device(
                android_id=body.android_id,
                is_active=body.is_active,
                clinic_site_id=body.clinic_site_id,
            )
        except IntegrityError:
            return json_error("other.api.tablet_android_id_exists", status=409)
        return JsonResponse(_serialize_tablet_device(device), status=201)

    return json_error("other.api.method_not_allowed", status=405)


@require_auth
def tablet_device_detail_view(
    request: HttpRequest, tablet_device_id: UUID
) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("other.api.method_not_allowed", status=405)
    try:
        device = TabletDevice.objects.get(id=tablet_device_id)
    except ObjectDoesNotExist:
        return json_error("other.api.tablet_device_not_found", status=404)
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    if not _is_device_in_scope(
        device=device, scoped_clinic_site_ids=scoped_clinic_site_ids
    ):
        return json_error("other.api.tablet_device_not_found", status=404)
    if request.method == "GET":
        return JsonResponse(_serialize_tablet_device(device))
    if request.method == "DELETE":
        try:
            device = deactivate_tablet_device(tablet_device_id=tablet_device_id)
        except ObjectDoesNotExist:
            return json_error("other.api.tablet_device_not_found", status=404)
        return JsonResponse(_serialize_tablet_device(device))

    try:
        body = UpdateTabletDeviceRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return JsonResponse(
            {"error": "Validation error.", "details": exc.errors()}, status=400
        )
    update_kwargs = {
        "tablet_device_id": tablet_device_id,
        "android_id": body.android_id,
        "is_active": body.is_active,
    }
    if "clinic_site_id" in body.model_fields_set:
        if (
            scoped_clinic_site_ids is not None
            and body.clinic_site_id is not None
            and body.clinic_site_id not in scoped_clinic_site_ids
        ):
            return json_error("other.api.clinic_site_not_found", status=404)
        update_kwargs["clinic_site_id"] = body.clinic_site_id
    try:
        device = update_tablet_device(**update_kwargs)
    except ObjectDoesNotExist:
        return json_error("other.api.tablet_device_not_found", status=404)
    except DomainError as exc:
        return json_domain_error(exc, status=400)
    except IntegrityError:
        return json_error("other.api.tablet_android_id_exists", status=409)
    return JsonResponse(_serialize_tablet_device(device))


@require_auth
def tablet_device_heartbeat_view(
    request: HttpRequest, tablet_device_id: UUID
) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        device = TabletDevice.objects.get(id=tablet_device_id)
    except ObjectDoesNotExist:
        return json_error("other.api.tablet_device_not_found", status=404)
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    if not _is_device_in_scope(
        device=device, scoped_clinic_site_ids=scoped_clinic_site_ids
    ):
        return json_error("other.api.tablet_device_not_found", status=404)
    device = mark_tablet_heartbeat(tablet_device_id=tablet_device_id)
    return JsonResponse({"last_seen_at": device.last_seen_at.isoformat()})
