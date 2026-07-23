"""Shared helpers for scenario video seeds (fictional demo data only — RODO)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
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

# Valid 1-page PDF (~515 B). Used when pypdf is unavailable (e.g. stale
# Playwright image) so HiDrive mock / MEDIA seeds still pass PdfReader.
_MINIMAL_PDF_B64 = (
    "JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgKENvZ2l0b21lZGljYSBtYW51YWwgZGVtbykK"
    "L1RpdGxlIChDb2dpdG8gRGVtbyBCZWZ1bmQpCi9DcmVhdG9yIChzY3JpcHRzXDA1Nm1hbnVhbFwxMzdkZW1v"
    "KQo+PgplbmRvYmoKMiAwIG9iago8PAovVHlwZSAvUGFnZXMKL0NvdW50IDEKL0tpZHMgWyA0IDAgUiBdCj4+"
    "CmVuZG9iagozIDAgb2JqCjw8Ci9UeXBlIC9DYXRhbG9nCi9QYWdlcyAyIDAgUgo+PgplbmRvYmoKNCAwIG9i"
    "ago8PAovVHlwZSAvUGFnZQovUmVzb3VyY2VzIDw8Cj4+Ci9NZWRpYUJveCBbIDAuMCAwLjAgNTk1IDg0MiBd"
    "Ci9QYXJlbnQgMiAwIFIKPj4KZW5kb2JqCnhyZWYKMCA1CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAx"
    "NSAwMDAwMCBuIAowMDAwMDAwMTM4IDAwMDAwIG4gCjAwMDAwMDAxOTcgMDAwMDAgbiAKMDAwMDAwMDI0NiAw"
    "MDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDUKL1Jvb3QgMyAwIFIKL0luZm8gMSAwIFIKPj4Kc3RhcnR4cmVm"
    "CjM0MAolJUVPRgo="
)


def minimal_demo_pdf_bytes(*, title: str = "Cogito Demo Befund") -> bytes:
    """Return a few-KB valid PDF (pypdf / PdfReader / browser preview).

    Used for MEDIA seeds, HiDrive mock ``download``, and external-upload demos.
    Prefers ``pypdf`` when installed; otherwise returns a baked-in valid PDF.
    """
    import base64

    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)  # A4
        writer.add_metadata(
            {
                "/Title": title,
                "/Producer": "Cogitomedica manual demo",
                "/Creator": "scripts.manual_demo",
            }
        )
        buf = BytesIO()
        writer.write(buf)
        return buf.getvalue()
    except ImportError:
        return base64.b64decode(_MINIMAL_PDF_B64)


def attach_demo_published_pdf(
    version,
    *,
    label: str = "demo",
    mark_delivered: bool = True,
    seed_hidrive_archive: bool = True,
) -> Path:
    """Write minimal PDF under MEDIA_ROOT and mark version COMPLETED.

    When ``mark_delivered`` is True, also sets HiDrive/SMS delivery flags so
    revoke UI / portal list behave like a finished outbox chain.
    """
    from django.conf import settings
    from django.utils import timezone

    from apps.medical.models import PdfStatus

    pdf_bytes = minimal_demo_pdf_bytes(title=f"Demo Befund {label}")
    rel = f"demo_befund/{label}_{version.id}.pdf"
    full = Path(settings.MEDIA_ROOT) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(pdf_bytes)

    version.pdf_generation_status = PdfStatus.COMPLETED
    version.pdf_local_path = rel.replace("\\", "/")
    version.pdf_checksum_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    update_fields = [
        "pdf_generation_status",
        "pdf_local_path",
        "pdf_checksum_sha256",
    ]

    hidrive_path = f"/public/patients/demo/{label}_v{version.version_no}.pdf"
    if mark_delivered:
        now = timezone.now()
        version.hidrive_sent = True
        version.hidrive_sent_at = now
        version.hidrive_path = hidrive_path
        version.sms_sent = True
        version.sms_sent_at = now
        update_fields.extend(
            [
                "hidrive_sent",
                "hidrive_sent_at",
                "hidrive_path",
                "sms_sent",
                "sms_sent_at",
            ]
        )

    version.save(update_fields=update_fields)

    if seed_hidrive_archive and mark_delivered:
        from apps.integrations.hidrive import client as hidrive_client

        hidrive_client._MockHiDriveAdapter.seed_file(hidrive_path, pdf_bytes)

    return full


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


def force_publish(
    ctx: dict,
    md,
    *,
    mark_outbox_processed: bool = True,
    with_pdf: bool = True,
    mark_delivered: bool = True,
    pdf_label: str | None = None,
):
    """Publish draft and optionally attach a mock PDF + mark outbox PROCESSED.

    ``with_pdf=True`` (default) writes a valid minimal PDF under MEDIA and sets
    ``pdf_generation_status=COMPLETED`` so doctor list / portal / revoke demos
    see real UI. Set ``with_pdf=False`` for GENERATE_PDF failure scenarios
    (e.g. SC-013).
    """
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
    if with_pdf:
        label = pdf_label or f"pub_{str(published.id)[:8]}"
        attach_demo_published_pdf(
            published,
            label=label,
            mark_delivered=mark_delivered,
        )
        published.refresh_from_db()
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
    file_bytes: bytes | None = None,
) -> None:
    """Seed mock /incoming listing visible to the ``web`` process (shared JSON state).

    Default ``file_bytes`` is a valid minimal PDF so ``download_external_pdf`` /
    PdfReader accept mock lab files (SC-011/012 and external-upload previews).
    Pass ``file_bytes=b""`` only when you need empty content; pass ``None`` to
    use the default valid PDF (or skip seeding file bodies when ``files`` is empty).
    """
    from apps.integrations.hidrive import client as hidrive_client
    from apps.medical.incoming_pdf_scan import hidrive_incoming_dir

    if file_bytes is None:
        file_bytes = minimal_demo_pdf_bytes(title="Demo lab incoming PDF")
    pdf_size = len(file_bytes)

    inc = remote_dir or hidrive_incoming_dir()
    # Rewrite relative paths to the configured incoming dir (e.g. /public/incoming).
    normalized_files: list[dict] = []
    for entry in files:
        name = str(entry.get("name") or "")
        path = str(entry.get("path") or "")
        if name and (not path or path.startswith("/incoming/")):
            path = f"{inc.rstrip('/')}/{name}"
        # Prefer real byte length so dashboard / matching UI show plausible sizes.
        normalized_files.append({**entry, "name": name, "path": path, "size": pdf_size})

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
    if file_bytes is not None and normalized_files:
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
