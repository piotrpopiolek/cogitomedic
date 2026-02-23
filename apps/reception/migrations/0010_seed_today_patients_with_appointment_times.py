# Seed today's queue with realistic patient data and appointment times.
# Forward: ensure queue for today exists; get/create 10 patients with full data (address);
#          get/create queue entries with appointment_time (9:00–12:00, 20-min slots).
# Reverse: no-op (data remains).

from datetime import datetime, time as dt_time

from django.db import migrations
from django.utils import timezone


# Realistic patients: German names, Berlin-area addresses, Doctolib-style IDs
SEED_PATIENTS = [
    {
        "doctolib_id": "DTL-2024-0001",
        "first_name": "Anna",
        "last_name": "Müller",
        "date_of_birth": "1975-03-12",
        "phone": "+493012345601",
        "email": "anna.mueller@example.com",
        "street": "Friedrichstraße 123",
        "postal_code": "10117",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2024-0002",
        "first_name": "Thomas",
        "last_name": "Schmidt",
        "date_of_birth": "1982-07-08",
        "phone": "+493012345602",
        "email": "thomas.schmidt@example.com",
        "street": "Unter den Linden 45",
        "postal_code": "10117",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2024-0003",
        "first_name": "Julia",
        "last_name": "Fischer",
        "date_of_birth": "1990-11-22",
        "phone": "+493012345603",
        "email": "julia.fischer@example.com",
        "street": "Alexanderplatz 7",
        "postal_code": "10178",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2024-0004",
        "first_name": "Michael",
        "last_name": "Weber",
        "date_of_birth": "1968-01-15",
        "phone": "+493012345604",
        "email": "michael.weber@example.com",
        "street": "Kurfürstendamm 189",
        "postal_code": "10707",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2024-0005",
        "first_name": "Sarah",
        "last_name": "Wagner",
        "date_of_birth": "1988-05-30",
        "phone": "+493012345605",
        "email": "sarah.wagner@example.com",
        "street": "Prenzlauer Allee 23",
        "postal_code": "10405",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2024-0006",
        "first_name": "Daniel",
        "last_name": "Becker",
        "date_of_birth": "1972-09-04",
        "phone": "+493012345606",
        "email": "daniel.becker@example.com",
        "street": "Warschauer Str. 56",
        "postal_code": "10243",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2024-0007",
        "first_name": "Laura",
        "last_name": "Hoffmann",
        "date_of_birth": "1995-12-18",
        "phone": "+493012345607",
        "email": "laura.hoffmann@example.com",
        "street": "Schönhauser Allee 88",
        "postal_code": "10439",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2024-0008",
        "first_name": "Stefan",
        "last_name": "Koch",
        "date_of_birth": "1980-06-25",
        "phone": "+493012345608",
        "email": "stefan.koch@example.com",
        "street": "Karl-Marx-Allee 112",
        "postal_code": "10243",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2024-0009",
        "first_name": "Christine",
        "last_name": "Richter",
        "date_of_birth": "1965-02-11",
        "phone": "+493012345609",
        "email": "christine.richter@example.com",
        "street": "Frankfurter Allee 34",
        "postal_code": "10247",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2024-0010",
        "first_name": "Martin",
        "last_name": "Klein",
        "date_of_birth": "1992-10-07",
        "phone": "+493012345610",
        "email": "martin.klein@example.com",
        "street": "Oranienburger Str. 67",
        "postal_code": "10117",
        "city": "Berlin",
    },
]

# Appointment times: 20-minute slots from 09:00 to 12:00 (10 slots)
APPOINTMENT_HOUR = 9
APPOINTMENT_MINUTE_START = 0
SLOT_MINUTES = 20


def _appointment_datetime(today, position_1based):
    """Return timezone-aware datetime for today at slot position (1-based)."""
    minutes = APPOINTMENT_MINUTE_START + (position_1based - 1) * SLOT_MINUTES
    hour = APPOINTMENT_HOUR + minutes // 60
    minute = minutes % 60
    naive = datetime.combine(today, dt_time(hour, minute, 0, 0))
    return timezone.make_aware(naive) if timezone.is_naive(naive) else naive


def seed_today_queue_with_times(apps, schema_editor):
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

    site, _ = ClinicSite.objects.get_or_create(
        code="DEMO",
        defaults={"name": "CogitoMedica Berlin", "is_active": True},
    )
    room, _ = ConsultingRoom.objects.get_or_create(
        clinic_site=site,
        code="A1",
        defaults={"name": "Gabinett 1", "is_active": True},
    )
    queue, _ = DailyQueue.objects.get_or_create(
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

    for i, data in enumerate(SEED_PATIENTS, start=1):
        dob = datetime.strptime(data["date_of_birth"], "%Y-%m-%d").date()
        patient, created = Patient.objects.get_or_create(
            doctolib_patient_id=data["doctolib_id"],
            defaults={
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "date_of_birth": dob,
                "phone": data["phone"],
                "email": data["email"],
                "is_active": True,
                "country_code": "DE",
            },
        )
        if not created:
            patient.street = data["street"]
            patient.postal_code = data["postal_code"]
            patient.city = data["city"]
            patient.country_code = "DE"
            patient.save(update_fields=["street", "postal_code", "city", "country_code", "updated_at"])

        appointment_dt = _appointment_datetime(today, i)
        entry, entry_created = QueueEntry.objects.get_or_create(
            daily_queue=queue,
            position_no=i,
            defaults={
                "patient": patient,
                "entry_status": "WAITING",
                "created_by_user_id": creator.id,
                "appointment_time": appointment_dt,
            },
        )
        if not entry_created:
            entry.appointment_time = appointment_dt
            entry.save(update_fields=["appointment_time", "updated_at"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0009_replace_demo_with_realistic_seed_data"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_today_queue_with_times, noop_reverse),
    ]
