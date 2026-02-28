from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0003_template_favorites_and_pl_locale"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicaldocumentversion",
            name="publish_locale",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddConstraint(
            model_name="medicaldocumentversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("publish_locale__isnull", True))
                | models.Q(("publish_locale__regex", "^(de|en|pl)(-[A-Z]{2})?$")),
                name="medical_document_publish_locale_format",
            ),
        ),
    ]
