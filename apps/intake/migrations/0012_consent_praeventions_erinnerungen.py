# Data migration: two new consents for Präventions-Erinnerungen (prevention reminders).
# 1) Agreement to be contacted for reminders and health offers.
# 2) Preferred contact method (E-Mail, SMS, Telefon).

from django.db import migrations
from django.utils import timezone

# (code, title_de, content_de, display_order); is_required=False – optional consent
CONSENTS = [
    (
        "PRAEVENTIONS_ERINNERUNGEN_EINWILLIGUNG",
        "Präventions-Erinnerungen – Einwilligung",
        """Möchten Sie zukünftig an empfohlene Vorsorgeuntersuchungen erinnert werden und Informationen zu weiteren Gesundheitsangeboten erhalten?

☐ Ja, ich bin mit einer Kontaktaufnahme einverstanden.""",
        11,
    ),
    (
        "PRAEVENTIONS_ERINNERUNGEN_KONTAKTWEG",
        "Präventions-Erinnerungen – Bevorzugter Kontaktweg",
        """Bevorzugter Kontaktweg:
☐ E-Mail
☐ SMS
☐ Telefon""",
        12,
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
                "is_required": False,
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
        ("intake", "0011_intakedocumentversion_intakeoutboxevent_and_more"),
    ]

    operations = [
        migrations.RunPython(add_consents, remove_consents),
    ]
