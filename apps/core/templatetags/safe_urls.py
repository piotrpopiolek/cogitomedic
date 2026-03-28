from __future__ import annotations

from urllib.parse import urlsplit

from django import template

register = template.Library()


@register.filter
def safe_href(value: str | None) -> str:
    """
    Allow only relative URLs and absolute http/https URLs.

    Unsafe or malformed values return "#".
    """
    if not value:
        return "#"
    text = str(value).strip()
    if not text:
        return "#"
    if any(ch in text for ch in ("\r", "\n", "\x00")):
        return "#"
    if text.startswith(("/", "./", "../")):
        return text
    parsed = urlsplit(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return text
    return "#"
