"""Shared list pagination: page_size / limit parsing and UI query helpers."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlencode

from django.conf import settings
from django.http import QueryDict

from apps.core.constants import ALLOWED_LIST_PAGE_SIZES, DEFAULT_LIST_LIMIT


def effective_default_page_size() -> int:
    """Default page size (50), overridable via ``settings.LIST_PAGE_SIZE_DEFAULT`` if allowed."""
    configured = getattr(settings, "LIST_PAGE_SIZE_DEFAULT", None)
    if configured is not None:
        try:
            value = int(configured)
        except (TypeError, ValueError):
            return DEFAULT_LIST_LIMIT
        if value in ALLOWED_LIST_PAGE_SIZES:
            return value
    return DEFAULT_LIST_LIMIT


def validate_allowed_page_size(value: object) -> int:
    """API strict parse: missing/empty → default; explicit invalid → ``ValueError``."""
    default = effective_default_page_size()
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    if isinstance(value, bool):
        raise ValueError("Invalid list page size.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise ValueError("Invalid list page size.") from exc
    else:
        raise ValueError("Invalid list page size.")
    if parsed not in ALLOWED_LIST_PAGE_SIZES:
        allowed = ", ".join(str(size) for size in ALLOWED_LIST_PAGE_SIZES)
        raise ValueError(f"List page size must be one of: {allowed}.")
    return parsed


def parse_page_size(value: str | int | None) -> int:
    """Lenient parse for HTML admin/doctor UI; invalid → default."""
    default = effective_default_page_size()
    if value is None:
        return default
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        if not value.strip():
            return default
        try:
            parsed = int(value.strip())
        except ValueError:
            return default
    else:
        return default
    if parsed in ALLOWED_LIST_PAGE_SIZES:
        return parsed
    return default


def coerce_page_number(value: object, *, maximum: int = 10_000) -> int:
    """Normalize ``page`` query param (invalid → 1, clamped to ``maximum``)."""
    default = 1
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return default
    else:
        return default
    if parsed < 1:
        return 1
    if parsed > maximum:
        return maximum
    return parsed


def coerce_allowed_page_size(value: object) -> int:
    """Normalize ``page_size`` / ``limit`` for Pydantic (strict; raises on invalid input)."""
    return validate_allowed_page_size(value)


def _copy_query_mapping(query: QueryDict | Mapping[str, Any]) -> dict[str, str]:
    if isinstance(query, QueryDict):
        return {key: query.get(key, "") for key in query.keys()}
    return {str(key): str(val) for key, val in query.items() if val is not None}


def build_page_size_query(
    query: QueryDict | Mapping[str, Any],
    *,
    page_size: int,
    param_name: str = "page_size",
    reset_page: bool = True,
) -> str:
    """Build query string with given page size; optionally reset ``page`` to 1."""
    q = _copy_query_mapping(query)
    if reset_page:
        q.pop("page", None)
        q.pop("p", None)
    default = effective_default_page_size()
    if page_size == default:
        q.pop(param_name, None)
    else:
        q[param_name] = str(page_size)
    encoded = urlencode(q)
    return f"?{encoded}" if encoded else ""


def page_size_switch_items(
    query: QueryDict | Mapping[str, Any],
    *,
    current_page_size: int,
    param_name: str = "page_size",
) -> list[dict[str, Any]]:
    """Options for page-size selector (links preserve filters; page → 1)."""
    return [
        {
            "size": size,
            "url": build_page_size_query(
                query, page_size=size, param_name=param_name, reset_page=True
            ),
            "active": size == current_page_size,
        }
        for size in ALLOWED_LIST_PAGE_SIZES
    ]
