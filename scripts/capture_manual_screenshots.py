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
  # Tylko portal pacjenta (login / OTP / dokumenty):
  python scripts/capture_manual_screenshots.py --only=patient-portal --base-url http://127.0.0.1:8000
  # Tylko zrzuty docs/manual/06 (bez pełnego importu Django na hoście — najpierw seed w docelowej bazie):
  SCREENSHOT_SKIP_DJANGO=1 python scripts/capture_manual_screenshots.py \\
    --only=reception-patient-personal-data --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.manual_demo import (
    cookie_domain,
    login_admin,
    login_doctor,
    login_reception,
    login_staff,
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


def _shot_locator(locator, name: str) -> None:
    path = OUTPUT_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    locator.screenshot(path=str(path))


def _minimal_pdf_path() -> Path:
    from scripts.manual_demo.scenario_helpers import minimal_demo_pdf_bytes

    path = Path(tempfile.gettempdir()) / "cogito-manual-external-demo.pdf"
    path.write_bytes(minimal_demo_pdf_bytes(title="Demo external upload"))
    return path


def _set_unfold_theme(page, theme: str) -> None:
    """Apply light/dark on the live page.

    Product ships ``unfold-force-light.js`` (resets theme on every load), so dark
    shots must mutate the DOM **after** load — do not reload afterwards.
    """
    page.evaluate(
        """(theme) => {
          const root = document.documentElement;
          try {
            localStorage.setItem('theme', theme);
            localStorage.setItem('unfold.theme', theme);
            localStorage.setItem('color-theme', theme);
          } catch (e) {}
          root.setAttribute('data-theme', theme);
          root.setAttribute('data-color-scheme', theme);
          root.style.colorScheme = theme;
          if (theme === 'dark') {
            root.classList.add('dark');
          } else {
            root.classList.remove('dark');
          }
        }""",
        theme,
    )
    page.wait_for_timeout(400)


def capture_reception_patient_personal_data_screenshots(
    page, base: str, pwd: str, shot_fn
) -> None:
    """Zrzuty dla docs/manual/06-zmiana-danych-pacjenta.md (rola Reception).

    Scenariusz: zmiana **imienia, nazwiska, daty urodzenia i telefonu** (stan wyjściowy
    pacjenta demo po seedzie — Anna Demo / 1985-05-15 / 1111111111111).
    Po zrzutach dane przywracane są w formularzu; pełny `seed_manual_demo` utrwala baseline w bazie.
    """
    patient_changelist = f"{base}/admin/reception/patient/"
    baseline = ("Anna", "Demo", "1985-05-15", "1111111111111")
    edited = ("Marianna", "Kowalska", "1992-08-14", "1222222222222")

    page.context.clear_cookies()
    login_reception(page, base, pwd)
    page.goto(patient_changelist, wait_until="networkidle")
    shot_fn(page, "reception-patient-01-changelist.png")
    # E-mail demo jest jednoznaczny na liście (uniknie wybrania „innego” Kowalskiego/Demo).
    page.locator('input[name="q"]').fill("anna.demo@example.invalid")
    page.locator("#changelist-search button[type='submit']").click()
    page.wait_for_load_state("networkidle")
    shot_fn(page, "reception-patient-02-search-results.png")
    page.locator("table#result_list tbody tr").first.locator("th a").click()
    page.wait_for_load_state("networkidle")
    shot_fn(page, "reception-patient-03-identity-before-edit.png")
    page.locator('input[name="first_name"]').fill(edited[0])
    page.locator('input[name="last_name"]').fill(edited[1])
    page.locator('input[name="date_of_birth"]').fill(edited[2])
    page.locator('input[name="phone"]').fill(edited[3])
    page.locator('input[name="first_name"]').scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    shot_fn(page, "reception-patient-04-identity-after-edit.png")
    page.locator('[name="_save"]').first.click()
    page.wait_for_load_state("networkidle")
    shot_fn(page, "reception-patient-05-save-confirmation.png")
    # Przywróć baseline w DB (bez zrzutu). Po zapisie widok może nie być klasycznym formularzem — znów otwórz rekord z listy.
    page.goto(patient_changelist, wait_until="networkidle")
    page.locator('input[name="q"]').fill("anna.demo@example.invalid")
    page.locator("#changelist-search button[type='submit']").click()
    page.wait_for_load_state("networkidle")
    page.locator("table#result_list tbody tr").first.locator("th a").click()
    page.wait_for_load_state("networkidle")
    page.locator('input[name="first_name"]').fill(baseline[0])
    page.locator('input[name="last_name"]').fill(baseline[1])
    page.locator('input[name="date_of_birth"]').fill(baseline[2])
    page.locator('input[name="phone"]').fill(baseline[3])
    page.locator('[name="_save"]').first.click()
    page.wait_for_load_state("networkidle")


def capture_external_upload_screenshots(page, base: str, pwd: str, ctx: dict) -> None:
    entry_id = ctx.get("external_upload_entry_id")
    if not entry_id:
        print("WARN: skip external-upload shots (no entry id)", file=sys.stderr)
        return

    page.context.clear_cookies()
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/", wait_until="networkidle")
    link = page.locator("a[href*='/admin/external-upload']").first
    if link.count():
        try:
            link.scroll_into_view_if_needed(timeout=5000)
            page.wait_for_timeout(300)
        except Exception:
            pass
        container = (
            page.locator("nav, aside, [data-sidebar]")
            .filter(has=page.locator("a[href*='/admin/external-upload']"))
            .first
        )
        try:
            if container.count():
                _shot_locator(container, "reception-external-upload-00-sidebar.png")
            else:
                _shot_locator(link, "reception-external-upload-00-sidebar.png")
        except Exception:
            _shot(page, "reception-external-upload-00-sidebar.png")
    else:
        _shot(page, "reception-external-upload-00-sidebar.png")

    page.goto(f"{base}/admin/external-upload/", wait_until="networkidle")
    _shot(page, "reception-external-upload-01-hub.png")

    page.goto(f"{base}/admin/external-upload/{entry_id}/", wait_until="networkidle")
    _shot(page, "reception-external-upload-02-entry-identity.png")

    pdf_path = _minimal_pdf_path()
    file_input = page.locator("#id_pdf_file")
    if file_input.count():
        file_input.set_input_files(str(pdf_path))
        page.wait_for_timeout(200)
        upload_form = page.locator('form:has(input[name="action"][value="upload"])')
        upload_form.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
    _shot(page, "reception-external-upload-03-entry-upload-select.png")

    preview = page.locator("a[href*='preview-pdf'], a[target='_blank']").filter(
        has_text="PDF"
    )
    if preview.count() == 0:
        preview = page.locator("a[href*='preview-pdf']")
    if preview.count():
        try:
            preview.first.scroll_into_view_if_needed(timeout=5000)
            page.wait_for_timeout(200)
        except Exception:
            pass
    _shot(page, "reception-external-upload-04-preview.png")

    publish_action = page.locator('input[name="action"][value="publish"]')
    if publish_action.count():
        try:
            publish_action.first.scroll_into_view_if_needed(timeout=5000)
            page.wait_for_timeout(200)
        except Exception:
            pass
    ack = page.locator('input[name="verification_ack"]')
    if ack.count():
        try:
            ack.check(timeout=3000)
        except Exception:
            pass
    _shot(page, "reception-external-upload-05-publish-confirm.png")


def capture_accounting_screenshots(page, base: str, pwd: str) -> None:
    page.context.clear_cookies()
    login_staff(page, base, pwd, username="screenshot_accounting")
    page.goto(f"{base}/admin/accounting/report/", wait_until="networkidle")
    _set_unfold_theme(page, "light")
    _shot(page, "accounting-01-report-light.png")
    _set_unfold_theme(page, "dark")
    _shot(page, "accounting-02-report-dark.png")
    _set_unfold_theme(page, "light")


def capture_paper_intake_screenshots(page, base: str, pwd: str, ctx: dict) -> None:
    entry_id = ctx.get("paper_intake_entry_id")
    if not entry_id:
        print("WARN: skip paper-intake shots (no entry id)", file=sys.stderr)
        return

    page.context.clear_cookies()
    login_staff(page, base, pwd, username="screenshot_admin")
    page.goto(f"{base}/admin/paper-intake/", wait_until="networkidle")
    _shot(page, "paper-intake-01-hub.png")

    page.goto(f"{base}/admin/paper-intake/{entry_id}/", wait_until="networkidle")
    reason = page.locator("#id_reason_auth").first
    if reason.count() == 0:
        reason = page.locator("textarea").first
    if reason.count():
        reason.fill("Demo: awaria tabletu — ścieżka papierowa (fikcyjna)")
        page.wait_for_timeout(200)
    _shot(page, "paper-intake-02-entry-authorize.png")

    auth_form = page.locator("form").filter(has=page.locator("#id_reason_auth"))
    if auth_form.count() == 0:
        auth_form = page.locator("form").filter(
            has=page.locator('input[name="action"][value="authorize"]')
        )
    if auth_form.count():
        try:
            auth_form.locator('button[type="submit"]').first.click(timeout=10000)
            page.wait_for_load_state("networkidle")
        except Exception as exc:
            print(f"WARN: paper-intake authorize submit failed: {exc}", file=sys.stderr)
    page.wait_for_timeout(400)
    revoke_reason = page.locator("#id_reason_revoke").first
    if revoke_reason.count():
        revoke_reason.fill("Demo: cofnięcie autoryzacji (fikcyjne)")
        page.wait_for_timeout(200)
    _shot(page, "paper-intake-03-entry-revoke.png")


def capture_hidrive_dashboard_screenshot(page, base: str, pwd: str) -> None:
    page.context.clear_cookies()
    login_reception(page, base, pwd)
    page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
    section = page.locator("text=HiDrive").first
    if section.count():
        section.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
    # Prefer the missing-results card/table if present.
    table = (
        page.locator("table")
        .filter(has_text="NoPdfDemo")
        .or_(page.locator("table").filter(has_text="HiDrive"))
    )
    if table.count():
        card = table.first.locator(
            "xpath=ancestor::div[contains(@class,'rounded') or contains(@class,'border')][1]"
        )
        if card.count():
            _shot_locator(card, "reception-hidrive-01-missing-results.png")
            return
    _shot(page, "reception-hidrive-01-missing-results.png")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SCREENSHOT_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--only",
        choices=("all", "patient-portal", "reception-patient-personal-data"),
        default="all",
        help=(
            "Domyślnie pełny zestaw z checklisty; "
            "patient-portal = login/OTP/dokumenty; "
            "reception-patient-personal-data = rozdz. 06."
        ),
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    skip_django = (
        os.environ.get("SCREENSHOT_SKIP_DJANGO", "").strip().lower()
        in ("1", "true", "yes")
        and args.only == "reception-patient-personal-data"
    )
    if skip_django:
        pwd = os.environ.get("SCREENSHOT_DEMO_PASSWORD", "ScreenshotDemo2026!")
        ctx: dict = {}
    else:
        setup_django()
        ctx = {}
        seed_manual_demo(ctx)
        pwd = ctx["password"]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Install: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.only == "all":
        _draw_overview_png(OUTPUT_DIR / "overview-01-process-diagram.png")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # --- Public / login pages ---
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        if args.only == "reception-patient-personal-data":
            capture_reception_patient_personal_data_screenshots(page, base, pwd, _shot)
            browser.close()
            print(f"Done (reception-patient-personal-data). PNG in {OUTPUT_DIR}")
            return 0

        if args.only == "patient-portal":
            page.goto(f"{base}/?locale=pl", wait_until="networkidle")
            _shot(page, "patient-01-login.png")
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
            print(f"Done (patient-portal). PNG in {OUTPUT_DIR}")
            return 0

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

        page.goto(
            f"{base}/admin/reception/dailyqueue/master-detail/",
            wait_until="networkidle",
        )
        _shot(page, "reception-04-master-detail.png")

        from django.urls import reverse

        imp_url = f"{base}{reverse('admin:reception_dailyqueue_import_xlsx')}"
        page.goto(imp_url, wait_until="networkidle")
        _shot(page, "reception-06-import-xlsx.png")
        _shot(page, "admin-03-import-xlsx.png")

        page.goto(
            f"{base}{reverse('admin:reception_queueentry_add')}",
            wait_until="networkidle",
        )
        _shot(page, "reception-05-queue-entry-add.png")

        page.goto(f"{base}/admin/intake-documents/", wait_until="networkidle")
        _shot(page, "reception-07-intake-documents-list.png")

        iv_id = ctx.get("intake_document_version_id")
        if iv_id:
            page.goto(
                f"{base}/admin/intake-documents/{iv_id}/", wait_until="networkidle"
            )
            _shot(page, "reception-08-intake-document-detail.png")

        page.goto(f"{base}/admin/", wait_until="networkidle")
        _shot(page, "admin-01-index.png")

        page.goto(
            f"{base}{reverse('admin:users_staffuser_change', args=[ctx['admin'].id])}",
            wait_until="networkidle",
        )
        _shot(page, "admin-02-staff-user.png")

        # --- Reception: zmiana danych pacjenta (docs/manual/06-zmiana-danych-pacjenta.md) ---
        capture_reception_patient_personal_data_screenshots(page, base, pwd, _shot)

        # --- External upload hub (07) ---
        capture_external_upload_screenshots(page, base, pwd, ctx)

        # --- HiDrive missing-results section on reception dashboard ---
        capture_hidrive_dashboard_screenshot(page, base, pwd)

        # --- Paper intake (admin) ---
        capture_paper_intake_screenshots(page, base, pwd, ctx)

        # --- Accounting report (08) ---
        capture_accounting_screenshots(page, base, pwd)

        # --- Doctor ---
        # Restore a matching lab PDF so DRAFT detail passes the HiDrive gate
        # (extras seed clears /incoming for the missing-results dashboard shot).
        # Avoid Django ORM here — Playwright sync API sets an async context.
        from scripts.manual_demo.scenario_helpers import (
            minimal_demo_pdf_bytes,
            seed_mock_incoming,
        )

        anna_name = ctx.get("anna_demo_incoming_pdf") or "Demo_Anna.pdf"
        seed_mock_incoming(
            [{"name": anna_name}],
            file_bytes=minimal_demo_pdf_bytes(title="Demo lab Anna"),
        )

        page.context.clear_cookies()
        login_doctor(page, base, pwd)
        page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
        _shot(page, "doctor-02-list-filters.png")

        page.goto(
            f"{base}/doctor/open/{ctx['queue_entry_err_id']}/?lang=de",
            wait_until="networkidle",
        )
        _shot(page, "doctor-03-error-no-intake.png")

        page.goto(
            f"{base}/doctor/{ctx['medical_document_id']}/?lang=de",
            wait_until="networkidle",
        )
        page.wait_for_timeout(2000)
        # Fallback: if lab gate still blocks draft, use open-revision demo (rich payload).
        if page.locator("#btn-save-draft").count() == 0:
            rev_fallback = ctx.get("revision_demo_doc_id")
            if rev_fallback:
                page.goto(
                    f"{base}/doctor/{rev_fallback}/?lang=de",
                    wait_until="networkidle",
                )
                page.wait_for_timeout(1800)
        # Scroll to lesion groups so the filled Befund is visible.
        page.evaluate("""() => {
              const markers = document.querySelectorAll(
                '#lesion-groups, [data-lesion-group], .lesion-group, textarea'
              );
              for (const g of markers) {
                if (g.closest('form') || g.id === 'lesion-groups') {
                  g.scrollIntoView({ block: 'center' });
                  break;
                }
              }
              window.scrollBy(0, 180);
            }""")
        page.wait_for_timeout(600)
        _shot(page, "doctor-04-befund-section.png")

        # Action bar: save draft / publish / preview (draft).
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
        _shot(page, "doctor-05-actions-draft.png")

        # Preview PDF (WeasyPrint) + published doc with COMPLETED mock PDF status.
        page.goto(
            f"{base}/doctor/{ctx['medical_document_id']}/?lang=de",
            wait_until="networkidle",
        )
        page.wait_for_timeout(1000)
        preview = page.locator("#btn-preview-pdf").first
        if preview.count():
            try:
                with page.expect_popup(timeout=8000) as popup_info:
                    preview.click()
                pdf_page = popup_info.value
                pdf_page.wait_for_load_state("domcontentloaded")
                pdf_page.wait_for_timeout(1200)
                pdf_page.close()
            except Exception:
                page.goto(
                    f"{base}/api/v1/medical-documents/{ctx['medical_document_id']}/preview-pdf",
                    wait_until="load",
                )
                page.wait_for_timeout(800)

        portal_doc = ctx.get("portal_published_doc_id")
        if portal_doc:
            page.goto(f"{base}/doctor/?lang=de", wait_until="networkidle")
            page.wait_for_timeout(800)
            page.goto(
                f"{base}/doctor/{portal_doc}/?lang=de",
                wait_until="networkidle",
            )
            page.wait_for_timeout(1500)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(400)
            _shot(page, "doctor-06-published-status.png")
            pub_preview = page.locator(
                "a[href*='preview-pdf'][href*='source=published'], "
                "#btn-preview-pdf, a[href*='preview-pdf']"
            ).first
            if pub_preview.count():
                try:
                    with page.expect_popup(timeout=8000) as popup_info:
                        pub_preview.click()
                    pdf_page = popup_info.value
                    pdf_page.wait_for_load_state("domcontentloaded")
                    pdf_page.wait_for_timeout(1000)
                    pdf_page.close()
                except Exception:
                    pass

        # Open revision + resend SMS checkbox.
        rev_doc = ctx.get("revision_demo_doc_id")
        if rev_doc:
            page.goto(f"{base}/doctor/{rev_doc}/?lang=de", wait_until="networkidle")
            page.wait_for_timeout(1800)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            resend = page.locator("#resend_sms").first
            if resend.count():
                try:
                    resend.check(force=True)
                except Exception:
                    pass
            page.wait_for_timeout(400)
            _shot(page, "doctor-07-revision-resend-sms.png")

        # Revoke confirmation modal.
        revoke_doc = ctx.get("revoke_demo_doc_id") or portal_doc
        if revoke_doc:
            page.goto(f"{base}/doctor/{revoke_doc}/?lang=de", wait_until="networkidle")
            page.wait_for_timeout(1800)
            btn = page.locator("#btn-revoke-publication").first
            if btn.count():
                page.evaluate(
                    "el => { el.hidden = false; el.classList.remove('hidden'); }",
                    btn.element_handle(),
                )
                page.wait_for_timeout(300)
                btn.click()
                page.wait_for_timeout(800)
                _shot(page, "doctor-08-revoke-modal.png")
                cancel = page.locator("#revision-modal-cancel").first
                if cancel.count():
                    cancel.click()
                    page.wait_for_timeout(400)

        # --- Tablet unassigned ---
        tpage.context.clear_cookies()
        tpage.goto(f"{base}/tablet/login/", wait_until="networkidle")
        tpage.evaluate(
            "() => { document.querySelector('#tablet-login-android-id').value = 'screenshot-unassigned-dev'; }"
        )
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
