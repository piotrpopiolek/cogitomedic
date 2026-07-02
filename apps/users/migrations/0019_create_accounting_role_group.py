from django.db import migrations


def create_accounting_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    accounting_group, _ = Group.objects.get_or_create(name="Accounting")

    accounting_perms = Permission.objects.filter(
        codename__in=[
            "view_staffuser",
            "view_patient",
            "view_clinicsite",
            "view_dailyqueue",
            "view_queueentry",
            "view_medicaldocument",
            "view_medicaldocumentversion",
        ]
    )
    accounting_group.permissions.set(accounting_perms)


def delete_accounting_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Accounting").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0018_staffuser_professional_title_no_default"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("reception", "0001_initial"),
        ("medical", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_accounting_group, delete_accounting_group),
    ]
