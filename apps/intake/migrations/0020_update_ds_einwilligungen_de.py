# Update German title and content for DS_EINWILLIGUNG_PORTAL_ABHOLCODE, DS_EINWILLIGUNG_SMS, DS_EINWILLIGUNG_EMAIL_RECHNUNG.

from django.db import migrations

UPDATES = [
    (
        "DS_EINWILLIGUNG_PORTAL_ABHOLCODE",
        "Ergebnis im Portal",
        "Ihr Untersuchungsergebnis wird Ihnen aus Datenschutzgründen ausschließlich elektronisch über unser Portal mit persönlichem Abholcode bereitgestellt.",
    ),
    (
        "DS_EINWILLIGUNG_SMS",
        "SMS-Benachrichtigung",
        "Ich möchte per SMS benachrichtigt werden, sobald mein Ergebnis im Portal verfügbar ist.",
    ),
    (
        "DS_EINWILLIGUNG_EMAIL_RECHNUNG",
        "Rechnungen und Unterlagen per E-Mail",
        "Ich möchte Rechnungen und sonstige Unterlagen elektronisch per E-Mail erhalten.",
    ),
]


def forward(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    for code, title_de, content_de in UPDATES:
        ConsentDefinition.objects.filter(code=code, version=1).update(
            title_de=title_de,
            content_de=content_de,
        )


def backward(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    # Restore values from 0006_consent_datenschutz_einwilligungen
    RESTORE = [
        (
            "DS_EINWILLIGUNG_PORTAL_ABHOLCODE",
            "Datenschutz – Ergebnis im Portal",
            "Elektronische Bereitstellung des Ergebnisses (Portal mit Abholcode).",
        ),
        (
            "DS_EINWILLIGUNG_SMS",
            "Datenschutz – Benachrichtigung per SMS",
            "Benachrichtigung zum Ergebnis: SMS.",
        ),
        (
            "DS_EINWILLIGUNG_EMAIL_RECHNUNG",
            "Datenschutz – Rechnungen per E-Mail",
            "Ich stimme dem Erhalt von Rechnungen und Unterlagen per E-Mail zu.",
        ),
    ]
    for code, title_de, content_de in RESTORE:
        ConsentDefinition.objects.filter(code=code, version=1).update(
            title_de=title_de,
            content_de=content_de,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0019_alter_anamnesisoptiondefinition_code_and_more"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
