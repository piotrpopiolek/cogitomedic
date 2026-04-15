# Observability – Prometheus, Grafana, dashboard

## Adresy usług monitorowania

Przy uruchomionym stosie Docker (`docker compose up`) usługi monitorowania są dostępne pod następującymi adresami (na hoście z Dockerem zamień `localhost` na odpowiedni host lub IP):

| Usługa | URL | Uwagi |
|--------|-----|--------|
| **Health (aplikacja)** | http://localhost:8000/api/v1/observability/health | Health check (GET, bez auth). W Swagger UI: sekcja **Observability**. |
| **Metryki Prometheus (aplikacja)** | http://localhost:8000/api/v1/observability/metrics | Eksport metryk dla Prometheusa. Wymaga `Authorization: Bearer <PROMETHEUS_METRICS_TOKEN>` lub sesji ADMIN. W Swagger UI: sekcja **Observability**. |
| **Grafana** | http://localhost:3000 | Dashboardy, Explore (Prometheus + Tempo). Domyślne logowanie: `admin` / `admin`. |
| **Prometheus** | http://localhost:9090 | Zapytania PromQL, konfiguracja, [targety](http://localhost:9090/targets). |
| **Alertmanager** | http://localhost:9093 | Lista alertów, status wysyłek, konfiguracja receiverów. |
| **Grafana Tempo** | http://localhost:3200 | Backend trace’ów; w praktyce używany z Grafany (Explore → wybór datasource **Tempo**). |
| **OTel Collector** | `localhost:4317` (gRPC), `localhost:4318` (HTTP) | Odbiera trace’y OTLP z aplikacji; brak UI – tylko wewnętrzne połączenia z kontenerów `web` i `scheduler`. |
| **postgres_exporter** | (brak mapowania na host) | Metryki PostgreSQL tylko w sieci Docker; Prometheus scrapuje `postgres_exporter:9187` (job `postgres`). Te same `DB_NAME` / `DB_USER` / `DB_PASSWORD` co aplikacja. |

---

## Alertmanager (webhook z `.env` + routing po `severity`)

- Szablon: [deploy/prometheus/alertmanager.yml.template](deploy/prometheus/alertmanager.yml.template) — placeholdery `__WEBHOOK_DEFAULT__`, `__WEBHOOK_CRITICAL__`, `__WEBHOOK_WARNING__`.
- Przy starcie kontenera `alertmanager` (dev i prod compose) plik trafia do `/tmp/alertmanager.yml` (`sed` z separatorem `#`).
- **Zmienne:**
  - **`ALERTMANAGER_WEBHOOK_URL`** — domyślny receiver (`webhook_default`) oraz wartość domyślna dla critical/warning, jeśli nie podasz dedykowanych URL-i (domyślnie `http://127.0.0.1:5001/`).
  - **`ALERTMANAGER_WEBHOOK_CRITICAL_URL`** (opcjonalnie) — tylko alerty z etykietą `severity: critical` (np. backlog outbox, spike integracji).
  - **`ALERTMANAGER_WEBHOOK_WARNING_URL`** (opcjonalnie) — alerty `severity: warning` (np. LowSuccessRatio, postgres_exporter).
- **Routing:** `group_by: [alertname, severity]`; dla `critical` krótszy `group_wait` i częstszy `repeat_interval` niż dla `warning` (szczegóły w szablonie).
- **Inhibicja:** alert `critical` o danym `alertname` tłumi powiązane `warning` z tym samym `alertname` (mniej duplikatów w kanale ostrzeżeń).
- **Uwaga:** znaki `#` i `|` w URL mogą psuć `sed` — unikaj ich w webhooku lub zmień entrypoint na `envsubst` / inny mechanizm.
- **Godziny pracy (PRD):** ograniczenie alertu backlogu do godzin recepcji ustaw w Alertmanagerze (`mute_time_intervals` / osobne route), zamiast skomplikowanego PromQL z `hour()` (łatwo o błąd etykiet).

## PostgreSQL — postgres_exporter

- Serwis **`postgres_exporter`** w [docker-compose.yml](../docker-compose.yml) / [docker-compose.prod.yml](../docker-compose.prod.yml): połączenie przez `DATA_SOURCE_URI` / `DATA_SOURCE_USER` / `DATA_SOURCE_PASS` (wartości z `.env`, spójne z kontenerem `db`).
- Port **9187** nie jest wystawiany na host — wyłącznie scrape wewnętrzny z Prometheusa.
- Alerty: [deploy/prometheus/alerts.yml](deploy/prometheus/alerts.yml) (`PostgresExporterTargetDown`, `PostgresDatabaseUnreachable`).

