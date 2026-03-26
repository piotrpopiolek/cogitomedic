"""
Seed minimal demo data and capture PNG screenshots for docs/manual (checklist).

Requires:
  - Django DB configured and migrated (PostgreSQL).
  - Runserver: python manage.py runserver 127.0.0.1:8000
  - pip install -r requirements-dev.txt && playwright install chromium

Optional .env for patient portal flow during seed:
  CAPTCHA_VERIFY_SKIP=1
  PATIENT_RESULTS_OTP_PEPPER=dev-pepper-not-for-prod
  SMSAPI_USE_MOCK=1

Usage (from repo root):
  python scripts/capture_manual_screenshots.py --base-url http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.manual_demo import (
    cookie_domain,
    login_admin,
    login_doctor,
    login_tablet,
    seed_manual_demo,
    setup_django,
)

OUTPUT_DIR = REPO_ROOT / "docs" / "manual" / "assets" / "screenshots"


def _draw_overview_png(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    w, h = 1200, 400
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    lines = [
        "Cogitomedica — proces (demo screenshot)",
        "1. Recepcja: kolejka i pacjenci",
        "2. Tablet: formularz intake (poczekalnia)",
        "3. Lekarz: Befund, publikacja",
        "4. Backend: PDF → archiwum → SMS logistyczny",
        "5. Pacjent: portal wyników (telefon + OTP)",
    ]
    y = 20
    for line in lines:
        draw.text((40, y), line, fill=(20, 20, 20), font=font)
        y += 56
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def _shot(page, name: str) -> None:
    path = OUTPUT_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("SCREENSHOT_BASE_URL", "http://127.0.0.1:8000"))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    setup_django()
    ctx: dict = {}
    seed_manual_demo(ctx)
    pwd = ctx["password"]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _draw_overview_png(OUTPUT_DIR / "overview-01-process-diagram.png")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # --- Public / login pages ---
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"{base}/admin/login/", wait_until="networkidle")
        _shot(page, "reception-01-admin-login.png")

        page.goto(f"{base}/doctor/login/", wait_until="networkidle")
        _shot(page, "doctor-01-login.png")

        tpage = browser.new_page(viewport={"width": 900, "height": 1200})
        tpage.goto(f"{base}/tablet/login/", wait_until="networkidle")
        _shot(tpage, "tablet-01-login.png")

        page.goto(f"{base}/", wait_until="networkidle")
        _shot(page, "patient-01-login.png")

        # --- Admin dashboard ---
        login_admin(page, base, pwd)
        page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
        _shot(page, "reception-02-reception-dashboard.png")

        page.goto(f"{base}/admin/reception/dailyqueue/", wait_until="networkidle")
        _shot(page, "reception-03-daily-queue-changelist.png")

        page.goto(f"{base}/admin/reception/dailyqueue/master-detail/", wait_until="networkidle")
        _shot(page, "reception-04-master-detail.png")

        from django.urls import reverse

        imp_url = f"{base}{reverse('admin:reception_dailyqueue_import_xlsx')}"
        page.goto(imp_url, wait_until="networkidle")
        _shot(page, "reception-06-import-xlsx.png")
        _shot(page, "admin-03-import-xlsx.png")

        page.goto(f"{base}{reverse('admin:reception_queueentry_add')}", wait_until="networkidle")
        _shot(page, "reception-05-queue-entry-add.png")

        page.goto(f"{base}/admin/intake-documents/", wait_until="networkidle")
        _shot(page, "reception-07-intake-documents-list.png")

        iv_id = ctx.get("intake_document_version_id")
        if iv_id:
            page.goto(f"{base}/admin/intake-documents/{iv_id}/", wait_until="networkidle")
            _shot(page, "reception-08-intake-document-detail.png")

        page.goto(f"{base}/admin/", wait_until="networkidle")
        _shot(page, "admin-01-index.png")

        page.goto(
            f"{base}{reverse('admin:users_staffuser_change', args=[ctx['admin'].id])}",
            wait_until="networkidle",
        )
        _shot(page, "admin-02-staff-user.png")

        # --- Doctor ---
        page.context.clear_cookies()
        login_doctor(page, base, pwd)
        page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
        _shot(page, "doctor-02-list-filters.png")

        page.goto(f"{base}/doctor/open/{ctx['queue_entry_err_id']}/?lang=de", wait_until="networkidle")
        _shot(page, "doctor-03-error-no-intake.png")

        page.goto(f"{base}/doctor/{ctx['medical_document_id']}/?lang=de", wait_until="networkidle")
        page.wait_for_timeout(1500)
        _shot(page, "doctor-04-befund-section.png")

        # --- Tablet unassigned ---
        tpage.context.clear_cookies()
        tpage.goto(f"{base}/tablet/login/", wait_until="networkidle")
        tpage.evaluate("() => { document.querySelector('#tablet-login-android-id').value = 'screenshot-unassigned-dev'; }")
        tpage.locator('input[name="username"]').fill("screenshot_tablet")
        tpage.locator('input[name="password"]').fill(pwd)
        tpage.locator('button[type="submit"]').click()
        tpage.wait_for_url("**/tablet/**")
        tpage.goto(f"{base}/tablet/", wait_until="networkidle")
        _shot(tpage, "tablet-00-unassigned-warning.png")

        # --- Tablet with clinic + form ---
        tpage.context.clear_cookies()
        login_tablet(tpage, base, pwd, "screenshot-assigned-dev")
        tpage.goto(f"{base}/tablet/", wait_until="networkidle")
        _shot(tpage, "tablet-02-home-queues.png")

        qid = str(ctx["queue"].id)
        tpage.goto(f"{base}/tablet/queue/{qid}/", wait_until="networkidle")
        _shot(tpage, "tablet-03-queue-entries.png")

        qet_id = ctx.get("queue_entry_tablet_id")
        if qet_id:
            tpage.goto(f"{base}/tablet/entry/{qet_id}/", wait_until="networkidle")
            tpage.locator('button[type="submit"]').click()
            tpage.wait_for_load_state("networkidle")
            _shot(tpage, "tablet-04-entry-started.png")

        fid = ctx["intake_form_tablet_id"]
        tpage.goto(f"{base}/tablet/form/{fid}/?locale=de", wait_until="networkidle")
        tpage.wait_for_timeout(800)
        _shot(tpage, "tablet-05-form-locale.png")
        _shot(tpage, "tablet-06-form-sections.png")
        tpage.goto(f"{base}/tablet/form/{fid}/?locale=de", wait_until="networkidle")
        tpage.wait_for_timeout(500)
        _shot(tpage, "tablet-07-body-map.png")
        _shot(tpage, "tablet-08-signature.png")

        done_id = ctx["intake_form_done_id"]
        tpage.goto(f"{base}/tablet/form/{done_id}/?locale=de", wait_until="networkidle")
        _shot(tpage, "tablet-09-form-submitted.png")

        # --- Patient portal OTP / documents (session cookie) ---
        ck_host = cookie_domain(base)
        page.context.clear_cookies()
        page.goto(f"{base}/")
        page.context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": ctx["session_otp_key"],
                    "domain": ck_host,
                    "path": "/",
                }
            ]
        )
        page.goto(f"{base}/otp/?locale=pl", wait_until="networkidle")
        _shot(page, "patient-02-otp.png")

        page.context.clear_cookies()
        page.goto(f"{base}/")
        page.context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": ctx["session_doc_key"],
                    "domain": ck_host,
                    "path": "/",
                }
            ]
        )
        page.goto(f"{base}/documents/?locale=pl", wait_until="networkidle")
        _shot(page, "patient-03-documents.png")

        browser.close()

    print(f"Done. PNG files in {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
