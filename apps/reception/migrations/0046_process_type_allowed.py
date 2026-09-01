from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0045_process_type"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="queueentry",
            constraint=models.CheckConstraint(
                condition=models.Q(("process_type__in", ("STANDARD", "TELEDERM"))),
                name="queue_entry_process_type_allowed",
            ),
        ),
    ]
