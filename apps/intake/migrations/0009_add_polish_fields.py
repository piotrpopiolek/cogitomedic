# Add Polish (title_pl, content_pl, question_text_pl, option_text_pl) for locale pl.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0008_consent_definition_fill_title_en_content_en"),
    ]

    operations = [
        migrations.AddField(
            model_name="consentdefinition",
            name="title_pl",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="consentdefinition",
            name="content_pl",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="anamnesisquestiondefinition",
            name="question_text_pl",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="anamnesisoptiondefinition",
            name="option_text_pl",
            field=models.TextField(blank=True, default=""),
        ),
    ]
