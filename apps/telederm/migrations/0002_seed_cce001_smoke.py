from django.db import migrations


def seed_telederm_smoke(apps, schema_editor):
    from apps.telederm.seed.cce001_smoke import TELEDERM_SMOKE_CATALOG

    Question = apps.get_model("telederm", "TeledermQuestionDefinition")
    Option = apps.get_model("telederm", "TeledermQuestionOption")
    db_alias = schema_editor.connection.alias

    for row in TELEDERM_SMOKE_CATALOG:
        data = dict(row)
        options = data.pop("options", [])
        question = Question.objects.using(db_alias).create(**data)
        for idx, opt in enumerate(options):
            Option.objects.using(db_alias).create(
                question=question,
                code=opt["code"],
                label_de=opt["label_de"],
                label_en=opt.get("label_en", opt["label_de"]),
                label_pl=opt.get("label_pl", opt["label_de"]),
                is_urgent=opt.get("is_urgent", False),
                activates_path_code=opt.get("activates_path_code", ""),
                display_order=idx,
            )


def unseed(apps, schema_editor):
    Question = apps.get_model("telederm", "TeledermQuestionDefinition")
    db_alias = schema_editor.connection.alias
    Question.objects.using(db_alias).all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("telederm", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_telederm_smoke, unseed),
    ]
