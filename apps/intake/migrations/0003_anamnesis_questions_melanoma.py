# Migracja danych: pytania anamnestyczne dla pacjenta (Anamnese – Melanom/Hautkrebs).
# Typy: wszystkie SINGLE_CHOICE (jedna odpowiedź z listy); pytanie 4 ma dodatkowo pole tekstowe (wo?).

from django.db import migrations
from django.utils import timezone


# (code, question_text_de, question_text_en, options: list of (code, text_de, text_en))
QUESTIONS = [
    (
        "Q1_MALIGNANT_MELANOMA_HISTORY",
        "Wurde bei Ihnen jemals ein malignes Melanom (schwarzer Hautkrebs) diagnostiziert?",
        "Have you ever been diagnosed with malignant melanoma (black skin cancer)?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes")],
    ),
    (
        "Q2_WHITE_SKIN_CANCER_HISTORY",
        "Wurde bei Ihnen jemals weißer Hautkrebs (z. B. Basalzellkarzinom, Plattenepithelkarzinom) oder eine Vorstufe davon festgestellt?",
        "Have you ever been diagnosed with non-melanoma skin cancer (e.g. BCC, SCC) or a precursor?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes")],
    ),
    (
        "Q3_FAMILY_MELANOMA",
        "Ist bei Verwandten ersten Grades (Eltern, Geschwister, Kinder) ein malignes Melanom bekannt?",
        "Do any first-degree relatives (parents, siblings, children) have malignant melanoma?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes"), ("UNKNOWN", "Weiß nicht", "Unknown")],
    ),
    (
        "Q4_NEW_SKIN_CHANGES_LOCATION",
        "Haben Sie aktuell neue Hautveränderungen, die Sie beunruhigen? Falls ja: wo? (z. B. Unterer Rücken, BWS, Bauch, andere Stelle – bitte im Feld Anmerkungen angeben)",
        "Do you currently have new skin changes that concern you? If yes: where? (e.g. lower back, thoracic spine, abdomen, other – please specify in notes)",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes")],
    ),
    (
        "Q5_EXISTING_CHANGES_NOTICED",
        "Haben Sie Veränderungen bereits bestehender Hautveränderungen bemerkt (Größe, Farbe, Form, Blutung, Juckreiz)?",
        "Have you noticed changes in existing skin lesions (size, colour, shape, bleeding, itching)?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes")],
    ),
    (
        "Q6_CHILDHOOD_SUNBURNS",
        "Hatten Sie in Kindheit/Jugend schwere Sonnenbrände (z. B. mit Blasenbildung)?",
        "Did you have severe sunburns in childhood/adolescence (e.g. with blistering)?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes")],
    ),
    (
        "Q7_OCCUPATIONAL_SUN_EXPOSURE",
        "Erhöhte Sonnenexposition im Beruf?",
        "Increased occupational sun exposure?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes")],
    ),
    (
        "Q8_PRIVATE_SUN_EXPOSURE",
        "Erhöhte Sonnenexposition privat (Reisen, Outdoor-Sport)?",
        "Increased private sun exposure (travel, outdoor sports)?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes")],
    ),
    (
        "Q9_SOLARIUM_USE",
        "Regelmäßige Solarium-Nutzung?",
        "Regular use of tanning beds?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes")],
    ),
    (
        "Q10_IMMUNOSUPPRESSIVE_MEDICATION",
        "Immundepressive Medikamente?",
        "Immunosuppressive medication?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes")],
    ),
    (
        "Q11_HYDROCHLOROTHIAZID",
        "Hydrochlorothiazid (HCT)?",
        "Hydrochlorothiazide (HCT)?",
        [("NO", "Nein", "No"), ("YES", "Ja", "Yes"), ("UNKNOWN", "Weiß nicht", "Unknown")],
    ),
]


def add_questions(apps, schema_editor):
    AnamnesisQuestionDefinition = apps.get_model("intake", "AnamnesisQuestionDefinition")
    AnamnesisOptionDefinition = apps.get_model("intake", "AnamnesisOptionDefinition")
    today = timezone.now().date()

    for order, (code, text_de, text_en, options) in enumerate(QUESTIONS, start=1):
        q, created = AnamnesisQuestionDefinition.objects.get_or_create(
            code=code,
            version=1,
            defaults={
                "question_text_de": text_de,
                "question_text_en": text_en,
                "answer_type": "SINGLE_CHOICE",
                "is_required": True,
                "display_order": order,
                "is_active": True,
                "effective_from": today,
            },
        )
        if not created:
            continue
        for opt_order, (opt_code, opt_de, opt_en) in enumerate(options, start=1):
            AnamnesisOptionDefinition.objects.create(
                question=q,
                code=opt_code,
                option_text_de=opt_de,
                option_text_en=opt_en,
                display_order=opt_order,
                is_active=True,
            )


def remove_questions(apps, schema_editor):
    AnamnesisQuestionDefinition = apps.get_model("intake", "AnamnesisQuestionDefinition")
    codes = [q[0] for q in QUESTIONS]
    AnamnesisQuestionDefinition.objects.filter(code__in=codes, version=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(add_questions, remove_questions),
    ]
