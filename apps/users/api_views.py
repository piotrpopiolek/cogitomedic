from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django_ratelimit.decorators import ratelimit
from pydantic import ValidationError

from apps.core.api_utils import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    json_domain_error,
    json_error,
    parse_bool_query,
    read_json_body,
    require_auth,
    require_authenticated_user,
    require_user_role,
    safe_parse_positive_int,
)
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding
from apps.core.http_utils import get_client_ip
from apps.operations.services import create_audit_event
from apps.reception.services import record_tablet_login_for_android_id
from apps.users.api_schemas import (
    AuthLoginRequest,
    CreateStaffUserRequest,
    UpdateStaffUserClinicSitesRequest,
    UpdateStaffUserRequest,
)
from apps.users.models import StaffUser
from apps.users.services import create_staff_user, deactivate_staff_user, update_staff_user


def get_primary_role(user) -> str | None:
    if not user.is_authenticated:
        return None
    if user.is_admin_role:
        return "ADMIN"
    elif user.is_doctor:
        return "DOCTOR"
    elif user.is_reception:
        return "RECEPTION"
    elif user.is_tablet:
        return "TABLET"
    return getattr(user, "role", None)

def _user_payload(request: HttpRequest) -> dict:
    user = request.user
    return {
        "id": str(user.id) if user.is_authenticated else None,
        "username": getattr(user, "username", None),
        "email": getattr(user, "email", None),
        "role": get_primary_role(user),
        "preferred_locale": getattr(user, "preferred_locale", None),
        "is_authenticated": bool(user.is_authenticated),
    }


def _serialize_staff_user(user: StaffUser) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone_number": user.phone_number,
        "role": get_primary_role(user),
        "preferred_locale": user.preferred_locale,
        "is_staff": user.is_staff,
        "is_active": user.is_active,
        "date_joined": user.date_joined.isoformat(),
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }


@ratelimit(key="ip", rate="5/m", method="POST", block=True)
def auth_login_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        body = AuthLoginRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    client_ip = get_client_ip(request)
    user = authenticate(request, username=body.username, password=body.password)
    if user is None:
        create_audit_event(
            event_type="STAFF_AUTH_LOGIN_FAILED",
            metadata={
                "username": body.username,
                "client_ip": client_ip,
                "reason": "invalid_credentials",
            },
        )
        return json_error("other.api.invalid_credentials", status=401)
    if not user.is_active:
        create_audit_event(
            event_type="STAFF_AUTH_LOGIN_FAILED",
            metadata={
                "username": body.username,
                "client_ip": client_ip,
                "reason": "inactive_user",
            },
        )
        return json_error("other.api.invalid_credentials", status=401)

    login(request, user)
    android_id = (body.android_id or "").strip()
    if android_id and (user.is_tablet or user.is_reception or user.is_admin_role):
        record_tablet_login_for_android_id(android_id=android_id)
    create_audit_event(
        event_type="STAFF_AUTH_LOGIN_SUCCESS",
        actor_user_id=user.id,
        metadata={"client_ip": client_ip},
    )
    return JsonResponse(
        {
            "user": _user_payload(request),
            "session_expires_in_seconds": request.session.get_expiry_age(),
        },
        status=200,
    )


def auth_logout_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)

    if request.user.is_authenticated:
        uid = request.user.id
        create_audit_event(
            event_type="STAFF_AUTH_LOGOUT",
            actor_user_id=uid,
            metadata={"client_ip": get_client_ip(request)},
        )
    logout(request)
    return JsonResponse({"ok": True}, status=200)


