"""Optional manual / CI gate for large external PDF memory usage (see deployment runbook)."""

from __future__ import annotations

import os
import unittest


class ExternalUploadMemoryGateTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("RUN_EXTERNAL_UPLOAD_MEMORY_GATE"),
        "Set RUN_EXTERNAL_UPLOAD_MEMORY_GATE=1 to run large-file memory probes locally.",
    )
    def test_memory_gate_placeholder(self) -> None:
        """When enabled: hook for future RSS sampling around preview / GENERATE_PDF."""
        self.assertTrue(True)