## OTel Collector — spanmetrics → Prometheus

- Kolektor eksportuje metryki RED ze spanów na porcie **8889** (job Prometheus `otel_spanmetrics` w [deploy/prometheus/prometheus.yml.template](deploy/prometheus/prometheus.yml.template)).
- W Grafanie (Tempo → **Explore** z correlate to metrics) zapytania `tracesToMetrics` zakładają nazwy w stylu `calls_total` i `duration_milliseconds_bucket` — jeśli po upgrade OTel nazwy się zmienią, sprawdź w Prometheusie: **Status → Targets → otel_spanmetrics** i metryki z prefiksem `duration_` / `calls_`.

---

## Bezpieczeństwo endpointów observability

- **`GET /api/v1/observability/health`** — odpowiedź anonimowa jest **minimalna** (status / DB). Szczegółowe `checks` tylko z nagłówkiem `Authorization: Bearer <PROMETHEUS_METRICS_TOKEN>` lub po zalogowaniu jako ADMIN.
- **`GET /api/v1/observability/metrics`** — wyłącznie **Bearer** ten sam co `PROMETHEUS_METRICS_TOKEN` lub sesja ADMIN; przeznaczone dla Prometheusa (tożsamość maszynowa), nie dla personelu w przeglądarce bez tokena.
- **Sieć:** na produkcji nie wystawiaj publicznie portów Grafana/Prometheus/Alertmanager/Tempo ani portu aplikacji używanego wyłącznie do scrapingu — użyj sieci Docker, VPN lub firewalla (patrz komentarze w `docker-compose.prod.yml`).
- **Alertmanager:** ustaw **`ALERTMANAGER_WEBHOOK_URL`** (oraz opcjonalnie `ALERTMANAGER_WEBHOOK_CRITICAL_URL` / `ALERTMANAGER_WEBHOOK_WARNING_URL`) w `.env`; szablon: [deploy/prometheus/alertmanager.yml.template](deploy/prometheus/alertmanager.yml.template).

---

## Gotowy dashboard (dashboard-as-code)

W repozytorium jest gotowy dashboard w formacie JSON:

- **Ścieżka:** `deploy/grafana/provisioning/dashboards/cogitomedica-observability.json`
- **Kopia (do ręcznego importu):** `deploy/grafana/dashboards/cogitomedica-observability.json`

Przy starcie kontenera Grafany (z `docker compose up`) dashboard jest **automatycznie ładowany** dzięki provisioningowi (`deploy/grafana/provisioning/`). Źródło danych Prometheus też jest dodawane z pliku `deploy/grafana/provisioning/datasources/datasources.yml`.

Po wejściu na http://localhost:3000 (admin/admin) w menu po lewej: **Dashboards → Cogitomedica → Cogitomedica – Observability**.

---

## Ręczny import dashboardu

Jeśli provisioning nie działa lub chcesz zaimportować dashboard w innej instancji Grafany:

