from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.core.translation_service import get_translation_map
from apps.medical.models import (
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocumentVersion,
)
from apps.core.translation_service import get_doctor_ui, get_fitzpatrick_choices
from apps.medical.external_pdf_service import (
    ExternalPdfCorruptError,
    download_external_pdf,
)
from apps.medical.pdf_merge import safe_merge_pdfs
from apps.operations.services import create_audit_event

# Map payload enum codes to doctor_ui keys so PDF shows translated text (DE/EN/PL)
RECOMMENDATION_CODE_TO_UI_KEY: dict[str, str] = {
    "FOLLOWUP_3_MONTHS": "rec_followup_3",
    "FOLLOWUP_6_MONTHS": "rec_followup_6",
    "FOLLOWUP_12_MONTHS": "rec_followup_12",
    "PROMPT_VISIT_ON_CHANGE": "rec_prompt_visit",
    "NO_SHORT_TERM_FOLLOWUP_REQUIRED": "rec_no_short",
}
EXAMINATION_SCOPE_CODE_TO_UI_KEY: dict[str, str] = {
    "INTIMATE_AREA_NOT_EXAMINED": "examination_intimate",
    "ORAL_MUCOSA_NOT_EXAMINED": "examination_oral",
}
OVERALL_IMAGE_CODE_TO_UI_KEY: dict[str, str] = {
    "NO_CONTROL_NEEDED": "overall_no_control",
    "CONTROL_NEEDED": "overall_control",
}
FINAL_ASSESSMENT_CODE_TO_UI_KEY: dict[str, str] = {
    "NO_HIGH_GRADE_SUSPICION": "final_no_suspicion",
    "HIGH_GRADE_CANNOT_BE_EXCLUDED": "final_high_grade",
}
CLINICAL_ASSESSMENT_CODE_TO_UI_KEY: dict[str, str] = {
    "UNREMARKABLE": "clinical_unremarkable",
    "SLIGHTLY_ATYPICAL": "clinical_slight",
    "CONTROL_NEEDED": "clinical_control",
    "SUSPICIOUS": "clinical_suspicious",
}
MALIGNANCY_RISK_CODE_TO_UI_KEY: dict[str, str] = {
    "NO_SUSPICION": "malignancy_none",
    "LOW_SUSPICION": "malignancy_low",
    "CANNOT_EXCLUDE": "malignancy_cannot_exclude",
}
DERMATOSCOPIC_FEATURE_CODE_TO_UI_KEY: dict[str, str] = {
    "ASYMMETRY": "feature_asymmetry",
    "IRREGULAR_BORDER": "feature_irregular_border",
    "INHOMOGENEOUS_PIGMENTATION": "feature_inhomogeneous",
    "MULTICOLOR": "feature_multicolor",
    "ATYPICAL_PIGMENT_NETWORK": "feature_atypical_network",
    "IRREGULAR_GLOBULES": "feature_irregular_globules",
    "IRREGULAR_DOTS": "feature_irregular_dots",
    "STRUCTURELESS_AREAS": "feature_structureless",
    "ATYPICAL_VASCULAR_STRUCTURES": "feature_vascular",
    "REGRESSION_AREAS": "feature_regression",
}


# PDF label short keys — user-facing strings live in DB (doctor.pdf_label.*), seeded from JSON.
def _pdf_labels(locale: str) -> dict[str, str]:
    """Return PDF labels from DB-only translation storage."""
    lang = _authoring_locale_to_lang(locale)
    mapping = get_translation_map(category="doctor", language_code=lang)
    keys = [
        "befund",
        "document_id",
        "version",
        "generated_at",
        "locale",
        "patient",
        "name",
        "date_of_birth",
        "phone",
        "email",
        "global_assessment",
        "fitzpatrick_type",
        "overall_image_assessment",
        "final_assessment",
        "diagnosis_code",
        "procedure_code",
        "examination_scope",
        "lesions",
        "group",
        "numbers",
        "clinical_assessment",
        "malignancy_risk",
        "dermatoscopic_features",
        "final_text",
        "recommendations",
        "summary",
        "no_lesions",
    ]
    labels: dict[str, str] = {}
    for key in keys:
        full_key = f"doctor.pdf_label.{key}"
        labels[key] = mapping.get(full_key) or key.replace("_", " ").title()
    return labels


