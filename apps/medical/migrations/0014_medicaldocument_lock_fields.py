# Generated manually: edit lock fields on MedicalDocument.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0013_medicaldocumentversion_anonymization_deleted_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicaldocument",
            name="locked_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Locked at",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocument",
            name="locked_by_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="locked_medical_documents",
                to="users.staffuser",
                verbose_name="Locked by",
            ),
        ),
    ]
