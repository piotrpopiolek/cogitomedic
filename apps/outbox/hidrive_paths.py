from __future__ import annotations

import re

if False:  # pragma: no cover
    from apps.intake.models import IntakeDocumentVersion
    from apps.medical.models import MedicalDocumentVersion

HIDRIVE_BEFUND_FILENAME_TEMPLATE = "Befund_v{version_no}.pdf"
HIDRIVE_INTAKE_FILENAME_TEMPLATE = "Intake_v{version_no}.pdf"


def _sanitize_folder_part(value: str) -> str:
    cleaned = re.sub(r"[\\/]+", " ", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _patient_folder_name(*, patient_id: str, first_name: str, last_name: str, doctolib_patient_id: str | None) -> str:
    last = _sanitize_folder_part(last_name)
    first = _sanitize_folder_part(first_name)
    full_name = f"{last} {first}".strip()
    if full_name:
        return full_name
    fallback = _sanitize_folder_part(doctolib_patient_id or "")
    return fallback or patient_id


def build_befund_hidrive_path(version: "MedicalDocumentVersion") -> str:
    patient = version.medical_document.queue_entry.patient
    folder = _patient_folder_name(
        patient_id=str(patient.id),
        first_name=patient.first_name,
        last_name=patient.last_name,
        doctolib_patient_id=patient.doctolib_patient_id,
    )
    file_name = HIDRIVE_BEFUND_FILENAME_TEMPLATE.format(version_no=version.version_no)
    return f"/hidrive/patients/{folder}/{file_name}"


def build_intake_hidrive_path(version: "IntakeDocumentVersion") -> str:
    patient = version.intake_form.queue_entry.patient
    folder = _patient_folder_name(
        patient_id=str(patient.id),
        first_name=patient.first_name,
        last_name=patient.last_name,
        doctolib_patient_id=patient.doctolib_patient_id,
    )
    file_name = HIDRIVE_INTAKE_FILENAME_TEMPLATE.format(version_no=version.version_no)
    return f"/hidrive/patients/{folder}/{file_name}"
