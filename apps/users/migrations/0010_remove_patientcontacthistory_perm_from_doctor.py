from django.db import migrations


def remove_patientcontacthistory_from_doctor_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    doctor = Group.objects.filter(name="Doctor").first()
    if not doctor:
        return
    for perm in Permission.objects.filter(codename="view_patientcontacthistory"):
        doctor.permissions.remove(perm)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_ensure_role_permissions"),
        ("reception", "0029_remove_patientcontacthistory"),
    ]

    operations = [
        migrations.RunPython(remove_patientcontacthistory_from_doctor_group, noop_reverse),
    ]
