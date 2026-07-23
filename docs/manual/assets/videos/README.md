# Filmy instruktażowe (WebM)

Nagrania ekranu generuje Playwright + te same dane demo co [zrzuty PNG](../screenshots/README.md): konta `screenshot_*`, fikcyjni pacjenci (RODO).

## Wymagania

- Działająca aplikacja i baza (`docker compose` → usługa `web`), zmienne jak przy zrzutach: `CAPTCHA_VERIFY_SKIP=1`, `SMSAPI_USE_MOCK=1`, itd.
- Obraz `manual-videos` / `screenshots` (Playwright + Chromium) **albo** lokalnie: `pip install -r requirements.txt` oraz `playwright install chromium`.

## Filmy per rola (01–05)

```bash
python manage.py runserver 127.0.0.1:8000
# drugi terminal:
python scripts/record_manual_videos.py --base-url http://127.0.0.1:8000 --role all
```

| Plik | Rola |
|------|------|
| `reception.webm` | [01-rejestracja.md](../../01-rejestracja.md) |
| `tablet.webm` | [02-tablet.md](../../02-tablet.md) |
| `doctor.webm` | [03-doktor.md](../../03-doktor.md) |
| `admin.webm` | [04-administrator.md](../../04-administrator.md) |
| `patient.webm` | [05-pacjent-wyniki.md](../../05-pacjent-wyniki.md) |

### Parametry

| Opcja | Znaczenie |
|-------|-----------|
| `--role reception` | Jedna rola zamiast `all` |
| `--slow-mo 300` | Wolniejsze akcje (ms) |
| `--video-width` / `--video-height` | Rozdzielczość (domyślnie 1280×720) |
| `--out-dir` | Inny katalog wyjściowy |

Docker:

```bash
docker compose --profile manual-videos run --rm manual-videos
```

## Scenariusze operacyjne (SC-001–SC-027)

Opisy: [scenariusze.md](../../scenariusze.md). Pliki w `scenariusze/` (poza SC-007).

### Widoczny kursor (symulacja użytkownika)

Playwright **nie nagrywa** systemowego kursora OS. Recorder scenariuszy
(`record_scenario_videos.py` oraz `record_import_troubleshooting_video.py`)
wstrzykuje żółty overlay DOM (`scripts/manual_demo/cursor_overlay.py`): śledzi
`mousemove` / kliknięcia, reinject po nawigacji i HTMX. Ruchy idą przez
`mouse.move(..., steps=28)` + krótkie pauzy przed/po kliknięciu. Włączane
automatycznie przy nagraniu — nie ma osobnej flagi CLI. Zalecane `--slow-mo 500`
(minimum ~400–500).

### Seed + nagranie (Windows / Docker)

```powershell
# Seed (w kontenerze web — wymaga PYTHONPATH)
docker compose exec -w /app -e PYTHONPATH=/app web `
  python scripts/manual_demo/seed_scenarios.py --all --write-ctx

# Nagranie (obraz Playwright)
docker compose --profile manual-videos run --rm --no-deps `
  -e PYTHONPATH=/app -e SCREENSHOT_SKIP_DJANGO=1 `
  manual-videos python scripts/record_scenario_videos.py `
  --all --base-url http://web:8000 --slow-mo 500
```

Pojedynczy scenariusz / priorytet:

```powershell
python scripts/record_scenario_videos.py --scenario sc-001 --slow-mo 500
python scripts/record_scenario_videos.py --priority high --slow-mo 500
```

Na hoście z `SCREENSHOT_SKIP_DJANGO=1` skrypt czyta JSON z `docs/manual/_build/scenario-ctx/`.

**SC-011 / SC-012 / SC-027:** mock HiDrive jest współdzielony z `web` przez
`docs/manual/_build/hidrive-mock-state.json` (volume `.:/app`). Nagranie ustawia
stan na starcie każdego scenariusza; ustaw też `HIDRIVE_INCOMING_PATH` jak w `.env`
web (domyślnie `/public/incoming`). Przykład:

