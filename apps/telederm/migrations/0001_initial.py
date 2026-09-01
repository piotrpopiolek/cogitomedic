# Generated manually for apps.telederm

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="TeledermQuestionDefinition",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("question_id", models.CharField(max_length=32, unique=True)),
                ("path_code", models.CharField(max_length=32)),
                ("section", models.CharField(max_length=32)),
                ("answer_type", models.CharField(max_length=20)),
                ("question_text_de", models.TextField()),
                ("question_text_en", models.TextField(blank=True, default="")),
                ("question_text_pl", models.TextField(blank=True, default="")),
                ("show_if", models.JSONField(blank=True, default=dict)),
                ("include_in_summary", models.BooleanField(default=True)),
                ("is_required", models.BooleanField(default=True)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "telederm_question_definition",
                "ordering": ["display_order", "question_id"],
            },
        ),
        migrations.CreateModel(
            name="TeledermQuestionOption",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("code", models.CharField(max_length=64)),
                ("label_de", models.CharField(max_length=500)),
                ("label_en", models.CharField(blank=True, default="", max_length=500)),
                ("label_pl", models.CharField(blank=True, default="", max_length=500)),
                ("is_urgent", models.BooleanField(default=False)),
                (
                    "activates_path_code",
                    models.CharField(blank=True, default="", max_length=32),
                ),
                ("display_order", models.PositiveIntegerField(default=0)),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="options",
                        to="telederm.teledermquestiondefinition",
                    ),
                ),
            ],
            options={
                "db_table": "telederm_question_option",
                "ordering": ["display_order", "code"],
            },
        ),
        migrations.AddConstraint(
            model_name="teledermquestionoption",
            constraint=models.UniqueConstraint(
                fields=("question", "code"),
                name="telederm_question_option_unique",
            ),
        ),
    ]
