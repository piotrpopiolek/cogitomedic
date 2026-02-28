from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.intake.models import IntakeDocumentVersion


def _normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Provide safe defaults expected by the intake PDF template."""
    patient = snapshot.get("patient") or {}
    return {
        "generated_at": timezone.now(),
        "base_locale": snapshot.get("base_locale") or "de-DE",
        "form_locale": snapshot.get("form_locale") or "de-DE",
        "submitted_at": snapshot.get("submitted_at"),
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


def build_intake_pdf_bytes(version: IntakeDocumentVersion) -> bytes:
    context = _normalize_snapshot(version.snapshot_payload or {})
    html = render_to_string("pdf/intake_document.html", context)
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()


def generate_intake_pdf(version: IntakeDocumentVersion) -> tuple[str, str]:
    pdf_bytes = build_intake_pdf_bytes(version)
    now = timezone.now()
    relative_dir = Path(getattr(settings, "PDF_RELATIVE_DIR", "pdfs")) / "intake" / f"{now.year:04d}" / f"{now.month:02d}"
    relative_path = relative_dir / f"{version.id}.pdf"
    full_path = Path(settings.MEDIA_ROOT) / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(pdf_bytes)

    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    relative_str = str(relative_path).replace("\\", "/")
    return relative_str, checksum
