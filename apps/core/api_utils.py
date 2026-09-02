from __future__ import annotations

import json
from functools import wraps
from typing import Any, Mapping, TypeVar
from uuid import UUID

from django.contrib.auth.models import Group
from django.http import HttpRequest, QueryDict
from django.http import JsonResponse
from pydantic import BaseModel, ValidationError

from apps.core.api_error_i18n import OTHER_I18N_KEY_DEFAULT_EN
from apps.core.constants import (
    MAX_JSON_BODY_BYTES,
)
from apps.core.list_pagination import validate_allowed_page_size
from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding
from apps.core.translation_service import (
    get_current_request,
    get_translation_map,
    resolve_other_message,
    translation_category_for_message_key,
)


def assign_group_to_test_user(user, group_name: str) -> None:
    """Helper for testing to replace `user = StaffUser.objects.create(..., role=StaffRole.XXX)`."""
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)


def json_error(message: str, *, status: int) -> JsonResponse:
    """Build a normalized JSON error payload; keyed ``other.*`` / ``doctor.*`` strings resolve from DB."""
    if message.startswith(("other.api.", "other.domain.", "doctor.")):
        default = OTHER_I18N_KEY_DEFAULT_EN.get(message, message)
        request = get_current_request()
        if request is not None:
            message = resolve_other_message(request, message, default)
        else:
            cat = translation_category_for_message_key(message)
            message = get_translation_map(cat, "en-GB").get(message, default)
    return JsonResponse({"error": message}, status=status)


def json_domain_error(exc: BaseException, *, status: int | None = None) -> JsonResponse:
    """Resolve error text from DB when ``api_message_key`` is set (``DomainError``, ``InvalidRequestBodyEncoding``)."""
    key: str | None = None
    params: dict[str, object] = {}
    effective_status: int
    if isinstance(exc, InvalidRequestBodyEncoding) and exc.api_message_key:
        key = exc.api_message_key
        params = exc.api_message_params or {}
        effective_status = exc.http_status
    elif isinstance(exc, DomainError) and exc.api_message_key:
        key = exc.api_message_key
        params = exc.api_message_params or {}
        effective_status = 400 if status is None else status
    else:
        effective_status = 400 if status is None else status
        return json_error(str(exc), status=effective_status)

    default = OTHER_I18N_KEY_DEFAULT_EN.get(key, str(exc))
    request = get_current_request()
    message = resolve_other_message(request, key, default, **params)
    return JsonResponse(
        {"error": message, "error_key": key},
        status=effective_status,
    )


def json_pydantic_validation_error(
    exc: ValidationError,
    *,
    error_key: str = "other.api.invalid_request_body",
) -> JsonResponse:
    """HTTP 400 for Pydantic request-body validation; same shape family as ``json_domain_error``."""
    default = OTHER_I18N_KEY_DEFAULT_EN.get(error_key, "Invalid request body.")
    request = get_current_request()
    if request is not None:
        message = resolve_other_message(request, error_key, default)
    else:
        # No HTTP request (e.g. tasks); avoid DB lookup via ``get_translation_map``.
        message = default
    return JsonResponse(
        {
            "error": message,
            "error_key": error_key,
            "details": exc.errors(include_url=False, include_context=False),
        },
        status=400,
    )


def json_pydantic_query_validation_error(exc: ValidationError) -> JsonResponse:
    """HTTP 400 for GET query validation; preserves legacy keys where applicable."""
    for err in exc.errors(include_url=False):
        loc = err.get("loc") or ()
        if loc == ("retry_count_gte",):
            return json_error("other.api.retry_count_gte_integer", status=400)
        if loc == ("role",):
            return json_error("other.api.invalid_role_query", status=400)
        if loc == ("is_active",):
            return json_error("other.api.invalid_is_active", status=400)
        if loc == ("page_size",):
            return json_error("other.api.invalid_page_size", status=400)
        if loc == ("limit",):
            return json_error("other.api.invalid_limit", status=400)
    return json_pydantic_validation_error(
        exc, error_key="other.api.invalid_request_body"
    )


def read_json_body(request: HttpRequest) -> dict:
    """Decode JSON body for API views. Raises JSONDecodeError or InvalidRequestBodyEncoding on invalid input."""
    if len(request.body) > MAX_JSON_BODY_BYTES:
        raise InvalidRequestBodyEncoding(
            domain_message(
                "other.api.request_body_too_large", max_bytes=MAX_JSON_BODY_BYTES
            ),
            api_message_key="other.api.request_body_too_large",
            api_message_params={"max_bytes": MAX_JSON_BODY_BYTES},
            http_status=413,
        )
    try:
        raw = request.body.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidRequestBodyEncoding(
            domain_message("other.api.invalid_request_encoding"),
            api_message_key="other.api.invalid_request_encoding",
        )
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


