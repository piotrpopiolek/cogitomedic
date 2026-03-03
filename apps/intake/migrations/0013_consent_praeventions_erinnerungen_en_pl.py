# Data migration: fill English and Polish (title_en, content_en, title_pl, content_pl)
# for Präventions-Erinnerungen consents added in 0012.

from django.db import migrations

# (code, version, title_en, content_en, title_pl, content_pl)
CONSENT_TRANSLATIONS = [
    (
        "PRAEVENTIONS_ERINNERUNGEN_EINWILLIGUNG",
        1,
        "Prevention reminders – Consent",
        """Would you like to be reminded about recommended preventive examinations in the future and receive information about other health services?

☐ Yes, I agree to be contacted.""",
        "Przypomnienia o profilaktyce – Zgoda",
        """Czy chciałbyś/chciałabyś w przyszłości otrzymywać przypomnienia o zalecanych badaniach profilaktycznych oraz informacje o innych ofertach zdrowotnych?

☐ Tak, wyrażam zgodę na kontakt.""",
    ),
    (
        "PRAEVENTIONS_ERINNERUNGEN_KONTAKTWEG",
        1,
        "Prevention reminders – Preferred contact method",
        """Preferred contact method:
☐ Email
☐ SMS
☐ Phone""",
        "Przypomnienia o profilaktyce – Preferowany sposób kontaktu",
        """Preferowany sposób kontaktu:
☐ E-mail
☐ SMS
☐ Telefon""",
    ),
]


def fill_en_pl(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    for code, version, title_en, content_en, title_pl, content_pl in CONSENT_TRANSLATIONS:
        ConsentDefinition.objects.filter(code=code, version=version).update(
            title_en=title_en,
            content_en=content_en,
            title_pl=title_pl,
            content_pl=content_pl,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0012_consent_praeventions_erinnerungen"),
    ]

    operations = [
        migrations.RunPython(fill_en_pl, noop_reverse),
    ]
