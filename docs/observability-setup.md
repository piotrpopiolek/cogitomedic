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

- Szablon: [deploy/prometheus/alertmanager.yml.template](deploy/prometheus/alertmanager.yml.template) (**`webhook_configs`**) lub [deploy/prometheus/alertmanager.discord.yml.template](deploy/prometheus/alertmanager.discord.yml.template) (**`discord_configs`**, gdy `ALERTMANAGER_USE_DISCORD=1`) — te same placeholdery `__WEBHOOK_*__`.
- Przy starcie kontenera `alertmanager` (dev i prod compose) plik trafia do `/tmp/alertmanager.yml` (`sed` z separatorem `#`).
- **Zmienne:**
  - **`ALERTMANAGER_WEBHOOK_URL`** — domyślny receiver (`webhook_default`) oraz wartość domyślna dla critical/warning, jeśli nie podasz dedykowanych URL-i (domyślnie `http://127.0.0.1:5001/`).
  - **`ALERTMANAGER_WEBHOOK_CRITICAL_URL`** (opcjonalnie) — tylko alerty z etykietą `severity: critical` (np. backlog outbox, spike integracji).
  - **`ALERTMANAGER_WEBHOOK_WARNING_URL`** (opcjonalnie) — alerty `severity: warning` (np. LowSuccessRatio, postgres_exporter).
- **Routing:** `group_by: [alertname, severity]`; dla `critical` krótszy `group_wait` i częstszy `repeat_interval` niż dla `warning` (szczegóły w szablonie).
- **Inhibicja:** alert `critical` o danym `alertname` tłumi powiązane `warning` z tym samym `alertname` (mniej duplikatów w kanale ostrzeżeń).
- **Uwaga:** znaki `#` i `|` w URL mogą psuć `sed` — unikaj ich w webhooku lub zmień entrypoint na `envsubst` / inny mechanizm.
- **Godziny pracy (PRD):** ograniczenie alertu backlogu do godzin recepcji ustaw w Alertmanagerze (`mute_time_intervals` / osobne route), zamiast skomplikowanego PromQL z `hour()` (łatwo o błąd etykiet).

### Realne powiadomienia (zamiast `127.0.0.1:5001`)

