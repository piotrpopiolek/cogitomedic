"""
Load translation keys/values from JSON files under apps/core/translation_data/.

Used by migrations and by ``load_default_translations`` management command.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings

REQUIRED_LANGS = ("de", "en", "pl")
LOCALE_BY_LANG = {"de": "de-DE", "en": "en-GB", "pl": "pl-PL"}


def _storage_language_code(TranslationValue: Any, lang: str) -> str:
    """
    Return language code matching current model schema:
    - historical migrations use short codes (de/en/pl)
    - current schema uses locale codes from StaffUserPreferredLocale.
    """
    field = TranslationValue._meta.get_field("language_code")
    choices = [c[0] for c in (getattr(field, "choices", None) or [])]
    if choices and "de-DE" in choices:
        return LOCALE_BY_LANG[lang]
    return lang


# Keys that need non-default TranslationKey fields (match historical migrations).
_KEY_ALLOWED_PLACEHOLDERS: dict[str, list[str]] = {
    "other.domain.invalid_shift_code": ["value"],
    "other.domain.invalid_queue_source": ["value"],
    "other.domain.invalid_queue_status": ["value"],
    "other.domain.invalid_queue_entry_status": ["value"],
    "other.domain.unsupported_form_locale": ["locale"],
    "other.domain.invalid_staff_role": ["role"],
    "other.domain.staff_role_group_missing": ["role", "group_name"],
    "other.domain.consent_definition_not_active": ["consent_id", "date"],
    "other.domain.signature_payload_too_large": ["max_bytes"],
    "other.api.request_body_too_large": ["max_bytes"],
    "other.domain.external_upload_file_too_large": ["max_bytes"],
    "other.sms.patient_results": ["url"],
    "other.auth.already_authenticated_other_account": ["username"],
    "administration.login_authenticated_but_unauthorized": ["username"],
    "administration.error_lesion_favorites_preset_not_object": ["preset_no"],
    "administration.error_lesion_favorites_preset_invalid": ["preset_no", "details"],
    "administration.error_lesion_favorites_preset_bad_feature": [
        "preset_no",
        "code",
        "allowed",
    ],
    "administration.error_lesion_favorites_preset_bad_clinical": [
        "preset_no",
        "value",
        "allowed",
    ],
    "administration.error_lesion_favorites_preset_bad_malignancy": [
        "preset_no",
        "value",
        "allowed",
    ],
    "administration.admin_paper_intake_revoke_result": ["ok", "failed"],
    "administration.admin_send_result_sms_result": ["ok", "failed"],
    "administration.paper_intake_admin_earliest_hint": ["hours"],
    "administration.hidrive_hours_waiting": ["hours"],
    "administration.intake_document_detail_title": ["patient_name"],
    "administration.accounting_report_mode_invalid": ["allowed"],
    "administration.str_medical_document": ["patient", "status"],
    "administration.str_medical_document_version": ["version_no", "document", "status"],
    "administration.str_intake_form": ["patient", "status"],
    "administration.str_intake_consent": ["consent", "yes_no"],
    "administration.str_intake_document_version": ["version_no", "form", "status"],
    "administration.str_queue_entry": ["patient", "position", "status"],
    "administration.str_patient_form_session": ["entry", "date"],
    "administration.str_queue_import_batch": ["filename", "date", "status"],
    "administration.str_queue_import_error": ["row", "code"],
    "administration.str_queue_import_error_detail": ["row", "code", "message"],
    "administration.str_outbox_event": ["event_type", "version", "status"],
    "other.domain.paper_intake_authorization_too_early": ["hours"],
    "other.domain.paper_intake_earliest_after_appointment": ["hours"],
}

_KEY_DESCRIPTIONS: dict[str, str] = {
    "other.sms.patient_results": "SMS text after Befund publish (portal wyniki); placeholder: {url}",
    "waiting_room.form.consent_result_portal_agree": (
        "Consent checkbox label: result in portal (DS_EINWILLIGUNG_ERGEBNISSES)"
    ),
    "waiting_room.staff.tablet_unassigned": (
        "Message when tablet device has no clinic_site assigned"
    ),
}


def translation_data_directory() -> Path:
    return Path(__file__).resolve().parent / "translation_data"


def category_for_key(full_key: str) -> str:
    if full_key.startswith("administration."):
        return "administration"
    if full_key.startswith("waiting_room."):
        return "waiting_room"
    if full_key.startswith("other."):
        return "other"
    if full_key.startswith("doctor."):
        return "doctor"
    raise ValueError(f"Cannot infer TranslationCategory for key: {full_key!r}")


def description_for_key(full_key: str) -> str:
    if full_key in _KEY_DESCRIPTIONS:
        return _KEY_DESCRIPTIONS[full_key]
    if full_key.startswith("other.domain."):
        return "Domain/service validation message (REST)"
    if full_key.startswith("other.api."):
        return "REST API error message"
    if full_key.startswith("other.ergebnisse."):
        short = full_key.removeprefix("other.ergebnisse.")
        return f"Ergebnisse portal: {short}"
    if ".fitzpatrick." in full_key:
        return "Fitzpatrick label"
    if full_key.startswith("doctor.pdf_label."):
        return "Doctor PDF label"
    if full_key.startswith("doctor."):
        return "Doctor UI translation"
    if full_key.startswith("waiting_room.form."):
        return "Waiting room tablet form UI"
    if full_key.startswith("waiting_room.staff."):
        return "Waiting room staff UI"
    if full_key.startswith("administration.choice_"):
        return "Enum choice label (admin)"
    if full_key.startswith("administration.error_"):
        return "Admin validation or form error message"
    if full_key.startswith("administration.field_"):
        return "Model field label"
    if full_key.startswith("administration.login_") or full_key.startswith(
        "administration.logout_"
    ):
        return "Login/logout UI labels"
    if full_key == "administration.return_to_site":
        return "Login/logout UI labels"
    if full_key.startswith("administration."):
        return "Admin panel UI"
    return ""


def _ensure_key(
    TranslationKey: Any,
    *,
    full_key: str,
    category: str,
    description: str,
    allowed_placeholders: list[str],
) -> Any:
    key, _ = TranslationKey.objects.get_or_create(
        key=full_key,
        defaults={
            "category": category,
            "description": description,
            "is_html_allowed": False,
            "allowed_placeholders": allowed_placeholders,
            "status": "ACTIVE",
        },
    )
    return key


def _seed_entry(
    TranslationKey: Any,
    TranslationValue: Any,
    *,
    full_key: str,
    values: dict[str, str],
) -> int:
    missing = [x for x in REQUIRED_LANGS if x not in values]
    if missing:
        raise ValueError(f"Key {full_key!r} missing languages: {missing}")
    category = category_for_key(full_key)
    desc = description_for_key(full_key)
    placeholders = list(_KEY_ALLOWED_PLACEHOLDERS.get(full_key, []))
    key = _ensure_key(
        TranslationKey,
        full_key=full_key,
        category=category,
        description=desc,
        allowed_placeholders=placeholders,
    )
    created = 0
    for lang in REQUIRED_LANGS:
        storage_lang = _storage_language_code(TranslationValue, lang)
        _, was_created = TranslationValue.objects.get_or_create(
            translation_key=key,
            language_code=storage_lang,
            defaults={"value": values[lang]},
        )
        if was_created:
            created += 1
    return created


def load_json_file(path: Path) -> dict[str, dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    out: dict[str, dict[str, str]] = {}
    for full_key, raw in data.items():
        if not isinstance(full_key, str) or not isinstance(raw, dict):
            continue
        out[full_key] = {k: str(v) for k, v in raw.items() if k in REQUIRED_LANGS}
    return out


def seed_from_translation_data_directory(
    *,
    directory: Path | None = None,
    apps: Any = None,
    only_json_filenames: tuple[str, ...] | None = None,
) -> int:
    """
    Load JSON translation files from *directory* (default: packaged translation_data/).

    If *only_json_filenames* is set, only those basenames are loaded (must exist).
    Otherwise every ``*.json`` in the directory is loaded.

    If *apps* is passed (migration RunPython), use historical models.

    Returns number of **new** TranslationValue rows created (not updated).
    """
    root = directory or translation_data_directory()
    if apps:
        TranslationKey = apps.get_model("core", "TranslationKey")
        TranslationValue = apps.get_model("core", "TranslationValue")
    else:
        from apps.core.models import TranslationKey, TranslationValue

    if only_json_filenames:
        paths = [root / name for name in only_json_filenames]
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(f"Translation seed file missing: {path}")
    else:
        paths = sorted(root.glob("*.json"))

    total_created = 0
    for path in paths:
        payload = load_json_file(path)
        for full_key, langs in payload.items():
            total_created += _seed_entry(
                TranslationKey,
                TranslationValue,
                full_key=full_key,
                values=langs,
            )
    return total_created


def seed_for_management_command() -> int:
    """Resolve data dir from BASE_DIR (same as migration)."""
    base = Path(settings.BASE_DIR)
    d = base / "apps" / "core" / "translation_data"
    return seed_from_translation_data_directory(directory=d, apps=None)
