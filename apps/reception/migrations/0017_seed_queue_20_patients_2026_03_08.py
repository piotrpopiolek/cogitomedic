# Seed queue for 8 March 2026 with 20 patients. Uses same patient set as 0012.
# Forward: get_or_create queue for 2026-03-08; ensure 20 queue entries.
# Reverse: no-op (data remains).

from datetime import date, datetime, time as dt_time

from django.db import migrations
from django.utils import timezone

TARGET_DATE = date(2026, 3, 8)
TARGET_ENTRIES = 20
APPOINTMENT_HOUR = 9
APPOINTMENT_MINUTE_START = 0
SLOT_MINUTES = 20

SEED_PATIENTS = [
    {"doctolib_id": "DTL-2026-0021", "first_name": "Helena", "last_name": "Schulz", "date_of_birth": "1987-04-15", "phone": "+493076543221", "email": "helena.schulz@example.com", "street": "Brunnenstraße 88", "postal_code": "10115", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0022", "first_name": "Tomasz", "last_name": "Lewandowski", "date_of_birth": "1978-11-03", "phone": "+493076543222", "email": "tomasz.lewandowski@example.com", "street": "Rosa-Luxemburg-Straße 30", "postal_code": "10178", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0023", "first_name": "Nina", "last_name": "Bauer", "date_of_birth": "1994-06-22", "phone": "+493076543223", "email": "nina.bauer@example.com", "street": "Prenzlauer Allee 176", "postal_code": "10409", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0024", "first_name": "Jakub", "last_name": "Kamiński", "date_of_birth": "1985-09-11", "phone": "+493076543224", "email": "jakub.kaminski@example.com", "street": "Warschauer Straße 45", "postal_code": "10243", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0025", "first_name": "Sophie", "last_name": "Hartmann", "date_of_birth": "1991-02-28", "phone": "+493076543225", "email": "sophie.hartmann@example.com", "street": "Bergmannstraße 102", "postal_code": "10961", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0026", "first_name": "Michał", "last_name": "Dąbrowski", "date_of_birth": "1982-12-07", "phone": "+493076543226", "email": "michal.dabrowski@example.com", "street": "Sonnenallee 65", "postal_code": "12045", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0027", "first_name": "Lisa", "last_name": "Lange", "date_of_birth": "1989-07-19", "phone": "+493076543227", "email": "lisa.lange@example.com", "street": "Oderberger Straße 12", "postal_code": "10435", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0028", "first_name": "Krzysztof", "last_name": "Szymański", "date_of_birth": "1976-03-25", "phone": "+493076543228", "email": "krzysztof.szymanski@example.com", "street": "Frankfurter Allee 200", "postal_code": "10365", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0029", "first_name": "Emma", "last_name": "Krause", "date_of_birth": "1997-10-08", "phone": "+493076543229", "email": "emma.krause@example.com", "street": "Boxhagener Straße 18", "postal_code": "10245", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0030", "first_name": "Paweł", "last_name": "Wozniak", "date_of_birth": "1983-01-14", "phone": "+493076543230", "email": "pawel.wozniak@example.com", "street": "Revaler Straße 99", "postal_code": "10245", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0031", "first_name": "Lea", "last_name": "Schmitt", "date_of_birth": "1990-05-30", "phone": "+493076543231", "email": "lea.schmitt@example.com", "street": "Grolmanstraße 44", "postal_code": "10623", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0032", "first_name": "Marcin", "last_name": "Kowalczyk", "date_of_birth": "1979-08-21", "phone": "+493076543232", "email": "marcin.kowalczyk@example.com", "street": "Kottbusser Damm 72", "postal_code": "10967", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0033", "first_name": "Hannah", "last_name": "Fuchs", "date_of_birth": "1995-11-12", "phone": "+493076543233", "email": "hannah.fuchs@example.com", "street": "Graefestraße 88", "postal_code": "10967", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0034", "first_name": "Łukasz", "last_name": "Jankowski", "date_of_birth": "1986-04-05", "phone": "+493076543234", "email": "lukasz.jankowski@example.com", "street": "Hermannplatz 5", "postal_code": "10967", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0035", "first_name": "Clara", "last_name": "Vogel", "date_of_birth": "1992-09-17", "phone": "+493076543235", "email": "clara.vogel@example.com", "street": "Maybachufer 48", "postal_code": "12047", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0036", "first_name": "Bartosz", "last_name": "Mazur", "date_of_birth": "1981-06-29", "phone": "+493076543236", "email": "bartosz.mazur@example.com", "street": "Weichselstraße 22", "postal_code": "12045", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0037", "first_name": "Marie", "last_name": "Schröder", "date_of_birth": "1988-12-01", "phone": "+493076543237", "email": "marie.schroeder@example.com", "street": "Flughafenstraße 50", "postal_code": "12053", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0038", "first_name": "Szymon", "last_name": "Kwiatkowski", "date_of_birth": "1974-02-18", "phone": "+493076543238", "email": "szymon.kwiatkowski@example.com", "street": "Tempelhofer Damm 120", "postal_code": "12099", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0039", "first_name": "Lena", "last_name": "Berger", "date_of_birth": "1993-07-24", "phone": "+493076543239", "email": "lena.berger@example.com", "street": "Hauptstraße 155", "postal_code": "10827", "city": "Berlin"},
    {"doctolib_id": "DTL-2026-0040", "first_name": "Adam", "last_name": "Krawczyk", "date_of_birth": "1980-10-09", "phone": "+493076543240", "email": "adam.krawczyk@example.com", "street": "Akazienstraße 33", "postal_code": "10823", "city": "Berlin"},
]


def _appointment_datetime(day, position_1based):
    minutes = APPOINTMENT_MINUTE_START + (position_1based - 1) * SLOT_MINUTES
    hour = APPOINTMENT_HOUR + minutes // 60
    minute = minutes % 60
    naive = datetime.combine(day, dt_time(hour, minute, 0, 0))
    return timezone.make_aware(naive) if timezone.is_naive(naive) else naive


def seed_queue_20_patients_2026_03_08(apps, schema_editor):
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
        ("reception", "0016_alter_clinicsite_options_and_more"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_queue_20_patients_2026_03_08, noop_reverse),
    ]
