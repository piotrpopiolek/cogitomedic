"""
Tests for Cogitomedica OpenAPI schema and Pydantic → OpenAPI conversion.
"""

from __future__ import annotations

from django.test import TestCase

from cogitomedica.openapi_extension import build_cogito_openapi_schema
from cogitomedica.openapi_schemas import (
    COMPONENTS_REF_PREFIX,
    PYDANTIC_DEFS_PREFIX,
    build_components_schemas,
    get_request_body_schema_for,
    pydantic_to_openapi_schema,
)
from pydantic import BaseModel, Field


class _DummyNested(BaseModel):
    value: str


class _DummyRequest(BaseModel):
    name: str = Field(min_length=1)
    nested: _DummyNested | None = None


class OpenAPISchemasConversionTests(TestCase):
    """Pure conversion tests (no Django app models)."""

    def test_pydantic_to_openapi_rewrites_refs(self) -> None:
        raw = _DummyRequest.model_json_schema()
        root, defs = pydantic_to_openapi_schema(raw)
        # Pydantic may return root as $ref or as inline schema (properties/required)
        if "$ref" in root:
            self.assertTrue(root["$ref"].startswith(COMPONENTS_REF_PREFIX))
        self.assertIn("_DummyNested", defs)
        # All $refs in result must point to components (no #/$defs/)
        for name, s in defs.items():
            self.assertNotIn(PYDANTIC_DEFS_PREFIX, str(s), msg=f"defs[{name}]")
        schema_str = str(root) + str(defs)
        self.assertNotIn("#/$defs/", schema_str)
        # Nested ref: may be in root.properties.nested or in defs
        has_component_ref = COMPONENTS_REF_PREFIX + "_DummyNested" in schema_str
        self.assertTrue(
            has_component_ref, msg="Expected $ref to _DummyNested in components"
        )

    def test_build_components_schemas_merges_defs(self) -> None:
        schemas = build_components_schemas([_DummyRequest])
        self.assertIn("_DummyRequest", schemas)
        self.assertIn("_DummyNested", schemas)
        self.assertNotIn("#/$defs/", str(schemas))


class OpenAPISchemaIntegrationTests(TestCase):
    """Integration: full schema build and path → $ref mapping."""

    def test_build_cogito_openapi_schema_has_components_and_refs(self) -> None:
        schema = build_cogito_openapi_schema()
        self.assertIn("components", schema)
        self.assertIn("schemas", schema["components"])
        comp = schema["components"]["schemas"]
        self.assertIn("AuthLoginRequest", comp)
        self.assertIn("UpdateAnamnesisPayloadRequest", comp)
        self.assertIn("AnamnesisAnswerPayload", comp)
        self.assertIn("SaveDraftMedicalDocumentRequest", comp)
        self.assertIn("PublishMedicalDocumentRequest", comp)
        self.assertIn("PaperIntakeAuthorizationRequest", comp)
        self.assertIn("ExternalUploadSelectAttachmentRequest", comp)
        self.assertIn("ExternalUploadRevisionStartRequest", comp)
        self.assertIn("ExternalUploadUploadResponse", comp)

    def test_external_upload_openapi_paths_request_and_response_refs(self) -> None:
        schema = build_cogito_openapi_schema()
        paths = schema["paths"]
        upload_op = paths["/api/v1/medical-documents/external-upload/upload"]["post"]
        self.assertIn("multipart/form-data", upload_op["requestBody"]["content"])
        self.assertNotIn("application/json", upload_op["requestBody"]["content"])
        rb201 = upload_op["responses"]["201"]["content"]["application/json"]["schema"]
        self.assertEqual(
            rb201, {"$ref": "#/components/schemas/ExternalUploadUploadResponse"}
        )
        sel_ref = get_request_body_schema_for(
            "/api/v1/medical-documents/{medical_document_id}/external-upload/select-attachment",
            "post",
        )
        self.assertEqual(
            sel_ref,
            {"$ref": "#/components/schemas/ExternalUploadSelectAttachmentRequest"},
        )
        pub_ref = get_request_body_schema_for(
            "/api/v1/medical-documents/{medical_document_id}/external-upload/publish",
            "post",
        )
        self.assertEqual(
            pub_ref, {"$ref": "#/components/schemas/PublishMedicalDocumentRequest"}
        )
        rev_ref = get_request_body_schema_for(
            "/api/v1/medical-documents/{medical_document_id}/external-upload/revision/start",
            "post",
        )
        self.assertEqual(
            rev_ref, {"$ref": "#/components/schemas/ExternalUploadRevisionStartRequest"}
        )
        pub_op = paths[
            "/api/v1/medical-documents/{medical_document_id}/external-upload/publish"
        ]["post"]
        pub_200 = pub_op["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(
            pub_200, {"$ref": "#/components/schemas/PublishDocumentVersionResponse"}
        )

    def test_auth_login_request_body_uses_ref(self) -> None:
        schema = build_cogito_openapi_schema()
        login = schema["paths"].get("/api/v1/auth/login", {}).get("post", {})
        rb = login.get("requestBody", {}).get("content", {}).get("application/json", {})
        self.assertEqual(
            rb.get("schema"), {"$ref": "#/components/schemas/AuthLoginRequest"}
        )

    def test_get_request_body_schema_for_returns_ref_for_registered(self) -> None:
        # Path format matches COGITO_PATHS keys (single braces from f-string {{ -> {)
        ref = get_request_body_schema_for(
            "/api/v1/medical-documents/{medical_document_id}/publish", "post"
        )
        self.assertEqual(
            ref, {"$ref": "#/components/schemas/PublishMedicalDocumentRequest"}
        )

    def test_get_request_body_schema_for_returns_none_for_unregistered(self) -> None:
        self.assertIsNone(
            get_request_body_schema_for("/api/v1/observability/health", "get")
        )

    def test_paper_intake_authorization_request_body_uses_ref(self) -> None:
        post_ref = get_request_body_schema_for(
            "/api/v1/queue-entries/{queue_entry_id}/paper-intake-authorization",
            "post",
        )
        del_ref = get_request_body_schema_for(
            "/api/v1/queue-entries/{queue_entry_id}/paper-intake-authorization",
            "delete",
        )
        expected = {"$ref": "#/components/schemas/PaperIntakeAuthorizationRequest"}
        self.assertEqual(post_ref, expected)
        self.assertEqual(del_ref, expected)

    def test_paper_intake_authorization_delete_documents_required_json_body(
        self,
    ) -> None:
        schema = build_cogito_openapi_schema()
        delete_op = (
            schema["paths"]
            .get(
                "/api/v1/queue-entries/{queue_entry_id}/paper-intake-authorization", {}
            )
            .get("delete", {})
        )
        rb = delete_op.get("requestBody", {})
        self.assertTrue(rb.get("required"))
        self.assertIn("PaperIntakeAuthorizationRequest", rb.get("description", ""))
        self.assertIn("reason", rb.get("description", ""))
        op_desc = (delete_op.get("description") or "").lower()
        self.assertIn("not a typical", op_desc)
        self.assertIn("body-less", op_desc)

    def test_metrics_endpoint_is_marked_as_authenticated_in_openapi(self) -> None:
        schema = build_cogito_openapi_schema()
        metrics = (
            schema["paths"].get("/api/v1/observability/metrics", {}).get("get", {})
        )
        self.assertEqual(metrics.get("security"), [{"sessionCookie": []}])
