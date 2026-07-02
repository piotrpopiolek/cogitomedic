"""Remove model view permissions from Accounting (report uses custom views only)."""

from django.db import migrations


def clear_accounting_group_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    try:
        accounting_group = Group.objects.get(name="Accounting")
    except Group.DoesNotExist:
        return
    accounting_group.permissions.clear()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0019_create_accounting_role_group"),
    ]

    operations = [
        migrations.RunPython(
            clear_accounting_group_permissions,
            migrations.RunPython.noop,
        ),
    ]
