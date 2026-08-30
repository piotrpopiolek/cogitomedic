# Generated manually: edit session / draft revision fields and cutover lock cleanup.

from __future__ import annotations

from django.db import migrations, models


def clear_legacy_edit_locks(apps, schema_editor) -> None:
    MedicalDocument = apps.get_model("medical", "MedicalDocument")
    MedicalDocument.objects.all().update(
        locked_by_user_id=None,
        locked_at=None,
        edit_session_token=None,
        last_edit_session_request_id=None,
        last_previewed_draft_revision=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0022_alter_externalpdfattachment_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicaldocument",
            name="draft_revision",
            field=models.PositiveBigIntegerField(
                default=0,
                verbose_name="Draft revision",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocument",
            name="edit_session_revision",
            field=models.PositiveBigIntegerField(
                default=0,
                verbose_name="Edit session revision",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocument",
            name="edit_session_token",
            field=models.UUIDField(
                blank=True,
                null=True,
                verbose_name="Edit session token",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocument",
            name="last_draft_request_base_revision",
            field=models.PositiveBigIntegerField(
                blank=True,
                null=True,
                verbose_name="Last draft request base revision",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocument",
            name="last_draft_request_id",
            field=models.UUIDField(
                blank=True,
                null=True,
                verbose_name="Last draft request ID",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocument",
            name="last_draft_request_result_revision",
            field=models.PositiveBigIntegerField(
                blank=True,
                null=True,
                verbose_name="Last draft request result revision",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocument",
            name="last_edit_session_request_id",
            field=models.UUIDField(
                blank=True,
                null=True,
                verbose_name="Last edit session request ID",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocument",
            name="last_previewed_draft_revision",
            field=models.PositiveBigIntegerField(
                blank=True,
                null=True,
                verbose_name="Last previewed draft revision",
            ),
        ),
        migrations.AddIndex(
            model_name="medicaldocument",
            index=models.Index(
                fields=["locked_by_user", "locked_at"],
                name="med_doc_locked_by_at_idx",
            ),
        ),
        migrations.RunPython(clear_legacy_edit_locks, migrations.RunPython.noop),
    ]
