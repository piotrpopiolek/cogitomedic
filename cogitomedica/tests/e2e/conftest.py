"""Pytest hooks for Playwright E2E suite."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "e2e: real browser tests (Playwright); excluded from default CI pytest job",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip e2e collection when E2E_BROWSER is unset and not explicitly selected."""
    markexpr = (config.option.markexpr or "").strip()
    if "e2e" in markexpr and "not e2e" not in markexpr.replace(" ", ""):
        return
    if os.environ.get("E2E_BROWSER"):
        return
    skip = pytest.mark.skip(
        reason="Set E2E_BROWSER=chromium|firefox|msedge to run Playwright E2E"
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)
