# New ExternalPdfAttachment statuses for staged HiDrive upload.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0020_medicaldocument_external_upload"),
    ]

    operations = [
        migrations.AlterField(
            model_name="externalpdfattachment",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING_UPLOAD", "Pending upload"),
                    ("MATCHED", "Matched"),
                    ("ACCEPTED", "Accepted"),
                    ("REJECTED", "Rejected"),
                    ("MERGE_FAILED", "Merge failed"),
                    ("UPLOAD_FAILED", "Upload failed"),
                ],
                default="MATCHED",
                max_length=20,
                verbose_name="Status",
            ),
        ),
    ]
