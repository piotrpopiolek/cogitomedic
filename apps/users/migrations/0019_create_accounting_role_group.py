from django.db import migrations


def create_accounting_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Accounting")
    # No Django model permissions: accounting uses custom report views
    # (accounting_report_access_ok + is_accounting group membership), not ModelAdmin.


def delete_accounting_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Accounting").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0018_staffuser_professional_title_no_default"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_accounting_group, delete_accounting_group),
    ]
