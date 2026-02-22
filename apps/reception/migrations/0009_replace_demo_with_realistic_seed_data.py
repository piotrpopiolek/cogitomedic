# Replace demo data (Pacjent Demo1, Klinika demo) with realistic seed data.
# Forward: remove MedicalDocument (and versions/outbox) for DEMO queue entries, then DEMO queue/entries and DEMO-PAT-* patients; update clinic name; add queue + realistic patients.
# Reverse: remove new queue/entries and DTL-2024-* patients; restore clinic name "Klinika demo".

from datetime import datetime as dt

from django.db import migrations
from django.utils import timezone

# Realistic seed patients (German names, Doctolib-style IDs for reverse cleanup)
SEED_PATIENTS = [
    {"doctolib_id": "DTL-2024-0001", "first_name": "Anna", "last_name": "Müller", "date_of_birth": "1975-03-12", "phone": "+493012345601", "email": "anna.mueller@example.com"},
    {"doctolib_id": "DTL-2024-0002", "first_name": "Thomas", "last_name": "Schmidt", "date_of_birth": "1982-07-08", "phone": "+493012345602", "email": "thomas.schmidt@example.com"},
    {"doctolib_id": "DTL-2024-0003", "first_name": "Julia", "last_name": "Fischer", "date_of_birth": "1990-11-22", "phone": "+493012345603", "email": "julia.fischer@example.com"},
    {"doctolib_id": "DTL-2024-0004", "first_name": "Michael", "last_name": "Weber", "date_of_birth": "1968-01-15", "phone": "+493012345604", "email": "michael.weber@example.com"},
    {"doctolib_id": "DTL-2024-0005", "first_name": "Sarah", "last_name": "Wagner", "date_of_birth": "1988-05-30", "phone": "+493012345605", "email": "sarah.wagner@example.com"},
    {"doctolib_id": "DTL-2024-0006", "first_name": "Daniel", "last_name": "Becker", "date_of_birth": "1972-09-04", "phone": "+493012345606", "email": "daniel.becker@example.com"},
    {"doctolib_id": "DTL-2024-0007", "first_name": "Laura", "last_name": "Hoffmann", "date_of_birth": "1995-12-18", "phone": "+493012345607", "email": "laura.hoffmann@example.com"},
    {"doctolib_id": "DTL-2024-0008", "first_name": "Stefan", "last_name": "Koch", "date_of_birth": "1980-06-25", "phone": "+493012345608", "email": "stefan.koch@example.com"},
    {"doctolib_id": "DTL-2024-0009", "first_name": "Christine", "last_name": "Richter", "date_of_birth": "1965-02-11", "phone": "+493012345609", "email": "christine.richter@example.com"},
    {"doctolib_id": "DTL-2024-0010", "first_name": "Martin", "last_name": "Klein", "date_of_birth": "1992-10-07", "phone": "+493012345610", "email": "martin.klein@example.com"},
]

SEED_DOCTOLIB_IDS = [p["doctolib_id"] for p in SEED_PATIENTS]