def parse_positive_int(
    value: str, *, default: int, minimum: int = 1, maximum: int = 100
) -> int:
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
    """Parse ``limit`` for API lists; same allowed sizes as ``page_size`` (strict)."""
    return validate_allowed_page_size(value)


def resolve_list_limit_query(value: str | None) -> int | JsonResponse:
    """Parse ``limit`` or return HTTP 400 ``JsonResponse`` for invalid explicit values."""
    try:
        return parse_list_limit(value)
    except ValueError:
        return json_error("other.api.invalid_limit", status=400)


QueryParamsModelT = TypeVar("QueryParamsModelT", bound=BaseModel)


def validate_get_query_params(
    model: type[QueryParamsModelT],
    query: QueryDict | Mapping[str, Any],
) -> QueryParamsModelT:
    """Build a Pydantic query model from GET parameters (field names and aliases)."""
    payload: dict[str, Any] = {}
    for name, field_info in model.model_fields.items():
        lookup_keys = [name]
        if field_info.alias and field_info.alias not in lookup_keys:
            lookup_keys.insert(0, field_info.alias)
        value = None
        for key in lookup_keys:
            if hasattr(query, "get"):
                candidate = query.get(key)
            else:
                candidate = query.get(key) if key in query else None
            if candidate is not None:
                value = candidate
                break
        payload[field_info.alias or name] = value
    return model.model_validate(payload)


def require_authenticated_user(request: HttpRequest) -> JsonResponse | None:
    """Return normalized 401 error response when user is not authenticated."""
    if not request.user.is_authenticated:
        return json_error("other.api.authentication_required", status=401)
    return None


def require_user_role(
    request: HttpRequest, *, allowed_roles: set[str]
) -> JsonResponse | None:
    """
    Return 401 when not authenticated (same semantics as require_auth).
    Return 403 when authenticated but role is not in allowed_roles.

    Użytkownik ma dostęp, jeśli spełnia **którąkolwiek** z ról w ``allowed_roles``
    (semantyka OR; niezależna od kolejności w zbiorze).
    """
    user = request.user
    if not user.is_authenticated:
        return json_error("other.api.authentication_required", status=401)

    def _matches_allowed_role(role: str) -> bool:
        if role == "DOCTOR":
            return bool(user.is_doctor)
        if role == "ADMIN":
            return bool(user.is_admin_role)
        if role == "MANAGER":
            return bool(getattr(user, "is_manager", False))
        if role == "RECEPTION":
            return bool(user.is_reception)
        if role == "TABLET":
            return bool(user.is_tablet)
        return False

    if not any(_matches_allowed_role(role) for role in allowed_roles):
        return json_error("other.api.forbidden", status=403)
    return None


def get_scoped_clinic_site_ids(user) -> list[UUID] | None:
    """
    Return clinic_site IDs for object-level scope, or None for no filter (ADMIN, ACCOUNTING).
    MANAGER, RECEPTION, DOCTOR and TABLET see only data for their assigned
    clinic_sites (staff_user_clinic_site).
    Returns empty list if user has no clinic_sites assigned (they see nothing).
    """
    if getattr(user, "is_admin_role", False) and user.is_admin_role:
        return None
    if getattr(user, "is_accounting", False) and user.is_accounting:
        return None
    if getattr(user, "is_manager", False) and user.is_manager:
        ids = list(user.clinic_sites.values_list("id", flat=True))
        return ids
    if getattr(user, "is_reception", False) and user.is_reception:
        ids = list(user.clinic_sites.values_list("id", flat=True))
        return ids
    if getattr(user, "is_doctor", False) and user.is_doctor:
        ids = list(user.clinic_sites.values_list("id", flat=True))
        return ids
    if getattr(user, "is_tablet", False) and user.is_tablet:
        ids = list(user.clinic_sites.values_list("id", flat=True))
        return ids
    return []


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
        device = TabletDevice.objects.only("clinic_site_id").get(
            id=device_id, is_active=True
        )
    except TabletDevice.DoesNotExist:
        return None
    if device.clinic_site_id is None:
        return []
    return [device.clinic_site_id]


def require_actor_match(
    request: HttpRequest, actor_id: UUID | None
) -> JsonResponse | None:
    """Return 403 when actor_id is not None and does not match request.user.id. Use for body/query actor fields."""
    if actor_id is not None and actor_id != request.user.id:
        return json_error("other.api.actor_mismatch", status=403)
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
