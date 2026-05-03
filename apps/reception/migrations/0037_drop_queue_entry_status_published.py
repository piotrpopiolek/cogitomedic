from __future__ import annotations

import uuid

from django.db import migrations, models


def _forward_backfill_published_status(apps, schema_editor) -> None:
    QueueEntry = apps.get_model("reception", "QueueEntry")
    AuditEvent = apps.get_model("operations", "AuditEvent")

    affected_count = QueueEntry.objects.filter(entry_status="PUBLISHED").update(
        entry_status="PATIENT_COMPLETED"
    )
    if affected_count > 0:
        AuditEvent.objects.create(
            id=uuid.uuid4(),
            event_type="QUEUE_STATUS_BACKFILL_PUBLISHED_TO_PATIENT_COMPLETED",
            metadata={"affected_count": affected_count},
        )


def _reverse_noop(apps, schema_editor) -> None:
    # Intentionally no-op: we do not reintroduce the removed dead status in downgrade.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0006_alter_auditevent_options_alter_auditevent_actor_user_and_more"),
        ("reception", "0036_patientimportbatch_skipped_already_present_count"),
    ]

    operations = [
        migrations.RunPython(
            code=_forward_backfill_published_status,
            reverse_code=_reverse_noop,
        ),
        migrations.AlterField(
            model_name="queueentry",
            name="entry_status",
            field=models.CharField(
                choices=[
                    ("WAITING", "Waiting"),
                    ("IN_PROGRESS", "In progress"),
                    ("PATIENT_COMPLETED", "Patient completed"),
                    ("DOCTOR_IN_PROGRESS", "Doctor in progress"),
                    ("PAPER_INTAKE_COMPLETED", "Paper intake completed"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="WAITING",
                max_length=30,
                verbose_name="Entry status",
            ),
        ),
    ]
