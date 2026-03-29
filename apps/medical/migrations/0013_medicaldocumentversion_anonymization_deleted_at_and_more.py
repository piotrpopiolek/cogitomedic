# US-013: anonymization_deleted_at + relaxed PDF path constraint after retention.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0012_doctor_text_template_template_locale_choices"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="medicaldocumentversion",
            name="medical_document_pdf_completed_requires_path",
        ),
        migrations.AddField(
            model_name="medicaldocumentversion",
            name="anonymization_deleted_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Anonymization deleted at",
            ),
        ),
        migrations.AddConstraint(
            model_name="medicaldocumentversion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("pdf_generation_status", "COMPLETED"), _negated=True)
                    | models.Q(("pdf_local_path__isnull", False))
                    | models.Q(("local_pdf_deleted_at__isnull", False))
                    | models.Q(("anonymization_deleted_at__isnull", False))
                ),
                name="medical_document_pdf_completed_requires_path",
            ),
        ),
    ]
