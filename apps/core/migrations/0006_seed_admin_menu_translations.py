# Generated manually – seed administration UI menu/theme buttons.

from django.db import migrations

def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    menu_translations = {
        "menu_view_site": {
            "de": "Seite anzeigen",
            "en": "View site",
            "pl": "Pokaż stronę"
        },
        "menu_change_password": {
            "de": "Passwort ändern",
            "en": "Change password",
            "pl": "Zmień hasło"
        },
        "menu_logout": {
            "de": "Abmelden",
            "en": "Log out",
            "pl": "Wyloguj się"
        },
        "theme_light": {
            "de": "Hell",
            "en": "Light",
            "pl": "Jasny"
        },
        "theme_dark": {
            "de": "Dunkel",
            "en": "Dark",
            "pl": "Ciemny"
        },
        "theme_system": {
            "de": "System",
            "en": "System",
            "pl": "System"
        },
    }

    for short_key, mapping in menu_translations.items():
        full_key = f"administration.{short_key}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "administration",
                "description": "Admin panel user menu and theme",
                "is_html_allowed": False,
                "allowed_placeholders": [],
                "status": "ACTIVE",
            },
        )
        for lang, text in mapping.items():
            TranslationValue.objects.get_or_create(
                translation_key=key,
                language_code=lang,
                defaults={"value": text},
            )

def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    keys_to_delete = [
        "administration.menu_view_site",
        "administration.menu_change_password",
        "administration.menu_logout",
        "administration.theme_light",
        "administration.theme_dark",
        "administration.theme_system",
    ]
    TranslationKey.objects.filter(key__in=keys_to_delete).delete()

class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_seed_admin_button_translations"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
