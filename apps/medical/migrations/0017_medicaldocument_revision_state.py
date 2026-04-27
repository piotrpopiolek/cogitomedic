# Generated manually: revision-state fields on MedicalDocument
# (Variant B of Stage 5b — explicit "revision of published document" lifecycle).

from django.db import migrations, models
from django.db.models import Max, Q


def _backfill_revision_state(apps, schema_editor):
    """
    Set ``published_version_no`` / ``has_pending_revision`` for existing data
    and repair documents that were silently reverted to DRAFT by the legacy
    ``save_draft_document_version`` path on a PUBLISHED document.

    Rules:
    - If the document has at least one PUBLISHED version, ``published_version_no``
      is the highest published ``version_no``.
    - If the document is in DRAFT status but has earlier PUBLISHED versions,
      this is the legacy "silent revert" case — restore ``status=PUBLISHED``,
      keep ``current_version_no`` aligned with the latest published version,
      and mark ``has_pending_revision=True`` if a higher DRAFT version exists.
    - If the document has no PUBLISHED version yet (clean DRAFT), leave
      ``published_version_no = NULL``, ``has_pending_revision = False``.
    """

    MedicalDocument = apps.get_model("medical", "MedicalDocument")
    MedicalDocumentVersion = apps.get_model("medical", "MedicalDocumentVersion")

    PUBLISHED = "PUBLISHED"
    DRAFT = "DRAFT"

    for doc in MedicalDocument.objects.all().iterator():
        max_published = (
            MedicalDocumentVersion.objects.filter(
                medical_document_id=doc.id,
                version_status=PUBLISHED,
            )
            .aggregate(max_no=Max("version_no"))
            .get("max_no")
        )
        max_draft = (
            MedicalDocumentVersion.objects.filter(
                medical_document_id=doc.id,
                version_status=DRAFT,
            )
            .aggregate(max_no=Max("version_no"))
            .get("max_no")
        )

        update_fields = ["published_version_no", "has_pending_revision"]

        if max_published is None:
            doc.published_version_no = None
            doc.has_pending_revision = False
            doc.save(update_fields=update_fields)
            continue

        doc.published_version_no = max_published
        if doc.status == DRAFT:
            doc.status = PUBLISHED
            doc.current_version_no = max_published
            update_fields.extend(["status", "current_version_no"])

        doc.has_pending_revision = bool(
            max_draft is not None and max_draft > max_published
        )
        doc.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    """No data needs to be removed; dropping the columns drops the values."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0016_alter_externalpdfattachment_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicaldocument",
            name="published_version_no",
            field=models.IntegerField(
                blank=True,
                null=True,
                verbose_name="Published version no",
            ),
        ),
        migrations.AddField(
            model_name="medicaldocument",
            name="has_pending_revision",
            field=models.BooleanField(
                default=False,
                verbose_name="Has pending revision",
            ),
        ),
        migrations.AddConstraint(
            model_name="medicaldocument",
            constraint=models.CheckConstraint(
                condition=Q(published_version_no__isnull=True)
                | Q(published_version_no__gte=0),
                name="medical_document_published_version_non_negative",
            ),
        ),
        migrations.AddIndex(
            model_name="medicaldocument",
            index=models.Index(
                fields=["status", "has_pending_revision", "-updated_at"],
                name="med_doc_status_rev_idx",
            ),
        ),
        migrations.RunPython(_backfill_revision_state, _noop_reverse),
    ]
