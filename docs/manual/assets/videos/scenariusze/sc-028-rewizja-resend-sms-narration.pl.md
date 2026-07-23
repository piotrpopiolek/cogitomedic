# Narracja — SC-028

Plik wideo: `sc-028-rewizja-resend-sms.webm` (skrypt `scripts/record_scenario_videos.py --scenario SC-028`).

Priorytet lektora: **standard**. Dane w filmie są **fikcyjne** (demo RODO).

Pełny opis operacyjny: [scenariusze.md — SC-028](../../../scenariusze.md).

---

## Wprowadzenie

Film pokazuje otwartą **rewizję** Befundu u lekarza oraz checkbox **Wyślij SMS ponownie** przed ponowną publikacją.

## Kroki

1. Lekarz loguje się do `/doctor/` i otwiera dokument z otwartą rewizją.
2. Przewija wypełniony Befund (kilka grup zmian).
3. Na dole zaznacza **Wyślij SMS ponownie** i wskazuje przycisk ponownej publikacji.
4. W praktyce: po podglądzie PDF kliknij publikację — pacjent dostanie kolejne powiadomienie logistyczne.

## Uwagi / ograniczenia dema

Film **nie** wykonuje pełnej publikacji (tylko UI). Treść SMS pozostaje logistyczna — bez opisu badania.
