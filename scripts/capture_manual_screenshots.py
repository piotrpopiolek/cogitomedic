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
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

# Repo root = parent of scripts/
REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "manual" / "assets" / "screenshots"


def _setup_django() -> None:
    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cogitomedica.settings")
    import django

    django.setup()


def _seed(ctx: dict) -> None:
    from django.contrib.sessions.backends.db import SessionStore
    from django.utils import timezone

    from apps.core.api_utils import assign_group_to_test_user
    from apps.intake.models import IntakeDocumentVersion, IntakePdfStatus, IntakeStatus, PatientIntakeForm
    from apps.medical.models import MedicalDocument
    from apps.medical.services import create_or_get_medical_document, save_draft_document_version
    from apps.reception.models import (
        ClinicSite,
        ConsultingRoom,
        DailyQueue,
        Patient,
        PatientFormSession,
        QueueEntry,
        QueueEntryStatus,
        QueueStatus,
        TabletDevice,
    )
    from apps.reception.services import issue_tablet_session_latest_wins
    from apps.users.models import StaffUser

    pwd = "ScreenshotDemo2026!"

    def _user(username: str, email: str, *groups: str) -> StaffUser:
        u, _ = StaffUser.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": "Screenshot",
                "last_name": username,
                "is_staff": True,
                "is_active": True,
            },
        )
        u.set_password(pwd)
        u.email = email
        u.is_staff = True
        u.is_active = True
        u.save()
        u.groups.clear()
        for g in groups:
            assign_group_to_test_user(u, g)
        return u

    admin = _user("screenshot_admin", "screenshot_admin@example.invalid", "Admin")
    admin.is_superuser = True
    admin.save()

    reception = _user("screenshot_reception", "screenshot_reception@example.invalid", "Reception")
    doctor = _user("screenshot_doctor", "screenshot_doctor@example.invalid", "Doctor")
    tablet_u = _user("screenshot_tablet", "screenshot_tablet@example.invalid", "Tablet")

    clinic, _ = ClinicSite.objects.get_or_create(
        code="SCR",
        defaults={"name": "Screenshot Klinik Demo"},
    )
    room, _ = ConsultingRoom.objects.get_or_create(
        clinic_site=clinic,
        code="R1",
        defaults={"name": "Raum 1"},
    )

    for u in (reception, doctor, tablet_u):
        u.clinic_sites.add(clinic)

    today = timezone.now().date()
    queue, _ = DailyQueue.objects.get_or_create(
        queue_date=today,
        clinic_site=clinic,
        consulting_room=room,
        defaults={
            "status": QueueStatus.OPEN,
            "created_by_user": reception,
            "assigned_doctor": doctor,
            "shift_code": "FULL_DAY",
        },
    )
    queue.assigned_doctor = doctor
    queue.status = QueueStatus.OPEN
    queue.save(update_fields=["assigned_doctor", "status", "updated_at"])

    # Remove previous screenshot rows (MedicalDocument blocks QueueEntry delete)
    MedicalDocument.objects.filter(queue_entry__daily_queue=queue).delete()
    QueueEntry.objects.filter(daily_queue=queue, position_no__in=(1, 2, 3)).delete()

    p_done, _ = Patient.objects.get_or_create(
        phone="1111111111111",
        defaults={
            "first_name": "Anna",
            "last_name": "Demo",
            "date_of_birth": date(1985, 5, 15),
            "email": "anna.demo@example.invalid",
        },
    )
    p_done.clinic_sites.add(clinic)

    entry_done = QueueEntry.objects.create(
        daily_queue=queue,
        patient=p_done,
        position_no=1,
        entry_status=QueueEntryStatus.PATIENT_COMPLETED,
        created_by_user=reception,
    )
    session_done = PatientFormSession.objects.create(
        queue_entry=entry_done,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(minutes=120),
        consumed_at=timezone.now(),
        created_by_user=reception,
    )
    entry_done.active_session = session_done
    entry_done.save(update_fields=["active_session", "updated_at"])

    intake_done = PatientIntakeForm.objects.create(
        queue_entry=entry_done,
        session=session_done,
        form_status=IntakeStatus.SUBMITTED,
        anamnesis_payload={"answers": []},
        submitted_at=timezone.now(),
        signature_file_path="/tmp/screenshot-signature.png",
        signature_sha256="a" * 64,
    )

    intake_doc_ver, _ = IntakeDocumentVersion.objects.get_or_create(
        intake_form=intake_done,
        version_no=1,
        defaults={
            "form_locale": "de-DE",
            "snapshot_payload": {},
            "pdf_generation_status": IntakePdfStatus.PENDING,
        },
    )

    md = create_or_get_medical_document(
        queue_entry_id=entry_done.id,
        intake_form_id=intake_done.id,
        created_by_user_id=doctor.id,
    )
    medical_payload_v1 = {
        "schema_version": 1,
        "authoring_locale": "de-DE",
        "overall_image_assessment": "NO_CONTROL_NEEDED",
        "lesions": [
            {
                "lesion_numbers": [2, 3],
                "dermatoscopic_features": [],
                "clinical_assessment": "UNREMARKABLE",
                "malignancy_risk": "NO_SUSPICION",
                "generated_text": "Demo-Läsionen Nr. 2, 3.",
                "edited_text": "Demo-Läsionen Nr. 2, 3.",
            }
        ],
        "summary_generated_text": "Zusammenfassung Demo.",
        "summary_edited_text": "Zusammenfassung Demo.",
    }
    save_draft_document_version(
        medical_document_id=md.id,
        updated_by_user_id=doctor.id,
        medical_payload=medical_payload_v1,
        diagnosis_code="DEMO",
        procedure_code="DEMO",
    )

    p_err, _ = Patient.objects.get_or_create(
        phone="2222222222222",
        defaults={
            "first_name": "Ben",
            "last_name": "Offen",
            "date_of_birth": date(1990, 1, 1),
            "email": "ben.offen@example.invalid",
        },
    )
    p_err.clinic_sites.add(clinic)
    entry_err = QueueEntry.objects.create(
        daily_queue=queue,
        patient=p_err,
        position_no=2,
        entry_status=QueueEntryStatus.IN_PROGRESS,
        created_by_user=reception,
    )
    sess_err = PatientFormSession.objects.create(
        queue_entry=entry_err,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(minutes=120),
        created_by_user=reception,
    )
    entry_err.active_session = sess_err
    entry_err.save(update_fields=["active_session", "updated_at"])
    PatientIntakeForm.objects.create(
        queue_entry=entry_err,
        session=sess_err,
        form_status=IntakeStatus.IN_PROGRESS,
        anamnesis_payload={},
    )

    p_tab, _ = Patient.objects.get_or_create(
        phone="3333333333333",
        defaults={
            "first_name": "Clara",
            "last_name": "Tablet",
            "date_of_birth": date(1977, 7, 7),
            "email": "clara.tablet@example.invalid",
        },
    )
    p_tab.clinic_sites.add(clinic)
    entry_tab = QueueEntry.objects.create(
        daily_queue=queue,
        patient=p_tab,
        position_no=3,
        entry_status=QueueEntryStatus.WAITING,
        created_by_user=reception,
    )
    issued = issue_tablet_session_latest_wins(
        queue_entry_id=entry_tab.id,
        created_by_user_id=tablet_u.id,
        form_locale="de-DE",
        expires_in_minutes=120,
        tablet_device_id=None,
    )

    p_portal, _ = Patient.objects.get_or_create(
        phone="17612345678",
        defaults={
            "first_name": "Portal",
            "last_name": "Patient",
            "date_of_birth": date(2000, 3, 20),
            "email": "portal.patient@example.invalid",
        },
    )
    p_portal.date_of_birth = date(2000, 3, 20)
    p_portal.save(update_fields=["date_of_birth", "updated_at"])

    TabletDevice.objects.update_or_create(
        android_id="screenshot-unassigned-dev",
        defaults={"is_active": True, "clinic_site": None},
    )
    dev_assigned, _ = TabletDevice.objects.update_or_create(
        android_id="screenshot-assigned-dev",
        defaults={"is_active": True, "clinic_site": clinic},
    )

    s_otp = SessionStore()
    s_otp.create()
    s_otp["ergebnisse_phone"] = "17612345678"
    s_otp["ergebnisse_dob"] = "2000-03-20"
    s_otp.save()

    s_doc = SessionStore()
    s_doc.create()
    s_doc["patient_results_patient_id"] = str(p_portal.id)
    s_doc["patient_results_verified_at"] = timezone.now().isoformat()
    s_doc.save()

    ctx.update(
        {
            "password": pwd,
            "admin": admin,
            "reception": reception,
            "doctor": doctor,
            "tablet": tablet_u,
            "queue": queue,
            "clinic": clinic,
            "medical_document_id": str(md.id),
            "queue_entry_err_id": str(entry_err.id),
            "queue_entry_tablet_id": str(entry_tab.id),
            "intake_form_tablet_id": str(issued.intake_form_id),
            "intake_form_done_id": str(intake_done.id),
            "intake_document_version_id": str(intake_doc_ver.id),
            "tablet_device_assigned_id": str(dev_assigned.id),
            "session_otp_key": s_otp.session_key,
            "session_doc_key": s_doc.session_key,
            "portal_phone": "17612345678",
            "portal_dob": "2000-03-20",
        }
    )


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


