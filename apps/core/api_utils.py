from __future__ import annotations

import json
from functools import wraps
from uuid import UUID

from django.contrib.auth.models import Group
from django.http import HttpRequest
from django.http import JsonResponse

from apps.core.exceptions import InvalidRequestBodyEncoding

# Default/max for offset pagination (`page` / `page_size`) and for reception list `limit` (`parse_list_limit`).
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100

def assign_group_to_test_user(user, group_name: str) -> None:
    """Helper for testing to replace `user = StaffUser.objects.create(..., role=StaffRole.XXX)`."""
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)

def json_error(message: str, *, status: int) -> JsonResponse:
    """Build a normalized JSON error response payload."""
    return JsonResponse({"error": message}, status=status)


def read_json_body(request: HttpRequest) -> dict:
    """Decode JSON body for API views. Raises JSONDecodeError or InvalidRequestBodyEncoding on invalid input."""
    try:
        raw = request.body.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidRequestBodyEncoding("Request body is not valid UTF-8.")
    return json.loads(raw or "{}")


def parse_bool_query(value: str | None) -> bool | None:
    """Parse query param to bool. Returns None if value is None or not a recognized boolean string."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def parse_positive_int(value: str, *, default: int, minimum: int = 1, maximum: int = 100) -> int:
    """Parse positive int; raises ValueError on invalid input. Prefer safe_parse_positive_int in views."""
    if not value:
        return default
    parsed = int(value)
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def safe_parse_positive_int(
    value: str | None,
    *,
    default: int,
    minimum: int = 1,
    maximum: int = 100,
) -> int:
    """Parse positive int for query params. Never raises; returns default on empty or invalid value."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        parsed = int(value.strip())
    except ValueError:
        return default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def parse_list_limit(value: str | None) -> int:
    """Parse `limit` query param for reception-style list endpoints. Same default/max as page_size (20/100). Never raises."""
    return safe_parse_positive_int(
        value,
        default=DEFAULT_LIST_LIMIT,
        maximum=MAX_LIST_LIMIT,
    )


def require_authenticated_user(request: HttpRequest) -> JsonResponse | None:
    """Return normalized 401 error response when user is not authenticated."""
    if not request.user.is_authenticated:
        return json_error("Authentication required.", status=401)
    return None


def require_user_role(request: HttpRequest, *, allowed_roles: set[str]) -> JsonResponse | None:
    """
    Return 401 when not authenticated (same semantics as require_auth).
    Return 403 when authenticated but role is not in allowed_roles.
    """
    user = request.user
    if not user.is_authenticated:
        return json_error("Authentication required.", status=401)

    has_role = False
    if "DOCTOR" in allowed_roles and user.is_doctor:
        has_role = True
    elif "ADMIN" in allowed_roles and user.is_admin_role:
        has_role = True
    elif "RECEPTION" in allowed_roles and user.is_reception:
        has_role = True
    elif "TABLET" in allowed_roles and user.is_tablet:
        has_role = True

    if not has_role:
        return json_error("Forbidden.", status=403)
    return None


def get_scoped_clinic_site_ids(user) -> list[UUID] | None:
    """
    Return clinic_site IDs for object-level scope, or None for no filter (ADMIN).
    RECEPTION, DOCTOR and TABLET see only data for their assigned clinic_sites (staff_user_clinic_site).
    Returns empty list if user has no clinic_sites assigned (they see nothing).
    """
    if getattr(user, "is_admin_role", False) and user.is_admin_role:
        return None
    if getattr(user, "is_reception", False) and user.is_reception:
        ids = list(user.clinic_sites.values_list("id", flat=True))
        return ids
    if getattr(user, "is_doctor", False) and user.is_doctor:
        ids = list(user.clinic_sites.values_list("id", flat=True))
        return ids
    if getattr(user, "is_tablet", False) and user.is_tablet:
        ids = list(user.clinic_sites.values_list("id", flat=True))
        return ids
    return None


def get_tablet_scope_clinic_site_ids(request: HttpRequest) -> list[UUID] | None:
    """
    When the request has a tablet device in session, return scope from that device.
    Returns [device.clinic_site_id] when device has a site; [] when device has no site (tablet sees nothing);
    None when no device in session (caller should use get_scoped_clinic_site_ids(request.user)).
    """
    from apps.reception.models import TabletDevice

    device_id_str = request.session.get("tablet_device_id")
    if not device_id_str:
        return None
    try:
        device_id = UUID(device_id_str)
    except (ValueError, TypeError):
        return None
    try:
        device = TabletDevice.objects.only("clinic_site_id").get(id=device_id, is_active=True)
    except TabletDevice.DoesNotExist:
        return None
    if device.clinic_site_id is None:
        return []
    return [device.clinic_site_id]


def require_actor_match(request: HttpRequest, actor_id: UUID | None) -> JsonResponse | None:
    """Return 403 when actor_id is not None and does not match request.user.id. Use for body/query actor fields."""
    if actor_id is not None and actor_id != request.user.id:
        return json_error("Actor mismatch.", status=403)
    return None


def require_auth(view_func):
    """Decorator: return 401 JSON when request.user is not authenticated. Use on API views that require login."""

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        err = require_authenticated_user(request)
        if err is not None:
            return err
        return view_func(request, *args, **kwargs)

    return wrapper
