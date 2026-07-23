"""Scenario-specific demo seeds for SC-001–SC-027 (fictional data only)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.manual_demo.scenario_helpers import (
    assert_demo_seed_dev_only,
    create_draft_document,
    create_outbox_event,
    create_submitted_entry,
    ensure_accounting_user,
    ensure_manager_user,
    ensure_screenshot_users,
    force_publish,
    seed_mock_incoming,
    upsert_patient,
)


def seed_base(ctx: dict) -> None:
    assert_demo_seed_dev_only()
    ensure_screenshot_users(ctx)
    ensure_accounting_user(ctx)
    ensure_manager_user(ctx)


def seed_sc_001(ctx: dict) -> None:
    """Cancelled entry: show cancel in reception then doctor list without patient."""
    seed_base(ctx)
    p = upsert_patient(
        phone="491111000001",
        first_name="Elena",
        last_name="CancelDemo",
        dob=date(1988, 4, 12),
        email="elena.canceldemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    create_draft_document(ctx, entry, intake)
    ctx["sc001_entry_id"] = str(entry.id)
    ctx["sc001_patient_last"] = p.last_name


def seed_sc_002(ctx: dict) -> None:
    """Submitted intake, no medical document → doctor sees dash status."""
    seed_base(ctx)
    p = upsert_patient(
        phone="491111000002",
        first_name="Felix",
        last_name="DraftGone",
        dob=date(1975, 9, 3),
        email="felix.draftgone@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, _intake = create_submitted_entry(ctx, patient=p)
    ctx["sc002_entry_id"] = str(entry.id)
    ctx["sc002_patient_last"] = p.last_name


def seed_sc_003(ctx: dict) -> None:
    """Published + pending revision for discard-revision demo."""
    seed_base(ctx)
    from apps.medical.services import save_draft_document_version
    from scripts.manual_demo.scenario_helpers import DEMO_PAYLOAD

    p = upsert_patient(
        phone="491111000003",
        first_name="Greta",
        last_name="RevisionDemo",
        dob=date(1982, 11, 21),
        email="greta.revisiondemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    md = create_draft_document(ctx, entry, intake)
    force_publish(ctx, md, pdf_label="sc003_rev")
    save_draft_document_version(
        medical_document_id=md.id,
        updated_by_user_id=ctx["doctor"].id,
        medical_payload={**DEMO_PAYLOAD, "summary_edited_text": "Rewizja demo."},
        intent="amend",
    )
    md.refresh_from_db()
    ctx["sc003_doc_id"] = str(md.id)
    ctx["sc003_patient_last"] = p.last_name


def seed_sc_004(ctx: dict) -> None:
    """Published Befund for accounting report."""
    seed_base(ctx)
    p = upsert_patient(
        phone="491111000004",
        first_name="Hans",
        last_name="AccountingDemo",
        dob=date(1969, 2, 14),
        email="hans.accountingdemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    md = create_draft_document(ctx, entry, intake)
    force_publish(ctx, md)
    ctx["sc004_patient_last"] = p.last_name


def seed_sc_005(ctx: dict) -> None:
    """Candidate for missing HiDrive PDF (empty incoming listing → NO_FILE)."""
    seed_base(ctx)
    seed_mock_incoming([])
    p = upsert_patient(
        phone="491111000005",
        first_name="Iris",
        last_name="NoPdfDemo",
        dob=date(1991, 6, 8),
        email="iris.nopdfdemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    create_draft_document(ctx, entry, intake)
    ctx["sc005_entry_id"] = str(entry.id)
    ctx["sc005_patient_last"] = p.last_name
    ctx["sc005_suggested"] = (
        f"{p.last_name}_{p.first_name}_{p.date_of_birth:%Y_%m_%d}.pdf"
    )


def seed_sc_006(ctx: dict) -> None:
    """Published with FAILED SMS_SEND outbox event."""
    seed_base(ctx)
    from apps.outbox.models import OutboxEventType, OutboxStatus

    p = upsert_patient(
        phone="491111000006",
        first_name="Jonas",
        last_name="SmsFailDemo",
        dob=date(1984, 1, 30),
        email="jonas.smsfaildemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    md = create_draft_document(ctx, entry, intake)
    # PDF ready; SMS outbox FAILED (do not mark sms_sent on version).
    published = force_publish(
        ctx,
        md,
        mark_outbox_processed=True,
        with_pdf=True,
        mark_delivered=False,
        pdf_label="sc006_sms",
    )
    from django.utils import timezone

    from apps.medical.models import MedicalDocumentVersion

    MedicalDocumentVersion.objects.filter(id=published.id).update(
        hidrive_sent=True,
        hidrive_sent_at=timezone.now(),
        hidrive_path=f"/public/patients/demo/sc006_v{published.version_no}.pdf",
    )
    published.refresh_from_db()
    ev = create_outbox_event(
        published,
        event_type=OutboxEventType.SMS_SEND,
        status=OutboxStatus.FAILED,
        error_message="Demo: SMS gateway timeout (fictional)",
    )
    ctx["sc006_event_id"] = str(ev.id)
    ctx["sc006_doc_id"] = str(md.id)
    ctx["sc006_patient_last"] = p.last_name


def seed_sc_007(ctx: dict) -> None:
    """Reuse import-troubleshooting seed."""
    from scripts.manual_demo.seed_import_troubleshooting import (
        seed_import_troubleshooting_demo,
    )

    assert_demo_seed_dev_only()
    seed_import_troubleshooting_demo(ctx)


def seed_sc_008(ctx: dict) -> None:
    """Patient with wrong phone for portal login correction demo."""
    seed_base(ctx)
    p = upsert_patient(
        phone="491111000008",
        first_name="Klara",
        last_name="PortalTypo",
        dob=date(1995, 12, 5),
        email="klara.portaltypo@example.invalid",
        clinic=ctx["clinic"],
    )
    ctx["sc008_patient_id"] = str(p.id)
    ctx["sc008_patient_last"] = p.last_name
    ctx["sc008_phone"] = p.phone
    ctx["sc008_dob"] = p.date_of_birth.isoformat()


def seed_sc_009(ctx: dict) -> None:
    """Two family members sharing phone, different DOB."""
    seed_base(ctx)
    shared = "491111000009"
    p1 = upsert_patient(
        phone=shared,
        first_name="Laura",
        last_name="FamilieDemo",
        dob=date(1980, 3, 10),
        email="laura.familiatedemo@example.invalid",
        clinic=ctx["clinic"],
    )
    p2 = upsert_patient(
        phone=shared,
        first_name="Max",
        last_name="FamilieDemo",
        dob=date(2008, 8, 19),
        email="max.familiatedemo@example.invalid",
        clinic=ctx["clinic"],
    )
    ctx["sc009_phone"] = shared
    ctx["sc009_parent_dob"] = p1.date_of_birth.isoformat()
    ctx["sc009_child_dob"] = p2.date_of_birth.isoformat()
    ctx["sc009_parent_last"] = p1.last_name


def seed_sc_010(ctx: dict) -> None:
    """Portal OTP screen (pre-seeded session like screenshots)."""
    seed_base(ctx)
    from django.contrib.sessions.backends.db import SessionStore

    p = upsert_patient(
        phone="17699990010",
        first_name="Nina",
        last_name="OtpDemo",
        dob=date(1993, 7, 17),
        email="nina.otpdemo@example.invalid",
        clinic=ctx["clinic"],
    )
    s = SessionStore()
    s.create()
    s["ergebnisse_phone"] = p.phone
    s["ergebnisse_dob"] = p.date_of_birth.isoformat()
    s.save()
    ctx["sc010_session_otp"] = s.session_key
    ctx["sc010_phone"] = p.phone
    ctx["sc010_dob"] = p.date_of_birth.isoformat()
    ctx["sc010_patient_last"] = p.last_name


def seed_sc_011(ctx: dict) -> None:
    """Two patients same short name → AMBIGUOUS with mock file."""
    seed_base(ctx)
    dob_a = date(1985, 3, 12)
    dob_b = date(1992, 11, 4)
    p1 = upsert_patient(
        phone="491111000011",
        first_name="Hans",
        last_name="MullerDemo",
        dob=dob_a,
        email="hans.mullerdemo.a@example.invalid",
        clinic=ctx["clinic"],
    )
    p2 = upsert_patient(
        phone="491111000012",
        first_name="Hans",
        last_name="MullerDemo",
        dob=dob_b,
        email="hans.mullerdemo.b@example.invalid",
        clinic=ctx["clinic"],
    )
    e1, i1 = create_submitted_entry(ctx, patient=p1)
    e2, i2 = create_submitted_entry(ctx, patient=p2)
    create_draft_document(ctx, e1, i1)
    create_draft_document(ctx, e2, i2)
    # Use persisted name casing (Patient.save normalizes display names).
    p1.refresh_from_db()
    ambiguous = f"{p1.last_name}_{p1.first_name}.pdf"
    suggested = f"{p1.last_name}_{p1.first_name}_{p1.date_of_birth:%Y_%m_%d}.pdf"
    seed_mock_incoming(
        [
            {
                "name": ambiguous,
                "path": f"/incoming/{ambiguous}",
                "size": 1024,
            }
        ]
    )
    ctx["sc011_suggested"] = suggested
    ctx["sc011_patient_last"] = p1.last_name
    ctx["sc011_ambiguous_name"] = ambiguous
    ctx["sc011_entry_a_id"] = str(e1.id)
    ctx["sc011_entry_b_id"] = str(e2.id)


def seed_sc_012(ctx: dict) -> None:
    """REJECTED_ONLY via rejected_ prefix in mock incoming."""
    seed_base(ctx)
    p = upsert_patient(
        phone="491111000013",
        first_name="Otto",
        last_name="RejectedDemo",
        dob=date(1978, 5, 25),
        email="otto.rejecteddemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    create_draft_document(ctx, entry, intake)
    p.refresh_from_db()
    fname = f"rejected_{p.last_name}_{p.first_name}.pdf"
    fixed = f"{p.last_name}_{p.first_name}.pdf"
    seed_mock_incoming([{"name": fname, "path": f"/incoming/{fname}", "size": 2048}])
    ctx["sc012_rejected_name"] = fname
    ctx["sc012_fixed_name"] = fixed
    ctx["sc012_patient_last"] = p.last_name
    ctx["sc012_entry_id"] = str(entry.id)


def seed_sc_013(ctx: dict) -> None:
    """FAILED GENERATE_PDF on dashboard."""
    seed_base(ctx)
    from apps.outbox.models import OutboxEventType, OutboxStatus

    p = upsert_patient(
        phone="491111000014",
        first_name="Paula",
        last_name="PdfFailDemo",
        dob=date(1987, 10, 2),
        email="paula.pdffaildemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    md = create_draft_document(ctx, entry, intake)
    # No mock PDF — status stays PENDING so FAILED GENERATE_PDF is the story.
    published = force_publish(ctx, md, mark_outbox_processed=False, with_pdf=False)
    from apps.outbox.models import OutboxEvent

    OutboxEvent.objects.filter(medical_document_version=published).delete()
    ev = create_outbox_event(
        published,
        event_type=OutboxEventType.GENERATE_PDF,
        status=OutboxStatus.FAILED,
        error_message="Demo: WeasyPrint failed (fictional)",
    )
    ctx["sc013_event_id"] = str(ev.id)
    ctx["sc013_patient_last"] = p.last_name


def seed_sc_014(ctx: dict) -> None:
    """Document locked by manager."""
    seed_base(ctx)
    from django.utils import timezone

    from apps.medical.models import MedicalDocument

    p = upsert_patient(
        phone="491111000015",
        first_name="Quinn",
        last_name="LockDemo",
        dob=date(1990, 4, 18),
        email="quinn.lockdemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    md = create_draft_document(ctx, entry, intake)
    MedicalDocument.objects.filter(id=md.id).update(
        locked_by_user=ctx["manager"],
        locked_at=timezone.now(),
    )
    ctx["sc014_doc_id"] = str(md.id)
    ctx["sc014_entry_id"] = str(entry.id)
    ctx["sc014_patient_last"] = p.last_name


def seed_sc_015(ctx: dict) -> None:
    """Published document ready for revoke UI."""
    seed_base(ctx)
    p = upsert_patient(
        phone="491111000016",
        first_name="Rita",
        last_name="RevokeDemo",
        dob=date(1983, 8, 9),
        email="rita.revokedemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    md = create_draft_document(ctx, entry, intake)
    force_publish(ctx, md, pdf_label="sc015_revoke")
    ctx["sc015_doc_id"] = str(md.id)
    ctx["sc015_patient_last"] = p.last_name


def seed_sc_016(ctx: dict) -> None:
    """Paper auth that will be auto-revoked after digital submit (show hub)."""
    seed_base(ctx)
    from django.utils import timezone

    from apps.intake.models import IntakeStatus, PatientIntakeForm
    from apps.medical.models import PaperIntakeAuthorization
    from apps.reception.models import (
        PatientFormSession,
        QueueEntry,
        QueueEntryStatus,
    )
    from scripts.manual_demo.scenario_helpers import next_position

    p = upsert_patient(
        phone="491111000017",
        first_name="Stefan",
        last_name="PaperThenTablet",
        dob=date(1972, 12, 1),
        email="stefan.paperthentablet@example.invalid",
        clinic=ctx["clinic"],
    )
    queue = ctx["queue"]
    reception = ctx["reception"]
    entry = QueueEntry.objects.create(
        daily_queue=queue,
        patient=p,
        position_no=next_position(queue),
        entry_status=QueueEntryStatus.WAITING,
        appointment_time=timezone.now() - timedelta(hours=5),
        created_by_user=reception,
    )
    PaperIntakeAuthorization.objects.create(
        queue_entry=entry,
        authorized_by=ctx["admin"],
        authorized_at=timezone.now(),
        reason="Demo: tablet awaria — ścieżka papierowa (fikcyjna)",
    )
    # Then patient submitted digital → auto-revoke path: create SUBMITTED
    session = PatientFormSession.objects.create(
        queue_entry=entry,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(minutes=120),
        consumed_at=timezone.now(),
        created_by_user=reception,
    )
    entry.active_session = session
    entry.entry_status = QueueEntryStatus.PATIENT_COMPLETED
    entry.save(update_fields=["active_session", "entry_status", "updated_at"])
    intake = PatientIntakeForm.objects.create(
        queue_entry=entry,
        session=session,
        form_status=IntakeStatus.SUBMITTED,
        anamnesis_payload={},
        submitted_at=timezone.now(),
        signature_sha256="c" * 64,
    )
    from django.db import transaction

    from apps.medical.services import (
        autorevoke_paper_intake_authorization_after_intake_submit,
    )

    with transaction.atomic():
        autorevoke_paper_intake_authorization_after_intake_submit(
            queue_entry_id=entry.id,
            intake_form_id=intake.id,
            actor_user_id=ctx["admin"].id,
        )
    ctx["sc016_entry_id"] = str(entry.id)
    ctx["sc016_patient_last"] = p.last_name


def seed_sc_017(ctx: dict) -> None:
    """WAITING entry without intake — needs T1 paper authorization."""
    seed_base(ctx)
    from django.utils import timezone

    from apps.reception.models import QueueEntry, QueueEntryStatus
    from scripts.manual_demo.scenario_helpers import next_position

    p = upsert_patient(
        phone="491111000018",
        first_name="Tina",
        last_name="NeedPaperT1",
        dob=date(1965, 6, 15),
        email="tina.needpapert1@example.invalid",
        clinic=ctx["clinic"],
    )
    entry = QueueEntry.objects.create(
        daily_queue=ctx["queue"],
        patient=p,
        position_no=next_position(ctx["queue"]),
        entry_status=QueueEntryStatus.WAITING,
        appointment_time=timezone.now() - timedelta(hours=6),
        created_by_user=ctx["reception"],
    )
    ctx["sc017_entry_id"] = str(entry.id)
    ctx["sc017_patient_last"] = p.last_name


def seed_sc_018(ctx: dict) -> None:
    """Unassigned tablet device already in seed_manual_demo."""
    seed_base(ctx)
    ctx["sc018_android_unassigned"] = "screenshot-unassigned-dev"
    ctx["sc018_android_assigned"] = "screenshot-assigned-dev"


def seed_sc_019(ctx: dict) -> None:
    """Two patients: wrong one has SUBMITTED, right one IN_PROGRESS."""
    seed_base(ctx)
    from django.utils import timezone

    from apps.intake.models import IntakeStatus, PatientIntakeForm
    from apps.reception.models import (
        PatientFormSession,
        QueueEntry,
        QueueEntryStatus,
    )
    from scripts.manual_demo.scenario_helpers import next_position

    wrong = upsert_patient(
        phone="491111000019",
        first_name="Uwe",
        last_name="WrongSlot",
        dob=date(1970, 1, 1),
        email="uwe.wrongslot@example.invalid",
        clinic=ctx["clinic"],
    )
    right = upsert_patient(
        phone="491111000020",
        first_name="Vera",
        last_name="RightPatient",
        dob=date(1986, 9, 22),
        email="vera.rightpatient@example.invalid",
        clinic=ctx["clinic"],
    )
    e_wrong, _ = create_submitted_entry(ctx, patient=wrong)
    e_right = QueueEntry.objects.create(
        daily_queue=ctx["queue"],
        patient=right,
        position_no=next_position(ctx["queue"]),
        entry_status=QueueEntryStatus.IN_PROGRESS,
        created_by_user=ctx["reception"],
    )
    sess = PatientFormSession.objects.create(
        queue_entry=e_right,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(minutes=120),
        created_by_user=ctx["reception"],
    )
    e_right.active_session = sess
    e_right.save(update_fields=["active_session", "updated_at"])
    PatientIntakeForm.objects.create(
        queue_entry=e_right,
        session=sess,
        form_status=IntakeStatus.IN_PROGRESS,
        anamnesis_payload={},
    )
    ctx["sc019_wrong_entry_id"] = str(e_wrong.id)
    ctx["sc019_right_entry_id"] = str(e_right.id)
    ctx["sc019_wrong_last"] = wrong.last_name
    ctx["sc019_right_last"] = right.last_name


def seed_sc_020(ctx: dict) -> None:
    """Submitted intake ready for external-upload hub."""
    seed_base(ctx)
    p = upsert_patient(
        phone="491111000021",
        first_name="Walter",
        last_name="ExternalDemo",
        dob=date(1979, 2, 28),
        email="walter.externaldemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    ctx["sc020_entry_id"] = str(entry.id)
    ctx["sc020_patient_last"] = p.last_name
    ctx["sc020_intake_id"] = str(intake.id)


def seed_sc_021(ctx: dict) -> None:
    """IN_PROGRESS intake — doctor cannot open digital doc."""
    seed_base(ctx)
    from django.utils import timezone

    from apps.intake.models import IntakeStatus, PatientIntakeForm
    from apps.reception.models import (
        PatientFormSession,
        QueueEntry,
        QueueEntryStatus,
    )
    from scripts.manual_demo.scenario_helpers import next_position

    p = upsert_patient(
        phone="491111000022",
        first_name="Xenia",
        last_name="NoSubmitYet",
        dob=date(1998, 3, 3),
        email="xenia.nosubmit@example.invalid",
        clinic=ctx["clinic"],
    )
    entry = QueueEntry.objects.create(
        daily_queue=ctx["queue"],
        patient=p,
        position_no=next_position(ctx["queue"]),
        entry_status=QueueEntryStatus.IN_PROGRESS,
        created_by_user=ctx["reception"],
    )
    sess = PatientFormSession.objects.create(
        queue_entry=entry,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(minutes=120),
        created_by_user=ctx["reception"],
    )
    entry.active_session = sess
    entry.save(update_fields=["active_session", "updated_at"])
    PatientIntakeForm.objects.create(
        queue_entry=entry,
        session=sess,
        form_status=IntakeStatus.IN_PROGRESS,
        anamnesis_payload={},
    )
    ctx["sc021_entry_id"] = str(entry.id)
    ctx["sc021_patient_last"] = p.last_name


def seed_sc_022(ctx: dict) -> None:
    """Verified portal session, empty documents list (after revoke)."""
    seed_base(ctx)
    from django.contrib.sessions.backends.db import SessionStore
    from django.utils import timezone

    from apps.medical.services import revoke_document_version

    p = upsert_patient(
        phone="17699990022",
        first_name="Yvonne",
        last_name="EmptyDocs",
        dob=date(2001, 5, 5),
        email="yvonne.emptydocs@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    md = create_draft_document(ctx, entry, intake)
    force_publish(ctx, md, pdf_label="sc022_revoked")
    revoke_document_version(
        medical_document_id=md.id,
        revoked_by_user_id=ctx["doctor"].id,
    )
    s = SessionStore()
    s.create()
    s["patient_results_patient_id"] = str(p.id)
    s["patient_results_verified_at"] = timezone.now().isoformat()
    s.save()
    ctx["sc022_session_doc"] = s.session_key
    ctx["sc022_patient_last"] = p.last_name
    ctx["sc022_doc_id"] = str(md.id)


def seed_sc_023(ctx: dict) -> None:
    """Show patient portal + reception patient change (retention explained in narration)."""
    seed_base(ctx)
    from django.contrib.sessions.backends.db import SessionStore
    from django.utils import timezone

    p = upsert_patient(
        phone="17699990023",
        first_name="Zara",
        last_name="RetentionDemo",
        dob=date(1977, 7, 7),
        email="zara.retentiondemo@example.invalid",
        clinic=ctx["clinic"],
    )
    s = SessionStore()
    s.create()
    s["patient_results_patient_id"] = str(p.id)
    s["patient_results_verified_at"] = timezone.now().isoformat()
    s.save()
    ctx["sc023_session_doc"] = s.session_key
    ctx["sc023_patient_id"] = str(p.id)
    ctx["sc023_patient_last"] = p.last_name


def seed_sc_024(ctx: dict) -> None:
    """OTP screen + reception dashboard (SMSAPI balance not automatable)."""
    seed_sc_010(ctx)
    ctx["sc024_note"] = "UI walkthrough only — SMSAPI balance not shown in app"


def seed_sc_025(ctx: dict) -> None:
    """Patient personal data edit screen."""
    seed_base(ctx)
    p = upsert_patient(
        phone="491111000025",
        first_name="Anna",
        last_name="RenameDemo",
        dob=date(1985, 5, 15),
        email="anna.renamedemo@example.invalid",
        clinic=ctx["clinic"],
    )
    ctx["sc025_patient_id"] = str(p.id)
    ctx["sc025_patient_last"] = p.last_name


def seed_sc_026(ctx: dict) -> None:
    """DEAD_LETTER outbox event."""
    seed_base(ctx)
    from apps.outbox.models import OutboxEventType, OutboxStatus

    p = upsert_patient(
        phone="491111000026",
        first_name="Bruno",
        last_name="DeadLetterDemo",
        dob=date(1968, 11, 11),
        email="bruno.deadletterdemo@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    md = create_draft_document(ctx, entry, intake)
    # PDF generated locally, but HiDrive upload failed → DEAD_LETTER.
    published = force_publish(
        ctx,
        md,
        mark_outbox_processed=False,
        with_pdf=True,
        mark_delivered=False,
        pdf_label="sc026_dead",
    )
    from apps.outbox.models import OutboxEvent

    OutboxEvent.objects.filter(medical_document_version=published).delete()
    ev = create_outbox_event(
        published,
        event_type=OutboxEventType.HIDRIVE_UPLOAD,
        status=OutboxStatus.DEAD_LETTER,
        error_message="Demo: HiDrive 401 after 3 retries (fictional)",
        retry_count=3,
    )
    ctx["sc026_event_id"] = str(ev.id)
    ctx["sc026_patient_last"] = p.last_name


def seed_sc_027(ctx: dict) -> None:
    """HiDrive error banner via shared mock state file (visible to web process)."""
    seed_base(ctx)
    from scripts.manual_demo.scenario_helpers import seed_mock_hidrive_timeout

    p = upsert_patient(
        phone="491111000027",
        first_name="Clara",
        last_name="HidriveDown",
        dob=date(1994, 4, 4),
        email="clara.hidrivedown@example.invalid",
        clinic=ctx["clinic"],
    )
    entry, intake = create_submitted_entry(ctx, patient=p)
    create_draft_document(ctx, entry, intake)
    seed_mock_hidrive_timeout("Demo timeout for SC-027 (fictional)")
    ctx["sc027_patient_last"] = p.last_name
    ctx["sc027_entry_id"] = str(entry.id)
    ctx["sc027_hidrive_timeout"] = True
    ctx["sc027_hidrive_error"] = "Demo timeout for SC-027 (fictional)"


SCENARIO_SEEDERS: dict[str, Callable[[dict], None]] = {
    "SC-001": seed_sc_001,
    "SC-002": seed_sc_002,
    "SC-003": seed_sc_003,
    "SC-004": seed_sc_004,
    "SC-005": seed_sc_005,
    "SC-006": seed_sc_006,
    "SC-007": seed_sc_007,
    "SC-008": seed_sc_008,
    "SC-009": seed_sc_009,
    "SC-010": seed_sc_010,
    "SC-011": seed_sc_011,
    "SC-012": seed_sc_012,
    "SC-013": seed_sc_013,
    "SC-014": seed_sc_014,
    "SC-015": seed_sc_015,
    "SC-016": seed_sc_016,
    "SC-017": seed_sc_017,
    "SC-018": seed_sc_018,
    "SC-019": seed_sc_019,
    "SC-020": seed_sc_020,
    "SC-021": seed_sc_021,
    "SC-022": seed_sc_022,
    "SC-023": seed_sc_023,
    "SC-024": seed_sc_024,
    "SC-025": seed_sc_025,
    "SC-026": seed_sc_026,
    "SC-027": seed_sc_027,
}


def seed_scenario(scenario_id: str, ctx: dict | None = None) -> dict:
    sid = scenario_id.upper().replace("_", "-")
    if not sid.startswith("SC-"):
        sid = f"SC-{sid}"
    if sid not in SCENARIO_SEEDERS:
        raise KeyError(f"Unknown scenario: {scenario_id}")
    out: dict = ctx if ctx is not None else {}
    SCENARIO_SEEDERS[sid](out)
    out["scenario_id"] = sid
    return out


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
    out.setdefault("password", ctx.get("password") or "ScreenshotDemo2026!")
    return out


if __name__ == "__main__":
    import argparse
    import json
    import sys
    from pathlib import Path

    _repo = Path(__file__).resolve().parents[2]
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))

    from scripts.manual_demo.django_setup import setup_django

    parser = argparse.ArgumentParser(description="Seed demo data for scenario videos.")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="np. sc-001 (można powtórzyć)",
    )
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--write-ctx",
        action="store_true",
        help="Zapisz JSON ctx do docs/manual/_build/scenario-ctx/",
    )
    parser.add_argument(
        "--ctx-dir",
        type=Path,
        default=_repo / "docs" / "manual" / "_build" / "scenario-ctx",
    )
    args = parser.parse_args()
    setup_django()

    # Re-import after path fix for direct script execution
    from scripts.manual_demo.seed_scenarios import (
        SCENARIO_SEEDERS,
        _serialize_ctx,
        seed_scenario,
    )

    if args.all:
        ids = list(SCENARIO_SEEDERS.keys())
    elif args.scenarios:
        ids = [s.upper().replace("_", "-") for s in args.scenarios]
        ids = [f"SC-{i}" if not i.startswith("SC-") else i for i in ids]
    else:
        parser.error("Podaj --scenario lub --all")

    args.ctx_dir.mkdir(parents=True, exist_ok=True)
    for sid in ids:
        ctx = seed_scenario(sid)
        print(f"OK seed {sid}")
        if args.write_ctx:
            path = args.ctx_dir / f"{sid.lower()}.json"
            path.write_text(
                json.dumps(_serialize_ctx(ctx), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  ctx → {path}")
