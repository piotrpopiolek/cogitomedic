"""Tests for ``apps.core.otel_spans`` (OpenTelemetry domain span helper)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.exceptions import DomainError, StateTransitionError
from apps.core.otel_spans import cogito_business_span


class CogitoBusinessSpanTests(SimpleTestCase):
    def test_domain_error_does_not_call_record_exception(self) -> None:
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_span
        mock_cm.__exit__.return_value = None  # must be falsy or exception is swallowed
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_cm

        with patch("apps.core.otel_spans.tracer", mock_tracer):
            with self.assertRaisesMessage(DomainError, "bad"):
                with cogito_business_span(
                    "test.span",
                    queue_entry_id=uuid.uuid4(),
                    audit_event_type="TEST_EVENT",
                ):
                    raise DomainError("bad", api_message_key="other.domain.test")

        mock_span.record_exception.assert_not_called()

    def test_state_transition_error_subclass_does_not_record(self) -> None:
        """DomainError subclasses must not be treated as span failures."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_span
        mock_cm.__exit__.return_value = None
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_cm

        with patch("apps.core.otel_spans.tracer", mock_tracer):
            with self.assertRaises(StateTransitionError):
                with cogito_business_span("test.span"):
                    raise StateTransitionError(
                        "no transition",
                        api_message_key="other.domain.test",
                    )

        mock_span.record_exception.assert_not_called()

    def test_non_domain_exception_calls_record_exception(self) -> None:
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_span
        mock_cm.__exit__.return_value = None
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_cm

        with patch("apps.core.otel_spans.tracer", mock_tracer):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                with cogito_business_span("test.span"):
                    raise RuntimeError("boom")

        mock_span.record_exception.assert_called_once()
        (exc_arg,) = mock_span.record_exception.call_args[0]
        self.assertIsInstance(exc_arg, RuntimeError)
        self.assertEqual(str(exc_arg), "boom")
