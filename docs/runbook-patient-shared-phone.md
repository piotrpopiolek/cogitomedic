# Runbook: migracja wspólnego numeru telefonu (prod)

Migracje: `reception.0040_restore_patient_identity_unique`, `0041_normalize_patient_name_casing` (jeśli jeszcze nie zastosowane).

## Przed `migrate`

1. **Kopia bazy** (snapshot / pg_dump).
2. **Preflight duplikatów czwórki** — migracja `0040` przerwie się z `RuntimeError`, jeśli istnieją dwie aktywne osoby z identycznym `(first_name, last_name, phone, date_of_birth)` po normalizacji. Zapytanie kontrolne (dostosuj do środowiska):

```sql
SELECT first_name, last_name, phone, date_of_birth, COUNT(*)
FROM reception_patient
WHERE anonymized_at IS NULL
GROUP BY 1, 2, 3, 4
HAVING COUNT(*) > 1;
```

3. **Audyt wspólnych telefonów** (informacyjnie — dozwolone po wdrożeniu):

```sql
SELECT phone, COUNT(*) AS cnt
FROM reception_patient
WHERE anonymized_at IS NULL
GROUP BY phone
HAVING COUNT(*) > 1
ORDER BY cnt DESC;
```

Rozwiąż duplikaty czwórki (merge w adminie / korekta literówek) **przed** migrate.

## Po wdrożeniu

- Recepcja: przy POST pacjenta z numerem już używanym — sprawdź pole `warnings` (`shared_phone`).
- Portal: kolizja `phone + DOB` u dwóch osób wymaga **nazwiska** na logowaniu.
- Komunikuj pacjentom rodzinnym wspólny numer: logowanie po **własnej** dacie urodzenia (i nazwisku w skrajnym przypadku).

## Rollback

Przywrócenie `patient_phone_unique` wymaga analizy danych (możliwe wiele rekordów z tym samym `phone`). Nie cofaj migracji bez planu merge.
