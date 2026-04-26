# Intake reopen (REOPENED) + reception note fields; tighten submitted/signature constraint.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("intake", "0024_alter_anamnesisoptiondefinition_options_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="patientintakeform",
            name="intake_submitted_requires_signature",
        ),
        migrations.AddField(
            model_name="patientintakeform",
            name="reception_note",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Reception note",
            ),
        ),
        migrations.AddField(
            model_name="patientintakeform",
            name="reception_note_updated_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Reception note updated at",
            ),
        ),
        migrations.AddField(
            model_name="patientintakeform",
            name="reception_note_updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="intake_reception_notes_updated",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Reception note updated by",
            ),
        ),
        migrations.AlterField(
            model_name="patientintakeform",
            name="form_status",
            field=models.CharField(
                choices=[
                    ("IN_PROGRESS", "In progress"),
                    ("REOPENED", "Reopened for patient"),
                    ("SUBMITTED", "Submitted"),
                ],
                default="IN_PROGRESS",
                max_length=20,
                verbose_name="Form status",
            ),
        ),
        migrations.AddConstraint(
            model_name="patientintakeform",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("form_status__in", ["IN_PROGRESS", "REOPENED"])
                )
                | (
                    models.Q(("form_status", "SUBMITTED"))
                    & models.Q(("submitted_at__isnull", False))
                    & (
                        models.Q(("signature_file_path__isnull", False))
                        | (
                            models.Q(("signature_sha256__isnull", False))
                            & models.Q(("signature_sha256", ""), _negated=True)
                        )
                    )
                ),
                name="intake_submitted_requires_signature",
            ),
        ),
    ]
