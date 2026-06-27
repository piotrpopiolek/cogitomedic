"""Sentry Performance sampling helpers."""

from __future__ import annotations

from typing import Any, Final

OBSERVABILITY_PATH_PREFIX: Final = "/api/v1/observability/"


def _path_from_sampling_context(sampling_context: dict[str, Any]) -> str | None:
    wsgi_environ = sampling_context.get("wsgi_environ")
    if isinstance(wsgi_environ, dict):
        path = wsgi_environ.get("PATH_INFO")
        if isinstance(path, str):
            return path

    transaction_context = sampling_context.get("transaction_context")
    if isinstance(transaction_context, dict):
        name = transaction_context.get("name")
        if isinstance(name, str):
            if name.startswith(("GET ", "POST ", "PUT ", "PATCH ", "DELETE ", "HEAD ")):
                parts = name.split(" ", 1)
                if len(parts) == 2:
                    return parts[1].split("?")[0]
            return name.split("?")[0]

    return None


def is_observability_request_path(path: str) -> bool:
    return path.startswith(OBSERVABILITY_PATH_PREFIX)


def parse_sentry_traces_sample_rate(raw: str | None, *, default: float = 0.5) -> float:
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        return default
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def sentry_traces_sampler(
    sampling_context: dict[str, Any],
    *,
    default_sample_rate: float,
) -> float:
    """Return trace sample rate for a transaction (0 = no Performance span)."""
    parent = sampling_context.get("parent_sampled")
    if parent is not None:
        return float(parent)

    path = _path_from_sampling_context(sampling_context)
    if path and is_observability_request_path(path):
        return 0.0

    return default_sample_rate