def _authoring_locale_to_lang(authoring_locale: str) -> str:
    """Return doctor_ui lang ('de', 'en', 'pl') from authoring_locale (e.g. de-DE, en-GB, pl-PL)."""
    if not authoring_locale:
        return "de"
    if authoring_locale.startswith("en"):
        return "en"
    if authoring_locale.startswith("pl"):
        return "pl"
    return "de"


def _translate_code(
    code: str | None,
    ui: dict[str, str],
    code_to_key: dict[str, str],
) -> str:
    """Return translated label for a payload enum code, or pretty code if unknown."""
    if not code:
        return "-"
    key = code_to_key.get(code)
    if key and key in ui:
        return ui[key]
    return code.replace("_", " ").title()


def _translate_recommendation(code: str, ui: dict[str, str]) -> str:
    """Return translated recommendation label for PDF."""
    return _translate_code(code, ui, RECOMMENDATION_CODE_TO_UI_KEY)


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


def _build_render_context(
    version: MedicalDocumentVersion,
    authoring_locale_override: str | None = None,
) -> dict[str, Any]:
    payload = version.medical_payload or {}
    patient = version.medical_document.queue_entry.patient

    authoring_locale = (
        (authoring_locale_override or "").strip()
        or (version.publish_locale or "").strip()
        or payload.get("authoring_locale")
        or "de-DE"
    )
    if not authoring_locale or len(authoring_locale) > 10:
        authoring_locale = "de-DE"
    labels = _pdf_labels(authoring_locale)
    lang = _authoring_locale_to_lang(authoring_locale)
    doctor_ui = get_doctor_ui(lang)
    fitzpatrick_labels = {
        value: label for value, label in get_fitzpatrick_choices(lang)
    }

    lesions = []
    for idx, lesion in enumerate(payload.get("lesions") or [], start=1):
        numbers = [str(n) for n in (lesion.get("lesion_numbers") or [])]
        lesions.append(
            {
                "index": idx,
                "numbers": ", ".join(numbers) if numbers else "-",
                "clinical_assessment": _translate_code(
                    lesion.get("clinical_assessment"),
                    doctor_ui,
                    CLINICAL_ASSESSMENT_CODE_TO_UI_KEY,
                ),
                "malignancy_risk": _translate_code(
                    lesion.get("malignancy_risk"),
                    doctor_ui,
                    MALIGNANCY_RISK_CODE_TO_UI_KEY,
                ),
                "features": [
                    _translate_code(v, doctor_ui, DERMATOSCOPIC_FEATURE_CODE_TO_UI_KEY)
                    for v in (lesion.get("dermatoscopic_features") or [])
                ],
                "final_text": _lesion_final_text(lesion),
            }
        )

    summary_text = (payload.get("summary_edited_text") or "").strip() or (
        payload.get("summary_generated_text") or ""
    ).strip()
    exam_scope = [
        _translate_code(v, doctor_ui, EXAMINATION_SCOPE_CODE_TO_UI_KEY)
        for v in (payload.get("examination_scope") or [])
    ]
    recommendations = [
        _translate_recommendation(v, doctor_ui)
        for v in (payload.get("recommendations") or [])
    ]

    fp_code = payload.get("fitzpatrick_type")
    fitzpatrick_type_label = fitzpatrick_labels.get(fp_code) if fp_code else None
    if not fitzpatrick_type_label:
        fitzpatrick_type_label = _pretty_code(fp_code)

    return {
        "document_id": str(version.medical_document_id),
        "version_no": version.version_no,
        "generated_at": timezone.now(),
        "authoring_locale": authoring_locale,
        "labels": labels,
        "patient": {
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "date_of_birth": patient.date_of_birth,
            "phone": patient.phone,
            "email": patient.email,
        },
        "befund": {
            "fitzpatrick_type": fitzpatrick_type_label,
            "overall_image_assessment": _translate_code(
                payload.get("overall_image_assessment"),
                doctor_ui,
                OVERALL_IMAGE_CODE_TO_UI_KEY,
            ),
            "final_assessment": _translate_code(
                payload.get("final_assessment"),
                doctor_ui,
                FINAL_ASSESSMENT_CODE_TO_UI_KEY,
            ),
            "diagnosis_code": version.diagnosis_code or "-",
            "procedure_code": version.procedure_code or "-",
            "examination_scope": exam_scope,
            "recommendations": recommendations,
            "lesions": lesions,
            "summary_text": summary_text or "-",
        },
    }


