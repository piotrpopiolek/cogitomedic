"""Narrow Django test-client redirects for mypy."""

from __future__ import annotations

from django.http import HttpResponseRedirect


def redirect_url(response: object) -> str:
    if not isinstance(response, HttpResponseRedirect):
        raise AssertionError("expected redirect response")
    return response.url
