# Remove summary_favorites from DoctorTextTemplate (field no longer used).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0008_alter_doctortexttemplate_options_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="doctortexttemplate",
            name="summary_favorites",
        ),
    ]
