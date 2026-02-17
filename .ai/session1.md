1. **Kto będzie posiadał dane dostępowe / kontakt techniczny do Doctolib i jakie dokładnie dane mają być pre-fillowane (imię, nazwisko, data urodzenia, PESEL, numer wizyty, inne)?**  
   Wyszczególniamy sekcję integracja/eksport z doctolib lub ewentualne dodanie ręczne 
   Wymagane dane (imię, nazwisko, adres, data urodzenia, telefon, email)

2. **Czy lista dokumentów do Kroku 1 (Zgody) jest zamknięta: Datenschutz.pdf, DE_Einverstaendnis_PrivatBehandlung.pdf, Anamnesebogen.pdf, Einwilligungserklärung.pdf – czy planowane są kolejne dokumenty?**  
   Lista dokumentów nie jest istotna, wszyskie zgody zostaną przełożone na checkboxy i pola informacyjne.

3. **Jak dokładnie ma wyglądać „część medyczna” (Krok Lekarza): jakie pola są obowiązkowe (np. rozpoznanie ICD, zalecenia, kod procedury, opis badania) i czy są na to wewnętrzne wytyczne lub szablony?**  
   Formularz będzie się składał z różnych pól, checkboxow, predefiniowanych list, pól opisowych itd.

4. **Czy flow zatwierdzenia ma być dokładnie: „Zapisz jako szkic” (edycja później) oraz „Zatwierdź i wyślij do pacjenta” (blokada edycji + HiDrive + SMS + wyniki w portalu)?**  
   Dokument może być w dwóch stanach przed publikacją (np jako szkic) oraz opublikowany, dopuszczamy możliwość zmiany w opublikowanym dokumencie i ponownej jego wysyłce.
   Wykorzystajmy Wzorzec Transactional Outbox to rozwiązanie problemu "podwójnego zapisu" (Dual Write Problem).

5. **Jak ma działać integracja z HiDrive: dostęp (OAuth / API / WebDAV), docelowa struktura folderów (np. Archiwum/ROK/MIESIĄC/pacjent), obsługa błędów (retry, kolejka, alerty)?**  
    Dostęp po API, docelowa struktrura do ustalenia później, zcelania zadań do kolejki, crona. Monitoring przez OpenTelemetry 

6. **Jakie mierzalne wskaźniki sukcesu ma spełniać produkt (np. skrócenie czasu rejestracji, odsetek formularzy wypełnionych bez błędów, liczba lekarzy korzystających z panelu)?**  
   Pomijamy wskaźniki.

7. **Czy tablet ma być jeden na recepcję (rejestrator otwiera formularz dla wywołanego pacjenta), czy wiele tabletów z możliwością wyboru pacjenta z listy dziennej?**  
   Będą do dyspozycji 4 tablety. Rejestrator otwiera formularz dla pacjenta z listy dziennej. 

8. **W jakiej kolejności realizować zakres: najpierw Doctolib, potem panel lekarza, potem HiDrive, czy najpierw dokończenie flow tabletu (np. ankieta Muster Befund) i PDF, a integracje później?**  
   W PRD wprowadzić fazy (np. Faza 1: tablet + zgody + schemat + podpis; Faza 2: panel lekarza + zatwierdzenie; Faza 3: Doctolib + HiDrive) z jasnymi kryteriami zakończenia fazy i zależnościami między nimi.

9. **Jak ma działać automatyczne usuwanie wyników z portalu po 30 dniach: harmonogram (cron), czy pacjent dostaje przypomnienie przed usunięciem, czy kopia w HiDrive jest jedyną po usunięciu?**  
    Cron usuwa PDF które mają powyżej 30 dni od publikacji, jedyna kopia pozostaje w HiDrive, zapis o usunięciu do logów. 

10. **Czy treści prawniczne zgód (szczególnie w wersji cyfrowej z podpisem) zostały lub zostaną zaopiniowane przez prawnika pod kątem RODO i prawa niemieckiego?**  
    Nie dotyczy
