# Migracja danych: Erklärung (privatärztliche Behandlung/GOÄ), Kosteninformation, Bestätigungen (IGeL-Blatt, Einwilligung/Datenschutz).
# Cztery osobne zgody = 4 checkboxy na formularzu.

from django.db import migrations
from django.utils import timezone

# (code, title_de, content_de, display_order)
CONSENTS = [
    (
        "ERKLAERUNG_PRIVATBEHANDLUNG_GOAE",
        "Erklärung – privatärztliche Behandlung / GOÄ",
        """Erklärung

Ich bin gesetzlich krankenversichert.

Auf meinen ausdrücklichen Wunsch nehme ich eine privatärztliche Behandlung in Anspruch.

Ich wurde darüber aufgeklärt, dass die gewünschte Leistung (Videodermatoskopie mit Befundung) nicht Bestandteil der vertragsärztlichen Versorgung ist und von meiner gesetzlichen Krankenkasse in der Regel nicht erstattet wird.

Die Abrechnung erfolgt privatärztlich nach der Gebührenordnung für Ärzte (GOÄ).""",
        1,
    ),
    (
        "KOSTENINFORMATION_VIDEODERMATOSKOPIE",
        "Kosteninformation",
        """Kosteninformation

Ich wurde über die Kosten informiert.

Betrag in EUR: 129,00 €""",
        2,
    ),
    (
        "IGEL_INFOBLATT_ERHALTEN",
        "Bestätigung: IGeL-Informationsblatt",
        "Ich habe das IGeL-Informationsblatt erhalten.",
        3,
    ),
    (
        "EINWILLIGUNG_DATENSCHUTZ_UNTERSCHRIEBEN",
        "Bestätigung: Einwilligung und Datenschutz",
        "Ich habe die medizinische Einwilligung und die Datenschutzinformation erhalten und unterschrieben.",
        4,
    ),
]


def add_consents(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    today = timezone.now().date()
    for code, title_de, content_de, display_order in CONSENTS:
        ConsentDefinition.objects.get_or_create(
            code=code,
            version=1,
            defaults={
                "title_de": title_de,
                "content_de": content_de,
                "is_required": True,
                "is_active": True,
                "display_order": display_order,
                "effective_from": today,
            },
        )


def remove_consents(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    codes = [c[0] for c in CONSENTS]
    ConsentDefinition.objects.filter(code__in=codes, version=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0004_consent_videodermatoscopy_igel"),
    ]

    operations = [
        migrations.RunPython(add_consents, remove_consents),
    ]
