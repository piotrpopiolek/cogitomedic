---
name: Instrukcje portalu role
overview: "Plan tworzenia obszernych instrukcji użytkowania (zrzuty ekranu + opisy krok po kroku) dla ról: Rejestracja, Tablet, Doktor, Administrator oraz osobno dla pacjenta (portal wyników), oparty na PRD, README i faktycznych ścieżkach URL w repozytorium."
todos:
  - id: inventory-screens
    content: Spisać checklistę wszystkich ekranów i ścieżek (admin/reception, tablet, doctor, ergebnisse) na podstawie stagingu
    status: completed
  - id: write-00-glossary
    content: "Napisać 00-przeglad.md: słownik, proces dnia, odnośniki do rozdziałów"
    status: completed
  - id: write-01-reception
    content: "Rozdział Rejestracja: kolejki, import, dashboard, intake PDF"
    status: completed
  - id: write-02-tablet
    content: "Rozdział Tablet: urządzenie, kolejka, pacjent, formularz, submit"
    status: completed
  - id: write-03-doctor
    content: "Rozdział Doktor: lista, Befund, publikacja, edycja, szablony"
    status: completed
  - id: write-04-admin
    content: "Rozdział Admin: użytkownicy, kliniki, tłumaczenia, import XLSX, operacje"
    status: completed
  - id: write-05-patient
    content: "Rozdział Pacjent: portal wyników (login, OTP, dokumenty)"
    status: completed
  - id: screenshots-pass
    content: Wykonać zrzuty, nazwać pliki, wstawić do MD z opisami
    status: completed
  - id: review-gap
    content: Przegląd pod kątem luk i niejasności (druga iteracja tekstu)
    status: completed
isProject: false
---

# Plan: instrukcje portalu Cogitomedica (role + pacjent)

## Źródła wiedzy (już przejrzane)

- Wymagania i procesy: `[.ai/prd.md](.ai/prd.md)` (Poczekalnia, tablet bez tokenów, panel lekarza Befund, outbox PDF→HiDrive→SMS, portal wyników 4-etapowy).
- Routing UI: `[cogitomedica/urls.py](cogitomedica/urls.py)` — m.in. `/admin/`, `/doctor/`, `/tablet/`, root `/` = portal pacjenta (`ergebnisse`).
- Role w modelu: `RECEPTION`, `DOCTOR`, `ADMIN`, `TABLET` (m.in. `[apps/users/migrations/0004_alter_staffuser_role.py](apps/users/migrations/0004_alter_staffuser_role.py)`); uprawnienia grup: `[apps/users/migrations/0006_create_roles_groups.py](apps/users/migrations/0006_create_roles_groups.py)`.
- Dokumenty pomocnicze do cytowania w rozdziałach „Admin”: `[.ai/translations-admin-runbook.md](.ai/translations-admin-runbook.md)`, `[.ai/instrukcja_szablony.md](.ai/instrukcja_szablony.md)` (jeśli dotyczy szablonów lekarza).

## Założenia dotyczące treści

- **Język narracji:** polski (spójnie z Twoją prośbą); etykiety na zrzutach mogą być w **DE/EN/PL** zgodnie z realnym UI — w podpisach wyjaśniać, co widać.
- **Szczegółowość:** każdy rozdział: wprowadzenie → wymagania wstępne → ścieżki URL → procedury krok po kroku → typowe błędy / komunikaty → dobre praktyki (bezpieczeństwo, RODO: np. SMS wyłącznie logistyczny).
- **Pacjent:** osobny rozdział (potwierdzone), opisujący root `/` (logowanie telefon + data urodzenia), `/otp/`, `/documents/` — zgodnie z `[apps/patient_results/views.py](apps/patient_results/views.py)` i PRD §3.4a (w tym uwaga o ewentualnym CAPTCHA/Turnstile w konfiguracji).

## Standard zrzutów ekranu

1. **Środowisko:** staging lub demo z **zanonimizowanymi** danymi (fikcyjne imiona, telefony); jedna rozdzielczość bazowa (np. 1920×1080 dla paneli, tablet w trybie landscape lub docelowa rozdzielczość urządzenia).
2. **Konwencja plików:** `rola-##-krótki-opis.png` (np. `reception-03-import-xlsx.png`), folder np. `docs/manual/` lub `.ai/manual/assets/` (dokładna lokalizacja do ustalenia przy realizacji).
3. **Oznaczenia:** na kluczowych zrzutach opcjonalnie numeracje kroków / strzałki (np. w edytorze), żeby tekst „Krok 3” odpowiadał wizualnie jednoznacznie.
4. **Wersja:** w nagłówku dokumentu data buildu / wersji aplikacji, żeby instrukcja była audytowalna w czasie.

## Struktura dokumentacji (proponowane pliki)


