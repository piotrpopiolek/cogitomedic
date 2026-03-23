# Runbook: INTEGRATION_ERROR (i LOW_SUCCESS_RATIO)

## Cel
Naprawa problemu, w którym usługi zewnętrzne (HiDrive lub SMS) zwracają błędy przetwarzania, przez co dokumentacja nie trafia do archiwum lub pacjenci nie dostają powiadomień.

## Warunek alertu
Alert zostaje wyzwolony, jeśli w ciągu ostatnich 10 minut wystąpił `FAILED` lub w ciągu 1 godziny stosunek pomyślnych wysyłek do całkowitych spadł poniżej 98%. 

## Kroki diagnostyki
1. Otwórz dashboard Recepcji w panelu: `/admin/reception-dashboard/`.
2. Zwróć uwagę na sekcję "Zaległe zdarzenia".
3. Przejdź do szczegółów danego zdarzenia klikając na link. Zobacz pole `error_message` (na samym dole zdarzenia outbox).
4. Rozróżnienie błędu:
   - **401 Unauthorized / Token expired** (HiDrive) – Problem z tokenem autoryzacyjnym. System automatycznie odświeża access token przez `HIDRIVE_REFRESH_TOKEN`; jeżeli po odświeżeniu nadal jest 401, refresh token mógł wygasnąć lub zostać unieważniony.
   - **503 / 500 / Timeout** (HiDrive / SMSApi) – Chwilowa awaria usługodawcy.
   - **Błędny numer telefonu** (SMSApi) – Pacjent podał zły numer w systemie recepcji.

## Obejście awaryjne / Naprawa
1. Dla błędu usług zewnętrznych (5xx): poczekaj 15 minut i ponów zadania ręcznie przyciskiem "Ponów" (Retry) w rekordzie.
2. Dla błędu numeru telefonu: 
   - Popraw numer telefonu w danych pacjenta (zakładka Pacjenci).
   - Wygeneruj i wyślij ponownie (ponów zdarzenie).
3. Dla błędu 4xx (Autoryzacja):
   - sprawdź w `.env`: `HIDRIVE_CLIENT_ID`, `HIDRIVE_CLIENT_SECRET`, `HIDRIVE_REFRESH_TOKEN`, `HIDRIVE_USE_MOCK=0`,
   - wykonaj ponownie OAuth code flow i podmień `HIDRIVE_REFRESH_TOKEN`,
   - zrestartuj usługę `web` i `scheduler` po zmianie sekretów.
4. Sprawdź metrykę `cogitomedica_hidrive_token_refresh_total{outcome="error"}` – wzrost wskazuje problemy z odświeżaniem tokena.

## Eskalacja
W przypadku przerw w działaniu HiDrive - weryfikacja na stronie statusu usług Strato (HiDrive). W przypadku SMS - na stronie SMSApi.
