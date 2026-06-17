# Instrukcja: Pacjent — portal wyników (Ergebnisse)

Dokumentacja dla **pacjenta**, który ma pobrać dokumentację medyczną po otrzymaniu **SMS** z placówki. Portal jest dostępny pod adresem **głównym serwisu** (w konfiguracji deweloperskiej często `http://127.0.0.1:8000/` — produkcyjnie np. dedykowana domena podana przez placówkę).

**Ważne (RODO / BÄK):** SMS ma charakter **wyłącznie logistyczny** — nie zawiera informacji o rodzaju badania ani wyniku. Treść w stylu: „Nowa dokumentacja w Cogito” (dokładnie wg ustawień systemu). Pacjent **nie dostaje linku w SMS** — sam wpisuje znany adres portalu lub korzysta z zakładki zapisaną wcześniej.

---

## Krok 1: Wejście na stronę logowania

1. Otwórz przeglądarkę na telefonie lub komputerze.
2. Wpisz adres portalu wyników podany przez placówkę (np. strona główna domeny).
3. Zobaczysz formularz z prośbą o **numer telefonu** i **datę urodzenia** (czasem także o **nazwisko** — patrz niżej).

![Ekran logowania portalu wyników](/docs/manual/assets/screenshots/patient-01-login.png)

**Dane muszą być zgodne** z tymi zarejestrowanymi przy wizycie (recepcja / tablet). Jeśli numer lub data urodzenia są inne, system nie wyśle kodu OTP lub nie dopasuje rekordu. Jeśli recepcja **poprawiła** Twój telefon lub datę urodzenia w systemie, używaj przy logowaniu **już zaktualizowanych** danych — szczegóły dla personelu: [Instrukcja recepcji, § 4.1](01-rejestracja.md).

**Wspólny numer telefonu w rodzinie:** jeśli kilka osób ma ten sam numer, portal zwykle rozróżnia je po **różnej dacie urodzenia**. Gdy **dwie osoby mają ten sam numer i tę samą datę urodzenia** (rzadki przypadek), po pierwszej próbie logowania system poprosi dodatkowo o **nazwisko** — wpisz je dokładnie tak, jak w recepcji.

### Weryfikacja captcha (jeśli jest włączona)

W niektórych wersjach strony nad przyciskiem wysłania kodu pojawi się dodatkowa kontrola bezpieczeństwa („captcha”). Pacjent musi ją ukończyć (zazwyczaj automatycznie lub jednym kliknięciem), zanim wyśle formularz.

Jeśli jej nie widzisz, ta funkcja może być czasowo wyłączona.

---

## Krok 2: Żądanie kodu SMS (OTP)

1. Wpisz **numer telefonu** w formacie akceptowanym przez formularz (np. bez spacji lub ze spacjami — zgodnie z polem).
2. Wybierz **datę urodzenia** w kalendarzu lub wpisz ją ręcznie.
3. Jeśli formularz pokazuje pole **nazwisko**, uzupełnij je (wymagane przy wspólnym numerze i tej samej dacie urodzenia u dwóch osób).
4. Kliknij przycisk w stylu **„Poproś o kod SMS”** / „Code per SMS anfordern” (tekst zależy od języka interfejsu).
5. Po poprawnym wysłaniu formularza przejdziesz do strony wpisywania kodu.

**Uwaga:** Jeśli pojawi się komunikat błędu — sprawdź, czy numer i data są poprawne; jeśli nadal nie działa, skontaktuj się z **recepcją placówki** (nie podawaj danych wrażliwych osobom postronnym).

---

## Krok 3: Wpis kodu OTP

1. Na stronie **`/otp/`** wpisz **6-cyfrowy kod** otrzymany SMS-em na podany numer.
2. Kod jest ważny przez **krótki czas** (zwykle około 15 minut).

![Ekran wpisywania kodu OTP](/docs/manual/assets/screenshots/patient-02-otp.png)

Jeśli kod wygasł, wróć do kroku 1 i **poproś ponownie** o kod.

---

## Krok 4: Lista dokumentów i pobranie PDF

Po poprawnym OTP zobaczysz stronę **`/documents/`** z listą dostępnych plików do pobrania.

1. Wybierz dokument (link **Pobierz** / „Download” — zależnie od tłumaczenia).
2. Plik pobierze się przez **HTTPS** — zapisz go w bezpiecznym miejscu.

![Lista dokumentów PDF](/docs/manual/assets/screenshots/patient-03-documents.png)

**Wycofanie publikacji:** jeśli lekarz **cofnie publikację** w systemie placówki, pacjent po wpisaniu OTP może **nie zobaczyć** już wycofanego pliku — zgodnie z PRD. W razie wątpliwości skontaktuj się z placówką.

**Okno dostępu do PDF:** plik można pobrać przez portal przez **60 dni** od publikacji (konfiguracja `PDF_RETENTION_DAYS` w systemie placówki). Po tym czasie lokalna kopia jest usuwana z serwera aplikacji (gdy wynik jest już bezpiecznie zarchiwizowany w chmurze placówki i wysłano SMS). Pobranie po upływie okna nie jest możliwe — skontaktuj się z **recepcją**, która może udostępnić kopię z archiwum zgodnie z procedurą placówki.

---

## Język interfejsu

Język strony zależy od ustawień systemu i przeglądarki. W razie potrzeby placówka może pomóc przełączyć właściwy język.

---

## Bezpieczeństwo

- **Nie przekazuj** kodu OTP innym osobom.
- **Nie** rób zdjęć ekranu z kodem OTP w miejscach publicznych.
- Logowanie jest **silniejsze** niż samo znanie daty urodzenia — wymaga dostępu do **SMS na Twój numer** w krótkim oknie czasowym.

---

## Problemy i gdzie szukać pomocy

| Problem | Co zrobić |
|---------|-----------|
| Brak SMS z kodem | Sprawdź zasięg sieci; poczekaj chwilę; poproś ponownie o kod; zadzwoń do recepcji. |
| „Nieprawidłowe dane” przy logowaniu | Upewnij się, że numer i data zgadzają się z danymi podanymi w placówce. |
| Pusta lista dokumentów | Możliwe opóźnienie publikacji; wycofanie przez lekarza; skontaktuj się z placówką. |
| Błąd pobrania / „dokument niedostępny” po dłuższym czasie | Minęło okno dostępu (zwykle **60 dni** od publikacji). Zadzwoń do recepcji — placówka może udostępnić kopię z archiwum. |
| Błąd captcha | Odśwież stronę; spróbuj innej przeglądarki; wyłącz VPN jeśli blokuje Turnstile. |

Powiązane u personelu: [Przegląd](00-przeglad.md), [Lekarz — publikacja](03-doktor.md).
