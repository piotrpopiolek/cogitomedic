"""Seed demo users, clinic, queue, and portal sessions for manual screenshots/videos.

Call :func:`scripts.manual_demo.django_setup.setup_django` once before this function.
"""

from __future__ import annotations

from datetime import date, timedelta


def _delete_medical_docs_for_queue(queue) -> None:
    """Drop medical docs for fixed screenshot rows (positions 1–3) only.

    Scenario seeds share the same daily queue; wiping *all* docs would destroy
    previously seeded SC-* medical documents when batch-seeding ``--all``.
    """
    from apps.medical.models import (
        ExternalPdfAttachment,
        MedicalDocument,
        MedicalDocumentVersion,
    )
    from apps.reception.models import QueueEntry

    entry_ids = QueueEntry.objects.filter(
        daily_queue=queue, position_no__in=(1, 2, 3)
    ).values_list("id", flat=True)
    docs = MedicalDocument.objects.filter(queue_entry_id__in=entry_ids)
    MedicalDocumentVersion.objects.filter(medical_document__in=docs).update(
        external_selected_attachment=None
    )
    ExternalPdfAttachment.objects.filter(medical_document__in=docs).delete()
    docs.delete()


def seed_manual_demo(ctx: dict) -> None:
    from django.contrib.sessions.backends.db import SessionStore
    from django.utils import timezone

    from apps.core.api_utils import assign_group_to_test_user
    from apps.intake.models import (
        IntakeDocumentVersion,
        IntakePdfStatus,
        IntakeStatus,
        PatientIntakeForm,
    )
    from apps.medical.services import (
        create_or_get_medical_document,
        save_draft_document_version,
    )
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

    reception = _user(
        "screenshot_reception", "screenshot_reception@example.invalid", "Reception"
    )
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

    _delete_medical_docs_for_queue(queue)
    QueueEntry.objects.filter(daily_queue=queue, position_no__in=(1, 2, 3)).delete()

    # Pacjent pod zrzuty manual/06: stabilny reset po adresie e-mail (zrzuty zmieniają m.in. telefon).
    p_done = Patient.objects.filter(email="anna.demo@example.invalid").first()
    if p_done is None:
        p_done, _ = Patient.objects.get_or_create(
            phone="1111111111111",
            defaults={
                "first_name": "Anna",
                "last_name": "Demo",
                "date_of_birth": date(1985, 5, 15),
                "email": "anna.demo@example.invalid",
            },
        )
    p_done.first_name = "Anna"
    p_done.last_name = "Demo"
    p_done.date_of_birth = date(1985, 5, 15)
    p_done.phone = "1111111111111"
    p_done.email = "anna.demo@example.invalid"
    p_done.street = ""
    p_done.save(
        update_fields=[
            "first_name",
            "last_name",
            "date_of_birth",
            "phone",
            "email",
            "street",
            "updated_at",
        ]
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

    from scripts.manual_demo.scenario_helpers import DEMO_PAYLOAD

    md = create_or_get_medical_document(
        queue_entry_id=entry_done.id,
        intake_form_id=intake_done.id,
        created_by_user_id=doctor.id,
    )
    save_draft_document_version(
        medical_document_id=md.id,
        updated_by_user_id=doctor.id,
        medical_payload=DEMO_PAYLOAD,
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
    from apps.medical.incoming_pdf_scan import suggest_incoming_pdf_filename

    ctx["anna_demo_incoming_pdf"] = suggest_incoming_pdf_filename(p_done)
    seed_manual_screenshot_extras(ctx)


def seed_manual_screenshot_extras(ctx: dict) -> None:
    """Extra demo rows for accounting / external-upload / paper / HiDrive screenshots."""
    from django.utils import timezone

    from apps.medical.models import (
        ExternalPdfAttachment,
        MedicalDocument,
        MedicalDocumentVersion,
        PaperIntakeAuthorization,
    )
    from apps.reception.models import Patient, QueueEntry, QueueEntryStatus
    from apps.medical.services import save_draft_document_version
    from scripts.manual_demo.scenario_helpers import (
        create_draft_document,
        create_submitted_entry,
        ensure_accounting_user,
        ensure_manager_user,
        force_publish,
        next_position,
        rich_revision_payload,
        seed_mock_incoming,
        upsert_patient,
    )

    ensure_accounting_user(ctx)
    ensure_manager_user(ctx)

    clinic = ctx["clinic"]
    queue = ctx["queue"]
    reception = ctx["reception"]

    demo_emails = (
        "hans.accountingdemo@example.invalid",
        "walter.externaldemo@example.invalid",
        "tina.needpapert1@example.invalid",
        "iris.nopdfdemo@example.invalid",
        "greta.revisionshot@example.invalid",
        "rita.revokeshot@example.invalid",
    )
    demo_patients = Patient.objects.filter(email__in=demo_emails)
    demo_entries = QueueEntry.objects.filter(
        daily_queue=queue, patient__in=demo_patients
    )
    PaperIntakeAuthorization.objects.filter(queue_entry__in=demo_entries).delete()
    docs = MedicalDocument.objects.filter(queue_entry__in=demo_entries)
    MedicalDocumentVersion.objects.filter(medical_document__in=docs).update(
        external_selected_attachment=None
    )
    ExternalPdfAttachment.objects.filter(medical_document__in=docs).delete()
    docs.delete()
    demo_entries.delete()

    p_acc = upsert_patient(
        phone="491111000004",
        first_name="Hans",
        last_name="AccountingDemo",
        dob=date(1969, 2, 14),
        email="hans.accountingdemo@example.invalid",
        clinic=clinic,
    )
    entry_acc, intake_acc = create_submitted_entry(ctx, patient=p_acc)
    md_acc = create_draft_document(ctx, entry_acc, intake_acc)
    force_publish(ctx, md_acc)
    ctx["accounting_entry_id"] = str(entry_acc.id)

    p_ext = upsert_patient(
        phone="491111000021",
        first_name="Walter",
        last_name="ExternalDemo",
        dob=date(1979, 2, 28),
        email="walter.externaldemo@example.invalid",
        clinic=clinic,
    )
    entry_ext, _intake_ext = create_submitted_entry(ctx, patient=p_ext)
    ctx["external_upload_entry_id"] = str(entry_ext.id)

    p_paper = upsert_patient(
        phone="491111000018",
        first_name="Tina",
        last_name="NeedPaperT1",
        dob=date(1965, 6, 15),
        email="tina.needpapert1@example.invalid",
        clinic=clinic,
    )
    entry_paper = QueueEntry.objects.create(
        daily_queue=queue,
        patient=p_paper,
        position_no=next_position(queue),
        entry_status=QueueEntryStatus.WAITING,
        appointment_time=timezone.now() - timedelta(hours=6),
        created_by_user=reception,
    )
    ctx["paper_intake_entry_id"] = str(entry_paper.id)

    # Empty /incoming so draft Befunds without lab PDF appear on reception dashboard.
    seed_mock_incoming([])
    p_hd = upsert_patient(
        phone="491111000005",
        first_name="Iris",
        last_name="NoPdfDemo",
        dob=date(1991, 6, 8),
        email="iris.nopdfdemo@example.invalid",
        clinic=clinic,
    )
    entry_hd, intake_hd = create_submitted_entry(ctx, patient=p_hd)
    create_draft_document(ctx, entry_hd, intake_hd)
    ctx["hidrive_missing_entry_id"] = str(entry_hd.id)

    # Portal patient (session_doc_key): published Befund + mock PDF for documents list.
    from apps.reception.models import Patient as PatientModel

    p_portal = PatientModel.objects.filter(
        email="portal.patient@example.invalid"
    ).first()
    if p_portal is not None:
        p_portal.clinic_sites.add(clinic)
        entry_portal, intake_portal = create_submitted_entry(ctx, patient=p_portal)
        md_portal = create_draft_document(ctx, entry_portal, intake_portal)
        force_publish(ctx, md_portal, pdf_label="portal_demo")
        ctx["portal_published_doc_id"] = str(md_portal.id)
        ctx["portal_published_entry_id"] = str(entry_portal.id)

    # Published + open revision (doctor-07 revision / resend SMS screenshots).
    p_rev = upsert_patient(
        phone="491111000029",
        first_name="Greta",
        last_name="RevisionShot",
        dob=date(1982, 11, 21),
        email="greta.revisionshot@example.invalid",
        clinic=clinic,
    )
    entry_rev, intake_rev = create_submitted_entry(ctx, patient=p_rev)
    md_rev = create_draft_document(ctx, entry_rev, intake_rev)
    force_publish(ctx, md_rev, pdf_label="revision_shot")
    save_draft_document_version(
        medical_document_id=md_rev.id,
        updated_by_user_id=ctx["doctor"].id,
        medical_payload=rich_revision_payload(),
        intent="amend",
    )
    md_rev.refresh_from_db()
    ctx["revision_demo_doc_id"] = str(md_rev.id)

    # Separate published doc for revoke modal (doctor-08) — delivery complete.
    p_revoke = upsert_patient(
        phone="491111000015",
        first_name="Rita",
        last_name="RevokeShot",
        dob=date(1975, 9, 9),
        email="rita.revokeshot@example.invalid",
        clinic=clinic,
    )
    entry_revoke, intake_revoke = create_submitted_entry(ctx, patient=p_revoke)
    md_revoke = create_draft_document(ctx, entry_revoke, intake_revoke)
    force_publish(ctx, md_revoke, pdf_label="revoke_shot")
    ctx["revoke_demo_doc_id"] = str(md_revoke.id)
