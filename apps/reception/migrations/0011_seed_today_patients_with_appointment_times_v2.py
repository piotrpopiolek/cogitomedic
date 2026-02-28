# Seed today's queue with realistic patient data and appointment times (v2).
# Forward: ensure queue for today exists; get/create 10 patients (DTL-2026-*),
#          add queue entries with appointment_time (20-min slots from 09:00).
# Reverse: no-op (data remains).

from datetime import datetime, time as dt_time

from django.db import migrations
from django.utils import timezone


SEED_PATIENTS = [
    {
        "doctolib_id": "DTL-2026-0001",
        "first_name": "Marta",
        "last_name": "Nowak",
        "date_of_birth": "1986-01-19",
        "phone": "+493076543201",
        "email": "marta.nowak@example.com",
        "street": "Invalidenstraße 44",
        "postal_code": "10115",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2026-0002",
        "first_name": "Piotr",
        "last_name": "Kowalski",
        "date_of_birth": "1979-04-03",
        "phone": "+493076543202",
        "email": "piotr.kowalski@example.com",
        "street": "Torstraße 78",
        "postal_code": "10119",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2026-0003",
        "first_name": "Katarzyna",
        "last_name": "Zielińska",
        "date_of_birth": "1991-08-27",
        "phone": "+493076543203",
        "email": "katarzyna.zielinska@example.com",
        "street": "Chausseestraße 12",
        "postal_code": "10115",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2026-0004",
        "first_name": "Andreas",
        "last_name": "Meyer",
        "date_of_birth": "1967-12-09",
        "phone": "+493076543204",
        "email": "andreas.meyer@example.com",
        "street": "Leipziger Straße 90",
        "postal_code": "10117",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2026-0005",
        "first_name": "Agnieszka",
        "last_name": "Wójcik",
        "date_of_birth": "1984-06-14",
        "phone": "+493076543205",
        "email": "agnieszka.wojcik@example.com",
        "street": "Schönhauser Allee 115",
        "postal_code": "10439",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2026-0006",
        "first_name": "Lukas",
        "last_name": "Krüger",
        "date_of_birth": "1993-11-01",
        "phone": "+493076543206",
        "email": "lukas.krueger@example.com",
        "street": "Greifswalder Straße 150",
        "postal_code": "10409",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2026-0007",
        "first_name": "Monika",
        "last_name": "Mazur",
        "date_of_birth": "1974-09-21",
        "phone": "+493076543207",
        "email": "monika.mazur@example.com",
        "street": "Pappelallee 35",
        "postal_code": "10437",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2026-0008",
        "first_name": "Sebastian",
        "last_name": "Neumann",
        "date_of_birth": "1988-02-06",
        "phone": "+493076543208",
        "email": "sebastian.neumann@example.com",
        "street": "Danziger Straße 62",
        "postal_code": "10435",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2026-0009",
        "first_name": "Ewa",
        "last_name": "Kaczmarek",
        "date_of_birth": "1996-05-10",
        "phone": "+493076543209",
        "email": "ewa.kaczmarek@example.com",
        "street": "Friedelstraße 21",
        "postal_code": "12047",
        "city": "Berlin",
    },
    {
        "doctolib_id": "DTL-2026-0010",
        "first_name": "Johannes",
        "last_name": "Wolf",
        "date_of_birth": "1981-03-28",
        "phone": "+493076543210",
        "email": "johannes.wolf@example.com",
        "street": "Karl-Marx-Straße 140",
        "postal_code": "12043",
        "city": "Berlin",
    },
]

APPOINTMENT_HOUR = 9
APPOINTMENT_MINUTE_START = 0
SLOT_MINUTES = 20


def _appointment_datetime(today, position_1based):
    minutes = APPOINTMENT_MINUTE_START + (position_1based - 1) * SLOT_MINUTES
    hour = APPOINTMENT_HOUR + minutes // 60
    minute = minutes % 60
    naive = datetime.combine(today, dt_time(hour, minute, 0, 0))
    return timezone.make_aware(naive) if timezone.is_naive(naive) else naive


def seed_today_queue_with_times_v2(apps, schema_editor):
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

    current_max_position = (
        QueueEntry.objects.filter(daily_queue=queue)
        .order_by("-position_no")
        .values_list("position_no", flat=True)
        .first()
        or 0
    )

    for data in SEED_PATIENTS:
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

        existing_entry = QueueEntry.objects.filter(daily_queue=queue, patient=patient).first()
        if existing_entry:
            continue

        current_max_position += 1
        appointment_dt = _appointment_datetime(today, current_max_position)
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
        ("reception", "0010_seed_today_patients_with_appointment_times"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_today_queue_with_times_v2, noop_reverse),
    ]
