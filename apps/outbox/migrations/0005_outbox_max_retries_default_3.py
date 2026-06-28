from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("outbox", "0004_alter_outboxevent_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="outboxevent",
            name="max_retries",
            field=models.SmallIntegerField(default=3),
        ),
    ]
