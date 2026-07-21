"""
Lightweight Prometheus scrape endpoint for the scheduler process.

Outbox Counter/Histogram live in the process that runs ImmediateBackend tasks
(``run_periodic_tasks``). Prometheus must scrape that process; Django ``web``
alone never sees those increments.
"""

from __future__ import annotations

import hmac
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from socketserver import BaseServer

logger = logging.getLogger(__name__)

_METRICS_PATH = "/api/v1/observability/metrics"
_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

_server: ThreadingHTTPServer | None = None
_server_lock = threading.Lock()


def build_runtime_metrics_payload() -> bytes:
    """
    Process-local Counters/Histograms only (no ORM Gauges).

    Avoids double-counting DB snapshot gauges when both ``web`` and ``scheduler``
    are scraped.
    """
    from prometheus_client import generate_latest

    from apps.operations.prom_metrics import _registry

    return generate_latest(_registry)


def _bearer_authorized(authorization: str | None) -> bool:
    token = getattr(settings, "PROMETHEUS_METRICS_TOKEN", None)
    if not token or not authorization:
        return False
    expected = f"Bearer {token}"
    if len(authorization) != len(expected):
        return False
    return hmac.compare_digest(authorization, expected)


class _MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        logger.debug("scheduler-metrics: " + format, *args)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != _METRICS_PATH:
            self.send_error(404, "Not Found")
            return
        if not _bearer_authorized(self.headers.get("Authorization")):
            self.send_response(401)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"unauthorized\n")
            return
        payload = build_runtime_metrics_payload()
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPE)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start_scheduler_metrics_server(*, host: str = "0.0.0.0", port: int) -> BaseServer:
    """
    Start a daemon HTTP server exposing runtime metrics.

    Idempotent: a second call with the same process returns the existing server.
    """
    global _server
    with _server_lock:
        if _server is not None:
            return _server
        server = ThreadingHTTPServer((host, port), _MetricsHandler)
        thread = threading.Thread(
            target=server.serve_forever,
            name="scheduler-prometheus-metrics",
            daemon=True,
        )
        thread.start()
        _server = server
        logger.info(
            "Scheduler Prometheus metrics listening on http://%s:%s%s",
            host,
            port,
            _METRICS_PATH,
        )
        return server
