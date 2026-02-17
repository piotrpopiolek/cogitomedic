from __future__ import annotations

from django.test import Client, TestCase


class ApiDocsEndpointTests(TestCase):
    def test_openapi_schema_endpoint_is_available(self) -> None:
        client = Client()
        response = client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)

    def test_swagger_and_redoc_views_are_available(self) -> None:
        client = Client()
        swagger = client.get("/api/docs/swagger/")
        redoc = client.get("/api/docs/redoc/")

        self.assertEqual(swagger.status_code, 200)
        self.assertEqual(redoc.status_code, 200)
