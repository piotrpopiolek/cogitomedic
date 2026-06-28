# Runbook: zajętość dysku VPS (alerty 50–90%)

Alerty Prometheus → Alertmanager → Discord (profil `observability`, `node_exporter`).

## Co monitorujemy

- Partycja **root** hosta (`/` widoczna w metrykach jako mountpoint `/rootfs` w kontenerze `node_exporter`).
- Progi: **50 / 60 / 70** (warning), **80 / 90** (critical), stan **Firing** po **10 min** powyżej progu.
- **Spadek zajętości:** gdy użycie spadnie poniżej progu (np. po retencji lokalnych PDF), alert przechodzi w **Resolved** — Discord dostaje wiadomość Resolved (`send_resolved: true`).
- **Wiele progów naraz:** Alertmanager wysyła tylko **najwyższy** aktywny próg (inhibit_rules); po zejściu np. z 85% do 75% znikają progi 90/80, aktywny zostaje 70%.

## Prometheus alerty vs Grafana

| | Progi wizualne / powiadomienia |
|--|-------------------------------|
| **Prometheus → Discord** | Osobne alerty co **10%**: **50, 60, 70, 80, 90** (`deploy/prometheus/alerts.yml`) |
| **Grafana** (dashboard **Cogitomedica – Observability**, panele VPS) | Linie progów kolorów: **50, 60, 70, 80, 90** — spójne z alertami; Grafana **nie wysyła** powiadomień, tylko trend |

Próg **60%** ma własną regułę alertu w Prometheusie (Discord po 10 min powyżej 60%). Na dashboardzie służy do odczytu trendu w tym samym miejscu co pozostałe progi — bez dodatkowej konfiguracji w Grafanie.

## Szybka diagnostyka (SSH na VPS)

```bash
df -h /
docker system df -v
sudo du -h --max-depth=1 /var | sort -hr | head -10
```

Typowe źródła w Cogitomedica:

| Źródło | Gdzie |
|--------|--------|
| Wolumeny Docker | `/var/lib/docker` (Postgres, `media_data`, Prometheus, Tempo…) |
| Lokalne PDF | wolumen `media_data` — kasowane przez `run_retention_cleanup` gdy `hidrive_sent && sms_sent` i wiek > `PDF_RETENTION_DAYS` (domyślnie **60 dni**) |
| Obrazy Docker | `docker images` — `docker image prune` po weryfikacji |

## Retencja a alerty

Wzrost zajętości może być **sezonowy** (więcej publikacji Befund → więcej PDF w `MEDIA_ROOT` przez okno 60 dni). Po cronie retencji część plików znika — **zajętość może spaść** i alerty się zamkną bez ręcznej interwencji. Jeśli dysk rośnie **mimo** działającego schedulera, sprawdź outbox/DEAD_LETTER i czy retencja faktycznie usuwa pliki (`local_pdf_deleted_at`).

## Eskalacja

| Poziom | Działanie |
|--------|-----------|
| 50–70% | Obserwacja; trend na Grafanie: **Dashboards → Cogitomedica – Observability** → panele **VPS — zajętość dysku root (%)** / **VPS — trend zajętości dysku** (`cogitomedica:node_root_filesystem_used_percent`). |
| 80% | Zaplanuj cleanup: `docker system prune`, starych obrazów, rozmiar `media_data`; rozważ większy dysk VPS. |
| 90% | Pilne — ryzyko awarii Postgres/aplikacji; nie używaj `docker volume prune` bez listy wolumenów. |

## Weryfikacja stacku monitoringu

```bash
cd ~/cogitomedica
docker compose -f docker-compose.prod.yml --profile observability ps node_exporter prometheus
```

Test z kontenera Prometheusa (uwaga: **http://** w URL — bez tego `wget` zgłasza `bad address`):

```bash
docker compose -f docker-compose.prod.yml --profile observability exec prometheus \
  wget -qO- 'http://node_exporter:9100/metrics' | head -3
```

Jeśli `bad address` mimo poprawnego URL — Prometheus nie widzi `node_exporter` w sieci Compose (częste po dodaniu serwisu bez recreate Prometheusa):

```bash
docker compose -f docker-compose.prod.yml --profile observability up -d --force-recreate prometheus
```

Po recreate sprawdź ponownie `wget` i **Targets** (job `node` = UP). Alert `NodeExporterTargetDown` powinien przejść w **Resolved** w ciągu ~5 min.

Prometheus (tunel SSH `-L 9090:127.0.0.1:9090`):

- **Targets** → job `node` = UP
- **Graph** → `cogitomedica:node_root_filesystem_used_percent`

Grafana (tunel SSH `-L 3000:127.0.0.1:3000`):

- **Dashboards → Cogitomedica – Observability** — panele dysku na dole dashboardu (stat + trend, progi kolorów **50 / 60 / 70 / 80 / 90**).

## Powiązane

- [docs/observability-setup.md](../observability-setup.md) — node_exporter, Discord
- `PDF_RETENTION_DAYS` — [cogitomedica/settings.py](../../cogitomedica/settings.py)
- Backlog backupów — [.ai/TODO.md](../../.ai/TODO.md)
