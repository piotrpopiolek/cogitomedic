"""Prod Nginx must not expose MEDIA_ROOT (PHI) without Django auth."""

from pathlib import Path

import pytest
from django.test import Client

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NGINX_PROD_CONF = _REPO_ROOT / "deploy" / "nginx" / "nginx.prod.conf"


def test_nginx_prod_conf_does_not_publicly_serve_media() -> None:
    """Public ``location /media/`` bypassed portal OTP and was removed (security fix)."""
    text = _NGINX_PROD_CONF.read_text(encoding="utf-8")
    assert "location /media/" not in text


@pytest.mark.django_db
def test_django_does_not_serve_media_urls(client: Client) -> None:
    """Nginx proxies unknown /media/ paths to Django; must not return PDF bytes."""
    response = client.get(
        "/media/pdfs/befund/2026/07/00000000-0000-0000-0000-000000000001.pdf"
    )
    assert response.status_code == 404
    assert (
        response.get("Content-Type", "").startswith("text/html")
        or response.content == b""
    )
