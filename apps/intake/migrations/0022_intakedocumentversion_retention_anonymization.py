# US-013: Intake retention / anonymization fields + constraint updates.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0021_consent_ds_einwilligung_ergebnisses"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="patientintakeform",
            name="intake_submitted_requires_signature",
        ),
        migrations.RemoveConstraint(
            model_name="intakedocumentversion",
            name="intake_document_pdf_completed_requires_path",
        ),
        migrations.AddField(
            model_name="intakedocumentversion",
            name="anonymization_deleted_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Anonymization deleted at",
            ),
        ),
        migrations.AddField(
            model_name="intakedocumentversion",
            name="local_pdf_deleted_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Local pdf deleted at",
            ),
        ),
        migrations.AddConstraint(
            model_name="patientintakeform",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("form_status", "IN_PROGRESS"))
                    | (
                        models.Q(("submitted_at__isnull", False))
                        & (
                            models.Q(("signature_file_path__isnull", False))
                            | (
                                models.Q(("signature_sha256__isnull", False))
                                & models.Q(("signature_sha256", ""), _negated=True)
                            )
                        )
                    )
                ),
                name="intake_submitted_requires_signature",
            ),
        ),
        migrations.AddConstraint(
            model_name="intakedocumentversion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("pdf_generation_status", "COMPLETED"), _negated=True)
                    | models.Q(("pdf_local_path__isnull", False))
                    | models.Q(("local_pdf_deleted_at__isnull", False))
                    | models.Q(("anonymization_deleted_at__isnull", False))
                ),
                name="intake_document_pdf_completed_requires_path",
            ),
        ),
        migrations.AddConstraint(
            model_name="intakedocumentversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("local_pdf_deleted_at__isnull", True))
                | models.Q(("hidrive_sent", True)),
                name="intake_document_local_pdf_deletion_guard",
            ),
        ),
        migrations.AddIndex(
            model_name="intakedocumentversion",
            index=models.Index(
                condition=models.Q(
                    ("hidrive_sent", True),
                    ("local_pdf_deleted_at__isnull", True),
                ),
                fields=["created_at"],
                name="intake_document_retention_idx",
            ),
        ),
    ]
