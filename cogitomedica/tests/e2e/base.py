"""Playwright + Django StaticLiveServerTestCase base for doctor E2E."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from django.test import override_settings
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from apps.medical.external_pdf_service import GateResult

ARTIFACT_DIR = Path(settings.BASE_DIR) / "artifacts" / "e2e"


def e2e_browser_name() -> str:
    return (os.environ.get("E2E_BROWSER") or "chromium").strip().lower()


def launch_browser(playwright: Playwright) -> Browser:
    name = e2e_browser_name()
    headless = os.environ.get("E2E_HEADLESS", "1") != "0"
    if name in {"msedge", "edge"}:
        return playwright.chromium.launch(channel="msedge", headless=headless)
    if name == "firefox":
        return playwright.firefox.launch(headless=headless)
    if name == "chromium":
        return playwright.chromium.launch(headless=headless)
    raise RuntimeError(
        f"Unsupported E2E_BROWSER={name!r}; use chromium, firefox, or msedge"
    )


_PASSING_GATE = GateResult(
    passed=True,
    matched_files=(),
    error_message=None,
    skip_attachment_sync=True,
)


@override_settings(
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
)
class PlaywrightDoctorE2EBase(StaticLiveServerTestCase):
    """One Playwright browser per test class; fresh context per test."""

    host = "localhost"
    password = "x"

    playwright: Playwright
    browser: Browser

    @classmethod
    def setUpClass(cls) -> None:
        # Playwright's sync API runs a nest of asyncio; Django ORM must still work.
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        os.environ.setdefault("E2E_AUTOSAVE_MS", "2000")
        super().setUpClass()
        origin = cls.live_server_url.rstrip("/")
        trusted = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
        if origin not in trusted:
            settings.CSRF_TRUSTED_ORIGINS = [*trusted, origin]
        for host in (cls.host, "127.0.0.1", "localhost"):
            if host not in settings.ALLOWED_HOSTS:
                settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, host]
        cls._gate_patcher = patch(
            "cogitomedica.doctor_views._external_pdf_gate_for_doctor_detail",
            return_value=_PASSING_GATE,
        )
        cls._gate_patcher.start()
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = launch_browser(cls.playwright)
        except Exception:
            cls._gate_patcher.stop()
            cls.playwright.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.browser.close()
        finally:
            try:
                cls._gate_patcher.stop()
            except Exception:
                pass
            cls.playwright.stop()
            super().tearDownClass()

    def setUp(self) -> None:
        super().setUp()
        # TransactionTestCase may drop translation rows; keep doctor UI complete.
        call_command("load_default_translations", verbosity=0)
        self._contexts: list[BrowserContext] = []
        self.context = self.new_context()
        self.page = self.context.new_page()

    def tearDown(self) -> None:
        for ctx in list(self._contexts):
            try:
                ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        super().tearDown()

    def new_context(self, **kwargs: Any) -> BrowserContext:
        ctx = self.browser.new_context(
            ignore_https_errors=True,
            locale="de-DE",
            **kwargs,
        )
        self._contexts.append(ctx)
        return ctx

    def dump_page_screenshot(self, page: Page, label: str) -> None:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACT_DIR / f"{e2e_browser_name()}_{label}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
        except Exception:
            pass

    def login_doctor(self, page: Page, *, username: str) -> None:
        page.goto(f"{self.live_server_url}/doctor/login/", wait_until="domcontentloaded")
        page.fill('input[name="username"]', username)
        page.fill('input[name="password"]', self.password)
        page.click('form button[type="submit"]')
        page.wait_for_function(
            "() => !window.location.pathname.includes('/doctor/login')",
            timeout=30_000,
        )

    def open_document(self, page: Page, document_id) -> None:
        page.goto(
            f"{self.live_server_url}/doctor/{document_id}/?lang=de",
            wait_until="domcontentloaded",
        )

    def open_document_acquiring_session(self, page: Page, document_id) -> dict:
        with page.expect_response(
            lambda r: "/edit-session" in r.url
            and r.request.method == "POST"
            and r.ok,
            timeout=45_000,
        ) as info:
            self.open_document(page, document_id)
        page.wait_for_selector("#btn-save-draft:not([disabled])", timeout=30_000)
        return info.value.json()

    def session_storage_token(
        self, page: Page, *, staff_user_id: str, document_id
    ) -> str | None:
        key = f"befundEditSession:{staff_user_id}:{document_id}"
        raw = page.evaluate(
            """(k) => {
              try { return sessionStorage.getItem(k); } catch (e) { return null; }
            }""",
            key,
        )
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("token")

    def mark_form_dirty(self, page: Page, text: str = "E2E dirty note") -> None:
        page.wait_for_selector("#summary_text", timeout=15_000)
        page.fill("#summary_text", text)

    def confirm_revision_modal(self, page: Page) -> None:
        page.wait_for_selector("#revision-modal:not(.hidden)", timeout=15_000)
        page.click("#revision-modal-confirm")

    def discard_pending_revision(self, page: Page) -> dict:
        page.wait_for_selector("#btn-discard-revision:not([disabled])", timeout=20_000)
        with page.expect_response(
            lambda r: "/discard-revision" in r.url
            and r.request.method == "POST"
            and r.ok,
            timeout=45_000,
        ) as info:
            page.click("#btn-discard-revision")
            self.confirm_revision_modal(page)
        return info.value.json()

    def start_amend_revision(self, page: Page) -> dict:
        page.wait_for_selector("#btn-start-revision", timeout=20_000)
        with page.expect_response(
            lambda r: "/edit-session" in r.url
            and r.request.method == "POST"
            and r.ok,
            timeout=45_000,
        ) as info:
            page.click("#btn-start-revision")
            self.confirm_revision_modal(page)
        page.wait_for_selector("#btn-save-draft:not([disabled])", timeout=30_000)
        return info.value.json()