1. Zaloguj się do Grafany (np. http://localhost:3000).
2. Menu **☰ → Dashboards → New → Import**.
3. Kliknij **Upload JSON file** i wskaż plik `deploy/grafana/dashboards/cogitomedica-observability.json` (lub wklej jego zawartość do pola **Import via panel json**).
4. Wybierz źródło danych **Prometheus** (UID musi być `prometheus`, jeśli dodałeś datasource ręcznie – przy tworzeniu ustaw UID na `prometheus`).
5. Kliknij **Import**.

---

## Jak dodać nowe panele

### 1. Otwórz dashboard

Wejdź w **Dashboards → Cogitomedica → Cogitomedica – Observability** i kliknij **Add → Visualization** (lub **Edit** na istniejącym panelu).

### 2. Wybierz źródło danych i wpisz PromQL

W nowym panelu:

- **Data source:** Prometheus.
- W polu **Query** (PromQL) wpisz jedno z wyrażeń poniżej.

### 3. Przykładowe zapytania PromQL (metryki Cogitomedica)

| Opis | PromQL |
|------|--------|
| Liczba zdarzeń outbox po typie i statusie | `cogitomedica_outbox_events_total` |
| Najstarszy pending (w sekundach) | `max(cogitomedica_outbox_pending_age_seconds)` |
| Wiek pending per typ zdarzenia | `cogitomedica_outbox_pending_age_seconds` |
| Średni czas przetwarzania (publish→done) | `cogitomedica_outbox_processing_duration_seconds_sum / cogitomedica_outbox_processing_duration_seconds_count` |
| Batche importu po statusie | `sum by (status) (cogitomedica_import_batches_total)` |
| Wiersze importu (inserted / error) | `cogitomedica_import_rows_total` |
| Success ratio HiDrive / SMS (runtime Counter; 1h) | `sum(rate(cogitomedica_outbox_executions_total{stream="befund",result="success",event_type="HIDRIVE_UPLOAD"}[1h])) / sum(rate(cogitomedica_outbox_executions_total{stream="befund",event_type="HIDRIVE_UPLOAD"}[1h]))` (analogicznie `SMS_SEND`) |
| Intake outbox (snapshot DB) | `cogitomedica_intake_outbox_events_total` |
| Intake pending age | `cogitomedica_intake_outbox_pending_age_seconds` |
| Tempo zakończeń outbox (worker) | `sum by (stream,event_type,result) (rate(cogitomedica_outbox_executions_total[5m]))` |
| Import batch zakończone (Counter) | `rate(cogitomedica_import_batches_completed_total[1h])` |
| p95 publish→processed (Histogram) | `histogram_quantile(0.95, sum by (le, stream, event_type) (rate(cogitomedica_outbox_publish_to_processed_seconds_bucket[15m])))` |

### 4. Typ panelu

- **Time series** – wykres w czasie (np. `cogitomedica_outbox_events_total`, średni czas).
- **Stat** – jedna wartość (np. max pending age, liczba batchy).
- **Table** – wiele serii w tabeli (w Query wybierz format **Table** lub użyj panelu typu Table).

### 5. Zapisz i wyeksportuj do repozytorium (dashboard-as-code)

1. Zapisz dashboard (**Save dashboard**).
2. Kliknij **Share dashboard → Export → Save to file** – pobierze się plik JSON.
3. Zastąp nim plik w repo:  
   `deploy/grafana/provisioning/dashboards/cogitomedica-observability.json`  
   (oraz opcjonalnie `deploy/grafana/dashboards/cogitomedica-observability.json`).
4. Zrób commit – przy następnym starcie Grafaną ten dashboard będzie ładowany z repo.

---

## Uwagi

- Datasource Prometheus musi mieć w Grafanie **UID = `prometheus`** (przy dodawaniu ręcznym można to ustawić), inaczej panele nie znajdą źródła.
- Odświeżanie dashboardu jest ustawione na 30 s; można to zmienić w ustawieniach dashboardu (ikona zębatki).
- Runbooki dla alertów: `docs/runbooks/`.

---

## Troubleshooting: „No data” na wszystkich panelach

1. **Sprawdź, czy Prometheus scrapuje aplikację**
   - Otwórz http://localhost:9090/targets (lub `http://<host>:9090/targets`).
   - Znajdź job **cogitomedica_web**. Status powinien być **UP**.
   - Jeśli jest **DOWN** lub **Unknown**: błąd połączenia lub **401 Unauthorized** (zły/brak tokena).

2. **Ustaw token w `.env`**
   - W katalogu projektu w pliku `.env` musi być zmienna:  
     `PROMETHEUS_METRICS_TOKEN=twoj-bezpieczny-token`  
     (np. długi losowy string).
   - **Ta sama wartość** musi trafić do Prometheusa – w `docker-compose` Prometheus dostaje `.env` przez `env_file`, a w `prometheus.yml.template` używana jest zmienna `${PROMETHEUS_METRICS_TOKEN}` (podstawiana przy starcie kontenera).
   - Po zmianie `.env` zrestartuj stos:  
     `docker compose down && docker compose up -d`.

3. **Sprawdź endpoint metryk z hosta**
   - Z maszyny, na której działa Docker (np. w PowerShell):  
     `Invoke-WebRequest -Uri "http://localhost:8000/api/v1/observability/metrics" -Headers @{ Authorization = "Bearer TWOJ_TOKEN_Z_ENV" } -UseBasicParsing`
   - Powinna wrócić odpowiedź 200 i tekst z liniami typu `cogitomedica_outbox_events_total` lub `cogitomedica_import_rows_total`.  
   - Jeśli 401 – token w nagłówku nie zgadza się z `PROMETHEUS_METRICS_TOKEN` w Django (czyli w `.env` dla kontenera `web`).
   - Jeśli **400 Bad Request** – najczęściej brak `web` w `ALLOWED_HOSTS`. Prometheus wysyła żądanie z hosta `web:8000`; w `.env` ustaw np. `ALLOWED_HOSTS=localhost,127.0.0.1,web`.

4. **Pusta baza**
   - Aplikacja emituje metryki także przy braku zdarzeń (wartości 0). Jeśli Prometheus ma status UP i token jest poprawny, po minucie odświeżenia w Grafanie powinny pojawić się zera zamiast „No data”.
