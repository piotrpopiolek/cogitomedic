from django.http import QueryDict
from django.test import SimpleTestCase
from pydantic import ValidationError

from apps.core.api_schemas import OffsetPaginationQueryParams
from apps.core.api_utils import validate_get_query_params
from apps.operations.api_schemas import AuditEventsListQueryParams
from apps.users.api_schemas import StaffUsersListQueryParams


class ValidateGetQueryParamsTests(SimpleTestCase):
    def test_offset_pagination_defaults(self) -> None:
        query = validate_get_query_params(OffsetPaginationQueryParams, QueryDict())
        self.assertEqual(query.page, 1)
        self.assertEqual(query.page_size, 50)

    def test_offset_pagination_invalid_page_size_raises(self) -> None:
        with self.assertRaises(ValidationError):
            validate_get_query_params(
                OffsetPaginationQueryParams,
                QueryDict("page_size=25"),
            )

    def test_staff_users_query_params(self) -> None:
        query = validate_get_query_params(
            StaffUsersListQueryParams,
            QueryDict("page=2&page_size=10&role=DOCTOR&search=ann"),
        )
        self.assertEqual(query.page, 2)
        self.assertEqual(query.page_size, 10)
        self.assertEqual(query.role, "DOCTOR")
        self.assertEqual(query.search, "ann")

    def test_staff_users_invalid_role_raises(self) -> None:
        with self.assertRaises(ValidationError):
            validate_get_query_params(
                StaffUsersListQueryParams,
                QueryDict("role=NOT_A_ROLE"),
            )

    def test_audit_events_query_reads_from_alias(self) -> None:
        query = validate_get_query_params(
            AuditEventsListQueryParams,
            QueryDict("from=2026-03-01T00:00:00Z&page_size=100"),
        )
        self.assertEqual(query.from_, "2026-03-01T00:00:00Z")
        self.assertEqual(query.page_size, 100)