```powershell
foreach ($s in 'sc-011','sc-012','sc-027') {
  docker compose exec -w /app -e PYTHONPATH=/app web `
    python scripts/manual_demo/seed_scenarios.py --scenario $s --write-ctx
}
docker compose --profile manual-videos run --rm --no-deps `
  -e PYTHONPATH=/app -e SCREENSHOT_SKIP_DJANGO=1 `
  -e HIDRIVE_INCOMING_PATH=/public/incoming `
  manual-videos python scripts/record_scenario_videos.py `
  --scenario sc-011 --scenario sc-012 --scenario sc-027 `
  --base-url http://web:8000 --slow-mo 500
```

### Lista filmów scenariuszy

| Plik | Scenariusz |
|------|------------|
| `scenariusze/sc-001-anulowany-wpis.webm` | SC-001 Anulowany wpis na liście lekarza |
| `scenariusze/sc-002-usuniety-szkic.webm` | SC-002 Usunięty szkic — status „—” |
| `scenariusze/sc-003-porzuc-rewizje.webm` | SC-003 Porzucenie rewizji |
| `scenariusze/sc-004-raport-ksiegowosci.webm` | SC-004 Raport tygodniowy księgowości |
| `scenariusze/sc-005-brak-pdf-hidrive.webm` | SC-005 Brak PDF z laboratorium |
| `scenariusze/sc-006-sms-outbox.webm` | SC-006 Powtórka SMS ze skrzynki wyjściowej |
| `reception/import-troubleshooting.webm` | SC-007 Brakujący pacjent po imporcie XLSX |
| `scenariusze/sc-008-portal-login.webm` | SC-008 Portal — błędny telefon / data urodzenia |
| `scenariusze/sc-009-wspolny-telefon.webm` | SC-009 Wspólny numer w rodzinie |
| `scenariusze/sc-010-otp-portal.webm` | SC-010 Brak kodu OTP do portalu |
| `scenariusze/sc-011-homonim-pdf.webm` | SC-011 Niejednoznaczna nazwa PDF |
| `scenariusze/sc-012-rejected-pdf.webm` | SC-012 Plik `rejected_` |
| `scenariusze/sc-013-outbox-pdf-hidrive.webm` | SC-013 Błąd PDF/HiDrive — Ponów |
| `scenariusze/sc-014-blokada-dokumentu.webm` | SC-014 Blokada edycji dokumentu |
| `scenariusze/sc-015-revoke-publikacji.webm` | SC-015 Cofnięcie publikacji |
| `scenariusze/sc-016-papier-po-tablecie.webm` | SC-016 Papier unieważniony po tablecie |
| `scenariusze/sc-017-paper-intake-t1.webm` | SC-017 Autoryzacja papierowa T1 |
| `scenariusze/sc-018-tablet-bez-placowki.webm` | SC-018 Tablet bez placówki |
| `scenariusze/sc-019-zla-ankieta.webm` | SC-019 Pomyłka pacjenta na tablecie |
| `scenariusze/sc-020-external-upload.webm` | SC-020 Zewnętrzne badanie (PDF) |
| `scenariusze/sc-021-brak-ankiety.webm` | SC-021 Brak ukończonej ankiety |
| `scenariusze/sc-022-pusta-lista-dokumentow.webm` | SC-022 Pusta lista w portalu |
| `scenariusze/sc-023-okno-60-dni.webm` | SC-023 Okno 60 dni dostępu |
| `scenariusze/sc-024-smsapi-saldo.webm` | SC-024 Awaria / saldo SMS |
| `scenariusze/sc-025-korekta-danych.webm` | SC-025 Korekta danych pacjenta |
| `scenariusze/sc-026-dead-letter.webm` | SC-026 Dead letter w skrzynce |
| `scenariusze/sc-027-baner-hidrive.webm` | SC-027 Baner awarii HiDrive |

Narracje (tekst lektora): pliki `scenariusze/*-narration.pl.md` obok filmów.

### HiDrive mock (SC-011 / SC-012 / SC-027)

Przy `HIDRIVE_USE_MOCK=1` adapter zapisuje stan do współdzielonego pliku JSON
(`docs/manual/_build/hidrive-mock-state.json`, gitignore), żeby proces `web` widział
listingi/`rejected_`/timeout z seeda i z recordera (osobny kontener Playwright).

