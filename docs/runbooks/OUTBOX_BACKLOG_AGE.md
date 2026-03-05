# Runbook: OUTBOX_BACKLOG_AGE

## Cel
Naprawa problemu, w którym zdarzenia outbox (np. generowanie PDF, wysyłka HiDrive, SMS) oczekują na przetworzenie zbyt długo (powyżej 15 minut) w godzinach pracy placówki.

## Warunek alertu
Metryka `cogitomedica_outbox_pending_age_seconds` wskazuje na zdarzenie starsze niż 900 sekund (15 minut).
Oznacza to, że worker zadań asynchronicznych (kontener `scheduler`) stoi w miejscu, uległ awarii lub nie nadąża za napływem zadań.

## Kroki diagnostyki
1. Sprawdź dashboard Grafany, aby upewnić się czy kolejka PENDING rośnie.
2. Zaloguj się na maszynę hostującą i sprawdź logi serwisu `scheduler`:
   `docker compose logs --tail=100 scheduler`
3. Zobacz, czy w logach widnieją błędy związane z połączeniem z bazą danych lub błędem biblioteki WeasyPrint.
4. Wejdź do panelu administracyjnego: `/admin/outbox/outboxevent/` i sprawdź które zdarzenia "wiszą".

## Obejście awaryjne / Naprawa
1. Ręczne wyzwolenie przetwarzania kolejki outbox:
   `docker compose run --rm web python manage.py enqueue_tasks`
2. Zwiększenie ilości powtórzeń (restart usługi):
   `docker compose restart scheduler`
3. Ręczne ponowienie zdarzeń przez Panel Recepcji:
   Wejdź na `/admin/reception-dashboard/` i dla każdego błędu kliknij 'Ponów' z poziomu konkretnego rekordu.

## Eskalacja
W przypadku permanentnej utraty PDF z powodu błędu dysku - kontakt z deweloperem / poziomem 3 utrzymania.
