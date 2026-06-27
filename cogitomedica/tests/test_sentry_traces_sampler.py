"""Unit tests for Sentry Performance trace sampling."""

from __future__ import annotations

from django.test import SimpleTestCase

from cogitomedica.sentry_sampling import (
    is_observability_request_path,
    parse_sentry_traces_sample_rate,
    sentry_traces_sampler,
)


class SentryTracesSamplerTests(SimpleTestCase):
    def test_is_observability_request_path(self) -> None:
        self.assertTrue(is_observability_request_path("/api/v1/observability/metrics"))
        self.assertTrue(is_observability_request_path("/api/v1/observability/health"))
        self.assertTrue(
            is_observability_request_path("/api/v1/observability/monitoring/prometheus")
        )
        self.assertFalse(is_observability_request_path("/api/v1/medical-documents"))
        self.assertFalse(is_observability_request_path("/accounts/login/"))

    def test_sampler_returns_zero_for_observability_wsgi_path(self) -> None:
        rate = sentry_traces_sampler(
            {
                "wsgi_environ": {"PATH_INFO": "/api/v1/observability/metrics"},
            },
            default_sample_rate=0.1,
        )
        self.assertEqual(rate, 0.0)

    def test_sampler_returns_default_for_business_path(self) -> None:
        rate = sentry_traces_sampler(
            {
                "wsgi_environ": {"PATH_INFO": "/api/v1/queue-entries"},
            },
            default_sample_rate=0.1,
        )
        self.assertEqual(rate, 0.1)

    def test_sampler_returns_zero_for_observability_transaction_name(self) -> None:
        rate = sentry_traces_sampler(
            {
                "transaction_context": {
                    "name": "GET /api/v1/observability/health",
                },
            },
            default_sample_rate=0.25,
        )
        self.assertEqual(rate, 0.0)

    def test_sampler_inherits_parent_sampled(self) -> None:
        rate = sentry_traces_sampler(
            {
                "parent_sampled": True,
                "wsgi_environ": {"PATH_INFO": "/api/v1/observability/metrics"},
            },
            default_sample_rate=0.1,
        )
        self.assertEqual(rate, 1.0)

    def test_parse_sentry_traces_sample_rate(self) -> None:
        self.assertEqual(parse_sentry_traces_sample_rate(None), 0.5)
        self.assertEqual(parse_sentry_traces_sample_rate(""), 0.5)
        self.assertEqual(parse_sentry_traces_sample_rate("0.25"), 0.25)
        self.assertEqual(parse_sentry_traces_sample_rate("2"), 1.0)
        self.assertEqual(parse_sentry_traces_sample_rate("-1"), 0.0)
        self.assertEqual(parse_sentry_traces_sample_rate("nope"), 0.5)
