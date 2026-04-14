# HiDrive external PDF attachments (matched /incoming files per medical document).

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0014_medicaldocument_lock_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalPdfAttachment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("hidrive_remote_path", models.CharField(max_length=500)),
                ("original_filename", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("MATCHED", "Matched"),
                            ("ACCEPTED", "Accepted"),
                            ("REJECTED", "Rejected"),
                            ("MERGE_FAILED", "Merge failed"),
                        ],
                        default="MATCHED",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "medical_document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="external_pdfs",
                        to="medical.medicaldocument",
                    ),
                ),
            ],
            options={
                "db_table": "external_pdf_attachment",
            },
        ),
        migrations.AddConstraint(
            model_name="externalpdfattachment",
            constraint=models.UniqueConstraint(
                fields=("medical_document", "hidrive_remote_path"),
                name="external_pdf_attachment_doc_path_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="externalpdfattachment",
            index=models.Index(
                fields=["medical_document", "status"],
                name="external_pdf_doc_status_idx",
            ),
        ),
    ]
