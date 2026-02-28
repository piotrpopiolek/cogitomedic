from __future__ import annotations

from datetime import datetime

if False:  # pragma: no cover
    from apps.intake.models import IntakeDocumentVersion
    from apps.medical.models import MedicalDocumentVersion


def _patient_folder_name(*, patient_id: str, doctolib_patient_id: str | None) -> str:
    return doctolib_patient_id or patient_id


def build_befund_hidrive_path(version: "MedicalDocumentVersion") -> str:
    patient = version.medical_document.queue_entry.patient
    folder = _patient_folder_name(patient_id=str(patient.id), doctolib_patient_id=patient.doctolib_patient_id)
    stamp = (version.published_at or version.created_at).strftime("%Y%m%d")
    return f"/hidrive/patients/{folder}/{stamp}_befund_{version.id}.pdf"


def build_intake_hidrive_path(version: "IntakeDocumentVersion", *, now: datetime) -> str:
    patient = version.intake_form.queue_entry.patient
    folder = _patient_folder_name(patient_id=str(patient.id), doctolib_patient_id=patient.doctolib_patient_id)
    stamp = (version.intake_form.submitted_at or now).strftime("%Y%m%d")
    return f"/hidrive/patients/{folder}/{stamp}_intake_{version.id}.pdf"