def build_befund_pdf_bytes(
    version: MedicalDocumentVersion,
    authoring_locale_override: str | None = None,
) -> bytes:
    """
    Build Befund PDF for the given version and return PDF bytes (no file write).
    Used for preview (with optional locale override) and by generate_befund_pdf.
    When authoring_locale_override is set (e.g. from request), PDF labels and
    locale match the doctor's current language; otherwise payload's authoring_locale is used.
    """
    context = _build_render_context(
        version, authoring_locale_override=authoring_locale_override
    )
    html = render_to_string("pdf/befund_document.html", context)
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()


def generate_befund_pdf(version: MedicalDocumentVersion) -> tuple[str, str]:
    """
    Generate and store Befund PDF for medical document version.

    Returns:
        (pdf_local_path_relative_to_media_root, sha256_checksum_hex)
    """
    befund_bytes = build_befund_pdf_bytes(version)
    doc = version.medical_document
    patient = doc.queue_entry.patient

    attachments = list(
        ExternalPdfAttachment.objects.filter(
            medical_document=doc,
            status=ExternalPdfStatus.MATCHED,
        ).order_by("original_filename", "hidrive_remote_path")
    )
    external_bytes_list: list[bytes] = []
    attachments_used: list[ExternalPdfAttachment] = []
    for att in attachments:
        try:
            ext_bytes = download_external_pdf(att)
        except ExternalPdfCorruptError:
            att.status = ExternalPdfStatus.MERGE_FAILED
            att.save(update_fields=["status"])
            create_audit_event(
                event_type="EXTERNAL_PDF_CORRUPT",
                patient_id=patient.id,
                medical_document_id=doc.id,
                metadata={
                    "hidrive_remote_path": att.hidrive_remote_path,
                    "external_pdf_attachment_id": str(att.id),
                },
            )
            continue
        external_bytes_list.append(ext_bytes)
        attachments_used.append(att)

    if external_bytes_list:
        pdf_bytes, merge_ok = safe_merge_pdfs(befund_bytes, external_bytes_list)
        if not merge_ok:
            for att in attachments_used:
                att.status = ExternalPdfStatus.MERGE_FAILED
            ExternalPdfAttachment.objects.bulk_update(attachments_used, ["status"])
            create_audit_event(
                event_type="EXTERNAL_PDF_MERGE_FAILED",
                patient_id=patient.id,
                medical_document_id=doc.id,
                metadata={
                    "error_message": "PDF merge failed; Befund-only PDF stored.",
                },
            )
    else:
        pdf_bytes = befund_bytes

    now = version.created_at
    relative_dir = (
        Path(getattr(settings, "PDF_RELATIVE_DIR", "pdfs"))
        / "befund"
        / f"{now.year:04d}"
        / f"{now.month:02d}"
    )
    relative_path = relative_dir / f"{version.id}.pdf"
    full_path = Path(settings.MEDIA_ROOT) / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(pdf_bytes)

    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    relative_str = str(relative_path).replace("\\", "/")
    return relative_str, checksum


def build_merged_preview_pdf_bytes(
    version: MedicalDocumentVersion,
    authoring_locale_override: str | None = None,
) -> tuple[bytes, str | None]:
    """
    Build Befund + external HiDrive PDFs for doctor preview (no DB status changes).

    Returns ``(pdf_bytes, warning_key_or_none)`` where warning is a short machine key
    for the client (e.g. merge failed, corrupt attachment).
    """
    befund_bytes = build_befund_pdf_bytes(
        version, authoring_locale_override=authoring_locale_override
    )
    doc = version.medical_document
    attachments = list(
        ExternalPdfAttachment.objects.filter(
            medical_document=doc,
            status=ExternalPdfStatus.MATCHED,
        ).order_by("original_filename", "hidrive_remote_path")
    )
    external_bytes_list: list[bytes] = []
    corrupt = False
    for att in attachments:
        try:
            external_bytes_list.append(download_external_pdf(att))
        except ExternalPdfCorruptError:
            corrupt = True
            continue
    warning: str | None = None
    if corrupt:
        warning = "external_pdf_corrupt"
    if external_bytes_list:
        pdf_bytes, merge_ok = safe_merge_pdfs(befund_bytes, external_bytes_list)
        if not merge_ok:
            warning = warning + "|merge_failed" if warning else "merge_failed"
        return pdf_bytes, warning
    return befund_bytes, warning
