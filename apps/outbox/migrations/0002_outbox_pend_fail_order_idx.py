# Generated manually for process_outbox_events ORDER BY optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("outbox", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="outboxevent",
            index=models.Index(
                condition=models.Q(("status__in", ["PENDING", "FAILED"])),
                fields=["available_at", "created_at"],
                name="outbox_pend_fail_order_idx",
            ),
        ),
    ]
