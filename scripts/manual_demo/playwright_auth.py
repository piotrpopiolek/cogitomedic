"""Playwright helpers shared by screenshot and video scripts."""

from __future__ import annotations

from urllib.parse import urlparse


def cookie_domain(base: str) -> str:
    host = urlparse(base).hostname or "127.0.0.1"
    return host


def login_admin(page, base: str, password: str) -> None:
    page.goto(f"{base}/admin/login/", wait_until="networkidle")
    page.locator('input[name="username"]').fill("screenshot_admin")
    page.locator('input[name="password"]').fill(password)
    page.locator('#login-form button[type="submit"]').click()
    page.wait_for_load_state("networkidle")


def login_doctor(page, base: str, password: str) -> None:
    page.goto(f"{base}/doctor/login/", wait_until="networkidle")
    page.locator('input[name="username"]').fill("screenshot_doctor")
    page.locator('input[name="password"]').fill(password)
    page.locator('form button[type="submit"]').first.click()
    page.wait_for_load_state("networkidle")


def login_tablet(page, base: str, password: str, android_id: str) -> None:
    page.goto(f"{base}/tablet/login/", wait_until="networkidle")
    page.evaluate(
        """(id) => { const el = document.querySelector('input[name="android_id"]'); if (el) el.value = id; }""",
        android_id,
    )
    page.locator('input[name="username"]').fill("screenshot_tablet")
    page.locator('input[name="password"]').fill(password)
    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")
