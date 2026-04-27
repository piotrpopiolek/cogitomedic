from django.db import migrations


def rename_klinikleitung_group_to_manager(apps, schema_editor):
    Group = apps.get_model("auth", "Group")

    legacy_group = Group.objects.filter(name="Klinikleitung").first()
    manager_group = Group.objects.filter(name="Manager").first()

    if legacy_group is None:
        return

    if manager_group is None:
        legacy_group.name = "Manager"
        legacy_group.save(update_fields=["name"])
        return

    manager_group.permissions.add(*legacy_group.permissions.all())
    manager_group.user_set.add(*legacy_group.user_set.all())
    legacy_group.delete()


def rename_manager_group_to_klinikleitung(apps, schema_editor):
    Group = apps.get_model("auth", "Group")

    manager_group = Group.objects.filter(name="Manager").first()
    legacy_group = Group.objects.filter(name="Klinikleitung").first()

    if manager_group is None:
        return

    if legacy_group is None:
        manager_group.name = "Klinikleitung"
        manager_group.save(update_fields=["name"])
        return

    legacy_group.permissions.add(*manager_group.permissions.all())
    legacy_group.user_set.add(*manager_group.user_set.all())
    manager_group.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0013_create_manager_role_group"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(
            rename_klinikleitung_group_to_manager,
            rename_manager_group_to_klinikleitung,
        ),
    ]
