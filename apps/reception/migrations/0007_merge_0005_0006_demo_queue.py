# Merge migration: 0005 and 0006 both add demo queue (conflicting leaves).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0005_add_demo_queue_and_10_patients_today"),
        ("reception", "0006_add_demo_queue_and_10_patients_today"),
    ]

    operations = []
