from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import MedicalDocStatus, MedicalDocumentVersion
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientFormSession,
    QueueEntry,
    QueueEntryStatus,
    QueueStatus,
)
from apps.users.models import StaffRole, StaffUser


class MedicalApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor_user = StaffUser.objects.create_user(
            username="api-doctor",
            email="api.doctor@example.com",
            password="safe-password",
            role=StaffRole.DOCTOR,
            is_staff=True,
        )
        self.reception_user = StaffUser.objects.create_user(
            username="api-reception-medical",
            email="api.reception.medical@example.com",
            password="safe-password",
            role=StaffRole.RECEPTION,
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="API2", name="API Clinic 2")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="B1", name="B1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Medical",
            last_name="Api",
            date_of_birth=date(1988, 8, 8),
            phone="+48111222333",
            email="medical.api@example.com",
            doctolib_patient_id="DOC-API-MED-1",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            token_hash="f" * 64,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        self.queue_entry.active_session = session
        self.queue_entry.save(update_fields=["active_session", "updated_at"])
        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature.png",
            signature_sha256="c" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"schema_version": 1, "answers": []},
        )
        self.client.force_login(self.doctor_user)

    def test_medical_document_create_draft_publish_flow(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]

        invalid_draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 2},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(invalid_draft_response.status_code, 400)

        draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 1, "authoring_locale": "de-DE", "lesions": []},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_response.json()["version_status"], "DRAFT")

        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["version_status"], "PUBLISHED")

        version_id = publish_response.json()["medical_document_version_id"]
        version = MedicalDocumentVersion.objects.get(id=version_id)
        self.assertEqual(version.version_status, "PUBLISHED")
        self.assertEqual(version.medical_document.status, MedicalDocStatus.PUBLISHED)

    def test_medical_document_endpoints_return_404_for_missing_resources(self) -> None:
        missing_doc_id = uuid4()

        create_missing_dependencies = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(uuid4()),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_missing_dependencies.status_code, 404)

        draft_missing_doc = self.client.put(
            f"/api/v1/medical-documents/{missing_doc_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 1},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_missing_doc.status_code, 404)

        publish_missing_doc = self.client.post(
            f"/api/v1/medical-documents/{missing_doc_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_missing_doc.status_code, 404)

    def test_medical_endpoints_require_authentication(self) -> None:
        self.client.logout()
        response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)


class DoctorTemplatesApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.admin_user = StaffUser.objects.create_user(
            username="api-admin-templates",
            email="api.admin.templates@example.com",
            password="safe-password",
            role=StaffRole.ADMIN,
            is_staff=True,
        )
        self.doctor_user = StaffUser.objects.create_user(
            username="api-doctor-templates",
            email="api.doctor.templates@example.com",
            password="safe-password",
            role=StaffRole.DOCTOR,
            is_staff=True,
        )
        self.other_doctor_user = StaffUser.objects.create_user(
            username="api-doctor-templates-2",
            email="api.doctor.templates2@example.com",
            password="safe-password",
            role=StaffRole.DOCTOR,
            is_staff=True,
        )

    def test_doctor_templates_create_list_patch_permissions(self) -> None:
        # Doctor can create private template
        self.client.force_login(self.doctor_user)
        create_private = self.client.post(
            "/api/v1/doctor-text-templates",
            data=json.dumps(
                {
                    "actor_user_id": str(self.doctor_user.id),
                    "name": "My Template",
                    "template_locale": "de-DE",
                    "template_body": "Text",
                    "is_global": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_private.status_code, 201)
        template_id = create_private.json()["id"]

        # Doctor cannot create global template
        create_global_forbidden = self.client.post(
            "/api/v1/doctor-text-templates",
            data=json.dumps(
                {
                    "actor_user_id": str(self.doctor_user.id),
                    "name": "Global Forbidden",
                    "template_locale": "de-DE",
                    "template_body": "Text",
                    "is_global": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_global_forbidden.status_code, 400)

        # Admin can create global template
        self.client.force_login(self.admin_user)
        create_global = self.client.post(
            "/api/v1/doctor-text-templates",
            data=json.dumps(
                {
                    "actor_user_id": str(self.admin_user.id),
                    "name": "Global Allowed",
                    "template_locale": "de-DE",
                    "template_body": "Global text",
                    "is_global": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_global.status_code, 201)

        # Doctor sees own + global templates
        self.client.force_login(self.doctor_user)
        doctor_list = self.client.get(
            f"/api/v1/doctor-text-templates?actor_user_id={self.doctor_user.id}&include_inactive=true"
        )
        self.assertEqual(doctor_list.status_code, 200)
        self.assertGreaterEqual(len(doctor_list.json()["results"]), 2)

        # Other doctor cannot patch someone else's private template
        self.client.force_login(self.other_doctor_user)
        patch_forbidden = self.client.patch(
            f"/api/v1/doctor-text-templates/{template_id}",
            data=json.dumps(
                {
                    "actor_user_id": str(self.other_doctor_user.id),
                    "name": "Hack",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_forbidden.status_code, 400)

        # Owner can patch own private template
        self.client.force_login(self.doctor_user)
        patch_owner = self.client.patch(
            f"/api/v1/doctor-text-templates/{template_id}",
            data=json.dumps(
                {
                    "actor_user_id": str(self.doctor_user.id),
                    "is_active": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_owner.status_code, 200)
        self.assertFalse(patch_owner.json()["is_active"])
