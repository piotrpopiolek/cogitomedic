# Data migration: fill title_en and content_en with English translations of existing German consents.

from django.db import migrations

# (code, version, title_en, content_en)
CONSENT_EN = [
    (
        "VIDEODERMATOSKOPIE_IGEL",
        1,
        "Consent for digital videodermatoscopy (IGeL)",
        """I, the patient, confirm that I have been personally and fully informed by the staff of CogitoMedica GmbH about the planned procedure of digital videodermatoscopy. I have been informed about the following points in plain language:

1. Purpose and benefits of the examination

Digital videodermatoscopy serves computer-assisted skin cancer early detection, in particular the examination of pigmented lesions (moles).

The procedure enables high-resolution documentation and objective follow-up of skin changes, which increases safety compared to visual examination alone.

The main benefit is the ability to detect even the smallest changes over time and to avoid unnecessary biopsies.

2. Course of the examination

The procedure is non-invasive and painless.

Digital images of the skin are taken and stored using a special dermatoscope.

This is usually done as part of a full-body examination with subsequent detailed documentation of suspicious skin areas.

The examination uses only visible light and does not involve any radiation exposure.

3. Possible risks and alternatives

I am aware that the examination itself is not associated with any special risks.

No hundred percent reliability: Although videodermatoscopy increases diagnostic precision, no examination method is 100% reliable. There is a small residual risk that a malignant change may be missed.

Risk of "overdiagnosis": If a skin change is classified as suspicious, this may cause psychological stress. There is a risk that the suspicion may turn out to be harmless.

Need for biopsy: A clear, definitive finding can only be obtained by histological examination of a tissue sample.

I have been informed about the alternative of the skin cancer screening examination offered by my statutory health insurance (GKV).

Patient confirmation and consent

I hereby confirm that I have received the information and understood it.

I had the opportunity to ask all my questions.

I expressly wish to undergo the above-mentioned digital videodermatoscopy as an individual health service (IGeL).""",
    ),
    (
        "ERKLAERUNG_PRIVATBEHANDLUNG_GOAE",
        1,
        "Declaration – private medical treatment / GOÄ",
        """Declaration

I am covered by statutory health insurance.

At my express request I am receiving private medical treatment.

I have been informed that the requested service (videodermatoscopy with report) is not part of the statutory healthcare package and will generally not be reimbursed by my statutory health insurance.

Billing will be carried out privately in accordance with the German Medical Fee Schedule (GOÄ).""",
    ),
    (
        "KOSTENINFORMATION_VIDEODERMATOSKOPIE",
        1,
        "Cost information",
        """Cost information

I have been informed about the costs.

Amount in EUR: €129.00""",
    ),
    (
        "IGEL_INFOBLATT_ERHALTEN",
        1,
        "Confirmation: IGeL information sheet",
        "I have received the IGeL information sheet.",
    ),
    (
        "EINWILLIGUNG_DATENSCHUTZ_UNTERSCHRIEBEN",
        1,
        "Confirmation: Consent and data protection",
        "I have received and signed the medical consent and the data protection information.",
    ),
]

DS_INTRO_EN = """Controller: CogitoMedica Deutschland GmbH, Mühlenstraße 8a, 14167 Berlin. Data protection officer: Mr Sebastian Lazniak (dsb@cogitomedica.de)

Purposes of processing: Performance of the examination, medical reporting, appointment and payment processing, statutory documentation.

Storage/hosting: HiDrive cloud service by STRATO AG (Berlin) and IONOS SE (Montabaur). Processing takes place exclusively in Germany/EU.

Result & telemedicine: The result is generally provided within 24 hours in the secure online portal via collection code.

Retention period: Images and reports are generally retained for 10 years after completion of treatment.

Consents – please tick:"""

# Data protection consents (code, version, title_en, content_en)
CONSENT_EN.extend([
    (
        "DS_EINWILLIGUNG_GESUNDHEITSDATEN",
        1,
        "Data protection – Processing of health data",
        DS_INTRO_EN + "\n\nI expressly consent to the processing of my health data.",
    ),
    (
        "DS_EINWILLIGUNG_HAUTBILDAUFNAHMEN",
        1,
        "Data protection – Skin image recordings",
        "I consent to the creation, storage and processing of skin image recordings.",
    ),
    (
        "DS_EINWILLIGUNG_TELEMEDIZIN",
        1,
        "Data protection – Telemedical assessment",
        "Telemedical assessment by dermatologists.",
    ),
    (
        "DS_EINWILLIGUNG_PORTAL_ABHOLCODE",
        1,
        "Data protection – Result in portal",
        "Electronic provision of the result (portal with collection code).",
    ),
    (
        "DS_EINWILLIGUNG_SMS",
        1,
        "Data protection – Notification by SMS",
        "Notification of the result: SMS.",
    ),
    (
        "DS_EINWILLIGUNG_EMAIL_RECHNUNG",
        1,
        "Data protection – Invoices by email",
        "I agree to receive invoices and documents by email.",
    ),
])


def fill_english(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    for code, version, title_en, content_en in CONSENT_EN:
        ConsentDefinition.objects.filter(code=code, version=version).update(
            title_en=title_en,
            content_en=content_en,
        )


def noop_reverse(apps, schema_editor):
    # Optional: clear title_en/content_en; leave as no-op to keep EN data
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0007_consent_definition_title_en_content_en"),
    ]

    operations = [
        migrations.RunPython(fill_english, noop_reverse),
    ]
