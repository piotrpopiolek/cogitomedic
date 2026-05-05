# Ścieżka papierowa — przepływ operacyjny (T1 / T1′ / T2)

Ten dokument jest **skrótowym opisem procesu** i uzupełnia [instrukcję lekarza](03-doktor.md) oraz [procedurę administratora / managera](04-administrator-paper-intake.md). Proces jest dwuetapowy: najpierw autoryzacja (T1), potem utworzenie dokumentu medycznego (T2).

## Diagram przepływu

```mermaid
flowchart TB
  subgraph t1 ["T1 — Admin / Manager"]
    W["QueueEntry WAITING (brak SUBMITTED intake)"]
    A["PaperIntakeAuthorization — kolejka nadal WAITING"]
    W -->|authorize + reason| A
  end

  subgraph list ["Lista lekarza /doctor/"]
    B["Stan B: akcja utworzenia dokumentu papierowego"]
    A -.->|wpis widoczny| B
  end

  subgraph t2 ["T2 — Doctor / Admin / Manager"]
    M["MedicalDocument PAPER_INTAKE, intake null"]
    PIC["QueueEntry: PAPER_INTAKE_COMPLETED"]
    B -->|potwierdzenie i utworzenie| M
    M --> PIC
  end

  subgraph revoke ["T1′ lub auto-revoke"]
    R1["Revoke ręczny przed dokumentem"]
    R2["Auto-revoke: cyfrowy submit"]
    R3["Auto-revoke: CANCELLED"]
    A --> R1
    A -.-> R2
    A -.-> R3
  end
```

## Tabela ról i skutków

| Krok | Kto | Skutek w systemie |
|------|-----|-------------------|
| **T1** | **Admin** lub **Manager** | Powstaje autoryzacja ścieżki papierowej. Wpis kolejki pozostaje na etapie oczekiwania. |
| **T1′** | **Admin** lub **Manager** | Cofnięcie autoryzacji (tylko gdy dokument medyczny jeszcze nie istnieje). |
| **T2** | **Doctor**, **Admin** lub **Manager** | Powstaje dokument papierowy, a wpis kolejki przechodzi do statusu „paper intake completed”. |

## Różnica względem ścieżki cyfrowej (tablet)

| Aspekt | Cyfrowa ankieta | Ścieżka papierowa |
|--------|-----------------|-------------------|
| Wejście lekarza w dokument | Zwykle z listy po wysłanej ankiecie lub przy istniejącym dokumencie | Po T2 — ten sam panel **Befund**; wcześniej dokument tworzy się z listy po autoryzacji papierowej |
| Status kolejki po „ankiecie” | **PATIENT_COMPLETED** (po wysłaniu formularza) | **PAPER_INTAKE_COMPLETED** dopiero po utworzeniu dokumentu medycznego |
| Cofnięcie | Inne reguły anulowania wizyty / intake | Autoryzację papieru można cofnąć **tylko przed T2**; **nie ma** cofania samego dokumentu utworzonego w tej ścieżce z poziomu tego przepływu. |

## Punkty synchronizacji (auto-revoke)

System automatycznie usuwa ważność autoryzacji papierowej, gdy:

1. Pacjent ukończy i wyśle cyfrową ankietę na tablecie.
2. Wpis kolejki zostanie oznaczony jako anulowany.

W obu przypadkach nie opieraj dalszej pracy na ścieżce papierowej. Odśwież listę i panel `/admin/paper-intake/`.

## Dowód papierowy poza systemem

CogitoMedica zapisuje informację o decyzji (kto, kiedy, powód, powiązanie z wpisem i dokumentem). Nie przechowuje skanu ani treści papierowej ankiety — sposób przechowywania papieru opisuje regulamin placówki.

Powiązane: [04-administrator-paper-intake.md](04-administrator-paper-intake.md), [03-doktor.md](03-doktor.md), [04-administrator.md](04-administrator.md).
