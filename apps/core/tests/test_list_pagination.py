from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.constants import DEFAULT_LIST_LIMIT
from apps.core.list_pagination import (
    build_page_size_query,
    effective_default_page_size,
    page_size_switch_items,
    parse_page_size,
    validate_allowed_page_size,
)


class ParsePageSizeTests(SimpleTestCase):
    def test_default_is_50(self) -> None:
        self.assertEqual(parse_page_size(None), 50)
        self.assertEqual(parse_page_size(""), 50)

    def test_allowed_values(self) -> None:
        for size in (10, 20, 50, 100):
            self.assertEqual(parse_page_size(str(size)), size)
            self.assertEqual(parse_page_size(size), size)

    def test_invalid_falls_back_to_default(self) -> None:
        self.assertEqual(parse_page_size("25"), DEFAULT_LIST_LIMIT)
        self.assertEqual(parse_page_size("999"), DEFAULT_LIST_LIMIT)
        self.assertEqual(parse_page_size("abc"), DEFAULT_LIST_LIMIT)

    def test_validate_allowed_page_size_rejects_invalid(self) -> None:
        with self.assertRaises(ValueError):
            validate_allowed_page_size("25")
        with self.assertRaises(ValueError):
            validate_allowed_page_size("abc")

    @override_settings(LIST_PAGE_SIZE_DEFAULT=20)
    def test_settings_override_when_allowed(self) -> None:
        self.assertEqual(effective_default_page_size(), 20)
        self.assertEqual(parse_page_size(None), 20)

    @override_settings(LIST_PAGE_SIZE_DEFAULT=25)
    def test_settings_invalid_ignored(self) -> None:
        self.assertEqual(effective_default_page_size(), DEFAULT_LIST_LIMIT)


class PageSizeQueryTests(SimpleTestCase):
    def test_build_page_size_query_resets_page(self) -> None:
        qs = build_page_size_query(
            {"page": "3", "p": "2", "status": "DRAFT"}, page_size=10
        )
        self.assertIn("page_size=10", qs)
        self.assertNotIn("page=", qs)
        self.assertNotIn("p=", qs)
        self.assertIn("status=DRAFT", qs)

    def test_build_page_size_query_omits_default_size(self) -> None:
        qs = build_page_size_query({"page_size": "20"}, page_size=50)
        self.assertNotIn("page_size", qs)

    def test_page_size_switch_items_marks_active(self) -> None:
        items = page_size_switch_items({"page": "2"}, current_page_size=50)
        self.assertEqual([item["size"] for item in items], [10, 20, 50, 100])
        active = [item for item in items if item["active"]]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["size"], 50)
        self.assertNotIn("page=", active[0]["url"])


class DoctorListQuerystringTests(SimpleTestCase):
    def test_build_doctor_list_querystring_preserves_page_size(self) -> None:
        from cogitomedica.doctor_views import build_doctor_list_querystring

        factory = RequestFactory()
        request = factory.get("/doctor/?status=DRAFT&page_size=10&page=2")
        qs = build_doctor_list_querystring(
            request, show_oversight_filters=False, page=2
        )
        self.assertIn("page_size=10", qs)
        self.assertIn("status=DRAFT", qs)
        self.assertIn("page=2", qs)
