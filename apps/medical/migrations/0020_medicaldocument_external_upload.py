# External upload: EXTERNAL_UPLOAD source type, intake constraint v3, version audit FKs.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0019_paper_intake_authorization"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="medicaldocument",
            name="medical_document_source_type_intake_consistency",
        ),
        migrations.AlterField(
            model_name="medicaldocument",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("DIGITAL_INTAKE", "Digital intake"),
                    ("PAPER_INTAKE", "Paper intake"),
                    ("EXTERNAL_UPLOAD", "External upload"),
                ],
                default="DIGITAL_INTAKE",
                max_length=32,
                verbose_name="Document source type",
            ),
        ),
        migrations.AddConstraint(
            model_name="medicaldocument",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("source_type", "DIGITAL_INTAKE"),
                        ("intake_form__isnull", False),
                    ),
                    models.Q(
                        ("source_type", "PAPER_INTAKE"),
                        ("intake_form__isnull", True),
                    ),
                    models.Q(
                        ("source_type", "EXTERNAL_UPLOAD"),
                        ("intake_form__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="medical_document_source_type_intake_consistency",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocumentversion",
            name="external_original_filename",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name="External original filename",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocumentversion",
            name="external_uploaded_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="External file linked at",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocumentversion",
            name="external_uploaded_by_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="external_upload_versions_uploaded",
                to=settings.AUTH_USER_MODEL,
                verbose_name="External file linked by",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocumentversion",
            name="external_verified_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="External publish verified at",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocumentversion",
            name="external_verified_by_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="external_upload_versions_verified",
                to=settings.AUTH_USER_MODEL,
                verbose_name="External publish verified by",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocumentversion",
            name="external_selected_attachment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="selected_for_versions",
                to="medical.externalpdfattachment",
                verbose_name="External selected attachment",
            ),
        ),
    ]
