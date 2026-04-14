from __future__ import annotations

from django.conf import settings

if False:  # pragma: no cover
    from apps.intake.models import IntakeDocumentVersion
    from apps.medical.models import MedicalDocumentVersion

HIDRIVE_BEFUND_FILENAME_TEMPLATE = "Befund_v{version_no}.pdf"
HIDRIVE_INTAKE_FILENAME_TEMPLATE = "Intake_v{version_no}.pdf"


def _patients_dir_prefix() -> str:
    """Directory for ``…/{patient_uuid}/Befund_vN.pdf`` (logical path before ``/users/<alias>``)."""
    raw = (
        getattr(settings, "HIDRIVE_PATIENTS_DIR_PREFIX", "/patients") or "/patients"
    ).strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or "/patients"


def build_befund_hidrive_path(version: "MedicalDocumentVersion") -> str:
    patient = version.medical_document.queue_entry.patient
    file_name = HIDRIVE_BEFUND_FILENAME_TEMPLATE.format(version_no=version.version_no)
    return f"{_patients_dir_prefix()}/{patient.id}/{file_name}"


def build_intake_hidrive_path(version: "IntakeDocumentVersion") -> str:
    patient = version.intake_form.queue_entry.patient
    file_name = HIDRIVE_INTAKE_FILENAME_TEMPLATE.format(version_no=version.version_no)
    return f"{_patients_dir_prefix()}/{patient.id}/{file_name}"
