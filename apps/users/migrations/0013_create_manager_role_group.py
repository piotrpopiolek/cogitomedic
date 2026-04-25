from django.db import migrations


def create_manager_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    manager_group, _ = Group.objects.get_or_create(name="Manager")

    manager_perms = Permission.objects.filter(
        codename__in=[
            "view_staffuser",
            "change_staffuser",
            "view_patient",
            "add_patient",
            "change_patient",
            "view_clinicsite",
            "view_consultingroom",
            "view_dailyqueue",
            "add_dailyqueue",
            "change_dailyqueue",
            "view_queueentry",
            "add_queueentry",
            "change_queueentry",
            "view_tabletdevice",
            "add_tabletdevice",
            "change_tabletdevice",
            "view_patientformsession",
            "add_patientformsession",
            "change_patientformsession",
            "view_patientimportbatch",
            "add_patientimportbatch",
            "change_patientimportbatch",
            "view_patientimporterror",
            "view_patientintakeform",
            "change_patientintakeform",
            "view_patientintakeconsent",
            "change_patientintakeconsent",
            "view_medicaldocument",
            "view_medicaldocumentversion",
        ]
    )
    manager_group.permissions.set(manager_perms)


def delete_manager_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Manager").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0012_alter_staffuser_clinic_sites_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("reception", "0001_initial"),
        ("medical", "0001_initial"),
        ("intake", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_manager_group, delete_manager_group),
    ]
