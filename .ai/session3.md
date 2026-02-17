
Na podstawie odpowiedzi z `session2.md` poniżej jest **kolejna seria pytań i zaleceń**, które doprecyzują ostatnie luki przed PRD:

---

1. **Faza 1 – zakres Kroku 2:** Lekarz potrzebuje „informacji z Fazy 1” do Fazy 2. Czy w Fazie 1 na tablecie pacjent wypełnia tylko **zgody + schemat ciała + podpis**, czy także **ankietę medyczną (Muster Befund)** przed przekazaniem do panelu lekarza?  
   Pacjent nie wypełnia ankiety medycznej, ankietę medyczną wypełnia tylko lekarz.

2. **Lista dzienna w Fazie 1–2 (ręczna):** W jaki sposób rejestrator ma uzupełniać listę – wyłącznie **ręczne dodawanie pojedynczego pacjenta** (imię, nazwisko, telefon, e-mail?), czy dopuszczalny **import z pliku (np. CSV/Excel)** na dany dzień?  

   Rejestracja może wprowadzić ręcznie nowego pacjenta lub wykonać import z pliku exel

3. **Link z tokenem do formularza na tablecie:** Czy link ma być **jednorazowy** (unieważniony po zapisaniu formularza), **ważny do końca dnia**, czy **bez limitu** do momentu wypełnienia?  
   Token jest ważny do pierwszego zapisu

4. **Snapshot treści zgód przy podpisaniu:** Skoro dodawanie zgód ma być rzadkie – czy przy zapisie formularza ma być **zapisana kopia treści** każdej zgody (tak jak była wyświetlona pacjentowi), np. w JSON, dla audytu i ewentualnych sporów?  
   Nie jest potrzebny snapshot zgód

5. **Outbox – sposób realizacji:** Czy zadania „zapis HiDrive” i „wyślij SMS” mają być realizowane przez **worker’a odczytującego tabelę Outbox** (np. Celery/Django-Q + cron), czy przez **cron, który cyklicznie przetwarza rekordy z flagami `hidrive_sent=false` / `sms_sent=false`**?  
   Wystraczy cron

6. **Mock HiDrive (zapis lokalny):** Czy ścieżka i struktura katalogów przy mocku (np. `MEDIA_ROOT/archive/ROK/MIESIĄC/`) mają **odzwierciedlać docelową strukturę HiDrive**, żeby przy przejściu na prawdziwe API zmieniła się tylko warstwa wysyłki, a nie ścieżki?  

   Mock używa tej samej konwencji ścieżek co docelowy HiDrive – ułatwi to Fazę 3.

---

Jeśli na te punkty nie ma już otwartych decyzji, można uznać zbiór pytań za zamknięty. Daj znać, czy mam przygotować **jednostronicowe podsumowanie do PRD** (zakres, fazy, kluczowe decyzje), czy wolisz jeszcze jedną rundę doprecyzowań.