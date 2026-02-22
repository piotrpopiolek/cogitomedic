# Data migration: fill Polish (_pl) with translations of German consents, questions and options.

from django.db import migrations

# --- Consent definitions: (code, version, title_pl, content_pl) ---

CONSENT_VIDEODERMATOSKOPIE_TITLE_PL = "Zgoda na cyfrową wideodermatoskopię (IGeL)"
CONSENT_VIDEODERMATOSKOPIE_CONTENT_PL = """Ja, pacjent/ka, potwierdzam, że zostałem/am osobiście i wyczerpująco poinformowany/a przez pracownika CogitoMedica GmbH o planowanym badaniu metodą cyfrowej wideodermatoskopii. Otrzymałem/am informacje w zrozumiałej formie dotyczące:

1. Celu i korzyści badania

Cyfrowa wideodermatoskopia służy komputerowo wspomaganemu wczesnemu wykrywaniu raka skóry, w szczególności badaniu znamion barwnikowych (pieprzyków).

Metoda umożliwia dokumentację w wysokiej rozdzielczości oraz obiektywną kontrolę zmian skórnych w czasie, co zwiększa bezpieczeństwo w porównaniu z samym badaniem wzrokowym.

Główna korzyść to możliwość wykrycia nawet najmniejszych zmian w czasie i uniknięcia niepotrzebnych biopsji.

2. Przebiegu badania

Badanie jest nieinwazyjne i bezbolesne.

Za pomocą specjalnego dermatoskopu wykonywane i zapisywane są cyfrowe zdjęcia skóry.

Zazwyczaj odbywa się to w ramach badania całego ciała z następową szczegółową dokumentacją podejrzanych zmian.

Badanie wykorzystuje wyłącznie światło widzialne i nie wiąże się z narażeniem na promieniowanie.

3. Możliwych ryzyk i alternatyw

Wiem, że samo badanie nie wiąże się ze szczególnym ryzykiem.

Brak stuprocentowej pewności: mimo że wideodermatoskopia zwiększa precyzję diagnostyczną, żadna metoda nie jest w 100% pewna. Istnieje niewielkie pozostałe ryzyko przeoczenia złośliwej zmiany.

Ryzyko „nadrozpoznawalności”: jeśli zmiana zostanie uznana za podejrzaną, może to wiązać się z obciążeniem psychicznym. Istnieje ryzyko, że podejrzenie okaże się niepotwierdzone.

Konieczność biopsji: jednoznacznego, ostatecznego rozpoznania można dokonać tylko na podstawie badania histologicznego wycinka.

Zostałem/am poinformowany/a o alternatywie w postaci badania w kierunku raka skóry oferowanego przez ubezpieczenie zdrowotne.

Potwierdzenie i zgoda pacjenta

Niniejszym potwierdzam, że otrzymałem/am informacje i je zrozumiałem/am.

Miałem/am możliwość zadania wszystkich pytań.

Wyrażam zgodę na przeprowadzenie ww. cyfrowej wideodermatoskopii jako indywidualnej usługi medycznej (IGeL)."""

DS_INTRO_PL = """Administrator danych: CogitoMedica Deutschland GmbH, Mühlenstraße 8a, 14167 Berlin. Inspektor ochrony danych: Sebastian Lazniak (dsb@cogitomedica.de)

Cele przetwarzania: przeprowadzenie badania, opracowanie wyniku lekarskiego, obsługa wizyt i płatności, dokumentacja wymagana przepisami.

Przechowywanie/hosting: usługa w chmurze HiDrive STRATO AG (Berlin) i IONOS SE (Montabaur). Przetwarzanie wyłącznie na terenie Niemiec/UE.

Wynik i telemedycyna: udostępnienie wyniku z reguły w ciągu 24 godzin w chronionym portalu online za pomocą kodu odbioru.

Okres przechowywania: zdjęcia i wyniki są z reguły przechowywane przez 10 lat od zakończenia leczenia.

Zgody – proszę zaznaczyć:"""