def remove_demo_and_add_seed(apps, schema_editor):
    Patient = apps.get_model("reception", "Patient")
    DailyQueue = apps.get_model("reception", "DailyQueue")
    QueueEntry = apps.get_model("reception", "QueueEntry")
    ClinicSite = apps.get_model("reception", "ClinicSite")
    ConsultingRoom = apps.get_model("reception", "ConsultingRoom")
    StaffUser = apps.get_model("users", "StaffUser")

    today = timezone.now().date()
    creator = StaffUser.objects.order_by("date_joined").first()
    if not creator:
        return

    # 1) Remove demo queue (CASCADE deletes QueueEntry)
    try:
        demo_site = ClinicSite.objects.get(code="DEMO")
    except ClinicSite.DoesNotExist:
        demo_site = None

    if demo_site:
        # 1a) Delete MedicalDocument (and versions, outbox) that reference DEMO queue entries, so DailyQueue can be deleted (RESTRICT)
        queue_entry_ids = list(
            QueueEntry.objects.filter(daily_queue__clinic_site=demo_site).values_list("id", flat=True)
        )
        if queue_entry_ids:
            MedicalDocument = apps.get_model("medical", "MedicalDocument")
            MedicalDocumentVersion = apps.get_model("medical", "MedicalDocumentVersion")
            OutboxEvent = apps.get_model("outbox", "OutboxEvent")
            doc_ids = list(
                MedicalDocument.objects.filter(queue_entry_id__in=queue_entry_ids).values_list(
                    "id", flat=True
                )
            )
            if doc_ids:
                version_ids = list(
                    MedicalDocumentVersion.objects.filter(
                        medical_document_id__in=doc_ids
                    ).values_list("id", flat=True)
                )
                OutboxEvent.objects.filter(medical_document_version_id__in=version_ids).delete()
                MedicalDocumentVersion.objects.filter(medical_document_id__in=doc_ids).delete()
                MedicalDocument.objects.filter(queue_entry_id__in=queue_entry_ids).delete()

        # 1b) Remove demo queue (CASCADE deletes QueueEntry, then intake forms etc.)
        DailyQueue.objects.filter(clinic_site=demo_site).delete()
        # 2) Remove demo patients
        Patient.objects.filter(doctolib_patient_id__startswith="DEMO-PAT-").delete()
        # 3) Realistic clinic name
        demo_site.name = "CogitoMedica Berlin"
        demo_site.save(update_fields=["name"])
        room = ConsultingRoom.objects.filter(clinic_site=demo_site, code="A1").first()
        if room:
            room.name = "Gabinett 1"
            room.save(update_fields=["name"])

    # 4) Get or create queue for today (same site DEMO / room A1)
    site, _ = ClinicSite.objects.get_or_create(
        code="DEMO",
        defaults={"name": "CogitoMedica Berlin", "is_active": True},
    )
    room, _ = ConsultingRoom.objects.get_or_create(
        clinic_site=site,
        code="A1",
        defaults={"name": "Gabinett 1", "is_active": True},
    )
    queue, created = DailyQueue.objects.get_or_create(
        queue_date=today,
        clinic_site=site,
        consulting_room=room,
        shift_code="FULL_DAY",
        defaults={
            "source": "MANUAL",
            "status": "OPEN",
            "created_by_user_id": creator.id,
        },
    )
    if not created:
        return

    # 5) Create seed patients and queue entries
    for i, data in enumerate(SEED_PATIENTS, start=1):
        dob = dt.strptime(data["date_of_birth"], "%Y-%m-%d").date()
        patient, _ = Patient.objects.get_or_create(
            doctolib_patient_id=data["doctolib_id"],
            defaults={
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "date_of_birth": dob,
                "phone": data["phone"],
                "email": data["email"],
                "is_active": True,
            },
        )
        QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            position_no=i,
            entry_status="WAITING",
            created_by_user_id=creator.id,
        )


def reverse_to_demo(apps, schema_editor):
    Patient = apps.get_model("reception", "Patient")
    DailyQueue = apps.get_model("reception", "DailyQueue")
    ClinicSite = apps.get_model("reception", "ClinicSite")
    ConsultingRoom = apps.get_model("reception", "ConsultingRoom")

    today = timezone.now().date()
    try:
        site = ClinicSite.objects.get(code="DEMO")
    except ClinicSite.DoesNotExist:
        return
    DailyQueue.objects.filter(clinic_site=site, queue_date=today).delete()
    Patient.objects.filter(doctolib_patient_id__in=SEED_DOCTOLIB_IDS).delete()
    site.name = "Klinika demo"
    site.save(update_fields=["name"])
    room = ConsultingRoom.objects.filter(clinic_site=site, code="A1").first()
    if room:
        room.name = "Gabinet A1"
        room.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0008_allow_pl_locale_session"),
        ("users", "0001_initial"),
        ("medical", "0002_initial"),
        ("outbox", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(remove_demo_and_add_seed, reverse_to_demo),
    ]
