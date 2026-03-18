# Seed queue for 17 March 2026 with 10 patients (DEMO site, room A1).
# Forward: get_or_create queue for 2026-03-17; ensure 10 queue entries.
# Reverse: no-op (data remains).
# Phone must match DB constraint: digits only, 7–20 chars (patient_phone_format).

from datetime import date, datetime, time as dt_time

from django.db import migrations
from django.utils import timezone

TARGET_DATE = date(2026, 3, 17)
TARGET_ENTRIES = 10
APPOINTMENT_HOUR = 9
APPOINTMENT_MINUTE_START = 0
SLOT_MINUTES = 20

SEED_PATIENTS = [
    {"doctolib_id": "DTL-2026-0051", "first_name": "Felix", "last_name": "Braun", "date_of_birth": "1988-02-14", "phone": "493076543301", "email": "felix.braun@example.com", "street": "Friedrichstraße 100", "postal_code": "10117", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0052", "first_name": "Magdalena", "last_name": "Nowak", "date_of_birth": "1993-07-08", "phone": "493076543302", "email": "magdalena.nowak@example.com", "street": "Alexanderplatz 5", "postal_code": "10178", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0053", "first_name": "Oliver", "last_name": "Schmidt", "date_of_birth": "1975-11-21", "phone": "493076543303", "email": "oliver.schmidt@example.com", "street": "Unter den Linden 77", "postal_code": "10117", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0054", "first_name": "Zofia", "last_name": "Wiśniewska", "date_of_birth": "1990-04-03", "phone": "493076543304", "email": "zofia.wisniewska@example.com", "street": "Karl-Marx-Allee 120", "postal_code": "10243", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0055", "first_name": "Max", "last_name": "Fischer", "date_of_birth": "1981-09-16", "phone": "493076543305", "email": "max.fischer@example.com", "street": "Kurfürstendamm 190", "postal_code": "10707", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0056", "first_name": "Natalia", "last_name": "Kowalczyk", "date_of_birth": "1996-01-29", "phone": "493076543306", "email": "natalia.kowalczyk@example.com", "street": "Schönhauser Allee 65", "postal_code": "10437", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0057", "first_name": "Leon", "last_name": "Weber", "date_of_birth": "1987-06-11", "phone": "493076543307", "email": "leon.weber@example.com", "street": "Potsdamer Platz 10", "postal_code": "10785", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0058", "first_name": "Amelia", "last_name": "Meyer", "date_of_birth": "1994-12-05", "phone": "493076543308", "email": "amelia.meyer@example.com", "street": "Torstraße 125", "postal_code": "10119", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0059", "first_name": "Jan", "last_name": "Zieliński", "date_of_birth": "1979-03-27", "phone": "493076543309", "email": "jan.zielinski@example.com", "street": "Genthiner Straße 38", "postal_code": "10785", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0060", "first_name": "Lena", "last_name": "Wagner", "date_of_birth": "1991-08-19", "phone": "493076543310", "email": "lena.wagner@example.com", "street": "Greifswalder Straße 88", "postal_code": "10409", "city": "Berlin"},
]


def _appointment_datetime(day, position_1based):
    minutes = APPOINTMENT_MINUTE_START + (position_1based - 1) * SLOT_MINUTES
    hour = APPOINTMENT_HOUR + minutes // 60
    minute = minutes % 60
    naive = datetime.combine(day, dt_time(hour, minute, 0, 0))
    return timezone.make_aware(naive) if timezone.is_naive(naive) else naive


def seed_queue_10_patients_2026_03_17(apps, schema_editor):
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
        code="DEMO",
        defaults={"name": "CogitoMedica Berlin", "is_active": True},
    )
    room, _ = ConsultingRoom.objects.get_or_create(
        clinic_site=site,
        code="A1",
        defaults={"name": "Gabinett 1", "is_active": True},
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
        ("reception", "0024_tabletdevice_clinic_site"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_queue_10_patients_2026_03_17, noop_reverse),
    ]
