# Allow empty body_map_data=[] / anamnesis_payload={} in admin forms.
# Django's JSONField treats [] and {} as empty values; without blank=True
# the admin change form rejects saving (e.g. reception notes).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0027_fix_q4_question_text_de_uwagi"),
    ]

    operations = [
        migrations.AlterField(
            model_name="patientintakeform",
            name="anamnesis_payload",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="Anamnesis payload",
            ),
        ),
        migrations.AlterField(
            model_name="patientintakeform",
            name="body_map_data",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="Body map data",
            ),
        ),
    ]
