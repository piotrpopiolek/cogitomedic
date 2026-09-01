from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0029_process_type"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="anamnesisquestiondefinitionprocess",
            constraint=models.CheckConstraint(
                condition=models.Q(("process_type__in", ("STANDARD", "TELEDERM"))),
                name="anamnesis_question_process_type_allowed",
            ),
        ),
        migrations.AddConstraint(
            model_name="consentdefinitionprocess",
            constraint=models.CheckConstraint(
                condition=models.Q(("process_type__in", ("STANDARD", "TELEDERM"))),
                name="consent_definition_process_type_allowed",
            ),
        ),
    ]
