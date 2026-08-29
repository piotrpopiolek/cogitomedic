"""Central write gate for doctor Befund mutations (token + draft_revision)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from django.db import transaction
from django.utils import timezone

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError, IdempotencyConflictError
from apps.medical.edit_session import (
    EditSessionResponseError,
    _assert_doctor_actor,
    _audit_edit_session_event,
    _effective_lock_holder_id,
    doctor_befund_edit_lock_applies,
    is_doctor_befund_source_type,
)
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocument,
    MedicalDocumentVersion,
)
from apps.users.display import staff_user_display_name
from apps.users.models import StaffUser

MutationKind = Literal["save_draft", "publish", "discard", "mark_preview"]


@dataclass(frozen=True, slots=True)
class DraftMutationResult:
    version: MedicalDocumentVersion
    document: MedicalDocument
    draft_revision: int
    replayed: bool


def _draft_content_fingerprint(
    *,
    medical_payload_schema_version: int,
    medical_payload: dict[str, Any] | None,
    diagnosis_code: str | None,
    procedure_code: str | None,
) -> tuple[int, str, str | None, str | None]:
    """Canonical snapshot of draft fields that affect publish preview freshness."""
    payload = medical_payload if isinstance(medical_payload, dict) else {}
    return (
        int(medical_payload_schema_version),
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        diagnosis_code or None,
        procedure_code or None,
    )


def _existing_draft_content_matches(
    existing: MedicalDocumentVersion | None,
    *,
    medical_payload_schema_version: int,
    medical_payload: dict[str, Any],
    diagnosis_code: str | None,
    procedure_code: str | None,
) -> bool:
    """True when an in-place DRAFT update would not change preview-relevant content."""
    if existing is None or existing.version_status != DocVersionStatus.DRAFT:
        return False
    return _draft_content_fingerprint(
        medical_payload_schema_version=existing.medical_payload_schema_version,
        medical_payload=(
            existing.medical_payload
            if isinstance(existing.medical_payload, dict)
            else {}
        ),
        diagnosis_code=existing.diagnosis_code,
        procedure_code=existing.procedure_code,
    ) == _draft_content_fingerprint(
        medical_payload_schema_version=medical_payload_schema_version,
        medical_payload=medical_payload,
        diagnosis_code=diagnosis_code,
        procedure_code=procedure_code,
    )


def _raise_locked_by_other(holder_id: uuid.UUID) -> None:
    holder = StaffUser.objects.filter(id=holder_id).first()
    raise EditSessionResponseError(
        error_key="document_locked_by_other",
        http_status=423,
        payload={"locked_by_username": staff_user_display_name(holder)},
    )


def assert_active_doctor_edit_session(
    doc: MedicalDocument,
    *,
    user: Any,
    edit_session_token: uuid.UUID,
    now: datetime | None = None,
    require_revision: int | None = None,
) -> StaffUser:
    """
    Validate holder + live write token (+ optional expected_draft_revision).

    Does not auto-acquire or silently refresh an expired lock.
    """
    doctor = _assert_doctor_actor(user)
    if not is_doctor_befund_source_type(doc) or not doctor_befund_edit_lock_applies(
        doc
    ):
        raise DomainError(
            domain_message("other.domain.edit_session_document_read_only"),
            api_message_key="other.domain.edit_session_document_read_only",
        )

    at = now or timezone.now()
    holder_id = _effective_lock_holder_id(doc, now=at)
    if holder_id is None:
        raise EditSessionResponseError(
            error_key="edit_session_expired",
            http_status=423,
            payload={"draft_revision": doc.draft_revision},
        )
    if holder_id != doctor.id:
        _raise_locked_by_other(holder_id)
    if doc.edit_session_token != edit_session_token:
        raise EditSessionResponseError(
            error_key="edit_session_stale",
            http_status=423,
            payload={
                "draft_revision": doc.draft_revision,
                "locked_by_username": staff_user_display_name(doctor),
            },
        )
    if require_revision is not None and require_revision != doc.draft_revision:
        raise EditSessionResponseError(
            error_key="draft_revision_conflict",
            http_status=409,
            payload={"draft_revision": doc.draft_revision},
        )
    return doctor


def _refresh_lock_on_mutation(
    doc: MedicalDocument, *, now: datetime, doctor: StaffUser
) -> None:
    doc.locked_at = now
    doc.save(update_fields=["locked_at", "updated_at"])
    _audit_edit_session_event(
        event_type="DOCUMENT_LOCK_REFRESHED_ON_SAVE",
        doc=doc,
        actor_user_id=doctor.id,
        metadata={
            "draft_revision": doc.draft_revision,
            "edit_session_revision": doc.edit_session_revision,
        },
    )


@transaction.atomic
def mutate_doctor_save_draft(
    *,
    medical_document_id: uuid.UUID,
    user: Any,
    edit_session_token: uuid.UUID,
    expected_draft_revision: int,
    draft_save_request_id: uuid.UUID,
    medical_payload_schema_version: int,
    medical_payload: dict,
    diagnosis_code: str | None = None,
    procedure_code: str | None = None,
    intent: str = "edit",
) -> DraftMutationResult:
    """Save draft under the write gate.

    Increments ``draft_revision`` only when DRAFT content changes. Identical
    payload/schema/codes leave the revision (and preview marker) intact so a
    pre-publish save after an unchanged preview does not force re-preview.
    """
    from apps.medical.services import (
        check_doctor_document_access,
        save_draft_document_version,
    )

    now = timezone.now()
    doc = (
        MedicalDocument.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=medical_document_id)
    )
    doctor = _assert_doctor_actor(user)
    check_doctor_document_access(doc, doctor)

    if (
        doc.last_draft_request_id is not None
        and doc.last_draft_request_id == draft_save_request_id
    ):
        if doc.last_draft_request_base_revision == expected_draft_revision:
            assert_active_doctor_edit_session(
                doc,
                user=doctor,
                edit_session_token=edit_session_token,
                now=now,
                require_revision=None,
            )
            version = (
                MedicalDocumentVersion.objects.filter(
                    medical_document_id=doc.id,
                    version_status=DocVersionStatus.DRAFT,
                )
                .order_by("-version_no")
                .first()
            )
            if version is None:
                raise DomainError(
                    domain_message("other.api.no_draft_before_publish"),
                    api_message_key="other.api.no_draft_before_publish",
                )
            result_rev = int(
                doc.last_draft_request_result_revision or doc.draft_revision
            )
            return DraftMutationResult(
                version=version,
                document=doc,
                draft_revision=result_rev,
                replayed=True,
            )
        raise EditSessionResponseError(
            error_key="draft_request_id_reused",
            http_status=409,
            payload={"draft_revision": doc.draft_revision},
        )

    doctor = assert_active_doctor_edit_session(
        doc,
        user=doctor,
        edit_session_token=edit_session_token,
        now=now,
        require_revision=expected_draft_revision,
    )

    existing_draft = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=doc.id,
            version_status=DocVersionStatus.DRAFT,
        )
        .order_by("-version_no")
        .first()
    )
    content_unchanged = _existing_draft_content_matches(
        existing_draft,
        medical_payload_schema_version=medical_payload_schema_version,
        medical_payload=medical_payload,
        diagnosis_code=diagnosis_code,
        procedure_code=procedure_code,
    )

    base_revision = doc.draft_revision
    version = save_draft_document_version(
        medical_document_id=medical_document_id,
        updated_by_user_id=doctor.id,
        medical_payload_schema_version=medical_payload_schema_version,
        medical_payload=medical_payload,
        diagnosis_code=diagnosis_code,
        procedure_code=procedure_code,
        intent=intent,
    )
    doc.refresh_from_db()
    result_revision = base_revision if content_unchanged else base_revision + 1
    doc.draft_revision = result_revision
    doc.last_draft_request_id = draft_save_request_id
    doc.last_draft_request_base_revision = base_revision
    doc.last_draft_request_result_revision = result_revision
    doc.save(
        update_fields=[
            "draft_revision",
            "last_draft_request_id",
            "last_draft_request_base_revision",
            "last_draft_request_result_revision",
            "updated_at",
        ]
    )
    _refresh_lock_on_mutation(doc, now=now, doctor=doctor)
    doc.refresh_from_db()
    return DraftMutationResult(
        version=version,
        document=doc,
        draft_revision=doc.draft_revision,
        replayed=False,
    )


@transaction.atomic
def mutate_doctor_publish(
    *,
    medical_document_id: uuid.UUID,
    user: Any,
    edit_session_token: uuid.UUID,
    expected_draft_revision: int,
    publish_request_id: uuid.UUID,
    publish_locale: str,
    resend_sms: bool = False,
) -> MedicalDocumentVersion:
    """Publish under the write gate; replay of ``publish_request_id`` skips token."""
    from apps.medical.services import (
        check_doctor_document_access,
        publish_document_version,
    )

    now = timezone.now()
    doctor = _assert_doctor_actor(user)
    doc = (
        MedicalDocument.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=medical_document_id)
    )
    check_doctor_document_access(doc, doctor)

    same_request = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            publish_request_id=publish_request_id,
        )
        .first()
    )
    if same_request is not None:
        if (
            same_request.publish_locale
            and same_request.publish_locale != publish_locale
        ):
            raise IdempotencyConflictError(
                domain_message("other.api.publish_request_id_locale_conflict"),
                api_message_key="other.api.publish_request_id_locale_conflict",
            )
        return same_request

    assert_active_doctor_edit_session(
        doc,
        user=doctor,
        edit_session_token=edit_session_token,
        now=now,
        require_revision=expected_draft_revision,
    )
    if doc.last_previewed_draft_revision != doc.draft_revision:
        raise EditSessionResponseError(
            error_key="publish_preview_revision_stale",
            http_status=409,
            payload={
                "draft_revision": doc.draft_revision,
                "last_previewed_draft_revision": doc.last_previewed_draft_revision,
            },
        )

    version = publish_document_version(
        medical_document_id=medical_document_id,
        publish_request_id=publish_request_id,
        published_by_user_id=doctor.id,
        publish_locale=publish_locale,
        resend_sms=resend_sms,
        now=now,
    )
    return version


@transaction.atomic
def mutate_doctor_discard_revision(
    *,
    medical_document_id: uuid.UUID,
    user: Any,
    edit_session_token: uuid.UUID,
    expected_draft_revision: int,
) -> MedicalDocument:
    """Discard pending revision under the write gate; clears lock/token."""
    from apps.medical.services import (
        check_doctor_document_access,
        discard_pending_revision,
    )

    now = timezone.now()
    doctor = _assert_doctor_actor(user)
    doc = (
        MedicalDocument.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=medical_document_id)
    )
    check_doctor_document_access(doc, doctor)
    assert_active_doctor_edit_session(
        doc,
        user=doctor,
        edit_session_token=edit_session_token,
        now=now,
        require_revision=expected_draft_revision,
    )
    return discard_pending_revision(
        medical_document_id=medical_document_id,
        actor_user_id=doctor.id,
    )


@transaction.atomic
def mark_doctor_draft_previewed(
    *,
    medical_document_id: uuid.UUID,
    user: Any,
    edit_session_token: uuid.UUID,
    expected_draft_revision: int,
) -> MedicalDocument:
    """
    Record that the current ``draft_revision`` was previewed.

    Call after PDF bytes are generated, with a fresh ``select_for_update`` so a
    concurrent save cannot mark a stale preview as current.
    """
    from apps.medical.services import check_doctor_document_access

    now = timezone.now()
    doctor = _assert_doctor_actor(user)
    doc = (
        MedicalDocument.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=medical_document_id)
    )
    check_doctor_document_access(doc, doctor)
    assert_active_doctor_edit_session(
        doc,
        user=doctor,
        edit_session_token=edit_session_token,
        now=now,
        require_revision=expected_draft_revision,
    )
    doc.last_previewed_draft_revision = doc.draft_revision
    doc.locked_at = now
    doc.save(update_fields=["last_previewed_draft_revision", "locked_at", "updated_at"])
    return doc


def assert_no_revision_in_progress_for_revoke(doc: MedicalDocument) -> None:
    """Revoke is outside the write gate but blocked while a revision/lock is open."""
    if not is_doctor_befund_source_type(doc):
        return
    if doc.has_pending_revision:
        raise EditSessionResponseError(
            error_key="revision_in_progress",
            http_status=409,
            payload={"draft_revision": doc.draft_revision},
        )
    if doctor_befund_edit_lock_applies(doc):
        holder_id = _effective_lock_holder_id(doc, now=timezone.now())
        if holder_id is not None:
            raise EditSessionResponseError(
                error_key="revision_in_progress",
                http_status=409,
                payload={"draft_revision": doc.draft_revision},
            )
