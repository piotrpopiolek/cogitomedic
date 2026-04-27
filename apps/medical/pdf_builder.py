from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.core.translation_service import (
    get_doctor_ui,
    get_fitzpatrick_choices,
    get_translation_map,
)
from apps.medical.external_pdf_service import (
    ExternalPdfCorruptError,
    download_external_pdf,
)
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocumentVersion,
)
from apps.medical.pdf_merge import safe_merge_pdfs
from apps.operations.services import create_audit_event
from apps.users.models import StaffUser, StaffUserGender

logger = logging.getLogger(__name__)


class AllExternalPdfDownloadsFailed(RuntimeError):
    """Every ``MATCHED`` lab PDF download failed (infra). Outbox records audits after savepoint rollback."""

    __slots__ = ("patient_id", "medical_document_id", "failed_download_metadata")

    def __init__(
        self,
        message: str,
        *,
        patient_id: uuid.UUID,
        medical_document_id: uuid.UUID,
        failed_download_metadata: list[dict[str, Any]],
    ) -> None:
        super().__init__(message)
        self.patient_id = patient_id
        self.medical_document_id = medical_document_id
        self.failed_download_metadata = failed_download_metadata


def _w3c_profile_datetime(dt: datetime | None) -> str | None:
    """Format for WeasyPrint ``<meta name=dcterms.*>`` (W3C datetime profile)."""
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.replace(microsecond=0).isoformat()


def _format_header_day_dmy(dt: datetime | None) -> str:
    """Calendar day as d.m.Y (same pattern as intake PDF header under title)."""
    if dt is None:
        return "–"
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt).strftime("%d.%m.%Y")


def _format_queue_date_dmy(d: date | None) -> str:
    if d is None:
        return "–"
    return d.strftime("%d.%m.%Y")


def _effective_publication_datetime_for_header(
    version: MedicalDocumentVersion,
    *,
    generated_at: datetime,
) -> datetime:
    """
    Calendar day under the Ergebnisse title (d.m.Y in local time).

    Prefer ``version.published_at``. If it is missing (e.g. draft preview, or rare
    inconsistent rows), fall back to ``medical_document.last_published_at``, then
    ``version.updated_at`` for a published version, then ``generated_at`` so the
    line is not a dash when a meaningful date exists or for preview parity with
    intake (render-time day).
    """
    if version.published_at:
        return version.published_at
    doc = version.medical_document
    if doc is not None and doc.last_published_at:
        return doc.last_published_at
    if version.version_status == DocVersionStatus.PUBLISHED and version.updated_at:
        return version.updated_at
    return generated_at


def _pdf_befund_document_subject(
    *,
    document_id: str,
    version_no: int,
    authoring_locale: str,
    generated_at: datetime,
    published_at: datetime | None,
    examination_date: date | None,
) -> str:
    """Single-line summary for PDF /Subject (former grey meta box, now file metadata)."""
    gen = timezone.localtime(generated_at).strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"Medical document ID: {document_id}",
        f"Version: {version_no}",
        f"Generated at: {gen}",
        f"Locale: {authoring_locale}",
    ]
    if published_at is not None:
        pub = timezone.localtime(published_at).strftime("%Y-%m-%d %H:%M:%S")
        parts.append(f"Published at: {pub}")
    else:
        parts.append("Published at: -")
    if examination_date is not None:
        parts.append(f"Examination date: {examination_date.isoformat()}")
    else:
        parts.append("Examination date: -")
    return "; ".join(parts)


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
        "ergebnisse",
        "examination_date",
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
        "lesion_numbers_heading",
        "group",
        "numbers",
        "clinical_assessment",
        "malignancy_risk",
        "dermatoscopic_features",
        "final_text",
        "recommendations",
        "reporting_physician",
        "summary",
        "no_lesions",
        "signoff_greeting",
        "specialty_female",
        "specialty_male",
        "teledermatology_line",
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


