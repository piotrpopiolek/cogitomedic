# Teledermatologie: Hinweistext + vier Einwilligungs-/Bestätigungstexte (display_order -5 .. -1).

from django.db import migrations
from django.utils import timezone


def forward(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    today = timezone.now().date()

    consents = [
        {
            "code": "TELEDERM_INFO",
            "version": 1,
            "display_order": -5,
            "title_de": "Teledermatologie – Information",
            "title_en": "Teledermatology – Information",
            "title_pl": "Teledermatologia – informacja",
            "content_de": (
                "Bei Ihrem Termin vor Ort werden die medizinischen Bildaufnahmen Ihrer Haut "
                "durch geschultes medizinisches Fachpersonal durchgeführt.\n"
                "Ein Arzt / eine Ärztin ist dabei nicht vor Ort anwesend.\n\n"
                "Die ärztliche Beurteilung Ihrer Hautveränderungen erfolgt im Anschluss "
                "ausschließlich im Rahmen einer teledermatologischen Fernbefundung durch eine "
                "kooperierende Dermatologin / einen kooperierenden Dermatologen.\n\n"
                "Zu diesem Zweck werden die im Rahmen der Untersuchung erstellten Bildaufnahmen "
                "sowie die für die Befundung erforderlichen Angaben aus Ihrer Anamnese und "
                "Dokumentation an den befundenden Arzt / die befundende Ärztin übermittelt.\n\n"
                "Die teledermatologische Befundung erfolgt auf Grundlage der übermittelten "
                "Bilder und Informationen. Sie ersetzt nicht in jedem Fall eine persönliche "
                "ärztliche Untersuchung. Falls medizinisch erforderlich, kann eine "
                "weiterführende Diagnostik, eine persönliche dermatologische Vorstellung oder "
                "eine Gewebeuntersuchung empfohlen werden.\n\n"
                "Bei der ärztlichen Befundung handelt es sich um eine privatärztliche Leistung. "
                "Die Abrechnung erfolgt nach der Gebührenordnung für Ärzte (GOÄ)."
            ),
            "content_en": (
                "At your on-site appointment, medical images of your skin will be taken by "
                "trained medical staff.\n"
                "A physician is not present on site.\n\n"
                "Assessment of your skin changes is subsequently provided exclusively as "
                "teledermatological remote reporting by a cooperating dermatologist.\n\n"
                "For this purpose, the images created during the examination and the "
                "information from your history and documentation required for reporting will be "
                "transmitted to the reporting physician.\n\n"
                "Teledermatological reporting is based on the transmitted images and "
                "information. It does not replace an in-person medical examination in every "
                "case. If medically necessary, further diagnostics, an in-person dermatology "
                "visit, or a tissue examination may be recommended.\n\n"
                "The medical reporting is a private medical service. Billing is in accordance "
                "with the German Schedule of Fees for Physicians (GOÄ)."
            ),
            "content_pl": (
                "Podczas wizyty na miejscu wykonywane są medyczne zdjęcia skóry przez "
                "przeszkolony personel medyczny.\n"
                "Lekarz nie przebywa na miejscu.\n\n"
                "Ocena zmian skórnych odbywa się następnie wyłącznie w formie "
                "teledermatologicznego zdalnego opisu przez współpracującą dermatolożkę / "
                "współpracującego dermatologa.\n\n"
                "W tym celu przekazywane są lekarzowi lub lekarce opisującemu zdjęcia wykonane "
                "w trakcie badania oraz niezbędne informacje z Pana/Pani anamnezy i dokumentacji."
                "\n\n"
                "Opis teledermatologiczny opiera się na przekazanych zdjęciach i informacjach. "
                "Nie zastępuje on w każdym przypadku osobistego badania lekarskiego. W razie "
                "wskazań medycznych można zalecić dalszą diagnostykę, osobistą wizytę u "
                "dermatologa lub badanie histopatologiczne.\n\n"
                "Opis lekarski jest usługą prywatną lekarską. Rozliczenie następuje według "
                "niemieckiej tabeli opłat lekarskich (GOÄ)."
            ),
        },
        {
            "code": "TELEDERM_VERSTANDEN_AUFNAHME",
            "version": 1,
            "display_order": -4,
            "title_de": "Teledermatologie – Bildaufnahme und Befundung",
            "title_en": "Teledermatology – Imaging and reporting",
            "title_pl": "Teledermatologia – wykonanie zdjęć i opis",
            "content_de": (
                "Ich habe verstanden, dass die Bildaufnahme vor Ort durch medizinisches "
                "Fachpersonal erfolgt und die ärztliche Befundung ausschließlich "
                "teledermatologisch durch eine kooperierende Dermatologin / einen "
                "kooperierenden Dermatologen vorgenommen wird."
            ),
            "content_en": (
                "I understand that imaging on site is performed by medical staff and that "
                "medical reporting is provided exclusively by teledermatology by a cooperating "
                "dermatologist."
            ),
            "content_pl": (
                "Rozumiem, że zdjęcia wykonywane są na miejscu przez personel medyczny, a opis "
                "lekarski następuje wyłącznie w trybie teledermatologicznym przez "
                "współpracującą dermatolożkę / współpracującego dermatologa."
            ),
        },
        {
            "code": "TELEDERM_EINWILLIGUNG_UEBERMITTLUNG",
            "version": 1,
            "display_order": -3,
            "title_de": "Teledermatologie – Übermittlung von Daten",
            "title_en": "Teledermatology – Transmission of data",
            "title_pl": "Teledermatologia – przekazanie danych",
            "content_de": (
                "Ich willige ein, dass die im Rahmen der Untersuchung erstellten Bildaufnahmen "
                "sowie die für die Befundung erforderlichen Gesundheitsdaten an den befundenden "
                "Arzt / die befundende Ärztin übermittelt und dort zum Zweck der ärztlichen "
                "Fernbefundung verarbeitet werden."
            ),
            "content_en": (
                "I consent to the examination images and the health data required for reporting "
                "being transmitted to the reporting physician and processed there for the purpose "
                "of remote medical reporting."
            ),
            "content_pl": (
                "Wyrażam zgodę na przekazanie lekarzowi lub lekarce opisującemu zdjęć wykonanych "
                "w trakcie badania oraz niezbędnych danych zdrowotnych oraz na ich przetwarzanie "
                "u niego/u niej w celu zdalnego opisu medycznego."
            ),
        },
        {
            "code": "TELEDERM_INFO_GRENZEN_FERNBEFUND",
            "version": 1,
            "display_order": -2,
            "title_de": "Teledermatologie – Grenzen der Fernbefundung",
            "title_en": "Teledermatology – Limits of remote reporting",
            "title_pl": "Teledermatologia – ograniczenia zdalnego opisu",
            "content_de": (
                "Ich wurde darüber informiert, dass die teledermatologische Befundung eine "
                "persönliche ärztliche Untersuchung nicht in jedem Fall ersetzen kann und bei "
                "medizinischer Notwendigkeit weitere diagnostische oder ärztliche Maßnahmen "
                "empfohlen werden können."
            ),
            "content_en": (
                "I have been informed that teledermatological reporting cannot replace an "
                "in-person medical examination in every case and that further diagnostic or "
                "medical measures may be recommended if medically necessary."
            ),
            "content_pl": (
                "Otrzymałem/am informację, że opis teledermatologiczny nie zastępuje w każdym "
                "przypadku osobistego badania lekarskiego oraz że w razie konieczności medycznej "
                "mogą zostać zalecone dalsze działania diagnostyczne lub lecznicze."
            ),
        },
        {
            "code": "TELEDERM_INFO_PRIVAT_GOAE",
            "version": 1,
            "display_order": -1,
            "title_de": "Teledermatologie – Privatleistung (GOÄ)",
            "title_en": "Teledermatology – Private service (GOÄ)",
            "title_pl": "Teledermatologia – usługa prywatna (GOÄ)",
            "content_de": (
                "Ich wurde darüber informiert, dass es sich bei der ärztlichen Befundung um "
                "eine privatärztliche Leistung handelt, die nach GOÄ abgerechnet wird."
            ),
            "content_en": (
                "I have been informed that the medical reporting is a private medical service "
                "billed in accordance with the GOÄ."
            ),
            "content_pl": (
                "Otrzymałem/am informację, że opis lekarski stanowi usługę prywatną lekarską "
                "rozliczaną zgodnie z GOÄ."
            ),
        },
    ]

    for row in consents:
        ConsentDefinition.objects.get_or_create(
            code=row["code"],
            version=row["version"],
            defaults={
                "title_de": row["title_de"],
                "title_en": row["title_en"],
                "title_pl": row["title_pl"],
                "content_de": row["content_de"],
                "content_en": row["content_en"],
                "content_pl": row["content_pl"],
                "is_required": True,
                "is_active": True,
                "display_order": row["display_order"],
                "effective_from": today,
            },
        )


def backward(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    codes = [
        "TELEDERM_INFO",
        "TELEDERM_VERSTANDEN_AUFNAHME",
        "TELEDERM_EINWILLIGUNG_UEBERMITTLUNG",
        "TELEDERM_INFO_GRENZEN_FERNBEFUND",
        "TELEDERM_INFO_PRIVAT_GOAE",
    ]
    ConsentDefinition.objects.filter(code__in=codes, version=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0022_intakedocumentversion_retention_anonymization"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
