# Migracja danych: Datenschutzinformation + 6 Einwilligungen (Gesundheitsdaten, Hautbilder, Telemedizin, Portal, SMS, E-Mail).
# Pierwsza zgoda zawiera pełny tekst informacyjny (Verantwortliche Stelle, Zwecke, Speicherung, Speicherdauer) + pierwszy checkbox.

from django.db import migrations
from django.utils import timezone

DS_INTRO = """Verantwortliche Stelle: CogitoMedica Deutschland GmbH, Mühlenstraße 8a, 14167 Berlin. Datenschutzbeauftragter: Herr Sebastian Lazniak (dsb@cogitomedica.de)

Zwecke der Verarbeitung: Durchführung der Untersuchung, ärztliche Befundung, Termin- und Zahlungsabwicklung, gesetzliche Dokumentation.

Speicherung/Hosting: Cloud-Dienst HiDrive der STRATO AG (Berlin) und IONOS SE (Montabaur). Verarbeitung erfolgt ausschließlich in Deutschland/EU.

Ergebnis & Telemedizin: Bereitstellung des Ergebnisses i. d. R. innerhalb von 24 Stunden im geschützten Online-Portal per Abholcode.

Speicherdauer: Bilder und Befunde werden i. d. R. 10 Jahre nach Abschluss der Behandlung aufbewahrt.

Einwilligungen – bitte ankreuzen:"""

# (code, title_de, content_de, display_order)
CONSENTS = [
    (
        "DS_EINWILLIGUNG_GESUNDHEITSDATEN",
        "Datenschutz – Verarbeitung Gesundheitsdaten",
        DS_INTRO
        + "\n\nIch willige ausdrücklich in die Verarbeitung meiner Gesundheitsdaten ein.",
        5,
    ),
    (
        "DS_EINWILLIGUNG_HAUTBILDAUFNAHMEN",
        "Datenschutz – Hautbildaufnahmen",
        "Ich willige in die Erstellung/Speicherung/Verarbeitung von Hautbildaufnahmen ein.",
        6,
    ),
    (
        "DS_EINWILLIGUNG_TELEMEDIZIN",
        "Datenschutz – Telemedizinische Befundung",
        "Telemedizinische Befundung durch Dermatolog:innen.",
        7,
    ),
    (
        "DS_EINWILLIGUNG_PORTAL_ABHOLCODE",
        "Datenschutz – Ergebnis im Portal",
        "Elektronische Bereitstellung des Ergebnisses (Portal mit Abholcode).",
        8,
    ),
    (
        "DS_EINWILLIGUNG_SMS",
        "Datenschutz – Benachrichtigung per SMS",
        "Benachrichtigung zum Ergebnis: SMS.",
        9,
    ),
    (
        "DS_EINWILLIGUNG_EMAIL_RECHNUNG",
        "Datenschutz – Rechnungen per E-Mail",
        "Ich stimme dem Erhalt von Rechnungen und Unterlagen per E-Mail zu.",
        10,
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
        ("intake", "0005_consent_erklaerung_kosten_bestaetigungen"),
    ]

    operations = [
        migrations.RunPython(add_consents, remove_consents),
    ]
