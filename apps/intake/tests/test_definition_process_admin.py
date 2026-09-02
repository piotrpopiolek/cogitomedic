"""ADD of consent/question definitions: UUID pk must not block Unfold inlines."""

from __future__ import annotations

import uuid

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.intake.models import (
    AnamnesisQuestionDefinition,
    ConsentDefinition,
)
from apps.reception.process_types import PROCESS_TYPE_STANDARD
from apps.users.models import StaffUser


def _process_inline_post(
    *,
    total_forms: int = 1,
    initial_forms: int = 0,
    rows: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    data = {
        "process_links-TOTAL_FORMS": str(total_forms),
        "process_links-INITIAL_FORMS": str(initial_forms),
        "process_links-MIN_NUM_FORMS": "0",
        "process_links-MAX_NUM_FORMS": "1000",
    }
    if rows is not None:
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"process_links-{index}-{key}"] = value
        return data
    if total_forms:
        data["process_links-0-id"] = ""
        data["process_links-0-process_type"] = PROCESS_TYPE_STANDARD
    return data


def _consent_parent_post(code: str, *, is_active: bool = True) -> dict[str, str]:
    data = {
        "code": code,
        "version": "1",
        "title_de": "Neue Einwilligung",
        "content_de": "Text",
        "title_en": "",
        "content_en": "",
        "title_pl": "",
        "content_pl": "",
        "display_order": "0",
        "is_required": "on",
        "_save": "Save",
    }
    if is_active:
        data["is_active"] = "on"
    return data


def _question_parent_post(code: str, *, is_active: bool = True) -> dict[str, str]:
    data = {
        "code": code,
        "version": "1",
        "question_text_de": "Neue Frage",
        "question_text_en": "New question",
        "question_text_pl": "",
        "answer_type": "TEXT_OPTIONAL",
        "display_order": "0",
        "is_required": "on",
        "_save": "Save",
    }
    if is_active:
        data["is_active"] = "on"
    return data


def _admin_form_errors(response) -> dict:
    if not hasattr(response, "context") or not response.context:
        return {}
    errors: dict = {}
    adminform = response.context.get("adminform")
    if adminform is not None:
        errors["form"] = dict(adminform.form.errors)
        errors["non_field"] = list(adminform.form.non_field_errors())
    inline_errors = []
    for inline in response.context.get("inline_admin_formsets") or []:
        inline_errors.append(list(inline.formset.errors))
        inline_errors.append(list(inline.formset.non_form_errors()))
    if inline_errors:
        errors["inlines"] = inline_errors
    return errors


class DefinitionProcessCleanTests(TestCase):
    def test_unsaved_consent_full_clean_allows_empty_process_links(self) -> None:
        obj = ConsentDefinition(
            code="ADD_CLEAN_CONSENT",
            version=1,
            title_de="Neu",
            content_de="Inhalt",
            is_active=True,
        )
        self.assertTrue(obj._state.adding)
        self.assertIsNotNone(obj.pk)
        obj.full_clean()

    def test_unsaved_question_full_clean_allows_empty_process_links(self) -> None:
        obj = AnamnesisQuestionDefinition(
            code="ADD_CLEAN_QUESTION",
            version=1,
            question_text_de="Frage",
            question_text_en="Question",
            is_active=True,
        )
        self.assertTrue(obj._state.adding)
        self.assertIsNotNone(obj.pk)
        obj.full_clean()

    def test_saved_active_consent_without_process_fails_clean(self) -> None:
        obj = ConsentDefinition.objects.create(
            code="SAVED_NO_PROCESS_CONSENT",
            version=1,
            title_de="X",
            content_de="X",
            process_types=[PROCESS_TYPE_STANDARD],
        )
        obj.process_links.all().delete()
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn(NON_FIELD_ERRORS, ctx.exception.message_dict)
        self.assertNotIn("process_links", ctx.exception.message_dict)

    def test_saved_active_question_without_process_fails_clean(self) -> None:
        obj = AnamnesisQuestionDefinition.objects.create(
            code="SAVED_NO_PROCESS_QUESTION",
            version=1,
            question_text_de="Frage",
            question_text_en="Question",
            process_types=[PROCESS_TYPE_STANDARD],
        )
        obj.process_links.all().delete()
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn(NON_FIELD_ERRORS, ctx.exception.message_dict)
        self.assertNotIn("process_links", ctx.exception.message_dict)


class DefinitionProcessAdminAddTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.superuser = StaffUser.objects.create_superuser(
            username="def-add-su",
            email="def-add-su@example.com",
            password="safe-password",
        )
        self.client.force_login(self.superuser)

    def test_admin_add_consent_with_process_inline_succeeds(self) -> None:
        code = f"ADD_ADMIN_C_{uuid.uuid4().hex[:10]}"
        url = reverse("admin:intake_consentdefinition_add")
        response = self.client.post(
            url,
            {
                **_consent_parent_post(code),
                **_process_inline_post(),
            },
        )
        if response.status_code != 302:
            self.fail(
                f"expected redirect, got {response.status_code}: "
                f"{_admin_form_errors(response)}"
            )
        created = ConsentDefinition.objects.get(code=code, version=1)
        self.assertEqual(
            list(created.process_links.values_list("process_type", flat=True)),
            [PROCESS_TYPE_STANDARD],
        )

    def test_admin_add_question_with_process_inline_succeeds(self) -> None:
        code = f"ADD_ADMIN_Q_{uuid.uuid4().hex[:10]}"
        url = reverse("admin:intake_anamnesisquestiondefinition_add")
        response = self.client.post(
            url,
            {
                **_question_parent_post(code),
                **_process_inline_post(),
            },
        )
        if response.status_code != 302:
            self.fail(
                f"expected redirect, got {response.status_code}: "
                f"{_admin_form_errors(response)}"
            )
        created = AnamnesisQuestionDefinition.objects.get(code=code, version=1)
        self.assertEqual(
            list(created.process_links.values_list("process_type", flat=True)),
            [PROCESS_TYPE_STANDARD],
        )

    def test_admin_add_active_consent_without_process_is_rejected(self) -> None:
        code = f"ADD_ADMIN_EMPTY_C_{uuid.uuid4().hex[:10]}"
        url = reverse("admin:intake_consentdefinition_add")
        response = self.client.post(
            url,
            {
                **_consent_parent_post(code),
                **_process_inline_post(total_forms=0),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ConsentDefinition.objects.filter(code=code, version=1).exists()
        )
        errors = _admin_form_errors(response)
        self.assertTrue(errors.get("inlines"))

    def test_admin_add_inactive_consent_without_process_succeeds(self) -> None:
        code = f"ADD_ADMIN_INACTIVE_C_{uuid.uuid4().hex[:10]}"
        url = reverse("admin:intake_consentdefinition_add")
        response = self.client.post(
            url,
            {
                **_consent_parent_post(code, is_active=False),
                **_process_inline_post(total_forms=0),
            },
        )
        if response.status_code != 302:
            self.fail(
                f"expected redirect, got {response.status_code}: "
                f"{_admin_form_errors(response)}"
            )
        created = ConsentDefinition.objects.get(code=code, version=1)
        self.assertFalse(created.is_active)
        self.assertEqual(created.process_links.count(), 0)

    def test_admin_change_active_without_process_returns_200_not_500(self) -> None:
        obj = ConsentDefinition.objects.create(
            code=f"CHG_EMPTY_{uuid.uuid4().hex[:10]}",
            version=1,
            title_de="X",
            content_de="X",
            process_types=[PROCESS_TYPE_STANDARD],
        )
        obj.process_links.all().delete()
        url = reverse("admin:intake_consentdefinition_change", args=[obj.pk])
        response = self.client.post(
            url,
            {
                **_consent_parent_post(obj.code),
                **_process_inline_post(total_forms=0),
            },
        )
        self.assertEqual(response.status_code, 200)
        errors = _admin_form_errors(response)
        self.assertTrue(errors.get("non_field") or errors.get("inlines"))
        obj.refresh_from_db()
        self.assertEqual(obj.process_links.count(), 0)

    def test_admin_change_cannot_delete_last_process_on_active_consent(self) -> None:
        obj = ConsentDefinition.objects.create(
            code=f"CHG_DEL_{uuid.uuid4().hex[:10]}",
            version=1,
            title_de="X",
            content_de="X",
            process_types=[PROCESS_TYPE_STANDARD],
        )
        link = obj.process_links.get()
        url = reverse("admin:intake_consentdefinition_change", args=[obj.pk])
        response = self.client.post(
            url,
            {
                **_consent_parent_post(obj.code),
                **_process_inline_post(
                    total_forms=1,
                    initial_forms=1,
                    rows=[
                        {
                            "id": str(link.pk),
                            "consent_definition": str(obj.pk),
                            "process_type": PROCESS_TYPE_STANDARD,
                            "DELETE": "on",
                        }
                    ],
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        obj.refresh_from_db()
        self.assertEqual(obj.process_links.count(), 1)
