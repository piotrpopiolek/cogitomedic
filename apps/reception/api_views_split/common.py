from __future__ import annotations

# List endpoints: default and max items per page (used by GET list views).
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100


def parse_bool_query(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def parse_positive_int(value: str, *, default: int, minimum: int = 1, maximum: int = 100) -> int:
    if not value:
        return default
    parsed = int(value)
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def parse_list_limit(value: str | None) -> int:
    """Parse limit query param for list endpoints. Uses DEFAULT_LIST_LIMIT and MAX_LIST_LIMIT."""
    return parse_positive_int(
        value or str(DEFAULT_LIST_LIMIT),
        default=DEFAULT_LIST_LIMIT,
        maximum=MAX_LIST_LIMIT,
    )
