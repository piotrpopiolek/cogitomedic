"""
Nagrywa wolne filmy WebM dla scenariuszy operacyjnych SC-001–SC-027.

Dane pacjentów: wyłącznie fikcyjne (seed scripts/manual_demo/seed_scenarios.py).
SC-007 korzysta z istniejącego record_import_troubleshooting_video.py.

Widoczny kursor: install_cursor() + scripts/manual_demo/cursor_overlay.py
(żółty overlay DOM; Playwright nie nagrywa kursora OS).

Usage:
  # seed w Dockerze (zalecane na Windows), nagranie na hoście:
  docker compose exec web python scripts/manual_demo/seed_scenarios.py --scenario sc-001 --write-ctx
  $env:SCREENSHOT_SKIP_DJANGO='1'
  python scripts/record_scenario_videos.py --scenario sc-001 --base-url http://127.0.0.1:8000 --slow-mo 500

  # wszystkie (poza SC-007 — osobny skrypt / ten sam --all z ctx importu):
  python scripts/record_scenario_videos.py --all --slow-mo 500

  # priorytet wysoki:
  python scripts/record_scenario_videos.py --priority high --slow-mo 500
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.manual_demo import (
    cookie_domain,
    login_doctor,
    login_reception,
    login_staff,
    login_tablet,
    setup_django,
)
from scripts.manual_demo.cursor_overlay import (
    ensure_cursor_alive,
    human_click,
    human_fill,
    human_hover,
    human_select_option,
    human_wheel,
    install_cursor,
)
from scripts.manual_demo.seed_scenarios import seed_scenario

DEFAULT_OUT = REPO_ROOT / "docs" / "manual" / "assets" / "videos" / "scenariusze"
DEFAULT_CTX_DIR = REPO_ROOT / "docs" / "manual" / "_build" / "scenario-ctx"
HIDRIVE_MOCK_STATE = (
    REPO_ROOT / "docs" / "manual" / "_build" / "hidrive-mock-state.json"
)

FILENAMES: dict[str, str] = {
    "SC-001": "sc-001-anulowany-wpis.webm",
    "SC-002": "sc-002-usuniety-szkic.webm",
    "SC-003": "sc-003-porzuc-rewizje.webm",
    "SC-004": "sc-004-raport-ksiegowosci.webm",
    "SC-005": "sc-005-brak-pdf-hidrive.webm",
    "SC-006": "sc-006-sms-outbox.webm",
    "SC-007": "import-troubleshooting.webm",  # reception/
    "SC-008": "sc-008-portal-login.webm",
    "SC-009": "sc-009-wspolny-telefon.webm",
    "SC-010": "sc-010-otp-portal.webm",
    "SC-011": "sc-011-homonim-pdf.webm",
    "SC-012": "sc-012-rejected-pdf.webm",
    "SC-013": "sc-013-outbox-pdf-hidrive.webm",
    "SC-014": "sc-014-blokada-dokumentu.webm",
    "SC-015": "sc-015-revoke-publikacji.webm",
    "SC-016": "sc-016-papier-po-tablecie.webm",
    "SC-017": "sc-017-paper-intake-t1.webm",
    "SC-018": "sc-018-tablet-bez-placowki.webm",
    "SC-019": "sc-019-zla-ankieta.webm",
    "SC-020": "sc-020-external-upload.webm",
    "SC-021": "sc-021-brak-ankiety.webm",
    "SC-022": "sc-022-pusta-lista-dokumentow.webm",
    "SC-023": "sc-023-okno-60-dni.webm",
    "SC-024": "sc-024-smsapi-saldo.webm",
    "SC-025": "sc-025-korekta-danych.webm",
    "SC-026": "sc-026-dead-letter.webm",
    "SC-027": "sc-027-baner-hidrive.webm",
}

PRIORITY_HIGH = [
    "SC-001",
    "SC-002",
    "SC-006",
    "SC-007",
    "SC-008",
    "SC-010",
    "SC-019",
]
PRIORITY_MEDIUM = [
    "SC-003",
    "SC-004",
    "SC-005",
    "SC-011",
    "SC-013",
    "SC-015",
    "SC-017",
    "SC-020",
]
PRIORITY_LOW = [
    sid for sid in FILENAMES if sid not in PRIORITY_HIGH and sid not in PRIORITY_MEDIUM
]


def _norm_sid(raw: str) -> str:
    sid = raw.strip().upper().replace("_", "-")
    if not sid.startswith("SC-"):
        sid = f"SC-{sid.zfill(3) if sid.isdigit() else sid}"
    return sid


def _pause(page, ms: int = 1600) -> None:
    page.wait_for_timeout(ms)


def _write_hidrive_mock_state(
    *,
    files: list[dict] | None = None,
    list_dir_error: str | None = None,
    remote_dir: str | None = None,
) -> None:
    """Update shared mock JSON so the ``web`` process sees HiDrive demo state.

    Incoming dir must match ``HIDRIVE_INCOMING_PATH`` used by ``web``
    (this repo's docker ``.env`` uses ``/public/incoming``).
    File bodies are valid minimal PDFs (PdfReader / external-upload preview).
    """
    import base64
    import time

    from scripts.manual_demo.scenario_helpers import minimal_demo_pdf_bytes

    demo_pdf = minimal_demo_pdf_bytes(title="Demo HiDrive incoming")
    demo_pdf_b64 = base64.b64encode(demo_pdf).decode("ascii")
    demo_pdf_size = len(demo_pdf)

    # Match docker .env default; override via env if needed.
    inc = (
        remote_dir
        or os.environ.get("HIDRIVE_INCOMING_PATH", "").strip()
        or "/public/incoming"
    )
    if not inc.startswith("/"):
        inc = "/" + inc
    inc = inc.rstrip("/") or "/public/incoming"
    HIDRIVE_MOCK_STATE.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if HIDRIVE_MOCK_STATE.is_file():
        try:
            existing = json.loads(HIDRIVE_MOCK_STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
    listings: dict = {}
    files_b64: dict = {}
    if files is not None:
        normalized: list[dict] = []
        for entry in files:
            name = str(entry.get("name") or "")
            path = str(entry.get("path") or "")
            if name and (not path or "/incoming/" in path):
                path = f"{inc}/{name}"
            normalized.append(
                {**entry, "name": name, "path": path, "size": demo_pdf_size}
            )
            if path:
                files_b64[path] = demo_pdf_b64
        listings[inc] = normalized
    else:
        # Keep prior listing for this incoming dir when only toggling list_dir_error.
        prev = (existing.get("listings") or {}).get(inc) or []
        listings[inc] = list(prev)
        files_b64 = dict(existing.get("files_b64") or {})
    payload = {
        "incoming_path": inc,
        "updated_at": time.time(),
        "listings": listings,
        "files_b64": files_b64,
        "list_dir_error": list_dir_error,
    }
    HIDRIVE_MOCK_STATE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _scroll_hidrive_section(page) -> None:
    ensure_cursor_alive(page)
    banner = page.locator(".cogito-reception-banner--warning").first
    table = page.locator("table").first
    target = banner if banner.count() else table
    if target.count():
        human_hover(page, target, pause_ms=700)
    else:
        human_wheel(page, 200, steps=3, pause_ms=350)


def _finalize(folder: Path, filename: str) -> Path | None:
    candidates = list(folder.glob("*.webm"))
    if not candidates:
        return None
    target = folder / filename
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    if target.exists() and target.resolve() != latest.resolve():
        others = [p for p in candidates if p.resolve() != target.resolve()]
        if others:
            latest = max(others, key=lambda p: p.stat().st_mtime)
            target.unlink(missing_ok=True)
            latest.rename(target)
        return target
    if latest.resolve() != target.resolve():
        latest.rename(target)
    return target


def _safe_fill(locator, value: str, page, pause_ms: int = 800) -> bool:
    return human_fill(page, locator, value, pause_after_ms=pause_ms)


def _safe_click(locator, page, pause_ms: int = 800) -> bool:
    return human_click(
        page,
        locator,
        pause_after_ms=pause_ms,
        wait_network=True,
    )


def _show_doctor_pdf_preview(page, base: str, doc_id: str, *, source: str = "") -> None:
    """Hover + open doctor preview-pdf (new tab) so the video shows a real PDF."""
    preview = page.locator("#btn-preview-pdf").first
    if not preview.count():
        preview = page.locator("a[href*='preview-pdf']").first
    if preview.count():
        human_hover(page, preview, pause_ms=1200)
        try:
            with page.context.expect_page(timeout=8000) as new_page_info:
                human_click(page, preview, pause_after_ms=400, wait_network=False)
            pdf_page = new_page_info.value
            try:
                pdf_page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            _pause(pdf_page, 2200)
            pdf_page.close()
            ensure_cursor_alive(page)
            _pause(page, 800)
            return
        except Exception:
            pass
    # Fallback: fetch via API (Chromium often aborts page.goto on application/pdf).
    qs = f"?source={source}" if source else ""
    url = f"{base}/api/v1/medical-documents/{doc_id}/preview-pdf{qs}"
    try:
        resp = page.request.get(url)
        ok = resp.ok and "pdf" in (resp.headers.get("content-type") or "").lower()
        # Brief hover on preview control again so the video still shows intent.
        if preview.count():
            human_hover(page, preview, pause_ms=1500)
        if not ok:
            page.goto(url, wait_until="commit")
            _pause(page, 1500)
    except Exception:
        pass
    ensure_cursor_alive(page)
    _pause(page, 800)


def _new_context(browser, folder: Path, *, width: int, height: int, slow_mo: int):
    folder.mkdir(parents=True, exist_ok=True)
    for p in folder.glob("*.webm"):
        # clear only previous output for this run folder temp files later
        if p.suffix == ".webm":
            pass
    return browser.new_context(
        viewport={"width": width, "height": height},
        record_video_dir=str(folder),
        record_video_size={"width": width, "height": height},
    )


def _clear_target(folder: Path, filename: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    if target.exists():
        target.unlink()
    for p in folder.glob("*.webm"):
        # remove leftover playwright temps in this scenario folder
        if p.name.startswith("sc-") or p.name == filename:
            p.unlink(missing_ok=True)


def _record_with(
    *,
    base: str,
    ctx: dict,
    out_dir: Path,
    sid: str,
    slow_mo: int,
    width: int,
    height: int,
    steps: Callable,
) -> Path | None:
    from playwright.sync_api import sync_playwright

    filename = FILENAMES[sid]
    folder = out_dir / sid.lower()
    _clear_target(folder, filename)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_mo)
        context = _new_context(
            browser, folder, width=width, height=height, slow_mo=slow_mo
        )
        page = context.new_page()
        install_cursor(page)
        step_error: Exception | None = None
        try:
            steps(page, base, ctx)
        except Exception as exc:
            step_error = exc
            try:
                page.wait_for_timeout(800)
            except Exception:
                pass
        finally:
            context.close()
            browser.close()

    path = _finalize(folder, filename)
    if path and path.parent != out_dir:
        # hoist to scenariusze/ root for docs paths
        final = out_dir / filename
        if final.exists():
            final.unlink()
        path.replace(final)
        try:
            # clean empty leftover dir
            for leftover in folder.glob("*"):
                leftover.unlink(missing_ok=True)
            folder.rmdir()
        except OSError:
            pass
        path = final
    if step_error:
        raise step_error
    return path


# --- scenario step functions ---


def steps_sc_001(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    entry_id = ctx["sc001_entry_id"]
    login_reception(page, base, pwd)
    _pause(page, 1200)
    page.goto(
        f"{base}/admin/reception/queueentry/{entry_id}/change/",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2000)
    human_select_option(page, page.locator('select[name="entry_status"]'), "CANCELLED")
    human_click(page, page.locator('[name="_save"]').first, wait_network=True)
    _pause(page, 1600)
    page.goto(
        f"{base}/admin/reception/dailyqueue/master-detail/",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2200)
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)
    human_wheel(page, 400, steps=4, pause_ms=350)
    _pause(page, 1800)


def steps_sc_002(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)
    human_wheel(page, 300, steps=3, pause_ms=400)
    _pause(page, 2000)
    page.context.clear_cookies()
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2200)


def steps_sc_003(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    doc_id = ctx["sc003_doc_id"]
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)
    page.goto(f"{base}/doctor/{doc_id}/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    page.wait_for_timeout(2000)
    # Published PDF available via source=published; default preview is pending draft.
    _show_doctor_pdf_preview(page, base, doc_id, source="published")
    page.goto(f"{base}/doctor/{doc_id}/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 1500)
    btn = page.locator("#btn-discard-revision")
    if btn.count():
        page.evaluate(
            "el => { el.hidden = false; el.classList.remove('hidden'); }",
            btn.element_handle(),
        )
        _pause(page, 1500)
        human_hover(page, btn, pause_ms=2000)


def steps_sc_004(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_staff(page, base, pwd, username="screenshot_accounting")
    _pause(page, 1000)
    page.goto(f"{base}/admin/accounting/report/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)
    mode = page.locator('select[name="report_mode"], #id_report_mode').first
    if mode.count():
        for val in ("published", "attended", "ausfall"):
            try:
                human_select_option(page, mode, val, pause_after_ms=1800)
            except Exception:
                pass
    export = page.locator("a", has_text="CSV").first
    if export.count():
        human_hover(page, export, pause_ms=1500)


def steps_sc_005(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2800)
    human_wheel(page, 600, steps=5, pause_ms=350)
    _pause(page, 2000)
    page.context.clear_cookies()
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2200)
    entry_id = ctx.get("sc005_entry_id")
    if entry_id:
        page.goto(
            f"{base}/doctor/open/{entry_id}/?lang=de",
            wait_until="networkidle",
        )
        ensure_cursor_alive(page)
        _pause(page, 2500)


def steps_sc_006(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    event_id = ctx["sc006_event_id"]
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)
    page.goto(f"{base}/admin/outbox/outboxevent/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 1800)
    page.goto(
        f"{base}/admin/outbox/outboxevent/{event_id}/change/",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2500)
    status = page.locator('select[name="status"]')
    if status.count():
        human_select_option(page, status, "PENDING", pause_after_ms=1500)
        # do not save — demo only shows the action
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2200)


def steps_sc_008(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    pid = ctx["sc008_patient_id"]
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception/patient/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 1200)
    search = page.locator("#searchbar")
    if search.count():
        human_fill(page, search, ctx.get("sc008_patient_last", "PortalTypo"))
        search.press("Enter")
        page.wait_for_load_state("networkidle")
        _pause(page, 1800)
    page.goto(
        f"{base}/admin/reception/patient/{pid}/change/",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2500)
    page.goto(f"{base}/?locale=pl", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 1500)
    phone = page.locator('input[name="phone"], input[name="ergebnisse_phone"]').first
    dob = page.locator(
        'input[name="date_of_birth"], input[name="dob"], input[type="date"]'
    ).first
    if phone.count():
        human_fill(page, phone, "0000000000")
    if dob.count():
        human_fill(page, dob, "1990-01-01")
    submit = page.locator('button[type="submit"], input[type="submit"]').first
    if submit.count():
        human_click(page, submit, wait_network=True, pause_after_ms=2200)


def steps_sc_009(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception/patient/", wait_until="networkidle")
    ensure_cursor_alive(page)
    search = page.locator("#searchbar")
    if search.count():
        human_fill(page, search, ctx.get("sc009_parent_last", "FamilieDemo"))
        search.press("Enter")
        page.wait_for_load_state("networkidle")
        _pause(page, 2200)
    page.goto(f"{base}/?locale=pl", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 1500)
    phone = page.locator('input[name="phone"], input[name="ergebnisse_phone"]').first
    if phone.count():
        human_fill(page, phone, ctx.get("sc009_phone", ""), pause_after_ms=1200)
    dob = page.locator(
        'input[name="date_of_birth"], input[name="dob"], input[type="date"]'
    ).first
    if dob.count():
        human_fill(
            page,
            dob,
            ctx.get("sc009_parent_dob", "1980-03-10"),
            pause_after_ms=1500,
        )


def steps_sc_010(page, base: str, ctx: dict) -> None:
    page.goto(f"{base}/?locale=pl", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 1500)
    page.context.add_cookies(
        [
            {
                "name": "sessionid",
                "value": ctx["sc010_session_otp"],
                "domain": cookie_domain(base),
                "path": "/",
            }
        ]
    )
    page.goto(f"{base}/otp/?locale=pl", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2800)
    login_reception(page, base, ctx["password"])
    page.goto(
        f"{base}/admin/reception/patient/?q={ctx.get('sc010_patient_last', 'OtpDemo')}",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2000)


def steps_sc_011(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    suggested = ctx.get("sc011_suggested", "MullerDemo_Hans_1985_03_12.pdf")
    ambiguous = ctx.get("sc011_ambiguous_name", "MullerDemo_Hans.pdf")
    # Ensure web sees AMBIGUOUS listing (shared JSON; independent of prior seeds).
    _write_hidrive_mock_state(
        files=[
            {
                "name": ambiguous,
                "path": f"/incoming/{ambiguous}",
                "size": 1024,
            }
        ],
        list_dir_error=None,
    )
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception/patient/", wait_until="networkidle")
    ensure_cursor_alive(page)
    search = page.locator("#searchbar")
    if search.count():
        human_fill(page, search, ctx.get("sc011_patient_last", "MullerDemo"))
        search.press("Enter")
        page.wait_for_load_state("networkidle")
        _pause(page, 2200)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)
    _scroll_hidrive_section(page)
    # Localized badge text (PL/DE/EN) — CSS class is stable.
    page.locator(".cogito-reception-badge--pending").first.wait_for(
        state="visible", timeout=10000
    )
    human_hover(
        page, page.locator(".cogito-reception-badge--pending").first, pause_ms=900
    )
    proof = REPO_ROOT / "docs" / "manual" / "_build" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(proof / "sc-011-ambiguous.png"), full_page=True)
    _pause(page, 3200)
    # Fix: rename with DOB (shared mock state → web)
    _write_hidrive_mock_state(
        files=[
            {
                "name": suggested,
                "path": f"/incoming/{suggested}",
                "size": 1024,
            }
        ],
        list_dir_error=None,
    )
    _pause(page, 1200)
    page.reload(wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)
    _scroll_hidrive_section(page)
    _pause(page, 2800)


def steps_sc_012(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    rejected = ctx.get("sc012_rejected_name", "rejected_RejectedDemo_Otto.pdf")
    fixed = ctx.get("sc012_fixed_name", "RejectedDemo_Otto.pdf")
    _write_hidrive_mock_state(
        files=[
            {
                "name": rejected,
                "path": f"/incoming/{rejected}",
                "size": 2048,
            }
        ],
        list_dir_error=None,
    )
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)
    _scroll_hidrive_section(page)
    page.locator(".cogito-reception-badge--neutral").first.wait_for(
        state="visible", timeout=10000
    )
    human_hover(
        page, page.locator(".cogito-reception-badge--neutral").first, pause_ms=900
    )
    proof = REPO_ROOT / "docs" / "manual" / "_build" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(proof / "sc-012-rejected.png"), full_page=True)
    _pause(page, 3200)
    # Fix: drop rejected_ prefix / re-upload under proper name
    _write_hidrive_mock_state(
        files=[
            {
                "name": fixed,
                "path": f"/incoming/{fixed}",
                "size": 2048,
            }
        ],
        list_dir_error=None,
    )
    _pause(page, 1200)
    page.reload(wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)
    _scroll_hidrive_section(page)
    _pause(page, 2800)


def steps_sc_027(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    _write_hidrive_mock_state(
        files=[],
        list_dir_error=ctx.get(
            "sc027_hidrive_error", "Demo timeout for SC-027 (fictional)"
        ),
    )
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)
    banner = page.locator(".cogito-reception-banner--warning").first
    banner.wait_for(state="visible", timeout=10000)
    human_hover(page, banner, pause_ms=1200)
    proof = REPO_ROOT / "docs" / "manual" / "_build" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(proof / "sc-027-banner.png"), full_page=True)
    _pause(page, 3500)
    # Recovery: clear timeout so listing works again
    _write_hidrive_mock_state(files=[], list_dir_error=None)
    _pause(page, 1000)
    page.reload(wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)
    _scroll_hidrive_section(page)
    _pause(page, 2800)


def steps_sc_013(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    event_id = ctx["sc013_event_id"]
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)
    page.goto(
        f"{base}/admin/outbox/outboxevent/{event_id}/change/",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2500)
    status = page.locator('select[name="status"]')
    if status.count():
        human_select_option(page, status, "PENDING", pause_after_ms=1800)


def steps_sc_014(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2200)
    page.goto(
        f"{base}/doctor/{ctx['sc014_doc_id']}/?lang=de",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2800)


def steps_sc_015(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    doc_id = ctx["sc015_doc_id"]
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 1800)
    page.goto(
        f"{base}/doctor/{doc_id}/?lang=de",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    page.wait_for_timeout(2000)
    _show_doctor_pdf_preview(page, base, doc_id, source="published")
    page.goto(f"{base}/doctor/{doc_id}/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 1200)
    btn = page.locator("#btn-revoke-publication").first
    if btn.count():
        page.evaluate(
            "el => { el.hidden = false; el.classList.remove('hidden'); }",
            btn.element_handle(),
        )
        human_hover(page, btn, pause_ms=2200)


def steps_sc_016(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_staff(page, base, pwd, username="screenshot_admin")
    page.goto(f"{base}/admin/paper-intake/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)
    entry_id = ctx.get("sc016_entry_id")
    if entry_id:
        page.goto(
            f"{base}/admin/paper-intake/{entry_id}/",
            wait_until="networkidle",
        )
        ensure_cursor_alive(page)
        _pause(page, 2200)
    page.context.clear_cookies()
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2200)


def steps_sc_017(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    entry_id = ctx["sc017_entry_id"]
    login_staff(page, base, pwd, username="screenshot_manager")
    page.goto(f"{base}/admin/paper-intake/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)
    page.goto(f"{base}/admin/paper-intake/{entry_id}/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)
    page.context.clear_cookies()
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)


def steps_sc_018(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_tablet(
        page,
        base,
        pwd,
        ctx.get("sc018_android_unassigned", "screenshot-unassigned-dev"),
    )
    page.goto(f"{base}/tablet/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2800)
    page.context.clear_cookies()
    login_staff(page, base, pwd, username="screenshot_admin")
    page.goto(f"{base}/admin/reception/tabletdevice/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2200)


def steps_sc_019(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)
    human_wheel(page, 400, steps=4, pause_ms=350)
    _pause(page, 1800)
    page.context.clear_cookies()
    login_tablet(page, base, pwd, "screenshot-assigned-dev")
    page.goto(f"{base}/tablet/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)
    qid = (
        str(ctx["queue"].id) if hasattr(ctx.get("queue"), "id") else ctx.get("queue_id")
    )
    if qid:
        page.goto(f"{base}/tablet/queue/{qid}/", wait_until="networkidle")
        ensure_cursor_alive(page)
        _pause(page, 2500)


def steps_sc_020(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/external-upload/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2500)
    entry_id = ctx.get("sc020_entry_id")
    if entry_id:
        page.goto(
            f"{base}/admin/external-upload/{entry_id}/",
            wait_until="networkidle",
        )
        ensure_cursor_alive(page)
        _pause(page, 2800)


def steps_sc_021(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    login_doctor(page, base, pwd)
    page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2200)
    entry_id = ctx.get("sc021_entry_id")
    if entry_id:
        page.goto(
            f"{base}/doctor/open/{entry_id}/?lang=de",
            wait_until="networkidle",
        )
        ensure_cursor_alive(page)
        _pause(page, 2800)


def steps_sc_022(page, base: str, ctx: dict) -> None:
    page.goto(f"{base}/?locale=pl", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 1200)
    page.context.add_cookies(
        [
            {
                "name": "sessionid",
                "value": ctx["sc022_session_doc"],
                "domain": cookie_domain(base),
                "path": "/",
            }
        ]
    )
    page.goto(f"{base}/documents/?locale=pl", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2800)


def steps_sc_023(page, base: str, ctx: dict) -> None:
    steps_sc_022(page, base, {**ctx, "sc022_session_doc": ctx["sc023_session_doc"]})
    login_reception(page, base, ctx["password"])
    page.goto(
        f"{base}/admin/reception/patient/{ctx['sc023_patient_id']}/change/",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2200)


def steps_sc_024(page, base: str, ctx: dict) -> None:
    steps_sc_010(page, base, ctx)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2200)


def steps_sc_025(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    pid = ctx["sc025_patient_id"]
    login_reception(page, base, pwd)
    page.goto(
        f"{base}/admin/reception/patient/{pid}/change/",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2500)
    phone = page.locator('input[name="phone"]').first
    if phone.count():
        human_fill(page, phone, "491111000099", pause_after_ms=1500)


def steps_sc_026(page, base: str, ctx: dict) -> None:
    pwd = ctx["password"]
    event_id = ctx["sc026_event_id"]
    login_reception(page, base, pwd)
    page.goto(
        f"{base}/admin/outbox/outboxevent/{event_id}/change/",
        wait_until="networkidle",
    )
    ensure_cursor_alive(page)
    _pause(page, 2800)
    status = page.locator('select[name="status"]')
    if status.count():
        human_select_option(page, status, "PENDING", pause_after_ms=1800)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    ensure_cursor_alive(page)
    _pause(page, 2000)


STEP_HANDLERS: dict[str, Callable] = {
    "SC-001": steps_sc_001,
    "SC-002": steps_sc_002,
    "SC-003": steps_sc_003,
    "SC-004": steps_sc_004,
    "SC-005": steps_sc_005,
    "SC-006": steps_sc_006,
    "SC-008": steps_sc_008,
    "SC-009": steps_sc_009,
    "SC-010": steps_sc_010,
    "SC-011": steps_sc_011,
    "SC-012": steps_sc_012,
    "SC-013": steps_sc_013,
    "SC-014": steps_sc_014,
    "SC-015": steps_sc_015,
    "SC-016": steps_sc_016,
    "SC-017": steps_sc_017,
    "SC-018": steps_sc_018,
    "SC-019": steps_sc_019,
    "SC-020": steps_sc_020,
    "SC-021": steps_sc_021,
    "SC-022": steps_sc_022,
    "SC-023": steps_sc_023,
    "SC-024": steps_sc_024,
    "SC-025": steps_sc_025,
    "SC-026": steps_sc_026,
    "SC-027": steps_sc_027,
}


def _serialize_ctx(ctx: dict) -> dict:
    out: dict = {}
    for k, v in ctx.items():
        if k in (
            "admin",
            "reception",
            "doctor",
            "tablet",
            "accounting",
            "manager",
            "clinic",
            "queue",
        ):
            if hasattr(v, "id"):
                out[f"{k}_id"] = str(v.id)
            if k == "queue" and hasattr(v, "id"):
                out["queue_id"] = str(v.id)
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    out.setdefault("password", ctx.get("password", "ScreenshotDemo2026!"))
    return out


def _load_ctx(sid: str, ctx_dir: Path) -> dict | None:
    path = ctx_dir / f"{sid.lower()}.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _record_sc007(base: str, slow_mo: int, width: int, height: int) -> Path | None:
    from scripts.record_import_troubleshooting_video import (
        record_import_troubleshooting_video,
    )
    from scripts.manual_demo.seed_import_troubleshooting import (
        seed_import_troubleshooting_demo,
    )

    setup_django()
    ctx: dict = {}
    seed_import_troubleshooting_demo(ctx)
    out = REPO_ROOT / "docs" / "manual" / "assets" / "videos" / "reception"
    return record_import_troubleshooting_video(
        base, ctx, out, slow_mo=slow_mo, width=width, height=height
    )


def record_one(
    sid: str,
    *,
    base: str,
    out_dir: Path,
    slow_mo: int,
    width: int,
    height: int,
    skip_django: bool,
    ctx_dir: Path,
) -> Path | None:
    if sid == "SC-007":
        if skip_django:
            from scripts.record_import_troubleshooting_video import (
                record_import_troubleshooting_video,
            )

            ctx_path = (
                REPO_ROOT
                / "docs"
                / "manual"
                / "_build"
                / "import-troubleshooting-ctx.json"
            )
            if not ctx_path.is_file():
                print(
                    "SC-007: brak ctx — uruchom seed_import_troubleshooting w Dockerze",
                    file=sys.stderr,
                )
                return None
            ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
            out = REPO_ROOT / "docs" / "manual" / "assets" / "videos" / "reception"
            return record_import_troubleshooting_video(
                base, ctx, out, slow_mo=slow_mo, width=width, height=height
            )
        return _record_sc007(base, slow_mo, width, height)

    handler = STEP_HANDLERS.get(sid)
    if not handler:
        print(f"Brak handlera dla {sid}", file=sys.stderr)
        return None

    if skip_django:
        ctx = _load_ctx(sid, ctx_dir)
        if not ctx:
            print(
                f"Brak ctx dla {sid} w {ctx_dir} — "
                f"docker compose exec web python scripts/manual_demo/seed_scenarios.py "
                f"--scenario {sid.lower()} --write-ctx",
                file=sys.stderr,
            )
            return None
    else:
        setup_django()
        ctx = seed_scenario(sid)

    return _record_with(
        base=base,
        ctx=ctx,
        out_dir=out_dir,
        sid=sid,
        slow_mo=slow_mo,
        width=width,
        height=height,
        steps=handler,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nagrywa WebM scenariuszy SC-001–SC-027 (wolne akcje demo)."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SCREENSHOT_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="np. sc-001 (wielokrotnie)",
    )
    parser.add_argument("--all", action="store_true", help="Wszystkie scenariusze")
    parser.add_argument(
        "--priority",
        choices=["high", "medium", "low", "high+medium"],
        help="Zestaw wg backlogu w scenariusze.md",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--slow-mo", type=int, default=500, help="Opóźnienie ms (domyślnie 500)"
    )
    parser.add_argument("--video-width", type=int, default=1280)
    parser.add_argument("--video-height", type=int, default=720)
    parser.add_argument("--ctx-dir", type=Path, default=DEFAULT_CTX_DIR)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    skip_django = os.environ.get("SCREENSHOT_SKIP_DJANGO", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        print(
            "Install: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    selected: list[str] = []
    if args.all:
        selected = list(FILENAMES.keys())
    elif args.priority == "high":
        selected = list(PRIORITY_HIGH)
    elif args.priority == "medium":
        selected = list(PRIORITY_MEDIUM)
    elif args.priority == "low":
        selected = list(PRIORITY_LOW)
    elif args.priority == "high+medium":
        selected = list(PRIORITY_HIGH) + list(PRIORITY_MEDIUM)
    elif args.scenarios:
        selected = [_norm_sid(s) for s in args.scenarios]
    else:
        parser.error("Podaj --scenario, --all lub --priority")

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx_dir = args.ctx_dir.resolve()

    ok = 0
    fail = 0
    for sid in selected:
        if sid not in FILENAMES:
            print(f"SKIP nieznany: {sid}", file=sys.stderr)
            fail += 1
            continue
        print(f"=== {sid} ===")
        try:
            path = record_one(
                sid,
                base=base,
                out_dir=out_dir,
                slow_mo=args.slow_mo,
                width=args.video_width,
                height=args.video_height,
                skip_django=skip_django,
                ctx_dir=ctx_dir,
            )
            step_warn = None
        except Exception as exc:
            # Video may still have been written before the raise
            step_warn = exc
            filename = FILENAMES.get(sid)
            path = (out_dir / filename) if filename else None
            if path and not path.is_file():
                path = None
            print(f"WARN {sid} steps: {exc}", file=sys.stderr)

        if path and path.is_file():
            msg = f"OK {sid}: {path}"
            if step_warn:
                msg += " (partial walkthrough)"
            print(msg)
            ok += 1
        else:
            print(f"WARN {sid}: brak .webm", file=sys.stderr)
            fail += 1

    print(f"Done: ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