def _pdf_global_assessment_lines(*display_parts: str | None) -> list[str]:
    """
    Gesamtbeurteilung: jedna linia PDF na każdą niepustą wartość.

    Pomijamy brak danych oraz placeholder ``-`` (ten sam co przy pustym kodzie
    w :func:`_translate_code` / :func:`_pretty_code` i brak ``diagnosis_code`` /
    ``procedure_code`` na wersji). W szablonie, gdy lista jest pusta, pokazujemy
    ``<div class="muted">-</div>`` — spójnie z pustym ``examination_scope``.
    """
    out: list[str] = []
    for part in display_parts:
        s = (part or "").strip()
        if s and s != "-":
            out.append(s)
    return out


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


def _staff_user_pdf_signoff_name(staff: Any | None) -> str | None:
    """German letter style after academic title: ``Vorname Nachname`` (not ``Nachname, Vorname``)."""
    if staff is None:
        return None
    first = (getattr(staff, "first_name", None) or "").strip()
    last = (getattr(staff, "last_name", None) or "").strip()
    if first and last:
        return f"{first} {last}"
    if first:
        return first
    if last:
        return last
    un = (getattr(staff, "username", None) or "").strip()
    return un or None


def _staff_user_display_name(user: Any) -> str | None:
    """Last name then first name, space-separated (list/metadata); username if names missing."""
    if user is None:
        return None
    last = (getattr(user, "last_name", None) or "").strip()
    first = (getattr(user, "first_name", None) or "").strip()
    if last and first:
        return f"{last} {first}"
    if last:
        return last
    if first:
        return first
    un = (getattr(user, "username", None) or "").strip()
    return un or None


def _reporting_physician_user(version: MedicalDocumentVersion) -> Any | None:
    """User whose name and PDF footer fields appear on the Befund PDF."""
    u = getattr(version, "published_by_user", None)
    if u is not None:
        return u
    doc = version.medical_document
    if doc is None:
        return None
    u = getattr(doc, "updated_by_user", None)
    if u is not None:
        return u
    return getattr(doc, "created_by_user", None)


def _reporting_physician_display(version: MedicalDocumentVersion) -> str | None:
    """
    Doctor who authored the report text: publisher for published versions, else
    last document editor, else document creator.
    """
    return _staff_user_display_name(_reporting_physician_user(version))


def _staff_user_for_pdf_footer(user: Any) -> Any | None:
    """Load title/gender from DB so PDF footer does not depend on join state on ``version``."""
    if user is None:
        return None
    pk = getattr(user, "pk", None)
    if pk is None:
        return user
    try:
        return StaffUser.objects.only(
            "first_name",
            "last_name",
            "username",
            "professional_title",
            "gender",
        ).get(pk=pk)
    except StaffUser.DoesNotExist:
        return user


def _pdf_signoff_footer_lines(
    *,
    staff: Any | None,
    name_display: str | None,
    labels: dict[str, str],
) -> list[str] | None:
    """Mit freundlichen Grüßen + ``Dr. med. Vorname Nachname`` + Facharzt/Fachärztin + Teledermatologie.

    Specialty line: explicit ``FEMALE`` / ``MALE`` from ``StaffUser.gender``. If gender is still
    ``UNSPECIFIED`` (legacy accounts), we use the **male** German line — Klaudia's spec avoids the
    slash form ``Facharzt/-in`` on patient-facing PDFs; female doctors should set gender to
    *Weiblich* in admin for ``Fachärztin``.
    """
    signoff_name = (_staff_user_pdf_signoff_name(staff) or "").strip()
    if not signoff_name:
        signoff_name = (name_display or "").strip()
    title = ""
    gender_val = StaffUserGender.UNSPECIFIED
    if staff is not None:
        title = (getattr(staff, "professional_title", None) or "").strip()
        gender_val = getattr(staff, "gender", None) or StaffUserGender.UNSPECIFIED
    if not title:
        title = "Dr. med."
    name_line = f"{title} {signoff_name}".strip() if signoff_name else title
    if gender_val == StaffUserGender.FEMALE:
        spec = (labels.get("specialty_female") or "").strip()
    else:
        # MALE or UNSPECIFIED: same German wording as Klaudia for Antczak / Rubens et al.
        spec = (labels.get("specialty_male") or "").strip()
    tele = (labels.get("teledermatology_line") or "").strip()
    greeting = (labels.get("signoff_greeting") or "").strip()
    lines: list[str] = []
    if greeting:
        lines.append(greeting)
    if name_line:
        lines.append(name_line)
    if spec:
        lines.append(spec)
    if tele:
        lines.append(tele)
    return lines or None


