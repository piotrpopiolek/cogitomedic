# Add optional consulting_room to StaffUser so doctors can be restricted to one cabinet.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
        ("reception", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffuser",
            name="consulting_room",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="staff_users",
                to="reception.consultingroom",
            ),
        ),
    ]
