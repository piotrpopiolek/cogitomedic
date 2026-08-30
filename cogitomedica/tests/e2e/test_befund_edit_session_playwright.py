"""Playwright E2E: doctor Befund edit-session, multitab, amend, autosave, unlock cutover."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from apps.medical.models import MedicalDocStatus, MedicalDocument
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

    def test_republish_releases_lock(self) -> None:
        self.open_document(self.page, self.pub.id)
        sess = self.start_amend_revision(self.page)
        self.mark_form_dirty(self.page, "republish note")
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.page.click("#btn-save-draft")
        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes",
            return_value=(_MIN_PDF, None),
        ):
            self.click_preview_pdf(self.page)
        self.wait_for_publish_enabled(self.page, enabled=True)
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/publish")
            and r.request.method == "POST"
            and r.ok,
            timeout=45_000,
        ):
            self.page.click("#btn-publish")
        self.pub.refresh_from_db()
        self.assertFalse(self.pub.has_pending_revision)
        self.assertIsNone(self.pub.locked_by_user_id)
        self.assertIsNone(self.pub.edit_session_token)
        self.assertIn("edit_session_token", sess)


class BefundEditSessionExtendedPlaywrightTests(PlaywrightDoctorE2EBase):
    """Remaining §6.3: BroadcastChannel, visibility, races, preview loop, logout/close."""

    def setUp(self) -> None:
        super().setUp()
        suffix = uuid.uuid4().hex[:8]
        self.doctor = create_doctor(username=f"e2e_doc_x_{suffix}")
        self.queue = create_clinic_queue(
            doctor=self.doctor, code=f"X{suffix[:4].upper()}"
        )
        self.doc = create_draft_document(
            doctor=self.doctor, daily_queue=self.queue, position_no=1
        )
        self.login_doctor(self.page, username=self.doctor.username)

    def test_broadcast_channel_invalidate_blocks_first_tab(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        # Inject sibling-tab invalidate (Web Locks reclaim path is separate).
        self.page.evaluate(
            """(docId) => {
              const ch = new BroadcastChannel('befund-edit-' + docId);
              ch.postMessage({ type: 'invalidate', docId: docId });
              ch.close();
            }""",
            str(self.doc.id),
        )
        self.page.wait_for_function(
            "() => { const b = document.querySelector('#btn-save-draft');"
            " return b && b.disabled; }",
            timeout=20_000,
        )
        self.mark_form_dirty(self.page, "blocked after broadcast")
        self.assertIn(
            "blocked after broadcast", self.page.input_value("#summary_text")
        )

    def test_session_storage_survives_navigation_and_resume(self) -> None:
        first = self.open_document_acquiring_session(self.page, self.doc.id)
        token = first["edit_session_token"]
        self.page.goto(
            f"{self.live_server_url}/doctor/?lang=de", wait_until="domcontentloaded"
        )
        stored = self.session_storage_token(
            self.page, staff_user_id=str(self.doctor.id), document_id=self.doc.id
        )
        # Leaving the form may clear or keep sessionStorage depending on same tab;
        # reopen must resume when token is still present, otherwise acquire cleanly.
        with self.page.expect_response(
            lambda r: "/edit-session" in r.url and r.request.method == "POST" and r.ok,
            timeout=45_000,
        ) as info:
            self.open_document(self.page, self.doc.id)
        body = info.value.json()
        self.page.wait_for_selector("#btn-save-draft:not([disabled])", timeout=30_000)
        if stored == token:
            self.assertEqual(body.get("edit_session_token"), token)
            self.assertEqual(body.get("mode"), "resumed")
        else:
            self.assertIn("edit_session_token", body)

    def test_logout_does_not_call_unlock(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        unlock_hits = self.track_unlock_posts(self.page)
        self.click_logout(self.page)
        self.assertEqual(unlock_hits, [])
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.locked_by_user_id, self.doctor.id)
        self.assertIsNotNone(self.doc.edit_session_token)

    def test_closing_tab_does_not_unlock(self) -> None:
        page2 = self.context.new_page()
        unlock_hits = self.track_unlock_posts(page2)
        self.open_document_acquiring_session(page2, self.doc.id)
        page2.close()
        self.assertEqual(unlock_hits, [])
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.locked_by_user_id, self.doctor.id)
        self.assertIsNotNone(self.doc.edit_session_token)

    def test_bfcache_style_back_does_not_unlock(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        unlock_hits = self.track_unlock_posts(self.page)
        self.page.goto(
            f"{self.live_server_url}/doctor/?lang=de", wait_until="domcontentloaded"
        )
        self.page.go_back(wait_until="domcontentloaded")
        # Simulate pageshow from bfcache restore (PageTransitionEvent may be missing).
        self.page.evaluate(
            """() => {
              try {
                const ev = new PageTransitionEvent('pageshow', { persisted: true });
                window.dispatchEvent(ev);
              } catch (e) {
                window.dispatchEvent(new Event('pageshow'));
              }
            }"""
        )
        self.page.wait_for_selector("#befund-form", timeout=30_000)
        self.assertEqual(unlock_hits, [])
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.locked_by_user_id, self.doctor.id)

    def test_hidden_tab_skips_autosave_until_visible(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        draft_puts: list[str] = []

        def on_request(req) -> None:
            if req.method == "PUT" and req.url.rstrip("/").endswith("/draft"):
                draft_puts.append(req.url)

        self.page.on("request", on_request)
        self.set_document_visibility(self.page, hidden=True)
        self.mark_form_dirty(self.page, "hidden dirty text")
        self.page.wait_for_timeout(3500)
        self.assertEqual(draft_puts, [])
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.set_document_visibility(self.page, hidden=False)
        self.assertIn("hidden dirty text", self.page.input_value("#summary_text"))

    def test_clean_form_does_not_autosave(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        draft_puts: list[str] = []

        def on_request(req) -> None:
            if req.method == "PUT" and req.url.rstrip("/").endswith("/draft"):
                draft_puts.append(req.url)

        self.page.on("request", on_request)
        self.page.wait_for_timeout(3500)
        self.assertEqual(draft_puts, [])

    def test_validation_error_skips_autosave(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        draft_puts: list[str] = []

        def on_request(req) -> None:
            if req.method == "PUT" and req.url.rstrip("/").endswith("/draft"):
                draft_puts.append(req.url)

        self.page.on("request", on_request)
        self.page.check(
            'input[name="overall_image_assessment"][value="CONTROL_NEEDED"]'
        )
        self.mark_form_dirty(self.page, "needs lesion")
        self.page.wait_for_timeout(3500)
        self.assertEqual(draft_puts, [])
        self.assertIn("needs lesion", self.page.input_value("#summary_text"))

    def test_autosave_timeout_keeps_form_text(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)

        def hang_then_timeout(route) -> None:
            if route.request.method == "PUT" and route.request.url.rstrip("/").endswith(
                "/draft"
            ):
                route.abort("timedout")
            else:
                route.continue_()

        self.page.route("**/api/v1/medical-documents/**", hang_then_timeout)
        self.mark_form_dirty(self.page, "must survive timeout")
        self.page.wait_for_timeout(3500)
        self.assertIn("must survive timeout", self.page.input_value("#summary_text"))

    def test_lost_response_after_commit_keeps_form_text(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)

        def drop_after_server(route) -> None:
            if route.request.method == "PUT" and route.request.url.rstrip("/").endswith(
                "/draft"
            ):
                # Let Django commit, then drop the body so the client sees a network error.
                route.fetch()
                route.abort("failed")
            else:
                route.continue_()

        self.page.route("**/api/v1/medical-documents/**", drop_after_server)
        self.mark_form_dirty(self.page, "committed but lost response")
        self.page.wait_for_timeout(4000)
        self.assertIn(
            "committed but lost response", self.page.input_value("#summary_text")
        )
        self.doc.refresh_from_db()
        # Server may have accepted the draft even though UI never saw the response.
        self.assertGreaterEqual(self.doc.draft_revision, 0)

    def test_concurrent_save_preview_publish_serialized(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        self.mark_form_dirty(self.page, "serialize writes")
        # Wait until first autosave/manual path is idle, then force overlapping clicks.
        self.page.wait_for_timeout(500)
        in_flight_peak = {"n": 0, "cur": 0}
        put_count = {"n": 0}

        def on_request(req) -> None:
            if req.method == "PUT" and req.url.rstrip("/").endswith("/draft"):
                put_count["n"] += 1
                in_flight_peak["cur"] += 1
                in_flight_peak["n"] = max(in_flight_peak["n"], in_flight_peak["cur"])

        def on_finished(req) -> None:
            if req.method == "PUT" and req.url.rstrip("/").endswith("/draft"):
                in_flight_peak["cur"] = max(0, in_flight_peak["cur"] - 1)

        self.page.on("request", on_request)
        self.page.on("requestfinished", on_finished)
        self.page.on("requestfailed", on_finished)

        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes",
            return_value=(_MIN_PDF, None),
        ):
            # Overlapping clicks: writeInFlight must keep concurrent mutators out.
            self.page.evaluate(
                """() => {
                  const save = document.querySelector('#btn-save-draft');
                  const preview = document.querySelector('#btn-preview-pdf');
                  const publish = document.querySelector('#btn-publish');
                  if (save) save.click();
                  if (preview) preview.click();
                  if (publish) publish.click();
                }"""
            )
            self.page.wait_for_timeout(4000)

        self.assertLessEqual(in_flight_peak["n"], 1)
        self.assertIn("serialize writes", self.page.input_value("#summary_text"))

    def test_second_preview_same_content_reenables_publish(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.mark_form_dirty(self.page, "stable preview content")
        self.wait_for_publish_enabled(self.page, enabled=False)

        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes",
            return_value=(_MIN_PDF, None),
        ):
            self.click_preview_pdf(self.page)
            self.wait_for_publish_enabled(self.page, enabled=True)

            with self.page.expect_response(
                lambda r: r.url.rstrip("/").endswith("/draft")
                and r.request.method == "PUT"
                and r.ok,
                timeout=20_000,
            ):
                self.mark_form_dirty(self.page, "after preview change")
            self.wait_for_publish_enabled(self.page, enabled=False)

            # Second preview of the current content re-arms Publish.
            self.click_preview_pdf(self.page)
            self.wait_for_publish_enabled(self.page, enabled=True)

    def test_session_restore_via_session_storage_init(self) -> None:
        first = self.open_document_acquiring_session(self.page, self.doc.id)
        token = first["edit_session_token"]
        key = f"befundEditSession:{self.doctor.id}:{self.doc.id}"
        raw = self.page.evaluate(
            """(k) => {
              try { return sessionStorage.getItem(k); } catch (e) { return null; }
            }""",
            key,
        )
        self.assertTrue(raw)
        self.page.close()
        page2 = self.context.new_page()
        # Browser session restore recreates sessionStorage for the document tab.
        page2.add_init_script(
            "try { sessionStorage.setItem(%s, %s); } catch (e) {}"
            % (json.dumps(key), json.dumps(raw))
        )
        with page2.expect_response(
            lambda r: "/edit-session" in r.url and r.request.method == "POST" and r.ok,
            timeout=45_000,
        ) as info:
            self.open_document(page2, self.doc.id)
        resumed = info.value.json()
        self.assertEqual(resumed["edit_session_token"], token)
        self.assertEqual(resumed.get("mode"), "resumed")


_MSG_PUBLISH_PREVIEW_REQUIRED = (
    "Bitte zuerst PDF-Vorschau nach dem letzten Speichern öffnen."
)
_MSG_AUTOSAVE_SUCCESS = "Entwurf automatisch gespeichert"
_MSG_AUTOSAVE_PREVIEW_AGAIN = (
    "Nach dem automatischen Speichern bitte erneut Vorschau prüfen vor dem Veröffentlichen."
)
_MSG_RECLAIM_TITLE = "Eigene Sitzung wiederherstellen?"
_MSG_LOCAL_TAB_TITLE = "Bereits in einem anderen Tab geöffnet"


class BefundEditSessionSection63GapsPlaywrightTests(PlaywrightDoctorE2EBase):
    """Remaining §6.3 gaps: storage fallback, Clock, 409/423, limit links, reclaim."""

    def setUp(self) -> None:
        super().setUp()
        suffix = uuid.uuid4().hex[:8]
        self.doctor = create_doctor(username=f"e2e_doc_g_{suffix}")
        self.queue = create_clinic_queue(
            doctor=self.doctor, code=f"G{suffix[:4].upper()}"
        )
        self.doc = create_draft_document(
            doctor=self.doctor,
            daily_queue=self.queue,
            position_no=1,
            patient_last=f"Gap{suffix[:6]}",
        )
        self.login_doctor(self.page, username=self.doctor.username)

    @contextmanager
    def _production_autosave_interval(self):
        prev = os.environ.get("E2E_AUTOSAVE_MS")
        os.environ["E2E_AUTOSAVE_MS"] = ""
        try:
            yield
        finally:
            if prev is None:
                os.environ.pop("E2E_AUTOSAVE_MS", None)
            else:
                os.environ["E2E_AUTOSAVE_MS"] = prev

    def test_storage_fallback_invalidates_first_tab(self) -> None:
        self.add_no_locks_no_broadcast_init()
        self.open_document_acquiring_session(self.page, self.doc.id)
        page2 = self.context.new_page()
        page2.goto(
            f"{self.live_server_url}/doctor/{self.doc.id}/?lang=de",
            wait_until="domcontentloaded",
        )
        page2.wait_for_selector("#revision-modal:not(.hidden)", timeout=20_000)
        self.assertIn(
            _MSG_LOCAL_TAB_TITLE, page2.locator("#revision-modal-title").inner_text()
        )
        with page2.expect_response(
            lambda r: "/edit-session" in r.url and r.request.method == "POST" and r.ok,
            timeout=45_000,
        ):
            self.confirm_revision_modal(page2)
        page2.wait_for_selector("#btn-save-draft:not([disabled])", timeout=30_000)
        self.page.wait_for_function(
            "() => { const b = document.querySelector('#btn-save-draft');"
            " return b && b.disabled; }",
            timeout=20_000,
        )
        self.mark_form_dirty(self.page, "blocked via storage fallback")
        self.assertIn(
            "blocked via storage fallback", self.page.input_value("#summary_text")
        )
        self.assertTrue(self.page.is_disabled("#btn-publish"))

    def test_simultaneous_two_tab_start_one_holder(self) -> None:
        page2 = self.context.new_page()
        url = f"{self.live_server_url}/doctor/{self.doc.id}/?lang=de"

        def delay_edit_session(route) -> None:
            if "/edit-session" in route.request.url and route.request.method == "POST":
                time.sleep(0.6)
            route.continue_()

        self.page.route("**/api/v1/medical-documents/**", delay_edit_session)
        page2.route("**/api/v1/medical-documents/**", delay_edit_session)
        self.page.goto(url, wait_until="commit")
        page2.goto(url, wait_until="commit")
        self.page.wait_for_load_state("domcontentloaded")
        page2.wait_for_load_state("domcontentloaded")

        deadline = time.time() + 40

        def state(page) -> dict:
            return page.evaluate(
                """() => {
                  const save = document.querySelector('#btn-save-draft');
                  const modal = document.querySelector('#revision-modal');
                  return {
                    saveEnabled: !!(save && !save.disabled),
                    modalOpen: !!(modal && !modal.classList.contains('hidden')),
                  };
                }"""
            )

        s1 = s2 = {"saveEnabled": False, "modalOpen": False}
        while time.time() < deadline:
            s1, s2 = state(self.page), state(page2)
            if (s1["saveEnabled"] or s1["modalOpen"]) and (
                s2["saveEnabled"] or s2["modalOpen"]
            ):
                break
            time.sleep(0.2)
        self.assertEqual(int(s1["saveEnabled"]) + int(s2["saveEnabled"]), 1)
        self.assertTrue(s1["modalOpen"] or s2["modalOpen"])
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.locked_by_user_id, self.doctor.id)
        self.assertIsNotNone(self.doc.edit_session_token)

    def test_draft_409_blocks_writes_without_reload(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        url_before = self.page.url
        puts_after_block: list[int] = []
        blocked = {"done": False}

        def conflict(route) -> None:
            if route.request.method == "PUT" and route.request.url.rstrip("/").endswith(
                "/draft"
            ):
                if blocked["done"]:
                    puts_after_block.append(1)
                route.fulfill(
                    status=409,
                    content_type="application/json",
                    body=json.dumps({"error_key": "draft_revision_conflict"}),
                )
            else:
                route.continue_()

        self.page.route("**/api/v1/medical-documents/**", conflict)
        self.mark_form_dirty(self.page, "must survive 409")
        self.page.click("#btn-save-draft")
        self.page.wait_for_function(
            "() => { const b = document.querySelector('#btn-save-draft');"
            " return b && b.disabled; }",
            timeout=15_000,
        )
        blocked["done"] = True
        self.assertEqual(self.page.url, url_before)
        self.assertIn("must survive 409", self.page.input_value("#summary_text"))
        self.assertTrue(self.page.is_disabled("#btn-publish"))
        self.page.wait_for_timeout(2500)
        self.assertEqual(puts_after_block, [])
        self.assertTrue(self.page.locator("#befund-form").is_visible())

    def test_draft_423_blocks_writes_without_reload(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        url_before = self.page.url

        def stale(route) -> None:
            if route.request.method == "PUT" and route.request.url.rstrip("/").endswith(
                "/draft"
            ):
                route.fulfill(
                    status=423,
                    content_type="application/json",
                    body=json.dumps({"error_key": "edit_session_stale"}),
                )
            else:
                route.continue_()

        self.page.route("**/api/v1/medical-documents/**", stale)
        self.mark_form_dirty(self.page, "must survive 423")
        self.page.click("#btn-save-draft")
        self.page.wait_for_function(
            "() => { const b = document.querySelector('#btn-save-draft');"
            " return b && b.disabled; }",
            timeout=15_000,
        )
        alert = self.alert_text(self.page)
        self.assertTrue(alert.strip())
        self.assertEqual(self.page.url, url_before)
        self.assertIn("must survive 423", self.page.input_value("#summary_text"))
        self.assertTrue(self.page.is_disabled("#btn-publish"))
        self.assertTrue(self.page.locator("#befund-form").is_visible())

    def test_publish_after_autosave_shows_preview_required(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.mark_form_dirty(self.page, "gate after autosave")
        self.wait_for_publish_enabled(self.page, enabled=False)
        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes",
            return_value=(_MIN_PDF, None),
        ):
            self.click_preview_pdf(self.page)
        self.wait_for_publish_enabled(self.page, enabled=True)
        # lastSuccessfulSaveAt blocks another autosave until AUTOSAVE_MS elapses.
        self.page.wait_for_timeout(2200)
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.mark_form_dirty(self.page, "autosave disables publish")
        self.wait_for_publish_enabled(self.page, enabled=False)
        self.dispatch_publish_click(self.page)
        self.assertIn(_MSG_PUBLISH_PREVIEW_REQUIRED, self.alert_text(self.page))
        self.assertEqual(self.page.locator("#befund-form").count(), 1)

    def test_autosave_keeps_caret_and_shows_status(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        text = "caret stays here after autosave"
        caret = 11
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.page.evaluate(
                """({ text, caret }) => {
                  const el = document.querySelector('#summary_text');
                  el.focus();
                  el.value = text;
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                  el.setSelectionRange(caret, caret);
                }""",
                {"text": text, "caret": caret},
            )
        after = self.page.evaluate(
            """() => {
              const el = document.querySelector('#summary_text');
              return {
                active: document.activeElement === el,
                start: el.selectionStart,
                end: el.selectionEnd,
                value: el.value,
              };
            }"""
        )
        self.assertEqual(after["value"], text)
        self.assertTrue(after["active"])
        self.assertEqual(after["start"], caret)
        self.assertEqual(after["end"], caret)
        self.assertIn(_MSG_AUTOSAVE_SUCCESS, self.alert_text(self.page))

    def test_clock_one_autosave_after_ten_minutes(self) -> None:
        with self._production_autosave_interval():
            page = self.context.new_page()
            page.clock.install()
            self.open_document_acquiring_session(page, self.doc.id)
            puts: list[str] = []

            def on_request(req) -> None:
                if req.method == "PUT" and req.url.rstrip("/").endswith("/draft"):
                    puts.append(req.url)

            page.on("request", on_request)
            self.mark_form_dirty(page, "clocked autosave once")
            page.clock.fast_forward("09:59")
            self.assertEqual(puts, [])
            with page.expect_response(
                lambda r: r.url.rstrip("/").endswith("/draft")
                and r.request.method == "PUT"
                and r.ok,
                timeout=20_000,
            ):
                page.clock.fast_forward("00:02")
            self.assertEqual(len(puts), 1)
            page.clock.fast_forward("10:00")
            self.assertEqual(len(puts), 1)
            self.assertIn("clocked autosave once", page.input_value("#summary_text"))

    def test_clock_hidden_overdue_saves_when_visible(self) -> None:
        with self._production_autosave_interval():
            page = self.context.new_page()
            page.clock.install()
            self.open_document_acquiring_session(page, self.doc.id)
            puts: list[str] = []

            def on_request(req) -> None:
                if req.method == "PUT" and req.url.rstrip("/").endswith("/draft"):
                    puts.append(req.url)

            page.on("request", on_request)
            self.set_document_visibility(page, hidden=True)
            self.mark_form_dirty(page, "overdue hidden tab")
            page.clock.fast_forward("10:00")
            self.assertEqual(puts, [])
            with page.expect_response(
                lambda r: r.url.rstrip("/").endswith("/draft")
                and r.request.method == "PUT"
                and r.ok,
                timeout=20_000,
            ):
                self.set_document_visibility(page, hidden=False)
            self.assertEqual(len(puts), 1)
            self.assertIn("overdue hidden tab", page.input_value("#summary_text"))

    def test_lock_limit_screen_links_three_cases(self) -> None:
        docs = [self.doc]
        for i in range(2, 4):
            docs.append(
                create_draft_document(
                    doctor=self.doctor,
                    daily_queue=self.queue,
                    position_no=i,
                    patient_last=f"Held{i}{uuid.uuid4().hex[:4]}",
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
        page4.wait_for_selector("#lock-limit-screen", timeout=30_000)
        links = page4.locator("#lock-limit-screen a.lock-limit-link")
        self.assertEqual(links.count(), 3)
        hrefs = [links.nth(i).get_attribute("href") or "" for i in range(3)]
        for d in docs:
            self.assertTrue(
                any(str(d.id) in href for href in hrefs),
                msg=f"missing link for {d.id} in {hrefs}",
            )
        fourth.refresh_from_db()
        self.assertIsNone(fourth.locked_by_user_id)

    def test_second_device_shows_reclaim_modal(self) -> None:
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
        self.assertEqual(first_attempt.value.status, 409)
        page2.wait_for_selector("#revision-modal:not(.hidden)", timeout=20_000)
        self.assertIn(
            _MSG_RECLAIM_TITLE, page2.locator("#revision-modal-title").inner_text()
        )
        with page2.expect_response(
            lambda r: "/edit-session" in r.url and r.request.method == "POST" and r.ok,
            timeout=45_000,
        ) as reclaim:
            self.confirm_revision_modal(page2)
        body = reclaim.value.json()
        self.assertEqual(body.get("mode"), "reclaimed")
        self.assertNotEqual(body.get("edit_session_token"), old_token)
        page2.wait_for_selector("#btn-save-draft:not([disabled])", timeout=30_000)

    def test_pending_revision_requires_first_preview_before_publish(self) -> None:
        pub = create_published_document(
            doctor=self.doctor, daily_queue=self.queue, position_no=40
        )
        self.open_document(self.page, pub.id)
        self.start_amend_revision(self.page)
        self.wait_for_publish_enabled(self.page, enabled=False)
        self.dispatch_publish_click(self.page)
        self.assertIn(_MSG_PUBLISH_PREVIEW_REQUIRED, self.alert_text(self.page))
        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes",
            return_value=(_MIN_PDF, None),
        ):
            self.click_preview_pdf(self.page)
        self.wait_for_publish_enabled(self.page, enabled=True)

    def test_autosave_shows_preview_again_status(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.mark_form_dirty(self.page, "autosave status note")
        alert = self.alert_text(self.page)
        self.assertIn(_MSG_AUTOSAVE_SUCCESS, alert)
        self.assertIn(_MSG_AUTOSAVE_PREVIEW_AGAIN, alert)
        self.wait_for_publish_enabled(self.page, enabled=False)
        self.dispatch_publish_click(self.page)
        self.assertIn(_MSG_PUBLISH_PREVIEW_REQUIRED, self.alert_text(self.page))

    def test_autosave_retries_after_online(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        puts: list[str] = []

        def on_request(req) -> None:
            if req.method == "PUT" and req.url.rstrip("/").endswith("/draft"):
                puts.append(req.url)

        self.page.on("request", on_request)
        self.page.evaluate(
            """() => {
              Object.defineProperty(navigator, 'onLine', {
                configurable: true,
                get: () => false,
              });
            }"""
        )
        self.page.context.set_offline(True)
        self.mark_form_dirty(self.page, "reconnect then save")
        self.page.wait_for_timeout(3500)
        self.assertEqual(puts, [])
        self.page.context.set_offline(False)
        with self.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            self.page.evaluate(
                """() => {
                  Object.defineProperty(navigator, 'onLine', {
                    configurable: true,
                    get: () => true,
                  });
                  window.dispatchEvent(new Event('online'));
                }"""
            )
        self.assertIn("reconnect then save", self.page.input_value("#summary_text"))
        self.assertIn(_MSG_AUTOSAVE_SUCCESS, self.alert_text(self.page))

    def test_local_tab_trotzdem_oeffnen_blocks_first_tab(self) -> None:
        self.open_document_acquiring_session(self.page, self.doc.id)
        page2 = self.context.new_page()
        page2.goto(
            f"{self.live_server_url}/doctor/{self.doc.id}/?lang=de",
            wait_until="domcontentloaded",
        )
        page2.wait_for_selector("#revision-modal:not(.hidden)", timeout=20_000)
        self.assertIn(
            _MSG_LOCAL_TAB_TITLE, page2.locator("#revision-modal-title").inner_text()
        )
        with page2.expect_response(
            lambda r: "/edit-session" in r.url and r.request.method == "POST" and r.ok,
            timeout=45_000,
        ):
            self.confirm_revision_modal(page2)
        page2.wait_for_selector("#btn-save-draft:not([disabled])", timeout=30_000)
        self.page.wait_for_function(
            "() => { const b = document.querySelector('#btn-save-draft');"
            " return b && b.disabled; }",
            timeout=20_000,
        )
        self.mark_form_dirty(self.page, "stale after trotzdem")
        self.assertIn("stale after trotzdem", self.page.input_value("#summary_text"))
        self.assertTrue(self.page.is_disabled("#btn-publish"))
        page2.fill("#summary_text", "second tab writes after trotzdem")
        with page2.expect_response(
            lambda r: r.url.rstrip("/").endswith("/draft")
            and r.request.method == "PUT"
            and r.ok,
            timeout=20_000,
        ):
            page2.click("#btn-save-draft")
        self.doc.refresh_from_db()
        self.assertGreaterEqual(self.doc.draft_revision, 1)

