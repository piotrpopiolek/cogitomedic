from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctortexttemplate",
            name="lesion_group_favorites",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="doctortexttemplate",
            name="summary_favorites",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RemoveConstraint(
            model_name="doctortexttemplate",
            name="doctor_template_locale_format",
        ),
        migrations.AddConstraint(
            model_name="doctortexttemplate",
            constraint=models.CheckConstraint(
                condition=models.Q(("template_locale__regex", "^(de|en|pl)(-[A-Z]{2})?$")),
                name="doctor_template_locale_format",
            ),
        ),
    ]