@require_auth
def auth_me_view(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    return JsonResponse({"user": _user_payload(request)}, status=200)


@require_auth
def staff_users_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"ADMIN"})
    if role_error:
        return role_error

    if request.method == "GET":
        qs = StaffUser.objects.all().order_by("username")
        role = request.GET.get("role")
        if role:
            valid_roles = {"RECEPTION", "DOCTOR", "ADMIN", "TABLET"}
            if role not in valid_roles:
                return json_error("other.api.invalid_role_query", status=400)
            group_name = role.capitalize()
            qs = qs.filter(groups__name=group_name).distinct()
        is_active = parse_bool_query(request.GET.get("is_active"))
        if request.GET.get("is_active") is not None and is_active is None:
            return json_error("other.api.invalid_is_active", status=400)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        search = request.GET.get("search")
        if search:
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))
        page = safe_parse_positive_int(request.GET.get("page"), default=1, maximum=10_000)
        page_size = safe_parse_positive_int(
            request.GET.get("page_size"),
            default=DEFAULT_LIST_LIMIT,
            maximum=MAX_LIST_LIMIT,
        )
        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        items = [_serialize_staff_user(user) for user in qs[start:end]]
        return JsonResponse({"items": items, "pagination": {"page": page, "page_size": page_size, "total": total}})

    if request.method == "POST":
        try:
            body = CreateStaffUserRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("other.api.invalid_json_payload", status=400)
        except InvalidRequestBodyEncoding as exc:
            return json_domain_error(exc)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            user = create_staff_user(
                username=body.username,
                email=body.email,
                first_name=body.first_name,
                last_name=body.last_name,
                phone_number=body.phone_number,
                role=body.role,
                preferred_locale=body.preferred_locale,
                is_staff=body.is_staff,
                is_active=body.is_active,
                password=body.password,
            )
        except IntegrityError:
            return json_error("other.api.username_or_email_exists", status=409)
        except DomainError as exc:
            return json_domain_error(exc, status=400)
        return JsonResponse(_serialize_staff_user(user), status=201)

    return json_error("other.api.method_not_allowed", status=405)


@require_auth
def staff_user_detail_view(request: HttpRequest, staff_user_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"ADMIN"})
    if role_error:
        return role_error

    if request.method not in ("GET", "PATCH", "DELETE"):
        return json_error("other.api.method_not_allowed", status=405)
    try:
        user = StaffUser.objects.get(id=staff_user_id)
    except ObjectDoesNotExist:
        return json_error("other.api.staff_user_not_found", status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_staff_user(user))
    if request.method == "DELETE":
        try:
            user = deactivate_staff_user(staff_user_id=staff_user_id)
        except ObjectDoesNotExist:
            return json_error("other.api.staff_user_not_found", status=404)
        return JsonResponse({"message": "User deactivated", "user": _serialize_staff_user(user)}, status=200)

    try:
        body = UpdateStaffUserRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        user = update_staff_user(
            staff_user_id=staff_user_id,
            email=body.email,
            first_name=body.first_name,
            last_name=body.last_name,
            phone_number=body.phone_number,
            role=body.role,
            preferred_locale=body.preferred_locale,
            is_staff=body.is_staff,
            is_active=body.is_active,
            password=body.password,
        )
    except ObjectDoesNotExist:
        return json_error("other.api.staff_user_not_found", status=404)
    except IntegrityError:
        return json_error("other.api.username_or_email_exists", status=409)
    except DomainError as exc:
        return json_domain_error(exc, status=400)
    return JsonResponse(_serialize_staff_user(user), status=200)


@require_auth
def staff_user_clinic_sites_view(request: HttpRequest, staff_user_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"ADMIN"})
    if role_error:
        return role_error
    try:
        user = StaffUser.objects.prefetch_related("clinic_sites").get(id=staff_user_id)
    except ObjectDoesNotExist:
        return json_error("other.api.staff_user_not_found", status=404)

    if request.method == "GET":
        items = [
            {
                "id": str(site.id),
                "code": site.code,
                "name": site.name,
                "is_active": site.is_active,
            }
            for site in user.clinic_sites.all()
        ]
        return JsonResponse({"items": items}, status=200)

    if request.method == "POST":
        try:
            body = UpdateStaffUserClinicSitesRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("other.api.invalid_json_payload", status=400)
        except InvalidRequestBodyEncoding as exc:
            return json_domain_error(exc)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

        user.clinic_sites.set(body.clinic_site_ids)
        items = [
            {
                "id": str(site.id),
                "code": site.code,
                "name": site.name,
                "is_active": site.is_active,
            }
            for site in user.clinic_sites.all()
        ]
        return JsonResponse({"items": items}, status=200)

    return json_error("other.api.method_not_allowed", status=405)
