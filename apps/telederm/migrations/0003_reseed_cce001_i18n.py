"""Reseed telederm smoke catalog with English codes and DE/EN/PL labels."""

from django.db import migrations


def reseed(apps, schema_editor):
    from apps.telederm.seed.cce001_smoke import TELEDERM_SMOKE_CATALOG

    Question = apps.get_model("telederm", "TeledermQuestionDefinition")
    Option = apps.get_model("telederm", "TeledermQuestionOption")
    db_alias = schema_editor.connection.alias

    Question.objects.using(db_alias).all().delete()

    for row in TELEDERM_SMOKE_CATALOG:
        data = dict(row)
        options = data.pop("options", [])
        question = Question.objects.using(db_alias).create(**data)
        for idx, opt in enumerate(options):
            Option.objects.using(db_alias).create(
                question=question,
                code=opt["code"],
                label_de=opt["label_de"],
                label_en=opt["label_en"],
                label_pl=opt["label_pl"],
                is_urgent=opt.get("is_urgent", False),
                activates_path_code=opt.get("activates_path_code", ""),
                display_order=idx,
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("telederm", "0002_seed_cce001_smoke"),
    ]

    operations = [
        migrations.RunPython(reseed, noop),
    ]
