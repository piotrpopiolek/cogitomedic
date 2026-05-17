# Checklista zrzutów ekranu (staging / demo)

Pełny zestaw plików z poniższej tabeli jest **generowany automatycznie** przez [`scripts/capture_manual_screenshots.py`](../../scripts/capture_manual_screenshots.py) (zob. [assets/screenshots/README.md](/docs/manual/assets/screenshots/README.md)). Przy ręcznym dogrywaniu zrzutów użyj danych zanonimizowanych i tych samych nazw plików w `assets/screenshots/`.

## Recepcja (`01-rejestracja`)


| #   | Plik                                      | Ekran                         |
| --- | ----------------------------------------- | ----------------------------- |
| 1   | `reception-01-admin-login.png`            | `/admin/login/`               |
| 2   | `reception-02-reception-dashboard.png`    | `/admin/reception-dashboard/` |
| 3   | `reception-03-daily-queue-changelist.png` | Admin → Daily queues          |
| 4   | `reception-04-master-detail.png`          | Widok master-detail kolejek   |
| 5   | `reception-05-queue-entry-add.png`        | Dodawanie/edycja Queue entry  |
| 6   | `reception-06-import-xlsx.png`            | Import XLSX                   |
| 7   | `reception-07-intake-documents-list.png`  | `/admin/intake-documents/`    |
| 8   | `reception-08-intake-document-detail.png` | Szczegóły intake + PDF        |


## Wgranie zewnętrznego badania (`07-wgranie-zewnetrznego-badania`)

Zrzuty z **UI huba** (Unfold): sidebar „Zewnętrzne badanie”, dashboard recepcji (skróty), `/admin/external-upload/`, `/admin/external-upload/<uuid>/`. Pliki PNG w `assets/screenshots/` — zgodnie z [assets/screenshots/README.md](/docs/manual/assets/screenshots/README.md); automatyzacja: [`scripts/capture_manual_screenshots.py`](../../scripts/capture_manual_screenshots.py).

| #   | Plik | Ekran / uwagi |
| --- | ---- | ------------- |
| 0   | `reception-external-upload-00-sidebar.png` | Fragment sidebara z sekcją „Zewnętrzne badanie” (link do huba) |
| 1   | `reception-external-upload-01-hub.png` | `/admin/external-upload/` — filtr statusu intake + pole wyboru wpisu w jednej karcie |
| 2   | `reception-external-upload-02-entry-identity.png` | `/admin/external-upload/<uuid>/` — blok tożsamości pacjenta / wizyty |
| 3   | `reception-external-upload-03-entry-upload-select.png` | Ten sam URL: upload PDF + lista załączników / radio wybór (wg stanu danych) |
| 4   | `reception-external-upload-04-preview.png` | Link „Open PDF preview” (opcjonalnie karta z podglądem w przeglądarce) |
| 5   | `reception-external-upload-05-publish-confirm.png` | Formularz publikacji: locale, checkbox SMS, drugie potwierdzenie, Publish |


## Zmiana danych pacjenta (`06-zmiana-danych-pacjenta`)


| #   | Plik | Ekran |
| --- | ---- | ----- |
| 1   | `reception-patient-01-changelist.png` | `/admin/reception/patient/` — lista |
| 2   | `reception-patient-02-search-results.png` | Lista po wyszukiwaniu (demo: jednoznaczny e-mail) |
| 3   | `reception-patient-03-identity-before-edit.png` | Edycja — imię, nazwisko, DOB, telefon **przed** zmianą |
| 4   | `reception-patient-04-identity-after-edit.png` | Te same pola **po** wpisaniu nowych wartości, przed **Save** |
| 5   | `reception-patient-05-save-confirmation.png` | Komunikat sukcesu po zapisie korekty tożsamości/kontaktu |

*Logowanie do admina: wspólny zrzut `reception-01-admin-login.png` (rozdział recepcja).*


## Tablet (`02-tablet`)


| #   | Plik                               | Ekran                                            |
| --- | ---------------------------------- | ------------------------------------------------ |
| 0   | `tablet-00-unassigned-warning.png` | (opcjonalnie) komunikat braku placówki na tablet |
| 1   | `tablet-01-login.png`              | `/tablet/login/`                                 |
| 2   | `tablet-02-home-queues.png`        | `/tablet/`                                       |
| 3   | `tablet-03-queue-entries.png`      | `/tablet/queue/<uuid>/`                          |
| 4   | `tablet-04-entry-started.png`      | Po starcie sesji / `entry_started`               |
| 5   | `tablet-05-form-locale.png`        | Formularz — nagłówek / locale                    |
| 6   | `tablet-06-form-sections.png`      | Ankieta / zgody                                  |
| 7   | `tablet-07-body-map.png`           | Schemat ciała                                    |
| 8   | `tablet-08-signature.png`          | Podpis                                           |
| 9   | `tablet-09-form-submitted.png`     | `form_submitted`                                 |


## Lekarz (`03-doktor`)


| #   | Plik                            | Ekran                             |
| --- | ------------------------------- | --------------------------------- |
| 1   | `doctor-01-login.png`           | `/doctor/login/`                  |
| 2   | `doctor-02-list-filters.png`    | `/doctor/` z filtrami             |
| 3   | `doctor-03-error-no-intake.png` | (opcjonalnie) błąd brak ankiety   |
| 4   | `doctor-04-befund-section.png`  | `/doctor/<uuid>/` fragment Befund |


## Administrator (`04-administrator`)


| #   | Plik                       | Ekran                        |
| --- | -------------------------- | ---------------------------- |
| 1   | `admin-01-index.png`       | `/admin/` indeks             |
| 2   | `admin-02-staff-user.png`  | Staff user — grupy + kliniki |
| 3   | `admin-03-import-xlsx.png` | Import XLSX (admin/recepcja) |


## Pacjent (`05-pacjent-wyniki`)


| #   | Plik                       | Ekran         |
| --- | -------------------------- | ------------- |
| 1   | `patient-01-login.png`     | `/` login     |
| 2   | `patient-02-otp.png`       | `/otp/`       |
| 3   | `patient-03-documents.png` | `/documents/` |


## Przegląd (`00-przeglad`)


| #   | Plik                              | Uwagi                                                  |
| --- | --------------------------------- | ------------------------------------------------------ |
| 1   | `overview-01-process-diagram.png` | Opcjonalny diagram (np. eksport z Mermaid lub draw.io) |