CONSENT_PL = [
    (
        "VIDEODERMATOSKOPIE_IGEL",
        1,
        CONSENT_VIDEODERMATOSKOPIE_TITLE_PL,
        CONSENT_VIDEODERMATOSKOPIE_CONTENT_PL,
    ),
    (
        "ERKLAERUNG_PRIVATBEHANDLUNG_GOAE",
        1,
        "Oświadczenie – leczenie prywatne / GOÄ",
        """Oświadczenie

Jestem ubezpieczony/a w publicznej kasie chorych.

Na moje wyraźne życzenie korzystam z prywatnego leczenia.

Zostałem/am poinformowany/a, że żądana usługa (wideodermatoskopia z opisem) nie wchodzi w zakres świadczeń lekarza z umowy z kasą chorych i z reguły nie jest refundowana przez moją publiczną kasę chorych.

Rozliczenie odbywa się prywatnie według niemieckiej taryfy dla lekarzy (GOÄ).""",
    ),
    (
        "KOSTENINFORMATION_VIDEODERMATOSKOPIE",
        1,
        "Informacja o kosztach",
        """Informacja o kosztach

Zostałem/am poinformowany/a o kosztach.

Kwota w EUR: 129,00 €""",
    ),
    (
        "IGEL_INFOBLATT_ERHALTEN",
        1,
        "Potwierdzenie: ulotka informacyjna IGeL",
        "Otrzymałem/am ulotkę informacyjną IGeL.",
    ),
    (
        "EINWILLIGUNG_DATENSCHUTZ_UNTERSCHRIEBEN",
        1,
        "Potwierdzenie: zgoda i ochrona danych",
        "Otrzymałem/am i podpisałem/am zgodę medyczną oraz informację o ochronie danych.",
    ),
    (
        "DS_EINWILLIGUNG_GESUNDHEITSDATEN",
        1,
        "Ochrona danych – przetwarzanie danych zdrowotnych",
        DS_INTRO_PL + "\n\nWyrażam zgodę na przetwarzanie moich danych zdrowotnych.",
    ),
    (
        "DS_EINWILLIGUNG_HAUTBILDAUFNAHMEN",
        1,
        "Ochrona danych – zdjęcia skóry",
        "Wyrażam zgodę na wykonywanie, przechowywanie i przetwarzanie zdjęć skóry.",
    ),
    (
        "DS_EINWILLIGUNG_TELEMEDIZIN",
        1,
        "Ochrona danych – telemedyczna ocena",
        "Telemedyczna ocena przez dermatologów.",
    ),
    (
        "DS_EINWILLIGUNG_PORTAL_ABHOLCODE",
        1,
        "Ochrona danych – wynik w portalu",
        "Udostępnienie wyniku w formie elektronicznej (portal z kodem odbioru).",
    ),
    (
        "DS_EINWILLIGUNG_SMS",
        1,
        "Ochrona danych – powiadomienie SMS",
        "Powiadomienie o wyniku: SMS.",
    ),
    (
        "DS_EINWILLIGUNG_EMAIL_RECHNUNG",
        1,
        "Ochrona danych – faktury e-mail",
        "Wyrażam zgodę na otrzymywanie faktur i dokumentów e-mailem.",
    ),
]

# --- Anamnesis questions: (code, version, question_text_pl) ---

QUESTION_PL = [
    ("Q1_MALIGNANT_MELANOMA_HISTORY", 1, "Czy kiedykolwiek zdiagnozowano u Pana/Pani czerniaka złośliwego?"),
    ("Q2_WHITE_SKIN_CANCER_HISTORY", 1, "Czy kiedykolwiek stwierdzono u Pana/Pani raka skóry niebędącego czerniakiem (np. rak podstawnokomórkowy, kolczystokomórkowy) lub stan przedrakowy?"),
    ("Q3_FAMILY_MELANOMA", 1, "Czy u krewnych pierwszego stopnia (rodzice, rodzeństwo, dzieci) występuje czerniak złośliwy?"),
    ("Q4_NEW_SKIN_CHANGES_LOCATION", 1, "Czy ma Pan/Pani obecnie nowe zmiany skórne, które niepokoją? Jeśli tak: gdzie? (np. dolna część pleców, klatka piersiowa, brzuch – proszę podać w uwagach)"),
    ("Q5_EXISTING_CHANGES_NOTICED", 1, "Czy zauważył/a Pan/Pani zmiany w istniejących znamionach (wielkość, kolor, kształt, krwawienie, świąd)?"),
    ("Q6_CHILDHOOD_SUNBURNS", 1, "Czy w dzieciństwie/młodości miał/a Pan/Pani silne oparzenia słoneczne (np. z pęcherzami)?"),
    ("Q7_OCCUPATIONAL_SUN_EXPOSURE", 1, "Zwiększona ekspozycja na słońce w pracy?"),
    ("Q8_PRIVATE_SUN_EXPOSURE", 1, "Zwiększona ekspozycja na słońce w życiu prywatnym (podróże, sport na świeżym powietrzu)?"),
    ("Q9_SOLARIUM_USE", 1, "Regularne korzystanie z solarium?"),
    ("Q10_IMMUNOSUPPRESSIVE_MEDICATION", 1, "Leki immunosupresyjne?"),
    ("Q11_HYDROCHLOROTHIAZID", 1, "Hydrochlorotiazyd (HCT)?"),
]

