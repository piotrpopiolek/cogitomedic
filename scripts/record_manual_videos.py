"""
Nagrywa krótkie filmy WebM (Playwright) per rola — scenariusze z docs/manual/ 01–05.

Wymaga tego samego środowiska co capture_manual_screenshots.py (DB, migrate, web).
Opcje .env: CAPTCHA_VERIFY_SKIP=1, SMSAPI_USE_MOCK=1, PATIENT_RESULTS_OTP_PEPPER=...

Portal pacjenta: krok OTP używa wstępnie utworzonej sesji (cookie), jak przy zrzutach PNG —
realne wpisywanie kodu z SMS wymagałoby osobnego scenariusza.

Usage:
  python scripts/record_manual_videos.py --role reception --base-url http://127.0.0.1:8000
  python scripts/record_manual_videos.py --role all --slow-mo 250
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

DEFAULT_OUT = REPO_ROOT / "docs" / "manual" / "assets" / "videos"


def _clear_webm(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for p in folder.glob("*.webm"):
        p.unlink(missing_ok=True)


def _finalize_webm(folder: Path, role: str) -> Path | None:
    webms = list(folder.glob("*.webm"))
    if not webms:
        return None
    target = folder / f"{role}.webm"
    latest = max(webms, key=lambda p: p.stat().st_mtime)
    if target.exists() and target.resolve() != latest.resolve():
        target.unlink(missing_ok=True)
    latest.rename(target)
    return target


def _pause(page, ms: int = 800) -> None:
    page.wait_for_timeout(ms)


def _record_reception(
    base: str, ctx: dict, out_dir: Path, slow_mo: int, vw: int, vh: int
) -> Path | None:
    from django.urls import reverse

    pwd = ctx["password"]
    folder = out_dir / "reception"
    _clear_webm(folder)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_mo)
        context = browser.new_context(
            viewport={"width": vw, "height": vh},
            record_video_dir=str(folder),
            record_video_size={"width": vw, "height": vh},
        )
        page = context.new_page()
        page.goto(f"{base}/admin/login/", wait_until="networkidle")
        _pause(page)
        login_admin(page, base, pwd)
        page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
        _pause(page)
        page.goto(f"{base}/admin/reception/dailyqueue/", wait_until="networkidle")
        _pause(page)
        page.goto(
            f"{base}/admin/reception/dailyqueue/master-detail/",
            wait_until="networkidle",
        )
        _pause(page)
        imp_url = f"{base}{reverse('admin:reception_dailyqueue_import_xlsx')}"
        page.goto(imp_url, wait_until="networkidle")
        _pause(page)
        page.goto(
            f"{base}{reverse('admin:reception_queueentry_add')}",
            wait_until="networkidle",
        )
        _pause(page)
        page.goto(f"{base}/admin/intake-documents/", wait_until="networkidle")
        _pause(page)
        iv_id = ctx.get("intake_document_version_id")
        if iv_id:
            page.goto(
                f"{base}/admin/intake-documents/{iv_id}/", wait_until="networkidle"
            )
            _pause(page, 1200)
        context.close()
        browser.close()

    return _finalize_webm(folder, "reception")


def _record_admin(
    base: str, ctx: dict, out_dir: Path, slow_mo: int, vw: int, vh: int
) -> Path | None:
    from django.urls import reverse

    pwd = ctx["password"]
    folder = out_dir / "admin"
    _clear_webm(folder)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_mo)
        context = browser.new_context(
            viewport={"width": vw, "height": vh},
            record_video_dir=str(folder),
            record_video_size={"width": vw, "height": vh},
        )
        page = context.new_page()
        login_admin(page, base, pwd)
        page.goto(f"{base}/admin/", wait_until="networkidle")
        _pause(page)
        page.goto(
            f"{base}{reverse('admin:users_staffuser_change', args=[ctx['admin'].id])}",
            wait_until="networkidle",
        )
        _pause(page, 1200)
        imp_url = f"{base}{reverse('admin:reception_dailyqueue_import_xlsx')}"
        page.goto(imp_url, wait_until="networkidle")
        _pause(page)
        context.close()
        browser.close()

    return _finalize_webm(folder, "admin")


def _record_doctor(
    base: str, ctx: dict, out_dir: Path, slow_mo: int, vw: int, vh: int
) -> Path | None:
    pwd = ctx["password"]
    folder = out_dir / "doctor"
    _clear_webm(folder)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_mo)
        context = browser.new_context(
            viewport={"width": vw, "height": vh},
            record_video_dir=str(folder),
            record_video_size={"width": vw, "height": vh},
        )
        page = context.new_page()
        # Matching lab PDF so DRAFT Befund detail opens (seed may clear /incoming).
        # No Django ORM here — Playwright sync API runs under an async loop.
        try:
            from scripts.manual_demo.scenario_helpers import (
                minimal_demo_pdf_bytes,
                seed_mock_incoming,
            )

            anna_name = ctx.get("anna_demo_incoming_pdf") or "Demo_Anna.pdf"
            seed_mock_incoming(
                [{"name": anna_name}],
                file_bytes=minimal_demo_pdf_bytes(title="Demo lab Anna"),
            )
        except Exception:
            pass
        page.goto(f"{base}/doctor/login/", wait_until="networkidle")
        _pause(page)
        login_doctor(page, base, pwd)
        page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
        _pause(page, 1200)
        page.goto(
            f"{base}/doctor/open/{ctx['queue_entry_err_id']}/?lang=de",
            wait_until="networkidle",
        )
        _pause(page, 1200)
        page.goto(
            f"{base}/doctor/{ctx['medical_document_id']}/?lang=de",
            wait_until="networkidle",
        )
        page.wait_for_timeout(2000)
        _pause(page, 1200)
        # Walk rich Befund sections (lesions → recommendations → actions).
        for _ in range(4):
            page.mouse.wheel(0, 350)
            _pause(page, 700)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _pause(page, 1500)
        preview = page.locator("#btn-preview-pdf").first
        if preview.count():
            try:
                with page.expect_popup(timeout=8000) as popup_info:
                    preview.click()
                pdf_page = popup_info.value
                pdf_page.wait_for_load_state("domcontentloaded")
                _pause(pdf_page, 2000)
                pdf_page.close()
            except Exception:
                page.goto(
                    f"{base}/api/v1/medical-documents/"
                    f"{ctx['medical_document_id']}/preview-pdf",
                    wait_until="load",
                )
                _pause(page, 1800)
        portal_doc = ctx.get("portal_published_doc_id")
        if portal_doc:
            page.goto(
                f"{base}/doctor/{portal_doc}/?lang=de",
                wait_until="networkidle",
            )
            _pause(page, 1800)
            start_rev = page.locator("#btn-start-revision").first
            if start_rev.count() and start_rev.is_visible():
                start_rev.hover()
                _pause(page, 1200)
            revoke = page.locator("#btn-revoke-publication").first
            if revoke.count() and revoke.is_visible():
                revoke.hover()
                _pause(page, 1400)
        rev_doc = ctx.get("revision_demo_doc_id")
        if rev_doc:
            page.goto(f"{base}/doctor/{rev_doc}/?lang=de", wait_until="networkidle")
            page.wait_for_timeout(1500)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            _pause(page, 1000)
            resend = page.locator("#resend_sms").first
            if resend.count():
                try:
                    resend.check(force=True)
                except Exception:
                    pass
                _pause(page, 1400)
            publish = page.locator("#btn-publish").first
            if publish.count():
                publish.hover()
                _pause(page, 1600)
        context.close()
        browser.close()

    return _finalize_webm(folder, "doctor")


def _record_tablet(
    base: str, ctx: dict, out_dir: Path, slow_mo: int, tw: int, th: int
) -> Path | None:
    pwd = ctx["password"]
    folder = out_dir / "tablet"
    _clear_webm(folder)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_mo)
        context = browser.new_context(
            viewport={"width": tw, "height": th},
            record_video_dir=str(folder),
            record_video_size={"width": tw, "height": th},
        )
        page = context.new_page()
        page.goto(f"{base}/tablet/login/", wait_until="networkidle")
        _pause(page)
        login_tablet(page, base, pwd, "screenshot-assigned-dev")
        page.goto(f"{base}/tablet/", wait_until="networkidle")
        _pause(page)
        qid = str(ctx["queue"].id)
        page.goto(f"{base}/tablet/queue/{qid}/", wait_until="networkidle")
        _pause(page)
        qet_id = ctx.get("queue_entry_tablet_id")
        if qet_id:
            page.goto(f"{base}/tablet/entry/{qet_id}/", wait_until="networkidle")
            _pause(page)
            page.locator('button[type="submit"]').click()
            page.wait_for_load_state("networkidle")
            _pause(page)
        fid = ctx["intake_form_tablet_id"]
        page.goto(f"{base}/tablet/form/{fid}/?locale=de", wait_until="networkidle")
        page.wait_for_timeout(1200)
        page.mouse.wheel(0, 400)
        _pause(page, 1200)
        context.close()
        browser.close()

    return _finalize_webm(folder, "tablet")


def _record_patient(
    base: str, ctx: dict, out_dir: Path, slow_mo: int, vw: int, vh: int
) -> Path | None:
    folder = out_dir / "patient"
    _clear_webm(folder)
    ck_host = cookie_domain(base)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_mo)
        context = browser.new_context(
            viewport={"width": vw, "height": vh},
            record_video_dir=str(folder),
            record_video_size={"width": vw, "height": vh},
        )
        page = context.new_page()
        page.goto(f"{base}/", wait_until="networkidle")
        _pause(page, 1200)
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
        _pause(page, 1500)
        page.context.clear_cookies()
        page.goto(f"{base}/", wait_until="networkidle")
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
        _pause(page, 1500)
        context.close()
        browser.close()

    return _finalize_webm(folder, "patient")


ROLE_HANDLERS = {
    "reception": _record_reception,
    "admin": _record_admin,
    "doctor": _record_doctor,
    "tablet": _record_tablet,
    "patient": _record_patient,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nagrywa WebM instruktażowe per rola (Playwright)."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SCREENSHOT_BASE_URL", "http://127.0.0.1:8000"),
        help="URL aplikacji (np. http://web:8000 w Dockerze)",
    )
    parser.add_argument(
        "--role",
        choices=[*ROLE_HANDLERS.keys(), "all"],
        default="all",
        help="Rola do nagrania lub all",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Katalog wyjściowy (domyślnie {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=200,
        help="Opóźnienie ms między akcjami Playwright",
    )
    parser.add_argument(
        "--video-width",
        type=int,
        default=1280,
        help="Szerokość nagrania (desktop/pacjent)",
    )
    parser.add_argument(
        "--video-height",
        type=int,
        default=720,
        help="Wysokość nagrania (desktop/pacjent)",
    )
    parser.add_argument(
        "--tablet-width", type=int, default=900, help="Szerokość widoku tabletu"
    )
    parser.add_argument(
        "--tablet-height", type=int, default=1200, help="Wysokość widoku tabletu"
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        print(
            "Install: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    skip_django = os.environ.get("SCREENSHOT_SKIP_DJANGO", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    ctx_path = REPO_ROOT / "docs" / "manual" / "_build" / "manual-video-ctx.json"
    if skip_django:
        if not ctx_path.is_file():
            print(
                f"Brak {ctx_path.name} — najpierw w kontenerze web:\n"
                "  docker compose exec -w /app -e PYTHONPATH=/app web "
                "python scripts/manual_demo/write_manual_video_ctx.py",
                file=sys.stderr,
            )
            return 1
        import json

        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        ctx.setdefault("password", "ScreenshotDemo2026!")
    else:
        setup_django()
        ctx = {}
        seed_manual_demo(ctx)

    roles = list(ROLE_HANDLERS.keys()) if args.role == "all" else [args.role]
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    for role in roles:
        handler = ROLE_HANDLERS[role]
        if role == "tablet":
            path = handler(
                base, ctx, out_dir, args.slow_mo, args.tablet_width, args.tablet_height
            )
        else:
            path = handler(
                base, ctx, out_dir, args.slow_mo, args.video_width, args.video_height
            )
        if path:
            print(f"OK {role}: {path}")
        else:
            print(f"WARN {role}: brak pliku .webm w {out_dir / role}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
