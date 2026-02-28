from django.db import migrations, models


def _normalize_locale(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value.startswith("en"):
        return "en-GB"
    if value.startswith("pl"):
        return "pl-PL"
    return "de-DE"


def backfill_publish_locale(apps, schema_editor):
    MedicalDocumentVersion = apps.get_model("medical", "MedicalDocumentVersion")
    rows = MedicalDocumentVersion.objects.filter(
        version_status="PUBLISHED",
        publish_locale__isnull=True,
    ).only("id", "medical_payload")
    for row in rows.iterator():
        payload = row.medical_payload or {}
        locale = _normalize_locale(payload.get("authoring_locale"))
        MedicalDocumentVersion.objects.filter(id=row.id).update(publish_locale=locale)


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0004_publish_locale_for_version"),
    ]

    operations = [
        migrations.RunPython(backfill_publish_locale, noop_reverse),
        migrations.AddConstraint(
            model_name="medicaldocumentversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("version_status", "DRAFT")) | models.Q(("publish_locale__isnull", False)),
                name="medical_document_published_requires_publish_locale",
            ),
        ),
    ]
