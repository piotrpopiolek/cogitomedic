from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from weasyprint import HTML

from apps.intake.models import IntakeDocumentVersion


def _w3c_profile_datetime(dt: datetime | None) -> str | None:
    """Format for WeasyPrint <meta name=dcterms.*> (W3C datetime profile)."""
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.replace(microsecond=0).isoformat()


def _pdf_consent_acceptance_summary(consents: list[Any]) -> str | None:
    """Compact consent code → accepted_at for PDF metadata (ISO timestamps from snapshot)."""
    bits: list[str] = []
    for row in consents:
        if not isinstance(row, dict):
            continue
        code = row.get("code")
        if not isinstance(code, str) or not code.strip():
            continue
        at = row.get("accepted_at")
        bits.append(f"{code}={at}" if at else f"{code}=-")
    if not bits:
        return None
    return "; ".join(bits)


def _pdf_document_subject(ctx: dict[str, Any]) -> str:
    """Single-line summary for PDF /Subject (document properties)."""
    parts: list[str] = []
    if ctx.get("intake_form_id"):
        parts.append(f"Intake form ID: {ctx['intake_form_id']}")
    if ctx.get("queue_entry_id"):
        parts.append(f"Queue entry ID: {ctx['queue_entry_id']}")
    ga = ctx.get("generated_at")
    if isinstance(ga, datetime):
        parts.append(f"Generated at: {ga.strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append(
        f"Locale: {ctx.get('base_locale') or ''} + {ctx.get('form_locale') or ''}"
    )
    sa = ctx.get("submitted_at")
    if isinstance(sa, datetime):
        parts.append(f"Submitted at: {sa.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        parts.append("Submitted at: -")
    consent_summary = _pdf_consent_acceptance_summary(ctx.get("consents") or [])
    if consent_summary:
        parts.append(f"Consent accepted_at: {consent_summary}")
    sig_sha = (ctx.get("signature") or {}).get("sha256")
    if isinstance(sig_sha, str) and sig_sha.strip():
        parts.append(f"Signature SHA-256: {sig_sha.strip()}")
    return "; ".join(parts)


def _normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Provide safe defaults expected by the intake PDF template."""
    patient = snapshot.get("patient") or {}

    captured_at_str = snapshot.get("captured_at")
    generated_at = (
        parse_datetime(captured_at_str) if captured_at_str else timezone.now()
    )

    submitted_at_str = snapshot.get("submitted_at")
    submitted_at = parse_datetime(submitted_at_str) if submitted_at_str else None

    base = {
        "generated_at": generated_at,
        "base_locale": snapshot.get("base_locale") or "de-DE",
        "form_locale": snapshot.get("form_locale") or "de-DE",
        "submitted_at": submitted_at,
        "intake_form_id": snapshot.get("intake_form_id"),
        "queue_entry_id": snapshot.get("queue_entry_id"),
        "patient": {
            "first_name": patient.get("first_name") or "",
            "last_name": patient.get("last_name") or "",
            "date_of_birth": patient.get("date_of_birth") or "",
            "phone": patient.get("phone") or "",
            "email": patient.get("email") or "",
        },
        "consents": snapshot.get("consents") or [],
        "anamnesis": snapshot.get("anamnesis") or {"answers": []},
        "signature": snapshot.get("signature") or {},
    }
    base["pdf_consent_acceptance_meta"] = _pdf_consent_acceptance_summary(
        base["consents"]
    )
    raw_sig_sha = base["signature"].get("sha256")
    base["pdf_signature_sha256"] = (
        raw_sig_sha.strip()
        if isinstance(raw_sig_sha, str) and raw_sig_sha.strip()
        else None
    )
    base["pdf_document_subject"] = _pdf_document_subject(base)
    base["pdf_dcterms_created"] = _w3c_profile_datetime(generated_at)
    base["pdf_dcterms_modified"] = _w3c_profile_datetime(submitted_at)
    return base


def build_intake_pdf_bytes(version: IntakeDocumentVersion) -> bytes:
    context = _normalize_snapshot(version.snapshot_payload or {})
    html = render_to_string("pdf/intake_document.html", context)
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(
        custom_metadata=True,
    )


def generate_intake_pdf(version: IntakeDocumentVersion) -> tuple[str, str]:
    pdf_bytes = build_intake_pdf_bytes(version)
    now = version.created_at
    relative_dir = (
        Path(getattr(settings, "PDF_RELATIVE_DIR", "pdfs"))
        / "intake"
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
