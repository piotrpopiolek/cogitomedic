"""English log messages for domain exceptions; keys map to ``translation_data`` (``other.*``)."""
from __future__ import annotations

from typing import Any


def domain_message(key: str, **params: Any) -> str:
    """Return canonical English string for logs / ``str(exc)``; same templates as DB ``en`` slot."""
    from apps.core.api_error_i18n import OTHER_I18N_KEY_DEFAULT_EN

    template = OTHER_I18N_KEY_DEFAULT_EN.get(key, key)
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        return template
