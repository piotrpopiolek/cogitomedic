# Filmy instruktażowe (WebM)

Nagrania ekranu generuje skrypt [`scripts/record_manual_videos.py`](../../../../scripts/record_manual_videos.py) (Playwright + te same dane demo co [zrzuty PNG](../screenshots/README.md): konta `screenshot_*`, fikcyjni pacjenci).

## Wymagania

- Działająca aplikacja i baza (migrate), zmienne jak przy zrzutach: `CAPTCHA_VERIFY_SKIP=1` itd.
- `pip install -r requirements.txt` (Playwright jest w projekcie) oraz `playwright install chromium`.

## Lokalnie (z korzenia repozytorium)

```bash
python manage.py runserver 127.0.0.1:8000
# drugi terminal:
python scripts/record_manual_videos.py --base-url http://127.0.0.1:8000 --role all
```

Pliki trafiają do tego katalogu, np. `reception/reception.webm`, `tablet/tablet.webm`. Rozszerzenie `.webm` jest w `.gitignore` (duże pliki).

### Parametry przydatne w pracy

| Opcja | Znaczenie |
|-------|-----------|
| `--role reception` | Jedna rola zamiast `all` |
| `--slow-mo 300` | Wolniejsze akcje (ms) |
| `--video-width` / `--video-height` | Rozdzielczość desktop/pacjent (domyślnie 1280×720) |
| `--tablet-width` / `--tablet-height` | Widok tabletu (domyślnie 900×1200) |
| `--out-dir` | Inny katalog wyjściowy |

## Docker

```bash
docker compose --profile manual-videos run --rm manual-videos
```

Wyniki są na volume `./docs/manual/assets/videos` (host).

## Konwersja do MP4 (opcjonalnie)

Jeśli masz ffmpeg:

```bash
ffmpeg -i reception/reception.webm -c:v libx264 -crf 23 -c:a aac reception.mp4
```

## Treść vs dokumentacja

| Plik | Rola |
|------|------|
| `reception.webm` | [01-rejestracja.md](../../01-rejestracja.md) |
| `tablet.webm` | [02-tablet.md](../../02-tablet.md) (skrócony flow formularza) |
| `doctor.webm` | [03-doktor.md](../../03-doktor.md) |
| `admin.webm` | [04-administrator.md](../../04-administrator.md) |
| `patient.webm` | [05-pacjent-wyniki.md](../../05-pacjent-wyniki.md) |
| `reception/import-troubleshooting.webm` | Zgłoszenie klienta: po imporcie XLSX widać tylko jednego pacjenta — weryfikacja i ręczne dopisanie do kolejki. Narracja: [import-troubleshooting-narration.pl.md](reception/import-troubleshooting-narration.pl.md) |

### Film: brakujący pacjent po imporcie

```bash
python manage.py runserver 127.0.0.1:8000
# drugi terminal:
python scripts/record_import_troubleshooting_video.py --base-url http://127.0.0.1:8000
```

Opcjonalnie MP4: `ffmpeg -i reception/import-troubleshooting.webm -c:v libx264 -crf 23 -pix_fmt yuv420p reception/import-troubleshooting.mp4`

Na Windows (seed w Dockerze, nagranie na hoście):

```bash
docker compose exec web python scripts/manual_demo/seed_import_troubleshooting.py
set SCREENSHOT_SKIP_DJANGO=1
python scripts/record_import_troubleshooting_video.py --base-url http://127.0.0.1:8000
```

**Pacjent:** scenariusz używa wstępnie utworzonej sesji (cookie), żeby pokazać ekrany `/otp/` i `/documents/` bez mocka SMS — to nie jest pełny „request OTP z formularza”. Lektor / napisy wyjaśniają krok z kodem SMS.

**Lektor:** Playwright nie generuje mowy; narracja to osobna warstwa (nagranie, TTS lub napisy w edytorze wideo).
