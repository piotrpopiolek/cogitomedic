# Generated manually: dodaje kolejkę na dzisiejszy dzień i 10 pacjentów (wpisy w kolejce).

from django.db import migrations
from django.utils import timezone


def add_demo_queue_and_patients(apps, schema_editor):
    Patient = apps.get_model("reception", "Patient")
    DailyQueue = apps.get_model("reception", "DailyQueue")
    QueueEntry = apps.get_model("reception", "QueueEntry")
    ClinicSite = apps.get_model("reception", "ClinicSite")
    ConsultingRoom = apps.get_model("reception", "ConsultingRoom")
    StaffUser = apps.get_model("users", "StaffUser")

    today = timezone.now().date()

    # Użytkownik do created_by (pierwszy staff lub pierwszego użytkownika)
    creator = StaffUser.objects.order_by("date_joined").first()
    if not creator:
        return  # brak użytkowników – pomijamy

    # Placówka i gabinet (get_or_create)
    site, _ = ClinicSite.objects.get_or_create(
        code="DEMO",
        defaults={"name": "Klinika demo", "is_active": True},
    )
    room, _ = ConsultingRoom.objects.get_or_create(
        clinic_site=site,
        code="A1",
        defaults={"name": "Gabinet A1", "is_active": True},
    )

    # Kolejka na dziś (get_or_create – nie duplikować przy ponownym uruchomieniu)
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
        # Kolejka już istnieje – nie dodajemy ponownie pacjentów
        return

    # 10 pacjentów + wpisy w kolejce
    for i in range(1, 11):
        patient, _ = Patient.objects.get_or_create(
            doctolib_patient_id=f"DEMO-PAT-{i:02d}",
            defaults={
                "first_name": f"Pacjent",
                "last_name": f"Demo{i}",
                "date_of_birth": "1980-01-01",
                "phone": f"+490000000{i:02d}",
                "email": f"demo.patient{i}@example.com",
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


def remove_demo_data(apps, schema_editor):
    """Odwracanie: usuń kolejkę demo na dziś i wpisy (pacjentów zostawiamy)."""
    DailyQueue = apps.get_model("reception", "DailyQueue")
    ClinicSite = apps.get_model("reception", "ClinicSite")

    today = timezone.now().date()
    try:
        site = ClinicSite.objects.get(code="DEMO")
    except ClinicSite.DoesNotExist:
        return
    DailyQueue.objects.filter(
        queue_date=today,
        clinic_site=site,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0004_tabletdevice_android_id_only"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_demo_queue_and_patients, remove_demo_data),
    ]
