# Migracja danych: zgoda pacjenta na digitalną Videodermatoskopię (IGeL).
# Jedna zgoda – cały dokument (Aufklärung + Patientenbestätigung und Einwilligung) = jeden checkbox.

from django.db import migrations
from django.utils import timezone

CONSENT_CODE = "VIDEODERMATOSKOPIE_IGEL"
CONSENT_TITLE_DE = "Einwilligung zur digitalen Videodermatoskopie (IGeL)"

CONSENT_CONTENT_DE = """Ich, der/die Patient/in, bestätige, dass ich von der Mitarbeiterin der CogitoMedica GmbH persönlich und umfassend über das geplante Verfahren der digitalen Videodermatoskopie aufgeklärt wurde. Ich wurde über folgende Punkte in verständlicher Sprache informiert:

1. Zweck und Nutzen der Untersuchung

Die digitale Videodermatoskopie dient der computergestützten Hautkrebsfrüherkennung, insbesondere zur Untersuchung von Pigmentmalen (Muttermalen).

Das Verfahren ermöglicht die hochauflösende Dokumentation und die objektive Verlaufskontrolle von Hautveränderungen, was die Sicherheit gegenüber einer reinen Sichtuntersuchung erhöht.

Der Hauptnutzen liegt in der Möglichkeit, selbst kleinste Veränderungen über die Zeit zu erkennen und unnötige Biopsien zu vermeiden.

2. Ablauf der Untersuchung

Das Verfahren ist nicht-invasiv und schmerzfrei.

Es werden mit einem speziellen Dermatoskop digitale Aufnahmen der Haut erstellt und gespeichert.

Dies geschieht in der Regel im Rahmen einer Ganzkörperuntersuchung mit anschließender detaillierter Dokumentation verdächtiger Hautstellen.

Die Untersuchung arbeitet ausschließlich mit sichtbarem Licht und birgt keine Strahlungsbelastung.

3. Mögliche Risiken und Alternativen

Mir ist bekannt, dass die Untersuchung selbst mit keinen besonderen Risiken verbunden ist.

Keine hundertprozentige Zuverlässigkeit: Obwohl die Videodermatoskopie die diagnostische Präzision erhöht, ist keine Untersuchungsmethode zu 100 % zuverlässig. Es besteht ein geringes Restrisiko, dass eine bösartige Veränderung übersehen wird.

Risiko der „Überdiagnose": Sollte eine Hautveränderung als verdächtig eingestuft werden, kann dies zu einer psychischen Belastung führen. Es besteht das Risiko, dass sich der Verdacht als harmlos herausstellt.

Notwendigkeit einer Biopsie: Ein eindeutiger, endgültiger Befund kann nur durch eine histologische Untersuchung einer Gewebeprobe erzielt werden.

Mir wurde die Alternative der von meiner gesetzlichen Krankenkasse (GKV) angebotenen Hautkrebsvorsorgeuntersuchung genannt.

Patientenbestätigung und Einwilligung

Ich bestätige hiermit, dass ich die Aufklärung erhalten und die Informationen verstanden habe.

Ich hatte die Möglichkeit, alle meine Fragen zu stellen.

Ich wünsche die Durchführung der oben genannten digitalen Videodermatoskopie als Individuelle Gesundheitsleistung ausdrücklich."""


def add_consent(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    today = timezone.now().date()
    ConsentDefinition.objects.get_or_create(
        code=CONSENT_CODE,
        version=1,
        defaults={
            "title_de": CONSENT_TITLE_DE,
            "content_de": CONSENT_CONTENT_DE,
            "is_required": True,
            "is_active": True,
            "display_order": 0,
            "effective_from": today,
        },
    )


def remove_consent(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    ConsentDefinition.objects.filter(code=CONSENT_CODE, version=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0003_anamnesis_questions_melanoma"),
    ]

    operations = [
        migrations.RunPython(add_consent, remove_consent),
    ]
