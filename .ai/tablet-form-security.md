# Zabezpieczenia formularza tabletu (pacjent)

## Wprowadzone

- **Usunięcie przycisku „Poczekalnia”** z widoku formularza (`form.html`). Po przekazaniu tabletu pacjentowi nie ma w interfejsie linku powrotu do listy kolejek – ogranicza to przypadkowe wyjście z ankiety.

## Rekomendowane dodatkowe zabezpieczenia

### 1. Tylko własna ankieta (izolacja na poziomie dostępu)

**Problem:** Obecnie dostęp do `/tablet/form/<uuid>/` ma każdy zalogowany użytkownik z rolą TABLET/RECEPTION/ADMIN. Jeśli pacjent (lub osoba przy tablecie) wpisze w przeglądarce inny UUID formularza, może zobaczyć cudzą ankietę.

**Rekomendacja:**

- **Opcja A – signed URL (token jednorazowy):**  
  Dla trybu „tablet przekazany pacjentowi” generować link z tokenem, np.  
  `/tablet/form/<intake_form_id>/?token=<signed_value>`  
  Widok weryfikuje podpis (np. HMAC z kluczem w ustawieniach + intake_form_id + opcjonalnie expiry).  
  Jeśli `request.GET.get("token")` jest poprawny, widok renderuje formularz **bez wymagania logowania** (sesja Django nie jest używana do autoryzacji tego jednego formularza).  
  Bez poprawnego tokenu zwracać 404.  
  Efekt: pacjent ma link tylko do swojej ankiety; wpisanie innego UUID bez tokenu nie daje dostępu.

- **Opcja B – sesja powiązana z jednym formularzem:**  
  Po „Otwórz formularz” zapisywać w sesji `allowed_intake_form_id = <uuid>`.  
  W `tablet_form_view` (oraz w API intake-forms) sprawdzać: jeśli użytkownik ma rolę TABLET i w sesji jest `allowed_intake_form_id`, zezwalać **tylko** na ten UUID.  
  Dla RECEPTION/ADMIN można zostawić pełny dostęp (bez ograniczenia do jednego ID).

### 2. Ograniczenie operacji API do „własnego” formularza

Wszystkie endpointy pod `/api/v1/intake-forms/<id>/...` (GET, PUT consents, PATCH, POST signature, POST submit) powinny w trybie pacjenta/tabletu sprawdzać, że `<id>` to formularz dozwolony dla bieżącej sesji/tokenu (np. ten sam `allowed_intake_form_id` lub token podpisany dla tego `id`).  
Obecnie API opiera się na sesji zalogowanego personelu – po wprowadzeniu tokenu lub `allowed_intake_form_id` trzeba dodać tę samą logikę w API (np. w widokach w `apps/intake/api_views.py` lub w warstwie permission).

### 3. Wygaśnięcie sesji / tokenu

- **Sesja:** Ustawić rozsądny `SESSION_COOKIE_AGE` (np. 2 h) i `SESSION_SAVE_EACH_REQUEST = True`, żeby aktywność przedłużała sesję. Po przekazaniu tabletu pacjentowi personel może wylogować się na innym urządzeniu, ale sesja na tablecie nadal będzie ważna do wygaśnięcia.
- **Token (gdy wprowadzony):** W wartości podpisu uwzględnić czas wygaśnięcia (np. 2 h od wygenerowania) i w widoku odrzucać token po tym czasie.

### 4. Brak nawigacji wstecz w przeglądarce

Pacjent może użyć przycisku „Wstecz” w przeglądarce. Można to ograniczyć przez:
- **History API:** Po wejściu na formularz wywołać `history.pushState` i nasłuchiwać `popstate` – przy próbie cofnięcia wrócić na ten sam URL (np. ponowne `pushState` dla bieżącego kroku). To nie chroni przed wpisaniem innego adresu, tylko przed przypadkowym cofnięciem.
- **Informacja dla personelu:** Instrukcja, żeby po przekazaniu tabletu nie zostawiać otwartych kart do poczekalni (np. zamknięcie karty do `/tablet/` po wejściu w formularz).

### 5. Audyt

- Logować (np. w modelu lub w logu aplikacji) zdarzenia: otwarcie formularza (GET), zapis zgód/anamnezy/podpisu, submit – z `intake_form_id`, timestamp, opcjonalnie identyfikator sesji/tokenu (bez PII). Ułatwi to weryfikację „kto kiedy miał dostęp do którego formularza”.

---

**Podsumowanie:** Usunięcie przycisku „Poczekalnia” ogranicza wyjście z formularza w UI. Aby pacjent mógł zobaczyć **tylko swoją** ankietę, konieczne jest zabezpieczenie dostępu po UUID (signed URL / token lub sesja z jednym dozwolonym `intake_form_id`) oraz spójna weryfikacja w widokach HTML i w API intake-forms.
