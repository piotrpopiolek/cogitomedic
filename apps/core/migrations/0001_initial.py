from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TranslationCacheVersion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.CharField(choices=[("doctor", "Doctor"), ("reception", "Reception"), ("waiting_room", "Waiting room"), ("administration", "Administration"), ("other", "Other")], max_length=32)),
                ("language_code", models.CharField(max_length=5)),
                ("version", models.BigIntegerField(default=1)),
            ],
            options={
                "db_table": "translation_cache_version",
            },
        ),
        migrations.CreateModel(
            name="TranslationKey",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.CharField(max_length=150, unique=True)),
                ("category", models.CharField(choices=[("doctor", "Doctor"), ("reception", "Reception"), ("waiting_room", "Waiting room"), ("administration", "Administration"), ("other", "Other")], max_length=32)),
                ("description", models.TextField(blank=True, default="")),
                ("is_html_allowed", models.BooleanField(default=False)),
                ("allowed_placeholders", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("DEPRECATED", "Deprecated")], default="ACTIVE", max_length=16)),
            ],
            options={
                "db_table": "translation_key",
            },
        ),
        migrations.CreateModel(
            name="TranslationValue",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("language_code", models.CharField(max_length=5)),
                ("value", models.TextField()),
                ("translation_key", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="values", to="core.translationkey")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_translation_values", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "translation_value",
            },
        ),
        migrations.AddIndex(
            model_name="translationkey",
            index=models.Index(fields=["category", "status"], name="translation__categor_f7ee83_idx"),
        ),
        migrations.AddConstraint(
            model_name="translationcacheversion",
            constraint=models.UniqueConstraint(fields=("category", "language_code"), name="translation_cache_version_category_language_unique"),
        ),
        migrations.AddConstraint(
            model_name="translationcacheversion",
            constraint=models.CheckConstraint(condition=models.Q(("language_code__in", ["de", "en", "pl"])), name="translation_cache_version_language_allowed"),
        ),
        migrations.AddConstraint(
            model_name="translationvalue",
            constraint=models.UniqueConstraint(fields=("translation_key", "language_code"), name="translation_value_key_language_unique"),
        ),
        migrations.AddConstraint(
            model_name="translationvalue",
            constraint=models.CheckConstraint(condition=models.Q(("language_code__in", ["de", "en", "pl"])), name="translation_value_language_allowed"),
        ),
        migrations.AddIndex(
            model_name="translationvalue",
            index=models.Index(fields=["language_code", "updated_at"], name="translation_language_7e9eca_idx"),
        ),
    ]
