from __future__ import annotations


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
