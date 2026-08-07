# Zrzuty ekranu do instrukcji

Komplet plików z [screenshot-checklist.md](../../screenshot-checklist.md) (ok. 46 PNG, w tym diagram przeglądu) powinien być w tym katalogu; odświeżenie: `docker compose --profile screenshots run --rm screenshots` (lub wyłącznie portal pacjenta: `docker compose --profile screenshots run --rm screenshots python scripts/capture_manual_screenshots.py --only=patient-portal --base-url http://web:8000`; albo wyłącznie zrzuty rozdz. 06: `SCREENSHOT_SKIP_DJANGO=1 python scripts/capture_manual_screenshots.py --only=reception-patient-personal-data --base-url …` po `seed_manual_demo` w docelowej bazie — zob. [06-zmiana-danych-pacjenta.md](../../06-zmiana-danych-pacjenta.md)). W rozdziałach instrukcji obrazy wstawiane są ścieżką od korzenia repozytorium, np. `/docs/manual/assets/screenshots/reception-01-admin-login.png` — dzięki temu podgląd Markdown w edytorze (Cursor/VS Code) poprawnie ładuje pliki PNG.

Ręczne zrzuty: umieść plik pod tą samą nazwą co w checklistie, z **danymi zanonimizowanymi**.

## Generowanie w Dockerze (Playwright)

Wymaga: `docker compose` oraz pliku `.env` (z `SECRET_KEY`, danymi DB zgodnymi z compose).

1. Uruchom aplikację (baza + web):

   ```bash
   docker compose up -d db web
   ```

2. Zbuduj obraz i wygeneruj PNG (jednorazowy kontener `screenshots`):

   ```bash
   docker compose build screenshots
   docker compose --profile screenshots run --rm screenshots
   ```

   W `.env` pole `ALLOWED_HOSTS` musi zawierać host `web` (jest w [`.env.example`](../../../.env.example)), żeby kontener `web` przyjmował żądania z Playwrighta po nazwie serwisu Docker.

Skrypt [`scripts/capture_manual_screenshots.py`](../../../scripts/capture_manual_screenshots.py) nasionkuje dane kont `screenshot_*` i zapisuje pliki w tym katalogu. Adres serwera w sieci Docker: `http://web:8000` (ustawiane w [`docker-compose.yml`](../../../docker-compose.yml)). Obraz z Chromium buduje [`Dockerfile.screenshots`](../../../Dockerfile.screenshots) (osobno od głównego [`Dockerfile`](../../../Dockerfile), żeby nie powiększać obrazu produkcyjnego `web`). Oczekiwanie na HTTP `web` jest wpisane w `docker-compose` (inline `sh`), żeby uniknąć problemów z końcami linii CRLF w plikach `.sh` na Windows.

## Zasady

1. **Anonimizacja:** fikcyjne dane testowe; nie używaj prawdziwych pacjentów.
2. **Spójność:** ta sama rozdzielczość dla paneli web (np. 1920×1080); tablet — orientacja landscape, typowa rozdzielczość urządzenia.
3. **Nazwy:** `rola-NN-opis-krotki.png` (np. `doctor-04-befund-form.png`).

### Mock PDF (Befund / portal)

Skrypt seeda (`scripts/manual_demo/seed.py` + `scenario_helpers.attach_demo_published_pdf`)
zapisuje **prawidłowe** minimalne PDF-y pod `MEDIA` i w mocku HiDrive
(`HIDRIVE_USE_MOCK=1`, stan w `docs/manual/_build/hidrive-mock-state.json`). Dzięki temu:

- lista lekarza pokazuje status PDF `COMPLETED` dla opublikowanych dem
- portal (`patient-03-documents.png`) ma wpis do pobrania
- bramka lab PDF / external-upload używa bajtów akceptowanych przez `PdfReader`

Podgląd w panelu lekarza (`preview-pdf`) jest generowany na żywo (WeasyPrint);
mock MEDIA nie zastępuje tego endpointu.

Jeśli plik jeszcze nie istnieje, w przeglądarce dokumentacji obraz się nie wyświetli — uzupełnij zrzuty na środowisku staging przed publikacją PDF/wiki.