- `settings.HIDRIVE_MOCK_STATE_PATH` — ścieżka (domyślnie włączona poza `prod`)
- Seed: `seed_mock_incoming(...)` / `seed_mock_hidrive_timeout()` w `scenario_helpers.py`
- Recorder na starcie SC-011/012/027 nadpisuje ten plik, potem pokazuje problem → poprawkę → reload dashboardu

Ścieżka listingu musi zgadzać się z `HIDRIVE_INCOMING_PATH` (u Was często `/public/incoming`).

### Mock PDF (Befund / portal / lab)

Seedy **nie** uruchamiają pełnego WeasyPrint + outbox workera. Zamiast tego
`force_publish(..., with_pdf=True)` (domyślnie) woła
`attach_demo_published_pdf()` w `scenario_helpers.py`:

- zapisuje **poprawny** minimalny PDF (kilka KB, `pypdf`) pod `MEDIA_ROOT/demo_befund/`
- ustawia `pdf_generation_status=COMPLETED`, checksum, opcjonalnie flagi HiDrive/SMS
  (żeby revoke i lista w portalu działały jak po pełnej dostawie)
- mock HiDrive dostaje te same bajty na ścieżce archiwum / `/incoming/` (SC-011/012)

Wyjątki: SC-013 (`with_pdf=False` — FAILED `GENERATE_PDF`), SC-006 (PDF bez
`sms_sent`), SC-026 (PDF bez pełnego delivery). SC-022: publikacja + revoke →
pusta lista w portalu.

Doctor **preview** (`/preview-pdf`) nadal generuje PDF na żywo (WeasyPrint);
mock MEDIA jest dla statusu COMPLETED, portalu i pobrania.

```powershell
# Seed PDF-heavy scenarios + nagranie
foreach ($s in 'sc-003','sc-011','sc-012','sc-015','sc-022') {
  docker compose exec -w /app -e PYTHONPATH=/app web `
    python scripts/manual_demo/seed_scenarios.py --scenario $s --write-ctx
}
docker compose --profile manual-videos run --rm --no-deps `
  -e PYTHONPATH=/app -e SCREENSHOT_SKIP_DJANGO=1 `
  -e HIDRIVE_INCOMING_PATH=/public/incoming `
  manual-videos python scripts/record_scenario_videos.py `
  --scenario sc-003 --scenario sc-011 --scenario sc-012 `
  --scenario sc-015 --scenario sc-022 `
  --base-url http://web:8000 --slow-mo 500
```

Film roli lekarz (podgląd PDF) przy przestarzałym obrazie Playwright:

```powershell
docker compose exec -w /app -e PYTHONPATH=/app web `
  python scripts/manual_demo/write_manual_video_ctx.py
docker compose --profile manual-videos run --rm --no-deps `
  -e PYTHONPATH=/app -e SCREENSHOT_SKIP_DJANGO=1 `
  manual-videos python scripts/record_manual_videos.py `
  --role doctor --base-url http://web:8000 --slow-mo 400
```

`minimal_demo_pdf_bytes()` ma wbudowany fallback PDF (bez `pypdf`), więc recorder
HiDrive działa nawet gdy obraz `Dockerfile.screenshots` jest nieaktualny.
Zalecane okresowe: `docker compose build screenshots manual-videos`.

### Film SC-007 (import)

```bash
python scripts/record_import_troubleshooting_video.py --base-url http://127.0.0.1:8000 --slow-mo 500
```

Na Windows (seed w Dockerze):

```powershell
docker compose exec -w /app -e PYTHONPATH=/app web python scripts/manual_demo/seed_import_troubleshooting.py
$env:SCREENSHOT_SKIP_DJANGO='1'
python scripts/record_import_troubleshooting_video.py --base-url http://127.0.0.1:8000 --slow-mo 500
```

## Uwagi

- Rozszerzenia `.webm` / `.mp4` są w `.gitignore` — generuj lokalnie, nie commituj binariów.
- Playwright nie generuje mowy; lektor / napisy to osobna warstwa.
- Portal pacjenta w filmach ról: krok OTP często używa wstępnie utworzonej sesji (cookie), jak przy zrzutach PNG.

### Konwersja do MP4 (opcjonalnie)

```bash
ffmpeg -i scenariusze/sc-001-anulowany-wpis.webm -c:v libx264 -crf 23 -pix_fmt yuv420p scenariusze/sc-001-anulowany-wpis.mp4
```