Domyślny URL nie wysyła nic użytecznego. **Alertmanager wysyła POST z JSON-em** (format [webhook v4](https://prometheus.io/docs/alerting/latest/configuration/#webhook_config)) — potrzebujesz endpointu, który ten JSON przyjmie i coś z nim zrobi (kanał czatu, ticket, automatyzacja).

**Rekomendowane ścieżki:**

1. **Slack (najprostsza na start)**  
   Utwórz [Incoming Webhook](https://api.slack.com/messaging/webhooks) dla kanału (np. `#alerts`), skopiuj URL do `.env`:
   ```env
   ALERTMANAGER_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
   ```
   Opcjonalnie osobne kanały: `ALERTMANAGER_WEBHOOK_CRITICAL_URL` / `ALERTMANAGER_WEBHOOK_WARNING_URL`. Po zmianie `.env` zrestartuj kontener `alertmanager` (`docker compose up -d alertmanager`). W Slacku domyślny JSON bywa „brzydki” — możesz później wstawić [slack receiver](https://prometheus.io/docs/alerting/latest/configuration/#slack_config) w szablonie zamiast generycznego `webhook_configs` (osobna iteracja).

2. **Szybki test bez Slacka**  
   Wejdź na [webhook.site](https://webhook.site), skopiuj **unikalny URL** i wklej jako `ALERTMANAGER_WEBHOOK_URL`. Po stronie Alertmanagera: **Status** w UI (http://localhost:9093) — widać, czy wysyłka się udała; na stronie webhook.site zobaczysz treść POST.

3. **Discord**  
   Użyj natywnego receivera Alertmanagera (`discord_configs`) — instrukcja: sekcja [**Integracja z Discordem**](#integracja-z-discordem) poniżej. **Nie** wklejaj URL Discorda do trybu domyślnego (`webhook_configs`) — Discord oczekuje innego formatu wiadomości.

4. **n8n / PagerDuty / własny backend**  
   Endpoint HTTP przyjmujący POST (np. workflow „Webhook” w n8n) — ten sam `ALERTMANAGER_WEBHOOK_URL`. Tam parsujesz `alerts[]` i wysyłasz maila, SMS, ticket Jiry itd.

**Weryfikacja:** Prometheus → **Alerts** (firing) + Alertmanager http://localhost:9093 → zakładka z alertami / **Status** (błędy dostarczania). Jeśli URL zawiera `#`, obecny `sed` w compose może go zepsuć — wtedy tymczasowo użyj URL bez `#` albo zmień mechanizm renderowania szablonu.

## Integracja z Discordem

Discord nie wyświetli sensownie surowego JSON-a z `webhook_configs` Alertmanagera. Ten projekt obsługuje **natywny** [`discord_configs`](https://prometheus.io/docs/alerting/latest/configuration/#discord_config) po ustawieniu **`ALERTMANAGER_USE_DISCORD=1`** (wtedy przy starcie wybierany jest szablon [alertmanager.discord.yml.template](../deploy/prometheus/alertmanager.discord.yml.template)).

### 1. Utwórz webhook w Discordzie

1. Otwórz **Discord** (aplikacja lub przeglądarka) i wejdź na **serwer**, na którym mają lądować alerty.
2. Wybierz **kanał tekstowy** (np. `#alerty`) albo utwórz nowy: **Utwórz kanał** → typ **Tekstowy**.
3. Kliknij kanał prawym przyciskiem myszy → **Edytuj kanał** (lub ikona zębatki przy nazwie kanału).
4. Po lewej: **Integracje** → **Webhooki** (ang. *Webhooks*).
5. **Nowy webhook** / **Utwórz webhook**:
   - **Nazwa** — np. `Cogitomedica Alertmanager`,
   - **Kanał** — ten, na który mają trafiać wiadomości,
   - opcjonalnie awatar.
6. Kliknij **Kopiuj adres URL webhooka** (*Copy Webhook URL*).  
   Ma postać `https://discord.com/api/webhooks/<ID>/<TOKEN>`. **Traktuj go jak hasło** — kto ma URL, może pisać na kanale.

### 2. Ustaw zmienne w `.env` (repozytorium / serwer)

1. W katalogu projektu otwórz plik **`.env`** (nie commituj go; wzorzec jest w [`.env.example`](../.env.example)).
2. Dodaj lub zmień:

   ```env
   ALERTMANAGER_USE_DISCORD=1
   ALERTMANAGER_WEBHOOK_URL=https://discord.com/api/webhooks/TWOJ_ID/TWOJ_TOKEN
   ```

3. **Opcjonalnie** osobne kanały Discorda na krytyczne vs ostrzeżenia:
   - utwórz **drugi** (trzeci) webhook na innym kanale (powtórz kroki z punktu 1 na innym kanale),
   - w `.env` ustaw dodatkowo:

   ```env
   ALERTMANAGER_WEBHOOK_CRITICAL_URL=https://discord.com/api/webhooks/.../...
   ALERTMANAGER_WEBHOOK_WARNING_URL=https://discord.com/api/webhooks/.../...
   ```

   Jeśli któregoś z nich nie ustawisz, Alertmanager użyje wartości z `ALERTMANAGER_WEBHOOK_URL` (jak przy routingu opisanym wyżej).

4. Upewnij się, że **nie** masz jednocześnie intencji używać **Slacka** tym samym trybem: dla Slacka zostaw **`ALERTMANAGER_USE_DISCORD` wyłączone** (puste lub `0`) i adres Slacka tylko przy `webhook_configs` (domyślny szablon).

### 3. Zrestartuj Alertmanagera

Z katalogu z `docker-compose.yml`:

```bash
docker compose up -d alertmanager
```

(produkcja: `docker compose -f docker-compose.prod.yml --profile observability up -d alertmanager`)

### 4. Sprawdź, czy działa

1. **Alertmanager UI:** http://localhost:9093 → **Status** — brak błędów ładowania konfiguracji; po stronie **Alerts** zobaczysz aktywne alerty z Prometheusa.
2. **Kanał Discord** — po **wystrzelonym** alercie (np. gdy reguła jest w stanie *Firing*) powinna pojawić się wiadomość z embedem Alertmanagera (także przy **Resolved**, jeśli `send_resolved: true` w szablonie).
3. Jeśli nic nie przychodzi: w UI Alertmanagera sprawdź, czy alert jest wysłany do receivra; w logach kontenera `docker compose logs alertmanager` szukaj błędów HTTP (np. zły URL, odwołany webhook w Discordzie).

### Szybki test bez czekania na Prometheus

1. Po zmianie `.env`: `docker compose up -d alertmanager` (żeby wczytał szablon z `discord_configs`).
2. Wyślij **sztuczny alert** do API Alertmanagera (port **9093** musi być dostępny z maszyny, z której uruchamiasz polecenie — np. `localhost` przy `docker compose up`).

**Bash / Git Bash / WSL** (w **cmd** / PowerShell użyj `curl.exe` zamiast `curl`):

```bash
curl -sS -X POST http://localhost:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{"labels":{"alertname":"DiscordManualTest","severity":"critical"},"annotations":{"summary":"Test Discord"}}]'
```

**PowerShell:**

```powershell
$body = '[{"labels":{"alertname":"DiscordManualTest","severity":"critical"},"annotations":{"summary":"Test Discord"}}]'
Invoke-RestMethod -Uri "http://localhost:9093/api/v2/alerts" -Method Post -ContentType "application/json" -Body $body
```

3. **`severity: critical`** trafia do trasy krytycznej (`group_wait` ok. 10 s) — na Discordzie wiadomość powinna pojawić się w ciągu **kilkunastu sekund**. Dla ścieżki **warning** zmień w JSON `"severity":"warning"`.
4. **Sprzątanie:** w http://localhost:9093 → **Silences** → **New silence** z matcherem `alertname="DiscordManualTest"` (albo wycisz na 1 h), żeby nie spamowało przy `repeat_interval`.

### 5. Typowe problemy

| Problem | Co zrobić |
|--------|-----------|
| Wiadomości w ogóle nie dochodzą | Sprawdź `ALERTMANAGER_USE_DISCORD=1`, poprawność URL, restart `alertmanager`. |
| Błąd przy starcie Alertmanagera | Obraz musi być w miarę nowy (`prom/alertmanager` z obsługą `discord_configs`); `docker compose pull alertmanager`. |
| URL z znakiem `#` | Obecny `sed` w compose może zepsuć podstawianie — użyj URL bez `#` lub zmień sposób renderowania szablonu. |

## PostgreSQL — postgres_exporter

- Serwis **`postgres_exporter`** w [docker-compose.yml](../docker-compose.yml) (zawsze) oraz w [docker-compose.prod.yml](../docker-compose.prod.yml) z profilem **`observability`**: połączenie przez `DATA_SOURCE_URI` / `DATA_SOURCE_USER` / `DATA_SOURCE_PASS` (wartości z `.env`, spójne z kontenerem `db`).
- Port **9187** nie jest wystawiany na host — wyłącznie scrape wewnętrzny z Prometheusa.
- Alerty: [deploy/prometheus/alerts.yml](deploy/prometheus/alerts.yml) (`PostgresExporterTargetDown`, `PostgresDatabaseUnreachable`).

## Dysk hosta — node_exporter

- Serwis **`node_exporter`** ([prom/node-exporter](https://github.com/prometheus/node_exporter)) w [docker-compose.yml](../docker-compose.yml) oraz [docker-compose.prod.yml](../docker-compose.prod.yml) z profilem **`observability`**: montuje `/`, `/proc`, `/sys` hosta (read-only), scrape wewnętrzny z Prometheusa (job `node`, port **9100** — nie wystawiony na Internet).
- Metryka: `cogitomedica:node_root_filesystem_used_percent` (recording rule w [deploy/prometheus/alerts.yml](deploy/prometheus/alerts.yml)).
- Alerty Discord/Alertmanager: **`DiskUsageAbove50Percent`** … **`DiskUsageAbove90Percent`** (warning 50–70, critical 80–90); **`for: 10m`** ogranicza flapping na granicy progu. Po **spadku** zajętości (np. retencja lokalnych PDF po `PDF_RETENTION_DAYS`, domyślnie 60 dni) alerty przechodzą w **Resolved** — wiadomość na Discordzie, jeśli `send_resolved: true`.
- Przy wielu progach naraz Alertmanager wysyła tylko **najwyższy** (inhibit_rules w szablonach Alertmanagera).
- Runbook: [docs/runbooks/DISK_USAGE.md](runbooks/DISK_USAGE.md).
- **Grafana:** dashboard [deploy/grafana/provisioning/dashboards/cogitomedica-observability.json](../deploy/grafana/provisioning/dashboards/cogitomedica-observability.json) — panele **VPS — zajętość dysku root (%)** (stat) i **VPS — trend zajętości dysku (alerty 50–90%)** (timeseries z progami 50/70/80%).
- **Wdrożenie na prod:** po `git pull` uruchom `docker compose -f docker-compose.prod.yml --profile observability up -d node_exporter prometheus alertmanager grafana` (restart Grafany wczytuje zaktualizowany dashboard z provisioning).

## OTel Collector — spanmetrics → Prometheus

- Kolektor eksportuje metryki RED ze spanów na porcie **8889** (job Prometheus `otel_spanmetrics` w [deploy/prometheus/prometheus.yml.template](deploy/prometheus/prometheus.yml.template)).
- W Grafanie (Tempo → **Explore** z correlate to metrics) zapytania `tracesToMetrics` zakładają nazwy w stylu `calls_total` i `duration_milliseconds_bucket` — jeśli po upgrade OTel nazwy się zmienią, sprawdź w Prometheusie: **Status → Targets → otel_spanmetrics** i metryki z prefiksem `duration_` / `calls_`.

---

## Bezpieczeństwo endpointów observability

- **`GET /api/v1/observability/health`** — odpowiedź anonimowa jest **minimalna** (status / DB). Szczegółowe `checks` tylko z nagłówkiem `Authorization: Bearer <PROMETHEUS_METRICS_TOKEN>` lub po zalogowaniu jako ADMIN.
- **`GET /api/v1/observability/metrics`** — wyłącznie **Bearer** ten sam co `PROMETHEUS_METRICS_TOKEN` lub sesja ADMIN; przeznaczone dla Prometheusa (tożsamość maszynowa), nie dla personelu w przeglądarce bez tokena.
- **Sieć (prod):** w [docker-compose.prod.yml](../docker-compose.prod.yml) stack monitoringu jest za profilem **`observability`**. Gdy profil jest włączony, porty **3000 / 9090 / 9093 / 3200 / 4317–4318 / 8889** są na hoście domyślnie związane z **`127.0.0.1`** (`OBSERVABILITY_BIND_ADDR`, domyślnie loopback) — **nie** nasłuchują na publicznym adresie VPS. Dostęp do Grafany z laptopa: tunel SSH, np. `ssh -L 3000:127.0.0.1:3000 user@twoj-vps`, potem http://127.0.0.1:3000 . Test Alertmanagera z maszyny operatorskiej: to samo z `-L 9093:127.0.0.1:9093`. Świadome wystawienie na wszystkie interfejsy: `OBSERVABILITY_BIND_ADDR=0.0.0.0` w `.env` **i** reguły firewalla.
- **Alertmanager:** ustaw **`ALERTMANAGER_WEBHOOK_URL`** (oraz opcjonalnie `ALERTMANAGER_WEBHOOK_CRITICAL_URL` / `ALERTMANAGER_WEBHOOK_WARNING_URL`) w `.env`; dla Discorda dodatkowo **`ALERTMANAGER_USE_DISCORD=1`** — szablony: [deploy/prometheus/alertmanager.yml.template](deploy/prometheus/alertmanager.yml.template) / [deploy/prometheus/alertmanager.discord.yml.template](deploy/prometheus/alertmanager.discord.yml.template).

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
| Zajętość dysku VPS root (%) | `cogitomedica:node_root_filesystem_used_percent` — panele **VPS — zajętość dysku root (%)** / **VPS — trend zajętości dysku** na dashboardzie **Cogitomedica – Observability** |

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
