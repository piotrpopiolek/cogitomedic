from __future__ import annotations

import json
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from apps.core.api_utils import MAX_JSON_BODY_BYTES, read_json_body
from apps.core.exceptions import InvalidRequestBodyEncoding
from apps.core.models import (
    TranslationCacheVersion,
    TranslationCategory,
    TranslationKey,
    TranslationKeyStatus,
    TranslationValue,
)
from apps.core.translation_service import get_translation_map


class TranslationServiceTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.key = TranslationKey.objects.create(
            key="doctor.test_key",
            category=TranslationCategory.DOCTOR,
            description="test key",
            is_html_allowed=False,
            allowed_placeholders=[],
            status=TranslationKeyStatus.ACTIVE,
        )

    def test_signal_bumps_version_on_value_save(self) -> None:
        get_translation_map("doctor", "pl-PL")
        before = TranslationCacheVersion.objects.get(
            category=TranslationCategory.DOCTOR,
            language_code="pl-PL",
        ).version
        TranslationValue.objects.create(
            translation_key=self.key,
            language_code="pl-PL",
            value="Wartosc",
        )
        after = TranslationCacheVersion.objects.get(
            category=TranslationCategory.DOCTOR,
            language_code="pl-PL",
        ).version
        self.assertEqual(after, before + 1)

    def test_get_translation_map_returns_only_active_values(self) -> None:
        deprecated_key = TranslationKey.objects.create(
            key="doctor.legacy_key",
            category=TranslationCategory.DOCTOR,
            description="legacy",
            is_html_allowed=False,
            allowed_placeholders=[],
            status=TranslationKeyStatus.DEPRECATED,
        )
        TranslationValue.objects.create(
            translation_key=self.key,
            language_code="de-DE",
            value="Aktiv",
        )
        TranslationValue.objects.create(
            translation_key=deprecated_key,
            language_code="de-DE",
            value="Legacy",
        )
        result = get_translation_map("doctor", "de-DE")
        self.assertIn("doctor.test_key", result)
        self.assertNotIn("doctor.legacy_key", result)

    def test_get_translation_map_refreshes_after_value_update(self) -> None:
        value = TranslationValue.objects.create(
            translation_key=self.key,
            language_code="de-DE",
            value="Old value",
        )
        first = get_translation_map("doctor", "de-DE")
        self.assertEqual(first.get("doctor.test_key"), "Old value")

        value.value = "New value"
        value.save()

        second = get_translation_map("doctor", "de-DE")
        self.assertEqual(second.get("doctor.test_key"), "New value")

    def test_value_clean_rejects_html_when_not_allowed(self) -> None:
        value = TranslationValue(
            translation_key=self.key,
            language_code="de-DE",
            value="<b>x</b>",
        )
        with self.assertRaises(ValidationError):
            value.full_clean()

    def test_value_clean_sanitizes_html_when_allowed(self) -> None:
        html_key = TranslationKey.objects.create(
            key="doctor.rich_text",
            category=TranslationCategory.DOCTOR,
            description="html key",
            is_html_allowed=True,
            allowed_placeholders=[],
            status=TranslationKeyStatus.ACTIVE,
        )
        value = TranslationValue(
            translation_key=html_key,
            language_code="de-DE",
            value='<b>ok</b><script>alert("x")</script>',
        )
        value.full_clean()
        self.assertEqual(value.value, "<b>ok</b>alert(\"x\")")

    def test_value_clean_rejects_percent_s_placeholder_format(self) -> None:
        placeholder_key = TranslationKey.objects.create(
            key="doctor.placeholder_text",
            category=TranslationCategory.DOCTOR,
            description="placeholder key",
            is_html_allowed=False,
            allowed_placeholders=["name"],
            status=TranslationKeyStatus.ACTIVE,
        )
        value = TranslationValue(
            translation_key=placeholder_key,
            language_code="de-DE",
            value="Hallo %s",
        )
        with self.assertRaises(ValidationError):
            value.full_clean()

    def test_value_clean_rejects_percent_named_placeholder_format(self) -> None:
        placeholder_key = TranslationKey.objects.create(
            key="doctor.placeholder_text_named",
            category=TranslationCategory.DOCTOR,
            description="placeholder key",
            is_html_allowed=False,
            allowed_placeholders=["name"],
            status=TranslationKeyStatus.ACTIVE,
        )
        value = TranslationValue(
            translation_key=placeholder_key,
            language_code="de-DE",
            value="Hallo %(name)s",
        )
        with self.assertRaises(ValidationError):
            value.full_clean()

    def test_value_clean_rejects_format_specifier_placeholder(self) -> None:
        placeholder_key = TranslationKey.objects.create(
            key="doctor.placeholder_text_spec",
            category=TranslationCategory.DOCTOR,
            description="placeholder key",
            is_html_allowed=False,
            allowed_placeholders=["amount"],
            status=TranslationKeyStatus.ACTIVE,
        )
        value = TranslationValue(
            translation_key=placeholder_key,
            language_code="de-DE",
            value="Kwota {amount:.2f}",
        )
        with self.assertRaises(ValidationError):
            value.full_clean()

    def test_value_clean_rejects_unknown_placeholder(self) -> None:
        placeholder_key = TranslationKey.objects.create(
            key="doctor.placeholder_text_unknown",
            category=TranslationCategory.DOCTOR,
            description="placeholder key",
            is_html_allowed=False,
            allowed_placeholders=["name"],
            status=TranslationKeyStatus.ACTIVE,
        )
        value = TranslationValue(
            translation_key=placeholder_key,
            language_code="de-DE",
            value="Hallo {surname}",
        )
        with self.assertRaises(ValidationError):
            value.full_clean()


class TranslationCompletenessCommandTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.key = TranslationKey.objects.create(
            key="doctor.completeness_key",
            category=TranslationCategory.DOCTOR,
            description="completeness",
            is_html_allowed=False,
            allowed_placeholders=[],
            status=TranslationKeyStatus.ACTIVE,
        )

    def test_command_fails_on_missing_languages(self) -> None:
        TranslationValue.objects.create(
            translation_key=self.key,
            language_code="de-DE",
            value="DE",
        )
        with self.assertRaises(CommandError):
            call_command("check_translations_completeness")

    def test_command_fails_when_no_active_keys(self) -> None:
        TranslationKey.objects.all().delete()
        with self.assertRaises(CommandError):
            call_command("check_translations_completeness")

    def test_command_passes_when_all_languages_present(self) -> None:
        TranslationValue.objects.create(translation_key=self.key, language_code="de-DE", value="DE")
        TranslationValue.objects.create(translation_key=self.key, language_code="en-GB", value="EN")
        TranslationValue.objects.create(translation_key=self.key, language_code="pl-PL", value="PL")
        out = StringIO()
        call_command("check_translations_completeness", stdout=out)
        self.assertIn("passed", out.getvalue().lower())


class ReadJsonBodyTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_read_json_body_rejects_payload_larger_than_limit(self) -> None:
        too_large_payload = {"payload": "a" * (MAX_JSON_BODY_BYTES + 1)}
        request = self.factory.post(
            "/api/v1/intake-forms/00000000-0000-0000-0000-000000000000",
            data=json.dumps(too_large_payload),
            content_type="application/json",
        )
        with self.assertRaises(InvalidRequestBodyEncoding):
            read_json_body(request)


class SafeHrefTemplateFilterTests(TestCase):
    def test_safe_href_allows_http_https_and_relative_urls(self) -> None:
        tpl = Template("{% load safe_urls %}{{ url|safe_href }}")
        self.assertEqual(tpl.render(Context({"url": "https://example.com/a"})), "https://example.com/a")
        self.assertEqual(tpl.render(Context({"url": "http://example.com/a"})), "http://example.com/a")
        self.assertEqual(tpl.render(Context({"url": "/admin/"})), "/admin/")

    def test_safe_href_blocks_javascript_urls(self) -> None:
        tpl = Template("{% load safe_urls %}{{ url|safe_href }}")
        self.assertEqual(tpl.render(Context({"url": "javascript:alert(1)"})), "#")
