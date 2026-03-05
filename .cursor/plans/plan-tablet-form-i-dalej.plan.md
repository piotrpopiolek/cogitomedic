---
name: ""
overview: ""
todos: []
isProject: false
---

# Plan: formularz pacjenta na tablecie i dalsze kroki

## Stan obecny

- **Tablet (poczekalnia):** działa logowanie (TABLET), lista kolejek, lista pacjentów, „Otwórz formularz” → ekran „Formularz przygotowany” z `intake_form_id`.
- **Brak:** interfejsu, w którym **pacjent** na tym samym tablecie wypełnia zgody, anamnezę i podpis (obecnie tylko opis wywołań API).

---

## 1. Formularz pacjenta na tablecie (kolejny krok)

**Cel:** Po „Otwórz formularz intake” pokazać widok dla pacjenta (lub od razu na niego przejść), bez używania Swaggera.

**Zakres:**

1. **Widok formularza** (np. `/tablet/form/<intake_form_id>/`)
  - Dostęp: ta sama sesja (TABLET/RECEPTION/ADMIN), bez osobnego logowania pacjenta.
  - GET kontekstu z API: `GET /api/v1/intake-forms/<id>` → dane pacjenta (read-only), lista zgód, pytania anamnezy, `has_signature`.
2. **Sekcje w UI (jedna strona lub kroki):**
  - **Weryfikacja danych** – tylko odczyt: imię, nazwisko, data urodzenia, kontakt (z kontekstu).
  - **Zgody** – checkboxy (tytuł + opcja Tak/Nie), zapis: `PUT /api/v1/intake-forms/<id>/consents` (np. po „Dalej” lub po każdej zmianie).
  - **Anamneza** – pytania z kontekstu (single/multi choice, text), zapis: `PUT /api/v1/intake-forms/<id>/anamnesis`.
  - **Podpis** – canvas (rysowanie palcem/długopisem), export do base64, wysłanie: `POST /api/v1/intake-forms/<id>/signature`.
  - **Submit** – przycisk „Zatwierdź”, wywołanie `POST /api/v1/intake-forms/<id>/submit`; po sukcesie: komunikat „Formularz wysłany” + przycisk „Wróć do listy pacjentów”.
3. **Technicznie:** szablony Django + lekki JS (fetch do API v1), responsywny layout pod tablet (duże przyciski, czytelne pola). Walidacja po stronie API (400) – wyświetlanie błędów w UI.
4. **Przepływ:** z ekranu „Formularz przygotowany” zamiast (lub obok) opisu API – przycisk **„Przekaż tablet pacjentowi – wypełnij formularz”** → przekierowanie na `/tablet/form/<intake_form_id>/`.

**Pliki do dodania/zmiany:**

- `cogitomedica/tablet_views.py` – widok `tablet_form_view(request, intake_form_id)` (GET render formularza; zapisy przez JS/fetch).
- `cogitomedica/tablet_urls.py` – `path("form/<uuid:intake_form_id>/", ...)`.
- Szablony: `tablet/form.html` (główny), ewentualnie fragmenty dla zgód/anamnezy/podpisu.
- W `entry_started.html` – link/CTA do `/tablet/form/{{ intake_form_id }}/`.

**Definition of done:** Recepcja wybiera pacjenta → „Otwórz formularz” → przekazuje tablet → pacjent na jednym ekranie (lub krokach) wypełnia zgody, anamnezę, podpis i wysyła; po submit wraca komunikat sukcesu i możliwość powrotu do listy pacjentów.

---

## 2. Kontrakt API staff i luki (przed/ równolegle z frontem staff)

- **Dokument:** `.ai/staff-api-contract.md` – lista endpointów dla recepcji/lekarza/admin (metody, payloady, kody błędów), źródło: obecna implementacja.
- **GET /api/v1/medical-documents** – lista dokumentów dla panelu lekarza (filtry, paginacja).
- **RBAC operations** – `operations/outbox/process` i `operations/retention/run` tylko dla roli ADMIN (lub dedykowana rola ops).

---

## 3. Front staff (Django Unfold)

Zgodnie z `.cursor/plans/plan_django_staff_frontend.plan.md`:

- Integracja Unfold, shell pod `/staff/`, auth.
- Recepcja MVP: kolejki, wpisy, pacjenci, tworzenie sesji tabletu.
- Lekarz MVP: create document, draft, publish.
- Ops MVP: outbox, retencja, health.

---

## 4. Późniejsze (backlog)

- Observability (metryki, alerty, runbooki).
- Hardening (sesja, HTTPS, testy E2E).
- Opcjonalnie: body map na tablecie (jeśli w PRD w scope Fazy 1).

---

## Proponowana kolejność


| Krok | Zadanie                                           | Efekt                            |
| ---- | ------------------------------------------------- | -------------------------------- |
| 1    | Formularz pacjenta na tablecie (pkt 1)            | Pełny flow tabletu bez Swaggera  |
| 2    | Kontrakt staff + GET medical-documents + RBAC ops | Gotowość do frontu staff         |
| 3    | Front staff (Unfold) – recepcja/lekarz/ops MVP    | Panel personelu w jednym miejscu |


Rekomendacja: najpierw **krok 1** (formularz pacjenta na tablecie), żeby zamknąć cały proces pacjenta w jednym miejscu; potem 2 i 3.