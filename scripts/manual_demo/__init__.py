"""Shared demo seed and Playwright auth for docs/manual automation."""

from __future__ import annotations

from scripts.manual_demo.django_setup import setup_django
from scripts.manual_demo.playwright_auth import (
    cookie_domain,
    login_admin,
    login_doctor,
    login_reception,
    login_staff,
    login_tablet,
)
from scripts.manual_demo.seed import seed_manual_demo, seed_manual_screenshot_extras

__all__ = [
    "setup_django",
    "seed_manual_demo",
    "seed_manual_screenshot_extras",
    "cookie_domain",
    "login_admin",
    "login_doctor",
    "login_reception",
    "login_staff",
    "login_tablet",
]
