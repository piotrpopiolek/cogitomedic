from __future__ import annotations

import os
from typing import Optional

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


def _resolve_mtime(relative_path: str) -> Optional[int]:
    """Return integer mtime for a static asset, or None if the file is not found.

    Uses Django's staticfiles finders so it works in both DEBUG (per-app static
    directories) and production (STATIC_ROOT after collectstatic).
    """
    try:
        absolute_path = finders.find(relative_path)
    except Exception:
        return None
    if not absolute_path:
        return None
    try:
        return int(os.path.getmtime(absolute_path))
    except OSError:
        return None


@register.simple_tag
def static_v(relative_path: str) -> str:
    """Return ``{% static path %}`` with an mtime-based ``?v=`` cache buster.

    The cache buster guarantees that browsers fetch the latest version of a
    static asset whenever the file on disk changes, which avoids stale JS/CSS
    being served from the HTTP cache after a deployment or hot-reload.

    Falls back gracefully to a plain static URL if the file cannot be resolved
    (the page should never break because of a missing version stamp).
    """
    base_url = static(relative_path)
    mtime = _resolve_mtime(relative_path)
    if mtime is None:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}v={mtime}"