| Plik                   | Odbiorcy                     | Główne tematy                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `00-przeglad.md`       | Wszyscy                      | Cel systemu, role, skrót procesu dnia, słownik stanów kolejki (`WAITING` → … → `PUBLISHED` z PRD), linki do pozostałych plików                                                                                                                                                                                                                                                                                                |
| `01-rejestracja.md`    | RECEPTION                    | Logowanie do Django Admin; **Poczekalnia** – `[DailyQueueAdmin](apps/reception/admin.py)`: lista kolejek, widok master-detail, dodawanie pacjentów, import (`[import_xlsx](apps/reception/admin.py)`); `[/admin/reception-dashboard/](cogitomedica/urls.py)`; `[/admin/intake-documents/](apps/intake/views.py)` — lista i podgląd PDF intake                                                                                 |
| `02-tablet.md`         | TABLET (+ kontekst recepcji) | `[/tablet/](cogitomedica/tablet_urls.py)`: logowanie, `android_id` / sesja urządzenia, `TabletDevice` i filtrowanie kolejek po klinice, wybór kolejki → pacjenta → start sesji → `[form](cogitomedica/tablet_views.py)` → język formularza (`locale`), ankieta, zgody, schemat ciała, podpis, stan SUBMITTED; zachowanie „latest-wins” (PRD); wylogowanie                                                                     |
| `03-doktor.md`         | DOCTOR (+ ADMIN)             | `[/doctor/](cogitomedica/doctor_urls.py)`: logowanie, lista pracy (`doctor/list.html`), filtry, „otwórz z kolejki” `[open/<queue_entry_id>/](cogitomedica/doctor_views.py)`, szczegóły dokumentu i Befund: grupy zmian (`lesion_numbers`), edycja tekstu generowanego, szkic vs publikacja, `publish_locale`, statusy przetwarzania, edycja po publikacji i ponowna wysyłka (PRD); szablony tekstu lekarza (zakres uprawnień) |
| `04-administrator.md`  | ADMIN                        | Pełny Django Admin: użytkownicy `[StaffUser](apps/users/models.py)`, przypisania do klinik, konfiguracja klinik/szablonów importu PDF; tłumaczenia (runbook); modele operacyjne (outbox, importy XLSX); **nie** powielać całej dokumentacji technicznej — zamiast tego linki do runbooków                                                                                                                                     |
| `05-pacjent-wyniki.md` | Pacjent                      | Portal w root: `ergebnisse` — logowanie, OTP, lista dokumentów PDF; zgodność z RODO (SMS bez treści medycznej); co zrobić przy błędzie / braku dokumentu                                                                                                                                                                                                                                                                      |


## Proces pracy (kolejność realizacji)

1. **Inwentaryzacja ekranów:** przejść każdą ścieżkę w stagingu i spisać listę wymaganych zrzutów (checklista w `00` lub osobny `screenshot-checklist.md`).
2. **Pisanie szkieletu:** nagłówki i kroki bez grafik — weryfikacja z kodem (szczególnie ograniczenia roli: np. TABLET tylko kolejki „dzisiaj” w API — `[apps/reception/api_views_split/queues.py](apps/reception/api_views_split/queues.py)`).
3. **Zrzuty + podpisy:** wykonać zrzuty, wstawić do MD z opisami „co jest na obrazku” i „co użytkownik robi dalej”.
4. **Redakcja:** druga osoba (lub autor po przerwie) czyta jak recepcjonista — szuka luk (np. „co jeśli pacjent nie ma jeszcze intake?”).
5. **Utrzymanie:** przy większych zmianach UI zaktualizować datę wersji i zrzuty; rozważyć wpis w README wskazujący na folder instrukcji (jedna linia).

## Ryzyka i uwagi

- **Rola TABLET vs RECEPTION na `/tablet/`:** kod dopuszcza `TABLET`, `RECEPTION`, `ADMIN` (`[tablet_views.py](cogitomedica/tablet_views.py)`) — instrukcja powinna wyraźnie rozdzielić **dedykowane konto TABLET** (zalecane na urządzeniu) od logowania recepcji na tablecie w wyjątku.
- **Różnice ADMIN vs DOCTOR:** obie role mają dostęp do `/doctor/`; ADMIN dodatkowo pełny Django Admin — unikać duplikacji: w `03` opisać wspólny panel lekarza, w `04` tylko administrację.
- **Portal pacjenta:** może być wymóg CAPTCHA/Turnstile — opisać w `05` jako „jeśli widzisz pole weryfikacji…”.

## Wynik końcowy

Jeden spójny pakiet (Markdown + katalog z PNG), gotowy do eksportu do PDF lub wklejenia do wiki; priorytet: **kompletność** i **jednoznaczna procedura** zamiast ogólników.