"""Seed demo users, clinic, queue, and portal sessions for manual screenshots/videos.

Call :func:`scripts.manual_demo.django_setup.setup_django` once before this function.
"""
from __future__ import annotations

from datetime import date, timedelta


def seed_manual_demo(ctx: dict) -> None:
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
