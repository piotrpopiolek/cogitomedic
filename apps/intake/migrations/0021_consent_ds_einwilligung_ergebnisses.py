# Add ConsentDefinition DS_EINWILLIGUNG_ERGEBNISSES (version 1).

from django.db import migrations
from django.utils import timezone

CODE = "DS_EINWILLIGUNG_ERGEBNISSES"
VERSION = 1
DISPLAY_ORDER = 12

TITLE_DE = "Datenschutz – Bereitstellung des Ergebnisses im Portal"
TITLE_EN = "Data protection – Provision of result in the portal"
TITLE_PL = "Ochrona danych – Udostępnienie wyniku w portalu"

CONTENT_DE = "Ihr Untersuchungsergebnis wird Ihnen aus Datenschutzgründen ausschließlich elektronisch über unser Portal mit persönlichem Abholcode bereitgestellt."
CONTENT_EN = "For data protection reasons, your examination result will be provided to you exclusively electronically via our portal with a personal collection code."
CONTENT_PL = "Ze względów ochrony danych Państwa wynik badania zostanie udostępniony wyłącznie elektronicznie przez nasz portal z indywidualnym kodem odbioru."


def forward(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    ConsentDefinition.objects.get_or_create(
        code=CODE,
        version=VERSION,
        defaults={
            "title_de": TITLE_DE,
            "title_en": TITLE_EN,
            "title_pl": TITLE_PL,
            "content_de": CONTENT_DE,
            "content_en": CONTENT_EN,
            "content_pl": CONTENT_PL,
            "is_required": True,
            "is_active": True,
            "display_order": DISPLAY_ORDER,
            "effective_from": timezone.now().date(),
        },
    )


def backward(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    ConsentDefinition.objects.filter(code=CODE, version=VERSION).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0020_update_ds_einwilligungen_de"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
