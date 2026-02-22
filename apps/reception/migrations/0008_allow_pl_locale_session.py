# Allow pl/pl-PL in PatientFormSession.form_locale (session_locale_format).

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0007_merge_0005_0006_demo_queue"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="patientformsession",
            name="session_locale_format",
        ),
        migrations.AddConstraint(
            model_name="patientformsession",
            constraint=models.CheckConstraint(
                condition=Q(form_locale__regex=r"^(de|en|pl)(-[A-Z]{2})?$"),
                name="session_locale_format",
            ),
        ),
    ]