# --- Anamnesis options: (question_code, option_code, option_text_pl) ---
# NO -> Nie, YES -> Tak, UNKNOWN -> Nie wiem

OPTION_PL = [
    ("Q1_MALIGNANT_MELANOMA_HISTORY", "NO", "Nie"),
    ("Q1_MALIGNANT_MELANOMA_HISTORY", "YES", "Tak"),
    ("Q2_WHITE_SKIN_CANCER_HISTORY", "NO", "Nie"),
    ("Q2_WHITE_SKIN_CANCER_HISTORY", "YES", "Tak"),
    ("Q3_FAMILY_MELANOMA", "NO", "Nie"),
    ("Q3_FAMILY_MELANOMA", "YES", "Tak"),
    ("Q3_FAMILY_MELANOMA", "UNKNOWN", "Nie wiem"),
    ("Q4_NEW_SKIN_CHANGES_LOCATION", "NO", "Nie"),
    ("Q4_NEW_SKIN_CHANGES_LOCATION", "YES", "Tak"),
    ("Q5_EXISTING_CHANGES_NOTICED", "NO", "Nie"),
    ("Q5_EXISTING_CHANGES_NOTICED", "YES", "Tak"),
    ("Q6_CHILDHOOD_SUNBURNS", "NO", "Nie"),
    ("Q6_CHILDHOOD_SUNBURNS", "YES", "Tak"),
    ("Q7_OCCUPATIONAL_SUN_EXPOSURE", "NO", "Nie"),
    ("Q7_OCCUPATIONAL_SUN_EXPOSURE", "YES", "Tak"),
    ("Q8_PRIVATE_SUN_EXPOSURE", "NO", "Nie"),
    ("Q8_PRIVATE_SUN_EXPOSURE", "YES", "Tak"),
    ("Q9_SOLARIUM_USE", "NO", "Nie"),
    ("Q9_SOLARIUM_USE", "YES", "Tak"),
    ("Q10_IMMUNOSUPPRESSIVE_MEDICATION", "NO", "Nie"),
    ("Q10_IMMUNOSUPPRESSIVE_MEDICATION", "YES", "Tak"),
    ("Q11_HYDROCHLOROTHIAZID", "NO", "Nie"),
    ("Q11_HYDROCHLOROTHIAZID", "YES", "Tak"),
    ("Q11_HYDROCHLOROTHIAZID", "UNKNOWN", "Nie wiem"),
]


def fill_polish_translations(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    AnamnesisQuestionDefinition = apps.get_model("intake", "AnamnesisQuestionDefinition")
    AnamnesisOptionDefinition = apps.get_model("intake", "AnamnesisOptionDefinition")

    for code, version, title_pl, content_pl in CONSENT_PL:
        ConsentDefinition.objects.filter(code=code, version=version).update(
            title_pl=title_pl, content_pl=content_pl
        )

    for code, version, question_text_pl in QUESTION_PL:
        AnamnesisQuestionDefinition.objects.filter(code=code, version=version).update(
            question_text_pl=question_text_pl
        )

    for question_code, option_code, option_text_pl in OPTION_PL:
        qs = AnamnesisQuestionDefinition.objects.filter(code=question_code, version=1)
        for q in qs:
            AnamnesisOptionDefinition.objects.filter(question=q, code=option_code).update(
                option_text_pl=option_text_pl
            )


def clear_polish(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    AnamnesisQuestionDefinition = apps.get_model("intake", "AnamnesisQuestionDefinition")
    AnamnesisOptionDefinition = apps.get_model("intake", "AnamnesisOptionDefinition")

    ConsentDefinition.objects.all().update(title_pl="", content_pl="")
    AnamnesisQuestionDefinition.objects.all().update(question_text_pl="")
    AnamnesisOptionDefinition.objects.all().update(option_text_pl="")


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0009_add_polish_fields"),
    ]

    operations = [
        migrations.RunPython(fill_polish_translations, clear_polish),
    ]
