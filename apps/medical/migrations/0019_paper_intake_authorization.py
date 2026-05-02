# Generated manually: PaperIntakeAuthorization for manager/admin paper path (T1).

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0018_medicaldocument_source_type_and_more"),
        ("reception", "0037_drop_queue_entry_status_published"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PaperIntakeAuthorization",
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
                ("authorized_at", models.DateTimeField(verbose_name="Authorized at")),
                (
                    "reason",
                    models.TextField(verbose_name="Authorization reason"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Created at"
                    ),
                ),
                (
                    "authorized_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="paper_intake_authorizations_granted",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Authorized by",
                    ),
                ),
                (
                    "queue_entry",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="paper_intake_authorization",
                        to="reception.queueentry",
                        verbose_name="Queue entry",
                    ),
                ),
            ],
            options={
                "verbose_name": "Paper intake authorization",
                "verbose_name_plural": "Paper intake authorizations",
                "db_table": "paper_intake_authorization",
            },
        ),
        migrations.AddIndex(
            model_name="paperintakeauthorization",
            index=models.Index(
                fields=["authorized_at"], name="paper_auth_authorized_at_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="paperintakeauthorization",
            index=models.Index(
                fields=["authorized_by"], name="paper_auth_authorized_by_idx"
            ),
        ),
    ]
