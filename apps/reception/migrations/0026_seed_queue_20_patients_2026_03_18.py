# Seed queue for 18 March 2026 with 20 patients (DEMO site, room A1).
# Forward: get_or_create queue for 2026-03-18; ensure 20 queue entries.
# Reverse: no-op (data remains).
# Phone must match DB constraint: digits only, 7–20 chars (patient_phone_format).

from datetime import date, datetime, time as dt_time

from django.db import migrations
from django.utils import timezone

TARGET_DATE = date(2026, 3, 18)
TARGET_ENTRIES = 20
APPOINTMENT_HOUR = 9
APPOINTMENT_MINUTE_START = 0
SLOT_MINUTES = 20

SEED_PATIENTS = [
    {"doctolib_id": "DTL-2026-0061", "first_name": "Hanna", "last_name": "Kowal", "date_of_birth": "1985-05-02", "phone": "493076543311", "email": "hanna.kowal@example.com", "street": "Chausseestraße 45", "postal_code": "10115", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0062", "first_name": "Philipp", "last_name": "Schulze", "date_of_birth": "1992-10-15", "phone": "493076543312", "email": "philipp.schulze@example.com", "street": "Linienstraße 120", "postal_code": "10115", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0063", "first_name": "Karolina", "last_name": "Piotrowska", "date_of_birth": "1988-01-28", "phone": "493076543313", "email": "karolina.piotrowska@example.com", "street": "Alte Schönhauser 22", "postal_code": "10119", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0064", "first_name": "Tim", "last_name": "Hoffmann", "date_of_birth": "1977-07-11", "phone": "493076543314", "email": "tim.hoffmann@example.com", "street": "Mulackstraße 8", "postal_code": "10119", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0065", "first_name": "Julia", "last_name": "Kaczmarek", "date_of_birth": "1995-12-04", "phone": "493076543315", "email": "julia.kaczmarek@example.com", "street": "Danziger Straße 55", "postal_code": "10435", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0066", "first_name": "Simon", "last_name": "Koch", "date_of_birth": "1983-03-19", "phone": "493076543316", "email": "simon.koch@example.com", "street": "Pappelallee 77", "postal_code": "10437", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0067", "first_name": "Martyna", "last_name": "Duda", "date_of_birth": "1990-08-23", "phone": "493076543317", "email": "martyna.duda@example.com", "street": "Stargarder Straße 60", "postal_code": "10437", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0068", "first_name": "Jonas", "last_name": "Richter", "date_of_birth": "1986-11-07", "phone": "493076543318", "email": "jonas.richter@example.com", "street": "Rykestraße 18", "postal_code": "10405", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0069", "first_name": "Weronika", "last_name": "Górka", "date_of_birth": "1993-04-30", "phone": "493076543319", "email": "weronika.gorka@example.com", "street": "Kollwitzplatz 5", "postal_code": "10435", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0070", "first_name": "Finn", "last_name": "Klein", "date_of_birth": "1981-09-12", "phone": "493076543320", "email": "finn.klein@example.com", "street": "Kastanienallee 85", "postal_code": "10435", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0071", "first_name": "Oliwia", "last_name": "Sikora", "date_of_birth": "1997-02-16", "phone": "493076543321", "email": "oliwia.sikora@example.com", "street": "Hufelandstraße 12", "postal_code": "10407", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0072", "first_name": "Erik", "last_name": "Wolf", "date_of_birth": "1974-06-08", "phone": "493076543322", "email": "erik.wolf@example.com", "street": "Dimitroffstraße 40", "postal_code": "10407", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0073", "first_name": "Maja", "last_name": "Czerwińska", "date_of_birth": "1989-11-25", "phone": "493076543323", "email": "maja.czerwinska@example.com", "street": "Warschauer Straße 70", "postal_code": "10243", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0074", "first_name": "Lukas", "last_name": "Schröder", "date_of_birth": "1996-01-14", "phone": "493076543324", "email": "lukas.schroeder@example.com", "street": "Revaler Straße 55", "postal_code": "10245", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0075", "first_name": "Natalia", "last_name": "Rutkowska", "date_of_birth": "1982-07-03", "phone": "493076543325", "email": "natalia.rutkowska@example.com", "street": "Boxhagener Straße 32", "postal_code": "10245", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0076", "first_name": "Noah", "last_name": "Neumann", "date_of_birth": "1991-10-21", "phone": "493076543326", "email": "noah.neumann@example.com", "street": "Simon-Dach-Straße 22", "postal_code": "10245", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0077", "first_name": "Zuzanna", "last_name": "Michalak", "date_of_birth": "1987-04-09", "phone": "493076543327", "email": "zuzanna.michalak@example.com", "street": "Grünberger Straße 88", "postal_code": "10245", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0078", "first_name": "Ben", "last_name": "Schwarz", "date_of_birth": "1979-08-17", "phone": "493076543328", "email": "ben.schwarz@example.com", "street": "Gärtnerstraße 15", "postal_code": "10245", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0079", "first_name": "Aleksandra", "last_name": "Pawlak", "date_of_birth": "1994-12-28", "phone": "493076543329", "email": "aleksandra.pawlak@example.com", "street": "Mainzer Straße 7", "postal_code": "10245", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0080", "first_name": "Paul", "last_name": "Zimmermann", "date_of_birth": "1980-05-06", "phone": "493076543330", "email": "paul.zimmermann@example.com", "street": "Sonnenallee 120", "postal_code": "12045", "city": "Berlin"},
]


def _appointment_datetime(day, position_1based):
    minutes = APPOINTMENT_MINUTE_START + (position_1based - 1) * SLOT_MINUTES
    hour = APPOINTMENT_HOUR + minutes // 60
    minute = minutes % 60
    naive = datetime.combine(day, dt_time(hour, minute, 0, 0))
    return timezone.make_aware(naive) if timezone.is_naive(naive) else naive


def seed_queue_20_patients_2026_03_18(apps, schema_editor):
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
        ("reception", "0025_seed_queue_10_patients_2026_03_17"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_queue_20_patients_2026_03_18, noop_reverse),
    ]
