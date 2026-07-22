"""Shared helpers for scenario video seeds (fictional demo data only — RODO)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

DEMO_PASSWORD = "ScreenshotDemo2026!"
DEMO_PAYLOAD = {
    "schema_version": 1,
    "authoring_locale": "de-DE",
    "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
    "fitzpatrick_type": "TYPE_III",
    "overall_image_assessment": "NO_CONTROL_NEEDED",
    "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
    "final_assessment": "NO_HIGH_GRADE_SUSPICION",
    "lesions": [],
    "summary_generated_text": "Zusammenfassung Demo Szenario.",
    "summary_edited_text": "Zusammenfassung Demo Szenario.",
}


def assert_demo_seed_dev_only() -> None:
    from django.conf import settings

    environment = (getattr(settings, "ENVIRONMENT", "dev") or "dev").strip().lower()
    if environment != "dev":
        raise RuntimeError(
            f"Demo seed must only run in dev (ENVIRONMENT={environment!r})"
        )


def ensure_screenshot_users(ctx: dict) -> None:
    """Ensure screenshot_* staff, SCR clinic, and today queue exist."""
    from scripts.manual_demo.seed import seed_manual_demo

    seed_manual_demo(ctx)
    ctx.setdefault("password", DEMO_PASSWORD)


def ensure_accounting_user(ctx: dict) -> None:
    from apps.core.api_utils import assign_group_to_test_user
    from apps.users.models import StaffUser

    pwd = ctx.get("password") or DEMO_PASSWORD
    u, _ = StaffUser.objects.get_or_create(
        username="screenshot_accounting",
        defaults={
            "email": "screenshot_accounting@example.invalid",
            "first_name": "Screenshot",
            "last_name": "Accounting",
            "is_staff": True,
            "is_active": True,
        },
    )
    u.set_password(pwd)
    u.is_staff = True
    u.is_active = True
    u.save()
    u.groups.clear()
    assign_group_to_test_user(u, "Accounting")
    clinic = ctx["clinic"]
    u.clinic_sites.add(clinic)
    ctx["accounting"] = u


def ensure_manager_user(ctx: dict) -> None:
    from apps.core.api_utils import assign_group_to_test_user
    from apps.users.models import StaffUser

    pwd = ctx.get("password") or DEMO_PASSWORD
    u, _ = StaffUser.objects.get_or_create(
        username="screenshot_manager",
        defaults={
            "email": "screenshot_manager@example.invalid",
            "first_name": "Screenshot",
            "last_name": "Manager",
            "is_staff": True,
            "is_active": True,
        },
    )
    u.set_password(pwd)
    u.is_staff = True
    u.is_active = True
    u.save()
    u.groups.clear()
    assign_group_to_test_user(u, "Manager")
    u.clinic_sites.add(ctx["clinic"])
    ctx["manager"] = u


def upsert_patient(
    *,
    phone: str,
    first_name: str,
    last_name: str,
    dob: date,
    email: str,
    clinic,
) -> Any:
    from apps.reception.models import Patient

    p = Patient.objects.filter(email=email).first()
    if p is None:
        p, _ = Patient.objects.get_or_create(
            phone=phone,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "date_of_birth": dob,
                "email": email,
            },
        )
    p.first_name = first_name
    p.last_name = last_name
    p.date_of_birth = dob
    p.phone = phone
    p.email = email
    p.save()
    p.clinic_sites.add(clinic)
    return p


def next_position(queue) -> int:
    from apps.reception.models import QueueEntry

    last = (
        QueueEntry.objects.filter(daily_queue=queue)
        .order_by("-position_no")
        .values_list("position_no", flat=True)
        .first()
    )
    return int(last or 0) + 1


def create_submitted_entry(
    ctx: dict,
    *,
    patient,
    position: int | None = None,
    entry_status=None,
) -> tuple[Any, Any]:
    """Create queue entry + SUBMITTED intake. Returns (entry, intake)."""
    from django.utils import timezone

    from apps.intake.models import IntakeStatus, PatientIntakeForm
    from apps.reception.models import (
        PatientFormSession,
        QueueEntry,
        QueueEntryStatus,
    )

    if entry_status is None:
        entry_status = QueueEntryStatus.PATIENT_COMPLETED

    queue = ctx["queue"]
    reception = ctx["reception"]
    pos = position or next_position(queue)
    entry = QueueEntry.objects.create(
        daily_queue=queue,
        patient=patient,
        position_no=pos,
        entry_status=entry_status,
        created_by_user=reception,
    )
    session = PatientFormSession.objects.create(
        queue_entry=entry,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(minutes=120),
        consumed_at=timezone.now(),
        created_by_user=reception,
    )
    entry.active_session = session
    entry.save(update_fields=["active_session", "updated_at"])
    intake = PatientIntakeForm.objects.create(
        queue_entry=entry,
        session=session,
        form_status=IntakeStatus.SUBMITTED,
        anamnesis_payload={"answers": []},
        submitted_at=timezone.now(),
        signature_file_path="/tmp/scenario-signature.png",
        signature_sha256="b" * 64,
    )
    return entry, intake


def create_draft_document(ctx: dict, entry, intake):
    from apps.medical.services import (
        create_or_get_medical_document,
        save_draft_document_version,
    )

    md = create_or_get_medical_document(
        queue_entry_id=entry.id,
        intake_form_id=intake.id,
        created_by_user_id=ctx["doctor"].id,
    )
    save_draft_document_version(
        medical_document_id=md.id,
        updated_by_user_id=ctx["doctor"].id,
        medical_payload=DEMO_PAYLOAD,
        diagnosis_code="DEMO",
        procedure_code="DEMO",
    )
    return md


def force_publish(ctx: dict, md, *, mark_outbox_processed: bool = True):
    """Publish draft and optionally mark outbox PROCESSED (avoids worker noise)."""
    from apps.medical.services import publish_document_version
    from apps.outbox.models import OutboxEvent, OutboxStatus

    published = publish_document_version(
        medical_document_id=md.id,
        publish_request_id=uuid.uuid4(),
        published_by_user_id=ctx["doctor"].id,
        publish_locale="de-DE",
    )
    if mark_outbox_processed:
        OutboxEvent.objects.filter(medical_document_version=published).update(
            status=OutboxStatus.PROCESSED
        )
    md.refresh_from_db()
    return published


def create_outbox_event(
    version,
    *,
    event_type: str,
    status: str,
    error_message: str = "Demo scenario error (fictional)",
    retry_count: int = 0,
):
    from apps.outbox.models import OutboxEvent

    return OutboxEvent.objects.create(
        medical_document_version=version,
        aggregate_id=version.id,
        event_type=event_type,
        payload={"schema_version": 1, "demo": True},
        status=status,
        error_message=error_message,
        retry_count=retry_count,
    )


def seed_mock_incoming(
    files: list[dict],
    *,
    remote_dir: str | None = None,
    file_bytes: bytes | None = b"%PDF-1.4 demo",
) -> None:
    """Seed mock /incoming listing visible to the ``web`` process (shared JSON state)."""
    from apps.integrations.hidrive import client as hidrive_client
    from apps.medical.incoming_pdf_scan import hidrive_incoming_dir

    inc = remote_dir or hidrive_incoming_dir()
    # Rewrite relative paths to the configured incoming dir (e.g. /public/incoming).
    normalized_files: list[dict] = []
    for entry in files:
        name = str(entry.get("name") or "")
        path = str(entry.get("path") or "")
        if name and (not path or path.startswith("/incoming/")):
            path = f"{inc.rstrip('/')}/{name}"
        normalized_files.append({**entry, "name": name, "path": path})

    adapter = hidrive_client._MockHiDriveAdapter
    adapter._load_state_from_disk()
    # Authoritative listing for this incoming dir only (drop legacy /incoming vs /public/incoming).
    adapter._dir_listings = {
        k: v
        for k, v in adapter._dir_listings.items()
        if k not in ("/incoming", "/public/incoming", inc)
    }
    adapter._dir_listings[inc] = normalized_files
    adapter._list_dir_error = None
    adapter._persist_state()
    if file_bytes is not None:
        for entry in normalized_files:
            path = str(entry.get("path") or "")
            if path:
                adapter.seed_file(path, file_bytes)


def seed_mock_hidrive_timeout(message: str = "Demo timeout for SC-027") -> None:
    """Force dashboard HiDrive error banner (shared JSON state)."""
    from apps.integrations.hidrive import client as hidrive_client

    hidrive_client._MockHiDriveAdapter.seed_list_dir_error(message)


def clear_mock_hidrive_timeout() -> None:
    from apps.integrations.hidrive import client as hidrive_client

    hidrive_client._MockHiDriveAdapter.seed_list_dir_error(None)
