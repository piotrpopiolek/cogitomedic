# Naprawa: jeśli 0006_create_roles_groups uruchomiła się przed migracjami reception/medical/operations,
# grupy powstały bez uprawnień. Ta migracja ponownie przypisuje uprawnienia do grup (idempotentna).
# Na serwerze mydevil: po wdrożeniu uruchom migrate – ta migracja uzupełni uprawnienia.

from django.db import migrations


def ensure_role_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    doctor_group = Group.objects.filter(name="Doctor").first()
    reception_group = Group.objects.filter(name="Reception").first()
    admin_group = Group.objects.filter(name="Admin").first()
    if not all([doctor_group, reception_group, admin_group]):
        return

    admin_group.permissions.set(Permission.objects.all())

    doctor_perms = Permission.objects.filter(
        codename__in=[
            "view_patient",
            "view_clinicsite",
            "view_consultingroom",
            "view_dailyqueue",
            "view_queueentry",
            "view_patientcontacthistory",
            "view_medicaldocument",
            "add_medicaldocument",
            "change_medicaldocument",
            "view_doctortexttemplate",
            "add_doctortexttemplate",
            "change_doctortexttemplate",
            "view_auditevent",
        ]
    )
    doctor_group.permissions.set(doctor_perms)

    reception_perms = Permission.objects.filter(
        codename__in=[
            "view_patient",
            "add_patient",
            "change_patient",
            "view_dailyqueue",
            "add_dailyqueue",
            "change_dailyqueue",
            "view_queueentry",
            "add_queueentry",
            "change_queueentry",
            "view_patientformsession",
            "add_patientformsession",
            "change_patientformsession",
            "view_patientimportbatch",
            "add_patientimportbatch",
            "view_patientimporterror",
            "view_clinicsite",
            "view_consultingroom",
        ]
    )
    reception_group.permissions.set(reception_perms)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0008_alter_staffuser_options_alter_staffuser_code_and_more"),
        ("reception", "0001_initial"),
        ("medical", "0001_initial"),
        ("operations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ensure_role_permissions, noop_reverse),
    ]
