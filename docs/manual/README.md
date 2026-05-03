# Instrukcje użytkowania portalu Cogitomedica

Dokumentacja dla personelu (Recepcja, Tablet, Lekarz, Manager, Administrator) oraz dla pacjenta (portal wyników).

## Jak otworzyć instrukcje, żeby widzieć zrzuty ekranu

Zrzuty są w katalogu `docs/manual/assets/screenshots/` i w Markdown są podlinkowane ścieżkami od **korzenia repozytorium** (np. `/docs/manual/assets/screenshots/reception-01-admin-login.png`). Dzięki temu podgląd w edytorze i widok na GitHubie znajdują pliki pod tym samym warunkiem: **otwarty folder roboczy to katalog główny projektu** (`cogitomedica`), a nie np. samo `docs/manual`.

1. W Cursorze lub VS Code wybierz **File → Open Folder** i wskaż folder **`cogitomedica`** (ten, w którym jest m.in. `manage.py`).
2. Otwórz plik z `docs/manual/`, np. `01-rejestracja.md`.
3. Włącz podgląd Markdown: **Ctrl+Shift+V** (podgląd w zakładce) albo **Ctrl+K**, potem **V** (podgląd obok edytora).
4. Jeśli nadal nie ma obrazków: sprawdź, czy pliki PNG są na dysku (`docs/manual/assets/screenshots/*.png`) — w razie potrzeby `git pull` albo ponowne wygenerowanie wg [assets/screenshots/README.md](/docs/manual/assets/screenshots/README.md).

**Podgląd na GitHubie:** po wypchnięciu zmian otwórz plik `.md` w repozytorium na stronie GitHuba — obrazy z ścieżką od roota repo powinny się wyświetlać.

### Eksport do PDF (wszystkie rozdziały 00–05)

Tak — można zbudować **jeden plik PDF** z plików `00-przeglad.md` … `05-pacjent-wyniki.md` (bez checklisty zrzutów).

1. Zainstaluj **[Pandoc](https://pandoc.org/installing.html)** oraz dystrybucję LaTeX z **`xelatex`** (np. [TeX Live](https://tug.org/texlive/) lub [MiKTeX](https://miktex.org/) — potrzebne do polskich znaków i osadzania obrazów).  
   **Windows (winget):** `winget install -e JohnMacFarlane.Pandoc` oraz `winget install -e MiKTeX.MiKTeX`. Po instalacji **otwórz nowy terminal** (lub zrestartuj Cursor), żeby zaktualizować `PATH` — inaczej `pandoc` / `xelatex` mogą być „niewidoczne”.
2. Z korzenia repozytorium uruchom:

   ```bash
   python scripts/build_manual_pdf.py
   ```

3. Plik wynikowy (domyślnie): `docs/manual/_build/Cogitomedica-Instrukcje.pdf` (katalog `_build/` jest w `.gitignore`).

Skrypt zamienia ścieżki obrazów z formy `/docs/manual/assets/...` na względne wobec korzenia projektu, żeby Pandoc poprawnie wstawił PNG.

**Inaczej (bez skryptu):** rozszerzenie VS Code/Cursor **„Markdown PDF”** — eksport plik po pliku; przy ścieżkach od roota repo otwórz folder **`cogitomedica`** jako workspace. **HTML → druk do PDF:** `pandoc docs/manual/01-rejestracja.md -o manual.html --resource-path=.` (z korzenia repo), potem otwórz `manual.html` w przeglądarce i drukuj do PDF.

| Dokument | Dla kogo |
|----------|----------|
| [00-przeglad.md](00-przeglad.md) | Wszyscy — słownik, proces dnia, odnośniki |
| [01-rejestracja.md](01-rejestracja.md) | Recepcja (`RECEPTION`) |
| [02-tablet.md](02-tablet.md) | Tablet poczekalni (`TABLET`; także recepcja/admin na `/tablet/`) |
| [03-doktor.md](03-doktor.md) | Lekarz w panelu medycznym (`DOCTOR`); `ADMIN` / `MANAGER` — pełen widok kolejki w HTML |
| [04-administrator.md](04-administrator.md) | Administrator systemu (`ADMIN`); w sekcji 11 również konto kierownicze (`Manager`); §3a — autoryzacja ścieżki papierowej (`/admin/paper-intake/`) |
| [05-pacjent-wyniki.md](05-pacjent-wyniki.md) | Pacjent — pobieranie dokumentacji po SMS |
| [screenshot-checklist.md](screenshot-checklist.md) | Lista plików PNG i odpowiadających im ekranów |

Zrzuty ekranu: katalog [assets/screenshots/](/docs/manual/assets/screenshots/README.md) — **komplet plików z checklisty** generuje się skryptem [`scripts/capture_manual_screenshots.py`](../../scripts/capture_manual_screenshots.py) (np. w Dockerze: `docker compose --profile screenshots run --rm screenshots`). Nazewnictwo: `rola-NN-opis.png`; dane demo (`screenshot_*`) są tylko do dokumentacji.

**Filmy WebM (instruktaż ekranu):** katalog [assets/videos/](/docs/manual/assets/videos/README.md) — skrypt [`scripts/record_manual_videos.py`](../../scripts/record_manual_videos.py); Docker: `docker compose --profile manual-videos run --rm manual-videos`. Pliki `.webm` nie są wersjonowane w git (`.gitignore`).

**Wersja treści:** 2026-04-25 (dopasuj datę przy aktualizacji UI).