def _build_render_context(
    version: MedicalDocumentVersion,
    authoring_locale_override: str | None = None,
) -> dict[str, Any]:
    payload = version.medical_payload or {}
    medical_document = version.medical_document
    queue_entry = medical_document.queue_entry
    patient = queue_entry.patient
    examination_day: date | None = getattr(
        getattr(queue_entry, "daily_queue", None), "queue_date", None
    )

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

    overall_image_assessment_display = _translate_code(
        payload.get("overall_image_assessment"),
        doctor_ui,
        OVERALL_IMAGE_CODE_TO_UI_KEY,
    )
    final_assessment_display = _translate_code(
        payload.get("final_assessment"),
        doctor_ui,
        FINAL_ASSESSMENT_CODE_TO_UI_KEY,
    )
    _diag = (version.diagnosis_code or "").strip()
    diagnosis_code_display = _diag if _diag else "-"
    _proc = (version.procedure_code or "").strip()
    procedure_code_display = _proc if _proc else "-"
    global_assessment_lines = _pdf_global_assessment_lines(
        fitzpatrick_type_label,
        overall_image_assessment_display,
        final_assessment_display,
        diagnosis_code_display,
        procedure_code_display,
    )

    generated_at = timezone.now()
    strict_published_at = version.published_at
    publication_dt = _effective_publication_datetime_for_header(
        version, generated_at=generated_at
    )
    publication_date_display = _format_header_day_dmy(publication_dt)
    examination_date_display = _format_queue_date_dmy(examination_day)
    pdf_document_subject = _pdf_befund_document_subject(
        document_id=str(version.medical_document_id),
        version_no=version.version_no,
        authoring_locale=authoring_locale,
        generated_at=generated_at,
        published_at=strict_published_at,
        examination_date=examination_day,
    )
    created_for_meta = strict_published_at or version.created_at
    reporting_physician_display = _reporting_physician_display(version)
    reporting_staff = _staff_user_for_pdf_footer(_reporting_physician_user(version))
    pdf_signoff_footer_lines = _pdf_signoff_footer_lines(
        staff=reporting_staff,
        name_display=reporting_physician_display,
        labels=labels,
    )
    return {
        "document_id": str(version.medical_document_id),
        "version_no": version.version_no,
        "generated_at": generated_at,
        "authoring_locale": authoring_locale,
        "publication_date_display": publication_date_display,
        "examination_date_display": examination_date_display,
        "reporting_physician_display": reporting_physician_display,
        "pdf_signoff_footer_lines": pdf_signoff_footer_lines,
        "pdf_document_subject": pdf_document_subject,
        "pdf_dcterms_created": _w3c_profile_datetime(created_for_meta),
        "pdf_dcterms_modified": _w3c_profile_datetime(
            strict_published_at or generated_at
        ),
        "pdf_meta_published_at": _w3c_profile_datetime(strict_published_at),
        "pdf_meta_generated_at": _w3c_profile_datetime(generated_at),
        "labels": labels,
        "global_assessment_lines": global_assessment_lines,
        "patient": {
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "date_of_birth": patient.date_of_birth,
            "phone": patient.phone,
            "email": patient.email,
        },
        "befund": {
            "fitzpatrick_type": fitzpatrick_type_label,
            "overall_image_assessment": overall_image_assessment_display,
            "final_assessment": final_assessment_display,
            "diagnosis_code": diagnosis_code_display,
            "procedure_code": procedure_code_display,
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
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(
        custom_metadata=True,
    )


def generate_befund_pdf(version: MedicalDocumentVersion) -> tuple[str, str]:
    """
    Generate and store Befund PDF for medical document version.

    Selects external PDF attachments to merge:

    - ``MATCHED`` attachments (newly accepted in this publish/republish cycle,
      still residing in HiDrive ``/incoming``) — they will be flipped to
      ``ACCEPTED`` after a successful merge so the outbox HiDrive uploader can
      move them to ``/processed``.
    - ``ACCEPTED`` attachments (historical, already moved to ``/processed`` by
      the previous publish) — needed when the user republishes a revision so
      the new PDF still contains the lab results that the patient already had
      in v1. Their status stays ``ACCEPTED`` (they are not re-moved).

    When there are ``MATCHED`` external (lab) PDF attachments and every download
    fails with an infrastructure error (not :class:`ExternalPdfCorruptError`),
    raises :class:`AllExternalPdfDownloadsFailed` — Befund must not be archived
    without lab bytes; outbox should retry once HiDrive serves the file.
    Attachments stay ``MATCHED``. ``EXTERNAL_PDF_DOWNLOAD_FAILED`` audits are
    written by the outbox handler after rolling back the per-event savepoint.

    Returns:
        (pdf_local_path_relative_to_media_root, sha256_checksum_hex)
    """
    befund_bytes = build_befund_pdf_bytes(version)
    doc = version.medical_document
    patient = doc.queue_entry.patient

    attachments = list(
        ExternalPdfAttachment.objects.filter(
            medical_document=doc,
            status__in=(ExternalPdfStatus.MATCHED, ExternalPdfStatus.ACCEPTED),
        ).order_by("original_filename", "hidrive_remote_path", "id")
    )
    external_bytes_list: list[bytes] = []
    attachments_used: list[ExternalPdfAttachment] = []
    infra_errors: list[tuple[ExternalPdfAttachment, Exception]] = []
    for att in attachments:
        try:
            ext_bytes = download_external_pdf(att)
        except ExternalPdfCorruptError:
            # Corrupt: only flip newly MATCHED to MERGE_FAILED. Historical
            # ACCEPTED attachments keep their state (audit log captures it).
            if att.status == ExternalPdfStatus.MATCHED:
                att.status = ExternalPdfStatus.MERGE_FAILED
                att.save(update_fields=["status"])
            create_audit_event(
                event_type="EXTERNAL_PDF_CORRUPT",
                patient_id=patient.id,
                medical_document_id=doc.id,
                metadata={
                    "hidrive_remote_path": att.hidrive_remote_path,
                    "external_pdf_attachment_id": str(att.id),
                    "previous_status": att.status,
                },
            )
            continue
        except Exception as exc:
            logger.warning(
                "download_external_pdf failed: attachment_id=%s path=%s",
                att.id,
                att.hidrive_remote_path,
                exc_info=True,
            )
            infra_errors.append((att, exc))
            continue
        external_bytes_list.append(ext_bytes)
        attachments_used.append(att)

    if attachments and not external_bytes_list and infra_errors:
        meta_list = [
            {
                "hidrive_remote_path": att.hidrive_remote_path,
                "external_pdf_attachment_id": str(att.id),
                "error_type": type(download_error).__name__,
                "attachment_status": att.status,
            }
            for att, download_error in infra_errors
        ]
        raise AllExternalPdfDownloadsFailed(
            f"All {len(infra_errors)} external PDF download(s) failed "
            f"(HiDrive unavailable?); refusing to publish Befund without "
            f"lab results. Outbox will retry.",
            patient_id=patient.id,
            medical_document_id=doc.id,
            failed_download_metadata=meta_list,
        )

    for att, download_error in infra_errors:
        # Only newly MATCHED attachments should flip to MERGE_FAILED on
        # transient download failure. Historical ACCEPTED stay as-is so a
        # transient HiDrive blip during republish does not erase v1 history.
        if att.status == ExternalPdfStatus.MATCHED:
            att.status = ExternalPdfStatus.MERGE_FAILED
            att.save(update_fields=["status"])
        create_audit_event(
            event_type="EXTERNAL_PDF_DOWNLOAD_FAILED",
            patient_id=patient.id,
            medical_document_id=doc.id,
            metadata={
                "hidrive_remote_path": att.hidrive_remote_path,
                "external_pdf_attachment_id": str(att.id),
                "error_type": type(download_error).__name__,
                "attachment_status": att.status,
            },
        )

    if external_bytes_list:
        pdf_bytes, merge_ok = safe_merge_pdfs(befund_bytes, external_bytes_list)
        if merge_ok:
            # Promote freshly merged MATCHED → ACCEPTED. ACCEPTED stay ACCEPTED
            # (idempotent on republish); HiDrive uploader moves only the new
            # ones from /incoming to /processed.
            promote = [
                a for a in attachments_used if a.status == ExternalPdfStatus.MATCHED
            ]
            for att in promote:
                att.status = ExternalPdfStatus.ACCEPTED
            if promote:
                ExternalPdfAttachment.objects.bulk_update(promote, ["status"])
        else:
            demote = [
                a for a in attachments_used if a.status == ExternalPdfStatus.MATCHED
            ]
            for att in demote:
                att.status = ExternalPdfStatus.MERGE_FAILED
            if demote:
                ExternalPdfAttachment.objects.bulk_update(demote, ["status"])
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

    Includes both ``MATCHED`` (new lab files awaiting publish) and ``ACCEPTED``
    (already merged & moved to ``/processed`` by an earlier publish)
    attachments, so the preview rendered for a published or in-revision
    document mirrors what the patient saw / will see, not just the Befund
    page. Statuses are never mutated here – this is a pure read.

    Returns ``(pdf_bytes, warning_key_or_none)`` where warning is a pipe-separated
    hint for the client (e.g. ``external_pdf_download_failed``, merge failed, corrupt attachment).
    """
    befund_bytes = build_befund_pdf_bytes(
        version, authoring_locale_override=authoring_locale_override
    )
    doc = version.medical_document
    attachments = list(
        ExternalPdfAttachment.objects.filter(
            medical_document=doc,
            status__in=(ExternalPdfStatus.MATCHED, ExternalPdfStatus.ACCEPTED),
        ).order_by("original_filename", "hidrive_remote_path", "id")
    )
    external_bytes_list: list[bytes] = []
    corrupt = False
    download_failed = False
    for att in attachments:
        try:
            external_bytes_list.append(download_external_pdf(att))
        except ExternalPdfCorruptError:
            corrupt = True
            continue
        except Exception:
            download_failed = True
            logger.warning(
                "download_external_pdf failed during preview (Befund-only): "
                "attachment_id=%s path=%s",
                att.id,
                att.hidrive_remote_path,
                exc_info=True,
            )
            continue
    warning: str | None = None
    if corrupt:
        warning = "external_pdf_corrupt"
    if download_failed:
        warning = (
            f"{warning}|external_pdf_download_failed"
            if warning
            else "external_pdf_download_failed"
        )
    if external_bytes_list:
        pdf_bytes, merge_ok = safe_merge_pdfs(befund_bytes, external_bytes_list)
        if not merge_ok:
            warning = warning + "|merge_failed" if warning else "merge_failed"
        return pdf_bytes, warning
    return befund_bytes, warning