def _cookie_domain(base: str) -> str:
    host = urlparse(base).hostname or "127.0.0.1"
    return host


def _login_admin(page, base: str, password: str) -> None:
    page.goto(f"{base}/admin/login/", wait_until="networkidle")
    page.locator('input[name="username"]').fill("screenshot_admin")
    page.locator('input[name="password"]').fill(password)
    page.locator('#login-form button[type="submit"]').click()
    page.wait_for_load_state("networkidle")


def _login_doctor(page, base: str, password: str) -> None:
    page.goto(f"{base}/doctor/login/", wait_until="networkidle")
    page.locator('input[name="username"]').fill("screenshot_doctor")
    page.locator('input[name="password"]').fill(password)
    page.locator('form button[type="submit"]').first.click()
    page.wait_for_load_state("networkidle")


def _login_tablet(page, base: str, password: str, android_id: str) -> None:
    page.goto(f"{base}/tablet/login/", wait_until="networkidle")
    page.evaluate(
        """(id) => { const el = document.querySelector('input[name="android_id"]'); if (el) el.value = id; }""",
        android_id,
    )
    page.locator('input[name="username"]').fill("screenshot_tablet")
    page.locator('input[name="password"]').fill(password)
    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")


def _shot(page, name: str) -> None:
    path = OUTPUT_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("SCREENSHOT_BASE_URL", "http://127.0.0.1:8000"))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    _setup_django()
    ctx: dict = {}
    _seed(ctx)
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
        _login_admin(page, base, pwd)
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
        _login_doctor(page, base, pwd)
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
        _login_tablet(tpage, base, pwd, "screenshot-assigned-dev")
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
        ck_host = _cookie_domain(base)
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
