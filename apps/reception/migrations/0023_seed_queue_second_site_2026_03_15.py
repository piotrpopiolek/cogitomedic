# Seed second clinic site (München) and queue for 15 March 2026 with 10 patients.
# Forward: get_or_create site MUC + room B1; get_or_create queue for 2026-03-15; ensure 10 queue entries.
# Reverse: no-op (data remains).

from datetime import date, datetime, time as dt_time

from django.db import migrations
from django.utils import timezone

TARGET_DATE = date(2026, 3, 15)
TARGET_ENTRIES = 10
APPOINTMENT_HOUR = 10
APPOINTMENT_MINUTE_START = 0
SLOT_MINUTES = 25

SITE_CODE = "MUC"
SITE_NAME = "CogitoMedica München"
ROOM_CODE = "B1"
ROOM_NAME = "Gabinett 2"

# Phone must match DB constraint: digits only, 7–20 chars (patient_phone_format).
SEED_PATIENTS = [
    {"doctolib_id": "DTL-2026-0041", "first_name": "Anna", "last_name": "Müller", "date_of_birth": "1984-05-12", "phone": "498912345601", "email": "anna.mueller@example.com", "street": "Leopoldstraße 50", "postal_code": "80802", "city": "München"},
    {"doctolib_id": "DTL-2026-0042", "first_name": "Stefan", "last_name": "Weber", "date_of_birth": "1979-08-23", "phone": "498912345602", "email": "stefan.weber@example.com", "street": "Maximilianstraße 12", "postal_code": "80539", "city": "München"},
    {"doctolib_id": "DTL-2026-0043", "first_name": "Julia", "last_name": "Fischer", "date_of_birth": "1992-01-07", "phone": "498912345603", "email": "julia.fischer@example.com", "street": "Sendlinger Straße 88", "postal_code": "80331", "city": "München"},
    {"doctolib_id": "DTL-2026-0044", "first_name": "Michael", "last_name": "Becker", "date_of_birth": "1986-11-30", "phone": "498912345604", "email": "michael.becker@example.com", "street": "Prinzregentenstraße 22", "postal_code": "80538", "city": "München"},
    {"doctolib_id": "DTL-2026-0045", "first_name": "Laura", "last_name": "Hoffmann", "date_of_birth": "1995-03-18", "phone": "498912345605", "email": "laura.hoffmann@example.com", "street": "Brienner Straße 5", "postal_code": "80333", "city": "München"},
    {"doctolib_id": "DTL-2026-0046", "first_name": "Thomas", "last_name": "Koch", "date_of_birth": "1972-07-04", "phone": "498912345606", "email": "thomas.koch@example.com", "street": "Residenzstraße 1", "postal_code": "80333", "city": "München"},
    {"doctolib_id": "DTL-2026-0047", "first_name": "Sarah", "last_name": "Richter", "date_of_birth": "1988-09-14", "phone": "498912345607", "email": "sarah.richter@example.com", "street": "Odeonsplatz 1", "postal_code": "80539", "city": "München"},
    {"doctolib_id": "DTL-2026-0048", "first_name": "Daniel", "last_name": "Klein", "date_of_birth": "1991-12-22", "phone": "498912345608", "email": "daniel.klein@example.com", "street": "Kaufingerstraße 15", "postal_code": "80331", "city": "München"},
    {"doctolib_id": "DTL-2026-0049", "first_name": "Christina", "last_name": "Wolf", "date_of_birth": "1982-04-09", "phone": "498912345609", "email": "christina.wolf@example.com", "street": "Tal 12", "postal_code": "80331", "city": "München"},
    {"doctolib_id": "DTL-2026-0050", "first_name": "Andreas", "last_name": "Schröder", "date_of_birth": "1976-06-27", "phone": "498912345610", "email": "andreas.schroeder@example.com", "street": "Rosenheimer Straße 30", "postal_code": "81669", "city": "München"},
]


def _appointment_datetime(day, position_1based):
    minutes = APPOINTMENT_MINUTE_START + (position_1based - 1) * SLOT_MINUTES
    hour = APPOINTMENT_HOUR + minutes // 60
    minute = minutes % 60
    naive = datetime.combine(day, dt_time(hour, minute, 0, 0))
    return timezone.make_aware(naive) if timezone.is_naive(naive) else naive


def seed_queue_second_site_2026_03_15(apps, schema_editor):
    Patient = apps.get_model("reception", "Patient")
    DailyQueue = apps.get_model("reception", "DailyQueue")
    QueueEntry = apps.get_model("reception", "QueueEntry")
    ClinicSite = apps.get_model("reception", "ClinicSite")
    ConsultingRoom = apps.get_model("reception", "ConsultingRoom")
    StaffUser = apps.get_model("users", "StaffUser")

    creator = StaffUser.objects.order_by("date_joined").first()
    if not creator:
        return

    site, _ = ClinicSite.objects.get_or_create(
        code=SITE_CODE,
        defaults={"name": SITE_NAME, "is_active": True},
    )
    room, _ = ConsultingRoom.objects.get_or_create(
        clinic_site=site,
        code=ROOM_CODE,
        defaults={"name": ROOM_NAME, "is_active": True},
    )
    queue, _ = DailyQueue.objects.get_or_create(
        queue_date=TARGET_DATE,
        clinic_site=site,
        consulting_room=room,
        shift_code="FULL_DAY",
        defaults={
            "source": "MANUAL",
            "status": "OPEN",
            "created_by_user_id": creator.id,
        },
    )

    current_count = QueueEntry.objects.filter(daily_queue=queue).count()
    if current_count >= TARGET_ENTRIES:
        return

    need = TARGET_ENTRIES - current_count
    current_max_position = (
        QueueEntry.objects.filter(daily_queue=queue)
        .order_by("-position_no")
        .values_list("position_no", flat=True)
        .first()
        or 0
    )

    for data in SEED_PATIENTS[:need]:
        dob = datetime.strptime(data["date_of_birth"], "%Y-%m-%d").date()
        patient, created = Patient.objects.get_or_create(
            doctolib_patient_id=data["doctolib_id"],
            defaults={
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "date_of_birth": dob,
                "phone": data["phone"],
                "email": data["email"],
                "street": data["street"],
                "postal_code": data["postal_code"],
                "city": data["city"],
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

        if QueueEntry.objects.filter(daily_queue=queue, patient=patient).exists():
            continue

        current_max_position += 1
        appointment_dt = _appointment_datetime(TARGET_DATE, current_max_position)
        QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            position_no=current_max_position,
            entry_status="WAITING",
            created_by_user_id=creator.id,
            appointment_time=appointment_dt,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0022_seed_queue_15_patients_2026_03_15"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_queue_second_site_2026_03_15, noop_reverse),
    ]
