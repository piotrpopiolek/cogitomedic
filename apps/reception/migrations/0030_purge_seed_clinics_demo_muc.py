# Forward: remove DEMO/MUC seed clinics, queues, and known synthetic patients (DEMO-PAT-*, DTL-2024-*, DTL-2026-*).
# Reverse: no-op (cannot restore deleted data).
# Fresh databases still run historical seed migrations first; this migration clears the result.
#
# All purge logic lives in this file (not a separate app module).

from __future__ import annotations

from collections.abc import Sequence

from django.db import migrations
from django.db.models import Q

# Codes created only by reception seed migrations (see .cursor/plans/czyszczenie_seedów_produkcja.plan.md).
DEFAULT_SEED_SITE_CODES: tuple[str, ...] = ("DEMO", "MUC")


def purge_seed_clinic_data(apps, site_codes: Sequence[str] | None = None) -> None:
    """
    Remove clinic sites and related data for the given codes, then delete known seed patients.

    Order matches reception migration 0009: medical documents (RESTRICT) → daily queues →
    patients (no remaining queue entries) → consulting rooms → clinic sites.
    No-op for missing sites.
    """
    codes = tuple(site_codes) if site_codes is not None else DEFAULT_SEED_SITE_CODES
    if not codes:
        return

    ClinicSite = apps.get_model("reception", "ClinicSite")
    ConsultingRoom = apps.get_model("reception", "ConsultingRoom")
    DailyQueue = apps.get_model("reception", "DailyQueue")
    QueueEntry = apps.get_model("reception", "QueueEntry")
    Patient = apps.get_model("reception", "Patient")
    MedicalDocument = apps.get_model("medical", "MedicalDocument")
    MedicalDocumentVersion = apps.get_model("medical", "MedicalDocumentVersion")
    OutboxEvent = apps.get_model("outbox", "OutboxEvent")

    existing_sites: list = []
    for code in codes:
        try:
            existing_sites.append(ClinicSite.objects.get(code=code))
        except ClinicSite.DoesNotExist:
            continue

    for site in existing_sites:
        queue_entry_ids = list(
            QueueEntry.objects.filter(daily_queue__clinic_site=site).values_list("id", flat=True)
        )
        if queue_entry_ids:
            doc_ids = list(
                MedicalDocument.objects.filter(queue_entry_id__in=queue_entry_ids).values_list(
                    "id", flat=True
                )
            )
            if doc_ids:
                version_ids = list(
                    MedicalDocumentVersion.objects.filter(medical_document_id__in=doc_ids).values_list(
                        "id", flat=True
                    )
                )
                if version_ids:
                    OutboxEvent.objects.filter(medical_document_version_id__in=version_ids).delete()
                MedicalDocumentVersion.objects.filter(medical_document_id__in=doc_ids).delete()
                MedicalDocument.objects.filter(queue_entry_id__in=queue_entry_ids).delete()

        DailyQueue.objects.filter(clinic_site=site).delete()

    seed_patient_q = (
        Q(doctolib_patient_id__startswith="DEMO-PAT-")
        | Q(doctolib_patient_id__startswith="DTL-2024-")
        | Q(doctolib_patient_id__startswith="DTL-2026-")
    )
    Patient.objects.filter(seed_patient_q).delete()

    for site in existing_sites:
        try:
            site_refresh = ClinicSite.objects.get(pk=site.pk)
        except ClinicSite.DoesNotExist:
            continue
        room_ids = list(
            ConsultingRoom.objects.filter(clinic_site=site_refresh).values_list("id", flat=True)
        )
        if room_ids:
            ClinicSite.objects.filter(pdf_import_default_consulting_room_id__in=room_ids).update(
                pdf_import_default_consulting_room_id=None
            )
            ConsultingRoom.objects.filter(id__in=room_ids).delete()
        site_refresh.delete()


def forward_purge_seed_clinics(apps, schema_editor):
    purge_seed_clinic_data(apps)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0029_remove_patientcontacthistory"),
        ("medical", "0010_add_revoked_at"),
        ("outbox", "0003_alter_outboxevent_aggregate_type_and_more"),
    ]

    operations = [
        migrations.RunPython(forward_purge_seed_clinics, noop_reverse),
    ]
