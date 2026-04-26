from __future__ import annotations

from unittest.mock import patch

from django.template import Context, Template
from django.test import TestCase


class StaticVersionedTagTests(TestCase):
    """Regression tests for the ``static_v`` template tag (cache buster)."""

    def _render(self, template_source: str) -> str:
        return Template(template_source).render(Context({}))

    def test_appends_version_query_param_when_file_exists(self) -> None:
        """``static_v`` should append ``?v=<mtime>`` for resolvable assets."""
        with patch(
            "apps.core.templatetags.static_versioned.finders.find",
            return_value="/abs/path/to/asset.js",
        ), patch(
            "apps.core.templatetags.static_versioned.os.path.getmtime",
            return_value=1700000000.5,
        ):
            output = self._render(
                "{% load static_versioned %}{% static_v 'doctor/js/befund-form.js' %}"
            )
        self.assertIn("doctor/js/befund-form.js", output)
        self.assertIn("?v=1700000000", output)

    def test_falls_back_to_plain_static_when_finder_returns_none(self) -> None:
        """If the asset cannot be resolved, the tag must not break rendering."""
        with patch(
            "apps.core.templatetags.static_versioned.finders.find",
            return_value=None,
        ):
            output = self._render(
                "{% load static_versioned %}{% static_v 'missing/asset.js' %}"
            )
        self.assertIn("missing/asset.js", output)
        self.assertNotIn("?v=", output)

    def test_uses_amp_separator_when_static_url_already_has_query(self) -> None:
        """If ``{% static %}`` returns a URL with an existing query, append with ``&``."""
        with patch(
            "apps.core.templatetags.static_versioned.static",
            return_value="/static/foo.js?bar=1",
        ), patch(
            "apps.core.templatetags.static_versioned.finders.find",
            return_value="/abs/path/to/foo.js",
        ), patch(
            "apps.core.templatetags.static_versioned.os.path.getmtime",
            return_value=42,
        ):
            output = self._render("{% load static_versioned %}{% static_v 'foo.js' %}")
        self.assertIn("/static/foo.js?bar=1", output)
        self.assertIn("v=42", output)
        self.assertNotIn("?v=42", output)

    def test_resolve_mtime_returns_none_when_finder_raises(self) -> None:
        with patch(
            "apps.core.templatetags.static_versioned.finders.find",
            side_effect=RuntimeError("finder boom"),
        ):
            output = self._render(
                "{% load static_versioned %}{% static_v 'any/path.js' %}"
            )
        self.assertNotIn("?v=", output)

    def test_resolve_mtime_returns_none_when_getmtime_raises_oserror(self) -> None:
        with patch(
            "apps.core.templatetags.static_versioned.finders.find",
            return_value="/abs/path.js",
        ), patch(
            "apps.core.templatetags.static_versioned.os.path.getmtime",
            side_effect=OSError("no mtime"),
        ):
            output = self._render(
                "{% load static_versioned %}{% static_v 'doctor/js/x.js' %}"
            )
        self.assertNotIn("?v=", output)
