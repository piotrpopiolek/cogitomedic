# Narracja — SC-006 — Pacjent nie dostał SMS (outbox)

Plik: `sc-006-sms-outbox-retry.webm`

---

## Wprowadzenie

Befund jest opublikowany, a pacjent mówi, że nie dostał SMS z kodem do portalu. Administrator **nie** publikuje ponownie Befundu — to robi wyłącznie lekarz. Recepcja / admin naprawia zdarzenie outbox `SMS_SEND`.

## Kroki

1. Dashboard recepcji — sekcja błędów outbox.
2. Lista zdarzeń outbox — filtr **Wysyłka SMS**, właściwa wersja dokumentu.
3. Przy statusie **Nieudane** / **Dead letter**: **Ponów** na dashboardzie albo ustaw status na **Oczekuje**.
4. Przy statusie **Przetworzono**, a SMS trzeba wysłać ponownie: cofnij na **Oczekuje**, wyczyść `processed_at` jeśli trzeba.
5. Poczekaj na worker (albo IT: `enqueue_tasks`). Odśwież dashboard.

## Uwaga

To **nie** jest problem OTP logowania portalu (SC-010). Nie wysyłaj treści medycznej prywatnym SMS.
