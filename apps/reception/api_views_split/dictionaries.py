from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Q
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
    CreateClinicSiteRequest,
    CreateConsultingRoomRequest,
    UpdateClinicSiteRequest,
    UpdateConsultingRoomRequest,
)
from apps.reception.models import ClinicSite, ConsultingRoom
from apps.reception.services import (
    CLINIC_SITE_FIELD_NOT_PROVIDED,
    create_clinic_site,
    create_consulting_room,
    deactivate_clinic_site,
    deactivate_consulting_room,
    update_clinic_site,
    update_consulting_room,
)



def _serialize_clinic_site(site: ClinicSite) -> dict:
    return {
        "id": str(site.id),
        "code": site.code,
        "name": site.name,
        "pdf_import_default_consulting_room_id": (
            str(site.pdf_import_default_consulting_room_id)
            if site.pdf_import_default_consulting_room_id
            else None
        ),
        "pdf_import_shift_code": site.pdf_import_shift_code,
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
def clinic_sites_view(request: HttpRequest) -> JsonResponse:
    allowed = {"RECEPTION", "ADMIN", "DOCTOR"} if request.method == "GET" else {"ADMIN"}
    role_error = require_user_role(request, allowed_roles=allowed)
    if role_error:
        return role_error
    if request.method == "GET":
        qs = ClinicSite.objects.all().order_by("code")
        scope_ids = get_scoped_clinic_site_ids(request.user)
        if scope_ids is not None:
            if not scope_ids:
                return JsonResponse({"items": []})
            qs = qs.filter(id__in=scope_ids)
        is_active = parse_bool_query(request.GET.get("is_active"))
        if request.GET.get("is_active") is not None and is_active is None:
            return json_error("other.api.invalid_is_active", status=400)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
        limit = parse_list_limit(request.GET.get("limit"))
        return JsonResponse({"items": [_serialize_clinic_site(site) for site in qs[:limit]]})

    if request.method == "POST":
        if not request.user.is_admin_role:
            return json_error("other.api.only_admin_create_clinic_site", status=403)
        try:
            body = CreateClinicSiteRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("other.api.invalid_json_payload", status=400)
        except InvalidRequestBodyEncoding as exc:
            return json_domain_error(exc)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            site = create_clinic_site(
                code=body.code,
                name=body.name,
                is_active=body.is_active,
                pdf_import_default_consulting_room_id=body.pdf_import_default_consulting_room_id,
                pdf_import_shift_code=body.pdf_import_shift_code,
            )
        except IntegrityError:
            return json_error("other.api.clinic_site_code_already_exists", status=409)
        except DomainError as exc:
            return json_domain_error(exc, status=400)
        return JsonResponse(_serialize_clinic_site(site), status=201)

    return json_error("other.api.method_not_allowed", status=405)


@require_auth
def clinic_site_detail_view(request: HttpRequest, clinic_site_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "DOCTOR"})
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("other.api.method_not_allowed", status=405)
    try:
        site = ClinicSite.objects.get(id=clinic_site_id)
    except ObjectDoesNotExist:
        return json_error("other.api.clinic_site_not_found", status=404)

    scope_ids = get_scoped_clinic_site_ids(request.user)
    if scope_ids is not None and site.id not in scope_ids:
        return json_error("other.api.clinic_site_not_in_scope", status=403)
    if request.method == "GET":
        return JsonResponse(_serialize_clinic_site(site))
    if request.method in ("PATCH", "DELETE") and not request.user.is_admin_role:
        return json_error("other.api.only_admin_update_clinic_site", status=403)
    if request.method == "DELETE":
        try:
            site = deactivate_clinic_site(clinic_site_id=clinic_site_id)
        except ObjectDoesNotExist:
            return json_error("other.api.clinic_site_not_found", status=404)
        return JsonResponse(_serialize_clinic_site(site))

    try:
        body = UpdateClinicSiteRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    fields_set = body.model_fields_set
    try:
        site = update_clinic_site(
            clinic_site_id=clinic_site_id,
            code=body.code,
            name=body.name,
            is_active=body.is_active,
            pdf_import_default_consulting_room_id=(
                body.pdf_import_default_consulting_room_id
                if "pdf_import_default_consulting_room_id" in fields_set
                else CLINIC_SITE_FIELD_NOT_PROVIDED
            ),
            pdf_import_shift_code=(
                body.pdf_import_shift_code
                if "pdf_import_shift_code" in fields_set
                else CLINIC_SITE_FIELD_NOT_PROVIDED
            ),
        )
    except ObjectDoesNotExist:
        return json_error("other.api.clinic_site_not_found", status=404)
    except DomainError as exc:
        return json_domain_error(exc, status=400)
    except IntegrityError:
        return json_error("other.api.clinic_site_code_already_exists", status=409)
    return JsonResponse(_serialize_clinic_site(site))


