from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.core.translation_service import get_translation_map
from apps.medical.models import MedicalDocumentVersion
from cogitomedica.doctor_i18n import get_doctor_ui, get_fitzpatrick_choices

# Map payload enum codes to doctor_ui keys so PDF shows translated text (DE/EN/PL)
RECOMMENDATION_CODE_TO_UI_KEY: dict[str, str] = {
    "FOLLOWUP_3_MONTHS": "rec_followup_3",
    "FOLLOWUP_6_MONTHS": "rec_followup_6",
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

# PDF section labels by locale (de-DE, en-GB, pl-PL)
PDF_LABELS: dict[str, dict[str, str]] = {
    "de-DE": {
        "befund": "Befund",
        "document_id": "Dokument-ID",
        "version": "Version",
        "generated_at": "Erstellt am",
        "locale": "Sprache",
        "patient": "Patient",
        "name": "Name",
        "date_of_birth": "Geburtsdatum",
        "phone": "Telefon",
        "email": "E-Mail",
        "global_assessment": "Gesamtbeurteilung",
        "fitzpatrick_type": "Hauttyp (Fitzpatrick)",
        "overall_image_assessment": "Gesamtbeurteilung Bildanalyse",
        "final_assessment": "Ärztliche Gesamteinschätzung",
        "diagnosis_code": "Diagnosecode",
        "procedure_code": "Prozedurcode",
        "examination_scope": "Untersuchungsumfang",
        "lesions": "Läsionen",
        "group": "Gruppe",
        "numbers": "Nummern",
        "clinical_assessment": "Klinisch-dermatoskopische Einschätzung",
        "malignancy_risk": "Malignitätsrisiko",
        "dermatoscopic_features": "Dermatoskopische Merkmale",
        "final_text": "Text",
        "recommendations": "Empfehlungen",
        "summary": "Zusammenfassung",
        "no_lesions": "Keine Läsionen angegeben.",
    },
    "en-GB": {
        "befund": "Befund",
        "document_id": "Document ID",
        "version": "Version",
        "generated_at": "Generated at",
        "locale": "Locale",
        "patient": "Patient",
        "name": "Name",
        "date_of_birth": "Date of birth",
        "phone": "Phone",
        "email": "Email",
        "global_assessment": "Global Assessment",
        "fitzpatrick_type": "Fitzpatrick type",
        "overall_image_assessment": "Overall image assessment",
        "final_assessment": "Final assessment",
        "diagnosis_code": "Diagnosis code",
        "procedure_code": "Procedure code",
        "examination_scope": "Examination Scope",
        "lesions": "Lesions",
        "group": "Group",
        "numbers": "Numbers",
        "clinical_assessment": "Clinical assessment",
        "malignancy_risk": "Malignancy risk",
        "dermatoscopic_features": "Dermatoscopic features",
        "final_text": "Final text",
        "recommendations": "Recommendations",
        "summary": "Summary",
        "no_lesions": "No lesions listed.",
    },
    "pl-PL": {
        "befund": "Befund",
        "document_id": "ID dokumentu",
        "version": "Wersja",
        "generated_at": "Wygenerowano",
        "locale": "Język",
        "patient": "Pacjent",
        "name": "Imię i nazwisko",
        "date_of_birth": "Data urodzenia",
        "phone": "Telefon",
        "email": "E-mail",
        "global_assessment": "Ocena ogólna",
        "fitzpatrick_type": "Typ skóry (Fitzpatrick)",
        "overall_image_assessment": "Ocena obrazu",
        "final_assessment": "Końcowa ocena lekarska",
        "diagnosis_code": "Kod rozpoznania",
        "procedure_code": "Kod procedury",
        "examination_scope": "Zakres badania",
        "lesions": "Zmiany",
        "group": "Grupa",
        "numbers": "Numery",
        "clinical_assessment": "Ocena kliniczno-dermatoskopowa",
        "malignancy_risk": "Ryzyko złośliwości",
        "dermatoscopic_features": "Cechy dermatoskopowe",
        "final_text": "Tekst",
        "recommendations": "Rekomendacje",
        "summary": "Podsumowanie",
        "no_lesions": "Brak wpisanych zmian.",
    },
}


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
    fitzpatrick_labels = {value: label for value, label in get_fitzpatrick_choices(lang)}

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

    summary_text = (payload.get("summary_edited_text") or "").strip() or (payload.get("summary_generated_text") or "").strip()
    exam_scope = [
        _translate_code(v, doctor_ui, EXAMINATION_SCOPE_CODE_TO_UI_KEY)
        for v in (payload.get("examination_scope") or [])
    ]
    recommendations = [_translate_recommendation(v, doctor_ui) for v in (payload.get("recommendations") or [])]

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
    context = _build_render_context(version, authoring_locale_override=authoring_locale_override)
    html = render_to_string("pdf/befund_document.html", context)
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()


def generate_befund_pdf(version: MedicalDocumentVersion) -> tuple[str, str]:
    """
    Generate and store Befund PDF for medical document version.

    Returns:
        (pdf_local_path_relative_to_media_root, sha256_checksum_hex)
    """
    pdf_bytes = build_befund_pdf_bytes(version)

    now = timezone.now()
    relative_dir = Path(getattr(settings, "PDF_RELATIVE_DIR", "pdfs")) / f"{now.year:04d}" / f"{now.month:02d}"
    relative_path = relative_dir / f"{version.id}.pdf"
    full_path = Path(settings.MEDIA_ROOT) / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(pdf_bytes)

    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    relative_str = str(relative_path).replace("\\", "/")
    return relative_str, checksum
