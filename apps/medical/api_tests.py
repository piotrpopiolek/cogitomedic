from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import MedicalDocStatus, MedicalDocument, MedicalDocumentVersion
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
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
        self.admin_user = StaffUser.objects.create_user(
            username="api-admin-medical",
            email="api.admin.medical@example.com",
            password="safe-password",
            role=StaffRole.ADMIN,
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

    def test_medical_documents_list_get(self) -> None:
        list_empty = self.client.get("/api/v1/medical-documents")
        self.assertEqual(list_empty.status_code, 200)
        data = list_empty.json()
        self.assertIn("items", data)
        self.assertIn("pagination", data)
        self.assertEqual(data["pagination"]["total"], 0)
        self.assertEqual(len(data["items"]), 0)

        self.client.post(
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
        list_one = self.client.get("/api/v1/medical-documents")
        self.assertEqual(list_one.status_code, 200)
        data = list_one.json()
        self.assertEqual(data["pagination"]["total"], 1)
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["status"], MedicalDocStatus.DRAFT)
        self.assertIn("queue_date", item)
        self.assertIn("patient", item)
        self.assertEqual(item["patient"]["last_name"], "Api")

    def test_medical_document_detail_get(self) -> None:
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

        detail = self.client.get(f"/api/v1/medical-documents/{medical_document_id}")
        self.assertEqual(detail.status_code, 200)
        data = detail.json()
        self.assertEqual(data["id"], medical_document_id)
        self.assertEqual(data["queue_entry_id"], str(self.queue_entry.id))
        self.assertIn("intake_summary", data)
        self.assertIn("patient", data["intake_summary"])
        self.assertIn("current_version", data)
        self.assertIsNone(data["current_version"])  # no version yet before first draft

        missing = self.client.get(f"/api/v1/medical-documents/{uuid4()}")
        self.assertEqual(missing.status_code, 404)

    def test_medical_document_generate_text(self) -> None:
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

        gen = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/generate-text",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "authoring_locale": "de-DE",
                    "medical_payload": {
                        "schema_version": 1,
                        "lesions": [
                            {
                                "lesion_numbers": [8],
                                "dermatoscopic_features": ["ASYMMETRY", "INHOMOGENEOUS_PIGMENTATION"],
                                "clinical_assessment": "CONTROL_NEEDED",
                                "malignancy_risk": "NO_SUSPICION",
                            }
                        ],
                        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(gen.status_code, 200)
        data = gen.json()
        self.assertTrue(data["generated"])
        self.assertEqual(len(data["lesions"]), 1)
        self.assertEqual(data["lesions"][0]["lesion_numbers"], [8])
        self.assertIn("Läsion Nr. 8", data["lesions"][0]["generated_text"])
        self.assertIn("Kontrollbedürftig", data["lesions"][0]["generated_text"])
        self.assertIn("summary_generated_text", data)
        self.assertIn("Bei der Analyse", data["summary_generated_text"])

        # Generate text for a group with multiple lesion numbers (Wideodermatoskop)
        gen2 = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/generate-text",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "authoring_locale": "de-DE",
                    "medical_payload": {
                        "schema_version": 1,
                        "lesions": [
                            {
                                "lesion_numbers": [2, 3, 13],
                                "dermatoscopic_features": ["ASYMMETRY"],
                                "clinical_assessment": "CONTROL_NEEDED",
                                "malignancy_risk": "NO_SUSPICION",
                            }
                        ],
                        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(gen2.status_code, 200)
        data2 = gen2.json()
        self.assertEqual(data2["lesions"][0]["lesion_numbers"], [2, 3, 13])
        self.assertIn("Läsion Nr. 2, 3, 13", data2["lesions"][0]["generated_text"])

        missing = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/generate-text",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 1, "lesions": []},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 404)

    def test_medical_document_generate_text_with_template_id(self) -> None:
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
        template_response = self.client.post(
            "/api/v1/doctor-text-templates",
            data=json.dumps(
                {
                    "name": "Befund Header",
                    "template_locale": "de-DE",
                    "template_body": "Befund-Kopfzeile gemäß Praxis.",
                    "is_global": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(template_response.status_code, 201)
        template_id = template_response.json()["id"]
        gen = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/generate-text",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "authoring_locale": "de-DE",
                    "template_id": template_id,
                    "medical_payload": {"schema_version": 1, "lesions": []},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(gen.status_code, 200)
        data = gen.json()
        self.assertIn("template_context", data)
        self.assertEqual(data["template_context"]["template_name"], "Befund Header")
        self.assertTrue(data["summary_generated_text"].startswith("Befund-Kopfzeile gemäß Praxis."))

    def test_published_version_keeps_template_snapshot_after_template_change(self) -> None:
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

        template_response = self.client.post(
            "/api/v1/doctor-text-templates",
            data=json.dumps(
                {
                    "name": "Snapshot Template",
                    "template_locale": "de-DE",
                    "template_body": "Version A header.",
                    "is_global": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(template_response.status_code, 201)
        template_id = template_response.json()["id"]

        generate_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/generate-text",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "authoring_locale": "de-DE",
                    "template_id": template_id,
                    "medical_payload": {"schema_version": 1, "lesions": []},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(generate_response.status_code, 200)
        generated = generate_response.json()

        draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "overall_image_assessment": "NO_CONTROL_NEEDED",
                        "lesions": [],
                        "summary_generated_text": generated["summary_generated_text"],
                        "template_context": generated["template_context"],
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)

        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "resend_sms": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)

        patch_template = self.client.patch(
            f"/api/v1/doctor-text-templates/{template_id}",
            data=json.dumps(
                {
                    "name": "Snapshot Template Changed",
                    "template_body": "Version B header.",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_template.status_code, 200)

        versions = self.client.get(f"/api/v1/medical-documents/{medical_document_id}/versions")
        self.assertEqual(versions.status_code, 200)
        published_version = versions.json()["items"][0]
        version_detail = self.client.get(f"/api/v1/medical-document-versions/{published_version['id']}")
        self.assertEqual(version_detail.status_code, 200)
        payload = version_detail.json()["medical_payload"]
        self.assertIn("Version A header.", payload.get("summary_generated_text", ""))
        self.assertEqual(payload.get("template_context", {}).get("template_name"), "Snapshot Template")

    def test_medical_document_versions_and_version_detail(self) -> None:
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

        versions_list = self.client.get(f"/api/v1/medical-documents/{medical_document_id}/versions")
        self.assertEqual(versions_list.status_code, 200)
        self.assertEqual(versions_list.json()["items"], [])

        self.client.put(
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
        versions_list2 = self.client.get(f"/api/v1/medical-documents/{medical_document_id}/versions")
        self.assertEqual(versions_list2.status_code, 200)
        items = versions_list2.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["version_no"], 1)
        self.assertEqual(items[0]["version_status"], "DRAFT")
        version_id = items[0]["id"]

        version_detail = self.client.get(f"/api/v1/medical-document-versions/{version_id}")
        self.assertEqual(version_detail.status_code, 200)
        v = version_detail.json()
        self.assertEqual(v["medical_document_id"], medical_document_id)
        self.assertEqual(v["version_no"], 1)
        self.assertEqual(v["medical_payload_schema_version"], 1)
        self.assertIn("lesions", v["medical_payload"])

        self.assertEqual(self.client.get(f"/api/v1/medical-document-versions/{uuid4()}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/medical-documents/{uuid4()}/versions").status_code, 404)

    def test_medical_document_draft_v1_validation_rejects_duplicate_lesion_numbers(self) -> None:
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
        r = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "lesions": [
                            {
                                "lesion_numbers": [2, 3, 2],
                                "clinical_assessment": "CONTROL_NEEDED",
                                "malignancy_risk": "NO_SUSPICION",
                            }
                        ],
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.json())

    def test_medical_document_draft_v1_validation_rejects_control_needed_without_lesions(self) -> None:
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
        r = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "overall_image_assessment": "CONTROL_NEEDED",
                        "lesions": [],
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.json())

    def test_publish_accepts_resend_sms(self) -> None:
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
        self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 1, "authoring_locale": "de-DE", "lesions": []},
                }
            ),
            content_type="application/json",
        )
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "resend_sms": True,
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)

    def test_publish_without_draft_returns_400(self) -> None:
        """Publish without prior 'Zapisz szkic' returns 400; full validation via draft is required."""
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
        # Do NOT save draft; publish directly
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 400)
        self.assertIn("No draft version available", publish_response.json().get("error", ""))

    def test_publish_same_request_id_with_different_locale_returns_400(self) -> None:
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

        draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "overall_image_assessment": "NO_CONTROL_NEEDED",
                        "lesions": [],
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)

        request_id = str(uuid4())
        first_publish = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": request_id,
                    "published_by_user_id": str(self.doctor_user.id),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(first_publish.status_code, 200)

        second_publish = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": request_id,
                    "published_by_user_id": str(self.doctor_user.id),
                    "publish_locale": "en-GB",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(second_publish.status_code, 400)
        self.assertIn("different publish_locale", second_publish.json().get("error", ""))

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

    def test_retry_processing_endpoint_allows_admin_and_rejects_doctor(self) -> None:
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
        self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 1, "authoring_locale": "de-DE", "lesions": []},
                }
            ),
            content_type="application/json",
        )
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps({"publish_request_id": str(uuid4())}),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        version_id = publish_response.json()["medical_document_version_id"]
        event = OutboxEvent.objects.get(
            medical_document_version_id=version_id,
            event_type=OutboxEventType.GENERATE_PDF,
        )
        event.status = OutboxStatus.FAILED
        event.error_message = "Simulated failure."
        event.save(update_fields=["status", "error_message", "updated_at"])

        doctor_retry = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/retry-processing",
            data=json.dumps({"reason": "retry"}),
            content_type="application/json",
        )
        self.assertEqual(doctor_retry.status_code, 403)

        self.client.force_login(self.admin_user)
        admin_retry = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/retry-processing",
            data=json.dumps({"reason": "manual retry"}),
            content_type="application/json",
        )
        self.assertEqual(admin_retry.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PENDING)

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
                    "template_locale": "pl-PL",
                    "template_body": "Text",
                    "lesion_group_favorites": [
                        {
                            "name": "Atypical control",
                            "dermatoscopic_features": ["ASYMMETRY", "MULTICOLOR"],
                            "clinical_assessment": "CONTROL_NEEDED",
                            "malignancy_risk": "LOW_SUSPICION",
                            "text": "Zmiana kontrolna do obserwacji.",
                        }
                    ],
                    "summary_favorites": [
                        {
                            "name": "Summary short",
                            "text": "Brak cech wysokiego ryzyka.",
                        }
                    ],
                    "is_global": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_private.status_code, 201)
        self.assertEqual(create_private.json()["template_locale"], "pl-PL")
        self.assertEqual(len(create_private.json()["lesion_group_favorites"]), 1)
        self.assertEqual(len(create_private.json()["summary_favorites"]), 1)
        template_id = create_private.json()["id"]

        template_detail = self.client.get(f"/api/v1/doctor-text-templates/{template_id}")
        self.assertEqual(template_detail.status_code, 200)
        self.assertEqual(template_detail.json()["lesion_group_favorites"][0]["clinical_assessment"], "CONTROL_NEEDED")
        self.assertEqual(template_detail.json()["summary_favorites"][0]["name"], "Summary short")

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
                    "summary_favorites": [{"name": "Summary changed", "text": "Nowy tekst podsumowania."}],
                    "is_active": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_owner.status_code, 200)
        self.assertFalse(patch_owner.json()["is_active"])
        self.assertEqual(patch_owner.json()["summary_favorites"][0]["name"], "Summary changed")
