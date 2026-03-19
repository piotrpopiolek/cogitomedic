# Seed queue for 19 March 2026 with 20 patients (DEMO site, room A1).
# Forward: get_or_create queue for 2026-03-19; ensure 20 queue entries.
# Reverse: no-op (data remains).
# Phone: digits only, 7–20 chars (patient_phone_format). Polish numbers: 48 + 9 digits.

from datetime import date, datetime, time as dt_time

from django.db import migrations
from django.utils import timezone

TARGET_DATE = date(2026, 3, 19)
TARGET_ENTRIES = 20
APPOINTMENT_HOUR = 9
APPOINTMENT_MINUTE_START = 0
SLOT_MINUTES = 20

SEED_PATIENTS = [
    {"doctolib_id": "DTL-2026-0081", "first_name": "Anna", "last_name": "Nowak", "date_of_birth": "1985-05-02", "phone": "791234567", "email": "anna.nowak@example.com", "street": "ul. Marszałkowska 10", "postal_code": "00-590", "city": "Warszawa"},
    {"doctolib_id": "DTL-2026-0082", "first_name": "Piotr", "last_name": "Kowalski", "date_of_birth": "1992-10-15", "phone": "602345678", "email": "piotr.kowalski@example.com", "street": "ul. Królowej Jadwigi 45", "postal_code": "30-209", "city": "Kraków"},
    {"doctolib_id": "DTL-2026-0083", "first_name": "Maria", "last_name": "Wiśniewska", "date_of_birth": "1988-01-28", "phone": "783456789", "email": "maria.wisniewska@example.com", "street": "ul. Piotrkowska 88", "postal_code": "90-001", "city": "Łódź"},
    {"doctolib_id": "DTL-2026-0084", "first_name": "Tomasz", "last_name": "Dąbrowski", "date_of_birth": "1977-07-11", "phone": "504567890", "email": "tomasz.dabrowski@example.com", "street": "ul. Świdnicka 22", "postal_code": "50-034", "city": "Wrocław"},
    {"doctolib_id": "DTL-2026-0085", "first_name": "Katarzyna", "last_name": "Lewandowska", "date_of_birth": "1995-12-04", "phone": "615678901", "email": "katarzyna.lewandowska@example.com", "street": "ul. Długa 5", "postal_code": "80-827", "city": "Gdańsk"},
    {"doctolib_id": "DTL-2026-0086", "first_name": "Michał", "last_name": "Wójcik", "date_of_birth": "1983-03-19", "phone": "726789012", "email": "michal.wojcik@example.com", "street": "ul. Główna 33", "postal_code": "61-729", "city": "Poznań"},
    {"doctolib_id": "DTL-2026-0087", "first_name": "Agnieszka", "last_name": "Kamińska", "date_of_birth": "1990-08-23", "phone": "837890123", "email": "agnieszka.kaminska@example.com", "street": "ul. 3 Maja 17", "postal_code": "40-096", "city": "Katowice"},
    {"doctolib_id": "DTL-2026-0088", "first_name": "Jakub", "last_name": "Kowalczyk", "date_of_birth": "1986-11-07", "phone": "948901234", "email": "jakub.kowalczyk@example.com", "street": "ul. Lubelska 52", "postal_code": "20-080", "city": "Lublin"},
    {"doctolib_id": "DTL-2026-0089", "first_name": "Magdalena", "last_name": "Zielińska", "date_of_birth": "1993-04-30", "phone": "550123456", "email": "magdalena.zielinska@example.com", "street": "ul. Grodzka 8", "postal_code": "31-044", "city": "Kraków"},
    {"doctolib_id": "DTL-2026-0090", "first_name": "Paweł", "last_name": "Szymański", "date_of_birth": "1981-09-12", "phone": "661234567", "email": "pawel.szymanski@example.com", "street": "ul. Floriańska 15", "postal_code": "31-019", "city": "Kraków"},
    {"doctolib_id": "DTL-2026-0091", "first_name": "Joanna", "last_name": "Woźniak", "date_of_birth": "1997-02-16", "phone": "772345678", "email": "joanna.wozniak@example.com", "street": "ul. Nowy Świat 42", "postal_code": "00-042", "city": "Warszawa"},
    {"doctolib_id": "DTL-2026-0092", "first_name": "Adam", "last_name": "Kozłowski", "date_of_birth": "1974-06-08", "phone": "883456789", "email": "adam.kozlowski@example.com", "street": "ul. Legionów 77", "postal_code": "90-508", "city": "Łódź"},
    {"doctolib_id": "DTL-2026-0093", "first_name": "Monika", "last_name": "Jankowska", "date_of_birth": "1989-11-25", "phone": "994567890", "email": "monika.jankowska@example.com", "street": "ul. Oławska 12", "postal_code": "50-123", "city": "Wrocław"},
    {"doctolib_id": "DTL-2026-0094", "first_name": "Marcin", "last_name": "Mazur", "date_of_birth": "1996-01-14", "phone": "505678901", "email": "marcin.mazur@example.com", "street": "ul. Długa 31", "postal_code": "80-827", "city": "Gdańsk"},
    {"doctolib_id": "DTL-2026-0095", "first_name": "Ewa", "last_name": "Kwiatkowska", "date_of_birth": "1982-07-03", "phone": "616789012", "email": "ewa.kwiatkowska@example.com", "street": "ul. Półwiejska 20", "postal_code": "61-888", "city": "Poznań"},
    {"doctolib_id": "DTL-2026-0096", "first_name": "Robert", "last_name": "Krawczyk", "date_of_birth": "1991-10-21", "phone": "727890123", "email": "robert.krawczyk@example.com", "street": "ul. Mariacka 7", "postal_code": "40-014", "city": "Katowice"},
    {"doctolib_id": "DTL-2026-0097", "first_name": "Barbara", "last_name": "Piotrowska", "date_of_birth": "1987-04-09", "phone": "838901234", "email": "barbara.piotrowska@example.com", "street": "ul. Krakowskie Przedmieście 1", "postal_code": "20-002", "city": "Lublin"},
    {"doctolib_id": "DTL-2026-0098", "first_name": "Grzegorz", "last_name": "Grabowski", "date_of_birth": "1979-08-17", "phone": "949012345", "email": "grzegorz.grabowski@example.com", "street": "ul. Chmielna 25", "postal_code": "00-020", "city": "Warszawa"},
    {"doctolib_id": "DTL-2026-0099", "first_name": "Aleksandra", "last_name": "Pawlak", "date_of_birth": "1994-12-28", "phone": "550123467", "email": "aleksandra.pawlak@example.com", "street": "ul. Senatorska 3", "postal_code": "00-075", "city": "Warszawa"},
    {"doctolib_id": "DTL-2026-0100", "first_name": "Łukasz", "last_name": "Michalski", "date_of_birth": "1980-05-06", "phone": "661234578", "email": "lukasz.michalski@example.com", "street": "ul. Stary Rynek 44", "postal_code": "61-772", "city": "Poznań"},
]


def _appointment_datetime(day, position_1based):
    minutes = APPOINTMENT_MINUTE_START + (position_1based - 1) * SLOT_MINUTES
    hour = APPOINTMENT_HOUR + minutes // 60
    minute = minutes % 60
    naive = datetime.combine(day, dt_time(hour, minute, 0, 0))
    return timezone.make_aware(naive) if timezone.is_naive(naive) else naive


def seed_queue_20_patients_2026_03_19(apps, schema_editor):
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
                "country_code": "PL",
            },
        )
        if not created:
            patient.street = data["street"]
            patient.postal_code = data["postal_code"]
            patient.city = data["city"]
            patient.country_code = "PL"
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
        ("reception", "0027_merge_20260317_0718"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_queue_20_patients_2026_03_19, noop_reverse),
    ]
