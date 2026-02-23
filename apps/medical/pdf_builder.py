from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.medical.models import MedicalDocumentVersion


def _pretty_code(value: str | None) -> str:
    if not value:
        return "-"
    return value.replace("_", " ").title()


def _lesion_final_text(lesion: dict[str, Any]) -> str:
    edited = (lesion.get("edited_text") or "").strip()
    if edited:
        return edited
    generated = (lesion.get("generated_text") or "").strip()
    if generated:
        return generated
    return "-"


def _build_render_context(version: MedicalDocumentVersion) -> dict[str, Any]:
    payload = version.medical_payload or {}
    patient = version.medical_document.queue_entry.patient

    lesions = []
    for idx, lesion in enumerate(payload.get("lesions") or [], start=1):
        numbers = [str(n) for n in (lesion.get("lesion_numbers") or [])]
        lesions.append(
            {
                "index": idx,
                "numbers": ", ".join(numbers) if numbers else "-",
                "clinical_assessment": _pretty_code(lesion.get("clinical_assessment")),
                "malignancy_risk": _pretty_code(lesion.get("malignancy_risk")),
                "features": [_pretty_code(v) for v in (lesion.get("dermatoscopic_features") or [])],
                "final_text": _lesion_final_text(lesion),
            }
        )

    summary_text = (payload.get("summary_edited_text") or "").strip() or (payload.get("summary_generated_text") or "").strip()
    exam_scope = [_pretty_code(v) for v in (payload.get("examination_scope") or [])]
    recommendations = [_pretty_code(v) for v in (payload.get("recommendations") or [])]

    return {
        "document_id": str(version.medical_document_id),
        "version_no": version.version_no,
        "generated_at": timezone.now(),
        "authoring_locale": payload.get("authoring_locale") or "de-DE",
        "patient": {
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "date_of_birth": patient.date_of_birth,
            "phone": patient.phone,
            "email": patient.email,
        },
        "befund": {
            "fitzpatrick_type": _pretty_code(payload.get("fitzpatrick_type")),
            "overall_image_assessment": _pretty_code(payload.get("overall_image_assessment")),
            "final_assessment": _pretty_code(payload.get("final_assessment")),
            "diagnosis_code": version.diagnosis_code or "-",
            "procedure_code": version.procedure_code or "-",
            "examination_scope": exam_scope,
            "recommendations": recommendations,
            "lesions": lesions,
            "summary_text": summary_text or "-",
        },
    }


def generate_befund_pdf(version: MedicalDocumentVersion) -> tuple[str, str]:
    """
    Generate and store Befund PDF for medical document version.

    Returns:
        (pdf_local_path_relative_to_media_root, sha256_checksum_hex)
    """
    context = _build_render_context(version)
    html = render_to_string("pdf/befund_document.html", context)
    pdf_bytes = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()

    now = timezone.now()
    relative_dir = Path(getattr(settings, "PDF_RELATIVE_DIR", "pdfs")) / f"{now.year:04d}" / f"{now.month:02d}"
    relative_path = relative_dir / f"{version.id}.pdf"
    full_path = Path(settings.MEDIA_ROOT) / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(pdf_bytes)

    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    relative_str = str(relative_path).replace("\\", "/")
    return relative_str, checksum
