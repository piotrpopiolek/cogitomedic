"""Playwright E2E: doctor Befund edit-session, multitab, amend, autosave, unlock cutover."""

from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest

from apps.medical.models import MedicalDocument
from apps.medical.write_gate import (
    mark_doctor_draft_previewed,
    mutate_doctor_publish,
    mutate_doctor_save_draft,
)
from cogitomedica.tests.e2e.base import PlaywrightDoctorE2EBase
from cogitomedica.tests.e2e.factories import (
    create_clinic_queue,
    create_doctor,
    create_draft_document,
    create_published_document,
)

pytestmark = pytest.mark.e2e

_MIN_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class BefundEditSessionPlaywrightTests(PlaywrightDoctorE2EBase):
    def setUp(self) -> None:
        super().setUp()
        suffix = uuid.uuid4().hex[:8]
        self.doctor = create_doctor(username=f"e2e_doc_a_{suffix}")
        self.queue = create_clinic_queue(
            doctor=self.doctor, code=f"A{suffix[:4].upper()}"
        )
        self.doc = create_draft_document(
            doctor=self.doctor, daily_queue=self.queue, position_no=1
        )
        self.login_doctor(self.page, username=self.doctor.username)

    def test_first_tab_acquires_edit_session(self) -> None:
        body = self.open_document_acquiring_session(self.page, self.doc.id)
        self.assertIn("edit_session_token", body)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.locked_by_user_id, self.doctor.id)
        self.assertIsNotNone(self.doc.edit_session_token)
        self.assertTrue(self.page.is_enabled("#btn-save-draft"))

    def test_reload_resumes_same_token(self) -> None:
        body = self.open_document_acquiring_session(self.page, self.doc.id)
        token = body["edit_session_token"]
        stored = self.session_storage_token(
            self.page, staff_user_id=str(self.doctor.id), document_id=self.doc.id
        )
        self.assertEqual(stored, token)

        with self.page.expect_response(
            lambda r: "/edit-session" in r.url and r.request.method == "POST" and r.ok,
            timeout=45_000,
        ) as info:
            self.page.reload(wait_until="domcontentloaded")
        resumed = info.value.json()
        self.assertEqual(resumed["edit_session_token"], token)
        self.assertEqual(resumed.get("mode"), "resumed")

    def test_second_tab_shows_local_lock_modal(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        page2 = self.context.new_page()
        page2.goto(
            f"{self.live_server_url}/doctor/{self.doc.id}/?lang=de",
            wait_until="domcontentloaded",
        )
        page2.wait_for_selector("#revision-modal:not(.hidden)", timeout=20_000)
        title = page2.locator("#revision-modal-title").inner_text()
        self.assertTrue(title.strip())

    def test_reclaim_from_second_context_invalidates_old_token(self) -> None:
        first = self.open_document_acquiring_session(self.page, self.doc.id)
        old_token = first["edit_session_token"]

        ctx2 = self.new_context()
        page2 = ctx2.new_page()
        self.login_doctor(page2, username=self.doctor.username)
        with page2.expect_response(
            lambda r: "/edit-session" in r.url and r.request.method == "POST",
            timeout=45_000,
        ) as first_attempt:
            self.open_document(page2, self.doc.id)
        resp = first_attempt.value
        if resp.status == 409:
            with page2.expect_response(
                lambda r: "/edit-session" in r.url
                and r.request.method == "POST"
                and r.ok,
                timeout=45_000,
            ) as reclaim:
                self.confirm_revision_modal(page2)
            body = reclaim.value.json()
        else:
            self.assertTrue(resp.ok, msg=resp.text())
            body = resp.json()
            page2.wait_for_selector("#btn-save-draft:not([disabled])", timeout=30_000)

        self.assertNotEqual(body.get("edit_session_token"), old_token)
        page2.wait_for_selector("#btn-save-draft:not([disabled])", timeout=30_000)

        self.doc.refresh_from_db()
        self.assertNotEqual(str(self.doc.edit_session_token), old_token)

        self.mark_form_dirty(self.page, "stale tab text must survive")
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft") and r.request.method == "PUT",
            timeout=30_000,
        ) as save_info:
            self.page.click("#btn-save-draft")
        self.assertEqual(save_info.value.status, 423)
        self.assertIn(
            "stale tab text must survive", self.page.input_value("#summary_text")
        )

    def test_other_doctor_gets_locked_without_reclaim(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        other = create_doctor(username=f"e2e_doc_b_{uuid.uuid4().hex[:8]}")

        ctx2 = self.new_context()
        page2 = ctx2.new_page()
        self.login_doctor(page2, username=other.username)
        page2.goto(
            f"{self.live_server_url}/doctor/{self.doc.id}/?lang=de",
            wait_until="domcontentloaded",
        )
        self.assertIn("/doctor/", page2.url)
        body = page2.locator("body").inner_text()
        self.assertTrue(body.strip())
        self.assertNotEqual(page2.locator("#befund-form").count(), 1)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.locked_by_user_id, self.doctor.id)

    def test_published_opens_readonly_amend_starts_session(self) -> None:
        pub = create_published_document(
            doctor=self.doctor, daily_queue=self.queue, position_no=9
        )
        self.open_document(self.page, pub.id)
        self.page.wait_for_selector("#btn-start-revision:not(.hidden)", timeout=20_000)
        body = self.start_amend_revision(self.page)
        self.assertIn("edit_session_token", body)
        pub.refresh_from_db()
        self.assertTrue(pub.has_pending_revision)
        self.assertEqual(pub.locked_by_user_id, self.doctor.id)

    def test_discard_revision_releases_lock(self) -> None:
        pub = create_published_document(
            doctor=self.doctor, daily_queue=self.queue, position_no=11
        )
        self.open_document(self.page, pub.id)
        self.start_amend_revision(self.page)
        self.discard_pending_revision(self.page)
        pub.refresh_from_db()
        self.assertFalse(pub.has_pending_revision)
        self.assertIsNone(pub.locked_by_user_id)
        self.assertIsNone(pub.edit_session_token)

    def test_lock_limit_blocks_fourth_document(self) -> None:
        docs = [self.doc]
        for i in range(2, 4):
            docs.append(
                create_draft_document(
                    doctor=self.doctor,
                    daily_queue=self.queue,
                    position_no=i,
                )
            )
        for d in docs:
            page = self.context.new_page()
            self.open_document_acquiring_session(page, d.id)

        fourth = create_draft_document(
            doctor=self.doctor, daily_queue=self.queue, position_no=4
        )
        page4 = self.context.new_page()
        page4.goto(
            f"{self.live_server_url}/doctor/{fourth.id}/?lang=de",
            wait_until="domcontentloaded",
        )
        page4.wait_for_selector('#alert-placeholder [role="alert"]', timeout=30_000)
        fourth.refresh_from_db()
        self.assertIsNone(fourth.locked_by_user_id)
        locked = MedicalDocument.objects.filter(
            locked_by_user_id=self.doctor.id,
            locked_at__isnull=False,
        ).count()
        self.assertEqual(locked, 3)

    def test_fourth_opens_after_publishing_one_of_three(self) -> None:
        docs = [self.doc]
        for i in range(2, 4):
            docs.append(
                create_draft_document(
                    doctor=self.doctor,
                    daily_queue=self.queue,
                    position_no=20 + i,
                )
            )
        for d in docs:
            page = self.context.new_page()
            self.open_document_acquiring_session(page, d.id)

        target = docs[0]
        target.refresh_from_db()
        token = target.edit_session_token
        assert token is not None
        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            "summary_text": "publish frees slot",
        }
        saved = mutate_doctor_save_draft(
            medical_document_id=target.id,
            user=self.doctor,
            edit_session_token=token,
            expected_draft_revision=target.draft_revision,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=payload,
        )
        mark_doctor_draft_previewed(
            medical_document_id=target.id,
            user=self.doctor,
            edit_session_token=token,
            expected_draft_revision=saved.draft_revision,
        )
        mutate_doctor_publish(
            medical_document_id=target.id,
            user=self.doctor,
            edit_session_token=token,
            expected_draft_revision=saved.draft_revision,
            publish_request_id=uuid.uuid4(),
            publish_locale="de-DE",
        )
        target.refresh_from_db()
        self.assertIsNone(target.locked_by_user_id)

        fourth = create_draft_document(
            doctor=self.doctor, daily_queue=self.queue, position_no=30
        )
        page4 = self.context.new_page()
        body = self.open_document_acquiring_session(page4, fourth.id)
        self.assertIn("edit_session_token", body)
        fourth.refresh_from_db()
        self.assertEqual(fourth.locked_by_user_id, self.doctor.id)

    def test_autosave_put_after_dirty_interval(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ) as info:
            self.mark_form_dirty(self.page, "autosave payload text")
        body = info.value.json()
        self.assertIn("draft_revision", body)
        self.assertIn("autosave payload text", self.page.input_value("#summary_text"))
        self.assertTrue(self.page.is_disabled("#btn-publish"))

    def test_preview_autosave_publish_gate(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.mark_form_dirty(self.page, "preview gate note")
        self.assertTrue(self.page.is_disabled("#btn-publish"))

        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes",
            return_value=(_MIN_PDF, None),
        ):
            with self.page.expect_popup(timeout=45_000):
                with self.page.expect_response(
                    lambda r: "preview-pdf" in r.url and r.ok,
                    timeout=45_000,
                ):
                    self.page.click("#btn-preview-pdf")

        self.page.wait_for_function(
            "() => { const b = document.querySelector('#btn-publish');"
            " return b && !b.disabled; }",
            timeout=15_000,
        )

        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.mark_form_dirty(self.page, "after preview dirty")
        self.page.wait_for_function(
            "() => { const b = document.querySelector('#btn-publish');"
            " return b && b.disabled; }",
            timeout=15_000,
        )
        # Button stays disabled; force click to assert the preview-required warning.
        self.page.click("#btn-publish", force=True)
        alert = self.page.locator('#alert-placeholder [role="alert"]').first
        alert.wait_for(timeout=10_000)
        self.assertTrue(alert.inner_text().strip())

    def test_autosave_500_keeps_form_text(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)

        def fail_draft(route) -> None:
            if route.request.method == "PUT" and route.request.url.rstrip("/").endswith(
                "/draft"
            ):
                route.fulfill(status=500, body="boom", content_type="text/plain")
            else:
                route.continue_()

        self.page.route("**/api/v1/medical-documents/**", fail_draft)
        self.mark_form_dirty(self.page, "must survive http 500")
        self.page.wait_for_timeout(3500)
        self.assertIn(
            "must survive http 500", self.page.input_value("#summary_text")
        )
        self.assertTrue(self.page.is_enabled("#summary_text"))

    def test_autosave_offline_keeps_form_text(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)

        def abort_draft(route) -> None:
            if route.request.method == "PUT" and route.request.url.rstrip("/").endswith(
                "/draft"
            ):
                route.abort("failed")
            else:
                route.continue_()

        self.page.route("**/api/v1/medical-documents/**", abort_draft)
        self.mark_form_dirty(self.page, "must survive offline")
        self.page.wait_for_timeout(3500)
        self.assertIn("must survive offline", self.page.input_value("#summary_text"))

    def test_delayed_autosave_does_not_clear_newer_dirty(self) -> None:
        """Server-side delay keeps Playwright free so the user can keep typing."""
        self.open_document_acquiring_session(self.page, self.doc.id)
        real_save = mutate_doctor_save_draft
        call_count = {"n": 0}

        def slow_save(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                time.sleep(2.5)
            return real_save(*args, **kwargs)

        with patch(
            "apps.medical.api_views.mutate_doctor_save_draft", side_effect=slow_save
        ):
            with self.page.expect_request(
                lambda r: r.url.rstrip("/").endswith("/draft")
                and r.method == "PUT",
                timeout=20_000,
            ):
                self.mark_form_dirty(self.page, "first draft")
            # First PUT is in flight (handler sleeps); type a newer value.
            self.mark_form_dirty(self.page, "second draft while in flight")
            self.page.wait_for_function(
                "() => !document.querySelector('#btn-save-draft')?.disabled",
                timeout=20_000,
            )
            self.assertIn(
                "second draft while in flight",
                self.page.input_value("#summary_text"),
            )
            with self.page.expect_response(
                lambda r: r.url.rstrip("/").endswith("/draft")
                and r.request.method == "PUT"
                and r.ok,
                timeout=25_000,
            ):
                self.page.click("#btn-save-draft")
        self.assertIn(
            "second draft while in flight", self.page.input_value("#summary_text")
        )

    def test_leave_list_does_not_call_unlock(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        unlock_hits: list[int] = []

        def on_request(req) -> None:
            if req.method == "POST" and "/unlock" in req.url:
                unlock_hits.append(1)

        self.page.on("request", on_request)
        self.page.goto(
            f"{self.live_server_url}/doctor/?lang=de", wait_until="domcontentloaded"
        )
        self.page.wait_for_selector("#id_status", timeout=15_000)
        self.assertEqual(unlock_hits, [])
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.locked_by_user_id, self.doctor.id)
        self.assertIsNotNone(self.doc.edit_session_token)

    def test_back_navigation_does_not_unlock(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        unlock_hits: list[int] = []

        def on_request(req) -> None:
            if req.method == "POST" and "/unlock" in req.url:
                unlock_hits.append(1)

        self.page.on("request", on_request)
        self.page.goto(
            f"{self.live_server_url}/doctor/?lang=de", wait_until="domcontentloaded"
        )
        self.page.go_back(wait_until="domcontentloaded")
        self.page.wait_for_selector("#befund-form", timeout=30_000)
        self.assertEqual(unlock_hits, [])
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.locked_by_user_id, self.doctor.id)

    def test_fallback_without_navigator_locks_still_acquires(self) -> None:
        self.page.add_init_script(
            "Object.defineProperty(navigator, 'locks', { get: () => undefined });"
        )
        body = self.open_document_acquiring_session(self.page, self.doc.id)
        self.assertIn("edit_session_token", body)


class BefundEditSessionM7PlaywrightTests(PlaywrightDoctorE2EBase):
    """PUBLISHED + pending revision semaphore (M7)."""

    def setUp(self) -> None:
        super().setUp()
        suffix = uuid.uuid4().hex[:8]
        self.doctor = create_doctor(username=f"e2e_doc_m7_{suffix}")
        self.other = create_doctor(username=f"e2e_doc_m7b_{suffix}")
        self.queue = create_clinic_queue(
            doctor=self.doctor, code=f"M{suffix[:4].upper()}"
        )
        self.pub = create_published_document(
            doctor=self.doctor, daily_queue=self.queue, position_no=1
        )
        self.login_doctor(self.page, username=self.doctor.username)

    def test_other_doctor_blocked_on_open_revision(self) -> None:
        self.open_document(self.page, self.pub.id)
        self.start_amend_revision(self.page)

        ctx2 = self.new_context()
        page2 = ctx2.new_page()
        self.login_doctor(page2, username=self.other.username)
        page2.goto(
            f"{self.live_server_url}/doctor/{self.pub.id}/?lang=de",
            wait_until="domcontentloaded",
        )
        body = page2.locator("body").inner_text()
        self.assertTrue(body.strip())
        self.assertEqual(page2.locator("#btn-save-draft").count(), 0)
        self.pub.refresh_from_db()
        self.assertEqual(self.pub.locked_by_user_id, self.doctor.id)
        self.assertTrue(self.pub.has_pending_revision)
