
Na podstawie Twoich odpowiedzi w `session1.md` poniżej są **dodatkowe pytania i rekomendacje** do doprecyzowania w PRD:

---

1. **Skoro lista dokumentów zgód nie jest sztywna i wszystko ma być „checkboxy i pola informacyjne” – kto i w jaki sposób ma zarządzać treściami zgód (np. dodawanie nowej zgody, zmiana tekstu)? Czy planujecie panel konfiguracyjny (np. w Django Admin) z wersjowaniem treści?**  
 
   Dodawanie nowych zgód będzie bardzo rzadki i będzie tylko przy okazji ewentualnych kolejnych rozbudów systemu/portalu.

2. **Część medyczna ma być „różne pola, checkboxy, listy, opisy” – czy struktura tego formularza ma być definiowana w systemie (np. przez admina / szablon), czy na stałe zapisana w kodzie?**  
   Może to być sztywny zestaw na stałe w kodzie.

3. **Przy „zmianie w opublikowanym dokumencie i ponownej wysyłce” – czy każda ponowna wysyłka ma tworzyć nową wersję pliku w HiDrive (np. `.../v1.pdf`, `.../v2.pdf`), czy nadpisywać ten sam plik? Czy pacjent w portalu ma widzieć tylko ostatnią wersję, czy historię wersji?**  
   Nadpisujemy stary plik, nową wersją, opcjonalna ponowna wysyłka SMSa. 

4. **Transactional Outbox ma obsłużyć zapis (np. DB + HiDrive, ewentualnie DB + SMS). Które dokładnie operacje mają iść przez Outbox (tylko wysyłka do HiDrive, tylko SMS, obie)? Czy po niepowodzeniu wysyłki do HiDrive dokument ma pozostawać w stanie „opublikowany” z flagą „pending_sync”, czy wrócić do szkicu?**  

    Przez Outbox ma iść zapis do HiDrive potem powiadomienie SMS. Stan dokumentu w przypadku błędu pozostanie opublikowany, od zapisu na hidrivi i smsów będę osobne flagi true.

5. **Czy „lista dzienna” pacjentów, z której rejestrator wybiera pacjenta i otwiera formularz na tablecie, ma pochodzić wyłącznie z Doctolib (Faza 3), czy do tego czasu ma istnieć ręczna lista (np. w portalu) lub import na dzień?**  
   **Zalecenie:** W PRD dla Fazy 1–2 założyć **ręczne zarządzanie listą dzienną** (np. widok „Poczekalnia” z dodawaniem pacjentów po imieniu/nazwisku lub z wcześniej zaimportowanej listy). W Fazie 3 – przełączenie na źródło Doctolib z zachowaniem tego samego flow rejestratora (wybór z listy → otwarcie formularza).
   Zgodnie z zaleceniem.

6. **Czy wszystkie 4 tablety współdzielą tę samą „listę dzienną”, a rejestrator przy wywołaniu pacjenta otwiera formularz na dowolnym wolnym tablecie, czy każdy tablet jest przypisany do konkretnego stanowiska/rejestratora?**  

    Jeden wspólny ekran listy poczekalni, po wyborze pacjenta powiązujemy formularz z pacjentem np tokenem w linku.

7. **Integracja z HiDrive „po API” – czy macie już wybrany konkretny interfejs (np. HiDrive REST API, WebDAV)? Od tego zależy wybór biblioteki i sposób autentykacji (OAuth2, token, hasło).**  
   Możemy w początkowej wersji zmokować zapis na HiDrive poprzez zapis lokalny, tak aby zasymulować flow przed integracją z HiDrive.

8. **Czy powiadomienie SMS do pacjenta po publikacji ma korzystać z tego samego mechanizmu i dostawcy co obecne wysyłanie SMS w module wyników (results), czy planowany jest osobny kanał/dostawca?**  
   Mamy już integrację z SMSApi, pozostanie to dalej w module wyników.

9. **Cron usuwający PDF po 30 dniach – czy usunięcie z portalu ma następować dopiero po potwierdzeniu, że plik został zapisany w HiDrive (np. status z Outbox), żeby nie usunąć dokumentu przy awarii synchronizacji?**  
   W PRD zapisać regułę: „Cron 30-dniowy usuwa rekord/plik tylko jeśli w Outbox (lub w tabeli archiwizacji) istnieje potwierdzenie udanego zapisu w HiDrive oraz wysłania SMSa dla tego dokumentu”.

10. **Czy Faza 1 ma obejmować wyłącznie obecny flow (zgody + schemat ciała + podpis + PDF do pobrania przez lekarza), czy już w Fazie 1 ma być wypełnienie ankiety medycznej (Muster Befund) na tablecie, zanim dokument trafi do lekarza?**  
    W PRD w opisie Fazy 1 wprost wymienić: które kroki są w scope (np. „Krok 1–3: zgody, schemat, podpis”; czy „Krok 2 rozszerzony o ankietę Muster Befund”). Od tego zależy, czy panel lekarza w Fazie 2 dostaje tylko zgody+schemat+podpis, czy też odpowiedzi z ankiety.
    Lekarz potrzebuje informacji z fazy 1 aby kontynować fazę 2.

---

Możesz uzupełnić te punkty w `session1.md` lub w osobnym pliku; gdy będziesz chciał, mogę na tej podstawie przygotować **podsumowanie do PRD** (jednostronicowy konsens: zakres, fazy, decyzje).