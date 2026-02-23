from __future__ import annotations

from django.db import migrations


def mark_admin_role_as_staff(apps, schema_editor):
    StaffUser = apps.get_model("users", "StaffUser")
    StaffUser.objects.filter(role="ADMIN", is_staff=False).update(is_staff=True)


def noop_reverse(apps, schema_editor):
    # Intentionally no-op: we do not want to demote staff access on rollback.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_staffuser_consulting_room"),
    ]

    operations = [
        migrations.RunPython(mark_admin_role_as_staff, noop_reverse),
    ]
