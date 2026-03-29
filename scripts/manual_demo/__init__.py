"""Shared demo seed and Playwright auth for docs/manual automation."""

from __future__ import annotations

from scripts.manual_demo.django_setup import setup_django
from scripts.manual_demo.playwright_auth import (
    cookie_domain,
    login_admin,
    login_doctor,
    login_tablet,
)
from scripts.manual_demo.seed import seed_manual_demo

__all__ = [
    "setup_django",
    "seed_manual_demo",
    "cookie_domain",
    "login_admin",
    "login_doctor",
    "login_tablet",
]
