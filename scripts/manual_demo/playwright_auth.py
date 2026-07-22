"""Playwright helpers shared by screenshot and video scripts."""

from __future__ import annotations

from urllib.parse import urlparse

from scripts.manual_demo.cursor_overlay import (
    cursor_enabled,
    ensure_cursor_alive,
    human_click,
    human_fill,
)


def cookie_domain(base: str) -> str:
    host = urlparse(base).hostname or "127.0.0.1"
    return host


def _fill(page, locator, value: str) -> None:
    if cursor_enabled(page):
        ensure_cursor_alive(page)
        if human_fill(page, locator, value):
            return
    locator.fill(value)


def _click_submit(page, locator) -> None:
    if cursor_enabled(page):
        ensure_cursor_alive(page)
        if human_click(page, locator, wait_network=True):
            return
    locator.click()
    page.wait_for_load_state("networkidle")


def login_admin(page, base: str, password: str) -> None:
    page.goto(f"{base}/admin/login/", wait_until="networkidle")
    _fill(page, page.locator('input[name="username"]'), "screenshot_admin")
    _fill(page, page.locator('input[name="password"]'), password)
    _click_submit(page, page.locator('#login-form button[type="submit"]'))


def login_reception(page, base: str, password: str) -> None:
    page.goto(f"{base}/admin/login/", wait_until="networkidle")
    _fill(page, page.locator('input[name="username"]'), "screenshot_reception")
    _fill(page, page.locator('input[name="password"]'), password)
    _click_submit(page, page.locator('#login-form button[type="submit"]'))


def login_staff(
    page, base: str, password: str, *, username: str = "screenshot_admin"
) -> None:
    page.goto(f"{base}/admin/login/", wait_until="networkidle")
    _fill(page, page.locator('input[name="username"]'), username)
    _fill(page, page.locator('input[name="password"]'), password)
    _click_submit(page, page.locator('#login-form button[type="submit"]'))


def login_doctor(page, base: str, password: str) -> None:
    page.goto(f"{base}/doctor/login/", wait_until="networkidle")
    _fill(page, page.locator('input[name="username"]'), "screenshot_doctor")
    _fill(page, page.locator('input[name="password"]'), password)
    _click_submit(page, page.locator('form button[type="submit"]').first)


def login_tablet(page, base: str, password: str, android_id: str) -> None:
    page.goto(f"{base}/tablet/login/", wait_until="networkidle")
    page.evaluate(
        """(id) => { const el = document.querySelector('input[name="android_id"]'); if (el) el.value = id; }""",
        android_id,
    )
    _fill(page, page.locator('input[name="username"]'), "screenshot_tablet")
    _fill(page, page.locator('input[name="password"]'), password)
    _click_submit(page, page.locator('button[type="submit"]'))
