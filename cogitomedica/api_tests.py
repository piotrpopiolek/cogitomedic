from __future__ import annotations

from django.test import Client, TestCase

from apps.core.api_utils import assign_group_to_test_user
from apps.users.models import StaffUser


class ApiDocsEndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        staff = StaffUser.objects.create_user(
            username="api-docs-staff",
            email="api-docs@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(staff, "Admin")
        self.client.force_login(staff)

    def test_openapi_schema_endpoint_is_available(self) -> None:
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)

    def test_swagger_and_redoc_views_are_available(self) -> None:
        swagger = self.client.get("/api/docs/swagger/")
        redoc = self.client.get("/api/docs/redoc/")
        self.assertEqual(swagger.status_code, 200)
        self.assertEqual(redoc.status_code, 200)

    def test_api_docs_require_staff(self) -> None:
        anonymous = Client()
        schema_resp = anonymous.get("/api/schema/")
        swagger_resp = anonymous.get("/api/docs/swagger/")
        self.assertIn(schema_resp.status_code, (302, 403))
        self.assertIn(swagger_resp.status_code, (302, 403))
