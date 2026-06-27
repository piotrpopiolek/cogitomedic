# Scenariusze operacyjne — FAQ i materiały wideo

Zbiór **realnych przypadków** z produkcji / testów, które warto opisać w instrukcji lub **nagrać krótkim filmikiem** (WebM), żeby recepcja, lekarz i manager szybko znaleźli rozwiązanie.

Powiązane: [README instrukcji](README.md), [nagrywanie filmów](assets/videos/README.md), backlog techniczny [`.ai/TODO.md`](../../.ai/TODO.md).

---

## Jak dopisywać nowy scenariusz

Skopiuj szablon na koniec pliku i uzupełnij:

```markdown
### SC-NNN — Krótki tytuł

| Pole | Treść |
|------|--------|
| **Role** | Recepcja / Lekarz / … |
| **Objaw** | Co widzi użytkownik |
| **Przyczyna (techniczna)** | 1–2 zdania, bez żargonu gdzie możliwe |
| **Co zrobić dziś (obejście)** | Kroki operacyjne |
| **Czego nie robić** | Pułapki |
| **Docelowo (produkt)** | Link do TODO / fix |
| **Film** | `nie nagrany` / `scenariusze/sc-NNN.webm` |
| **Powiązane** | `docs/manual/…`, issue |
```

---

## Indeks

| ID | Tytuł | Role | Film |
|----|--------|------|------|
| [SC-001](#sc-001-anulowany-wpis-nadal-w-kolejce-lekarza) | Anulowany wpis nadal w kolejce lekarza | Recepcja, Lekarz | nie nagrany |
| [SC-002](#sc-002-usunięty-szkic-wpis-z-statusem--) | Usunięty szkic — wpis ze statusem „—” | Recepcja, Lekarz, Admin | nie nagrany |
| [SC-003](#sc-003-otwarta-rewizja-revision-a-nie-chcemy-jej-kończyć) | Otwarta rewizja — porzucenie | Lekarz | nie nagrany |

---

### SC-001 — Anulowany wpis nadal w kolejce lekarza

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | W recepcji wpis ma status **Anulowano**, ale na liście lekarza (`/doctor/`) wiersz **nadal jest** (różowe tło, status `—` lub wcześniej SZKIC). |
| **Przyczyna (techniczna)** | Kolejka lekarza (`list_doctor_work_queue`) kwalifikuje wpis, gdy ankieta ma status **Złożona** (`SUBMITTED`) lub **Ponownie otwarta** (`REOPENED`). Anulowanie wpisu kolejki (`CANCELLED`) **nie wyklucza** go z tej listy. |
| **Co zrobić dziś (obejście)** | 1) Upewnij się, że anulowałeś **właściwy** wpis (ten ze statusem „Pacjent zakończył”, nie inny slot tego samego dnia). 2) **Nie klikaj „Otwórz”** u lekarza — odtworzy szkic. 3) Dla danych testowych / jednorazowo: cleanup wpisu w adminie (cały `QueueEntry` + powiązania) — tylko po uzgodnieniu z IT. 4) Poczekaj na fix: wykluczenie `CANCELLED` z kolejki (TODO). |
| **Czego nie robić** | Nie traktuj anulowania wpisu jako „zamknięcia przypadku” przy złożonej ankiecie. Nie ma osobnej akcji „anuluj ankietę” w UI. |
| **Docelowo (produkt)** | [`.ai/TODO.md`](../../.ai/TODO.md) — wykluczenie `CANCELLED` z `list_doctor_work_queue`. |
| **Film** | nie nagrany — proponowany tytuł: *„Anulowałem wizytę, a lekarz nadal widzi pacjenta”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md), [03-doktor.md](03-doktor.md) § lista pracy |

---

### SC-002 — Usunięty szkic — wpis ze statusem „—”

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz, Administrator |
| **Objaw** | Po usunięciu **szkicu dokumentu** (`MedicalDocument` w adminie) lekarz nadal widzi wiersz: status **`—`**, kolumny PDF/HiDrive/SMS puste, przycisk **Otwórz**, różowe tło (SLA). |
| **Przyczyna (techniczna)** | Usunięcie szkicu = brak dokumentu. System traktuje to jak **nowego kandydata do opisania** (tier 0: `medical_document IS NULL` + ankieta `SUBMITTED`). To **nie** zamyka wizyty. |
| **Co zrobić dziś (obejście)** | Jeśli wizyta jest nieaktualna: anuluj wpis w recepcji **i** licz się z tym, że wpis może **nadal** być widoczny (patrz SC-001). Dla śmieciowych danych testowych — usunięcie całego wpisu kolejki w adminie. Jeśli wizyta jest realna — lekarz ma **opublikować** Befund, nie usuwać szkicu. |
| **Czego nie robić** | **Nie klikać „Otwórz”** — `create_or_get_medical_document` utworzy **nowy** szkic DRAFT. Nie zmieniać ręcznie statusu ankiety na `IN_PROGRESS` w adminie bez procedury RODO. |
| **Docelowo (produkt)** | Wykluczenie `CANCELLED` + akcja „zamknij przypadek bez publikacji” (backlog). |
| **Film** | nie nagrany — proponowany tytuł: *„Usunąłem szkic w adminie — dlaczego pacjent zostaje na liście?”* |
| **Powiązane** | [03-doktor.md](03-doktor.md) |

---

### SC-003 — Otwarta rewizja (REVISION) — nie chcemy jej kończyć

| Pole | Treść |
|------|--------|
| **Role** | Lekarz |
| **Objaw** | Na liście: **Opublikowany** + etykieta **Rewizja**; kolumny outbox **Oczekuje**. Lekarz otworzył korektę, ale ma wrócić do poprzedniej opublikowanej wersji. |
| **Przyczyna (techniczna)** | `has_pending_revision=True` — dokument w tier 0 (wspólna praca). Istnieje wersja DRAFT rewizji. |
| **Co zrobić dziś (obejście)** | W szczegółach Befundu: **Porzuć rewizję** (`POST …/discard-revision`). Opublikowana wersja zostaje; pacjent w portalu widzi poprzedni wynik. |
| **Czego nie robić** | Nie publikować pustej rewizji „żeby zniknęło”. Nie usuwać ręcznie wersji w adminie bez znajomości outbox. |
| **Docelowo (produkt)** | Już obsłużone w produkcie — brak dodatkowego fixu; ewentualnie krótszy opis w manualu lekarza. |
| **Film** | nie nagrany — proponowany tytuł: *„Jak anulować rozpoczętą korektę Befundu”* |
| **Powiązane** | [03-doktor.md](03-doktor.md), API `discard-revision` |

---

## Backlog filmów (propozycje)

| Priorytet | SC | Czas ~ | Odbiorca |
|-----------|-----|--------|----------|
| Wysoki | SC-001 | 2–3 min | Recepcja + lekarz |
| Wysoki | SC-002 | 2 min | Admin / recepcja |
| Średni | SC-003 | 2 min | Lekarz |

Po nagraniu: plik w `docs/manual/assets/videos/scenariusze/` (np. `sc-001-anulowany-wpis.webm`), aktualizacja kolumny **Film** w tabeli powyżej i ewentualny link z rozdziału manuala.