@require_auth
def consulting_rooms_view(request: HttpRequest) -> JsonResponse:
    allowed = {"RECEPTION", "ADMIN", "DOCTOR"} if request.method == "GET" else {"ADMIN"}
    role_error = require_user_role(request, allowed_roles=allowed)
    if role_error:
        return role_error
    if request.method == "GET":
        qs = ConsultingRoom.objects.all().order_by("clinic_site_id", "code")
        scope_ids = get_scoped_clinic_site_ids(request.user)
        if scope_ids is not None:
            if not scope_ids:
                return JsonResponse({"items": []})
            qs = qs.filter(clinic_site_id__in=scope_ids)
        clinic_site_id = request.GET.get("clinic_site_id")
        if clinic_site_id:
            qs = qs.filter(clinic_site_id=clinic_site_id)
        is_active = parse_bool_query(request.GET.get("is_active"))
        if request.GET.get("is_active") is not None and is_active is None:
            return json_error("other.api.invalid_is_active", status=400)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
        limit = parse_list_limit(request.GET.get("limit"))
        return JsonResponse({"items": [_serialize_consulting_room(room) for room in qs[:limit]]})

    if request.method == "POST":
        if not request.user.is_admin_role:
            return json_error("other.api.only_admin_create_consulting_room", status=403)
        try:
            body = CreateConsultingRoomRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("other.api.invalid_json_payload", status=400)
        except InvalidRequestBodyEncoding as exc:
            return json_domain_error(exc)
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
            return json_error("other.api.clinic_site_not_found", status=404)
        except IntegrityError:
            return json_error("other.api.consulting_room_code_exists", status=409)
        return JsonResponse(_serialize_consulting_room(room), status=201)

    return json_error("other.api.method_not_allowed", status=405)


@require_auth
def consulting_room_detail_view(request: HttpRequest, consulting_room_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "DOCTOR"})
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("other.api.method_not_allowed", status=405)
    try:
        room = ConsultingRoom.objects.get(id=consulting_room_id)
    except ObjectDoesNotExist:
        return json_error("other.api.consulting_room_not_found", status=404)
    scope_ids = get_scoped_clinic_site_ids(request.user)
    if scope_ids is not None and room.clinic_site_id not in scope_ids:
        return json_error("other.api.consulting_room_not_in_scope", status=403)
    if request.method == "GET":
        return JsonResponse(_serialize_consulting_room(room))
    if request.method in ("PATCH", "DELETE") and not request.user.is_admin_role:
        return json_error("other.api.only_admin_update_consulting_room", status=403)
    if request.method == "DELETE":
        try:
            room = deactivate_consulting_room(consulting_room_id=consulting_room_id)
        except ObjectDoesNotExist:
            return json_error("other.api.consulting_room_not_found", status=404)
        return JsonResponse(_serialize_consulting_room(room))

    try:
        body = UpdateConsultingRoomRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
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
        return json_error("other.api.clinic_site_or_consulting_room_not_found", status=404)
    except DomainError as exc:
        return json_domain_error(exc, status=400)
    except IntegrityError:
        return json_error("other.api.consulting_room_code_exists", status=409)
    return JsonResponse(_serialize_consulting_room(room))
