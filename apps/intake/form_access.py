"""Intake form access guards shared by intake and telederm services."""

from __future__ import annotations

from typing import Iterable
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist

from apps.intake.models import IntakeStatus, PatientIntakeForm

_INTAKE_STATUSES_ALLOWING_PATIENT_EDITS = frozenset(
    {IntakeStatus.IN_PROGRESS, IntakeStatus.REOPENED}
)


def intake_allows_patient_edits(form_status: str) -> bool:
    """True when the patient/tablet may still mutate the intake form."""
    return form_status in _INTAKE_STATUSES_ALLOWING_PATIENT_EDITS


def assert_intake_form_clinic_scope(
    *,
    intake_form: PatientIntakeForm,
    allowed_clinic_site_ids: Iterable[UUID] | None,
) -> None:
    """Raise ``ObjectDoesNotExist`` when the form's clinic is outside the allowed set."""
    if allowed_clinic_site_ids is None:
        return
    allowed = set(allowed_clinic_site_ids)
    clinic_site_id = intake_form.queue_entry.daily_queue.clinic_site_id
    if clinic_site_id not in allowed:
        raise ObjectDoesNotExist("Intake form is outside clinic scope.")
