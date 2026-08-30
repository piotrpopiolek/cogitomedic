"""Static contract: doctor befund-form.js write-gate edit-session protocol."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class BefundFormEditSessionJsContractTests(SimpleTestCase):
    """Verify the JS form honours the new edit-session write-gate contract."""

    def _js_source(self) -> str:
        path = Path(settings.BASE_DIR) / "static" / "doctor" / "js" / "befund-form.js"
        return path.read_text(encoding="utf-8")

    # ── Must NOT contain old unlock artefacts ──────────────────────────

    def test_no_unlock_artefacts(self) -> None:
        src = self._js_source()
        self.assertNotIn("releaseEditLockBestEffort", src)
        self.assertNotIn("releaseEditLockOnIntentionalLeave", src)
        self.assertNotIn("js-release-document-lock", src)
        self.assertNotIn("/unlock", src)

    def test_no_pagehide_listener(self) -> None:
        src = self._js_source()
        self.assertNotIn("pagehide", src)

    # ── Must contain edit-session artefacts ─────────────────────────────

    def test_edit_session_endpoint(self) -> None:
        src = self._js_source()
        self.assertIn("edit-session", src)

    def test_edit_session_token_field(self) -> None:
        src = self._js_source()
        self.assertIn("edit_session_token", src)

    def test_expected_draft_revision_field(self) -> None:
        src = self._js_source()
        self.assertIn("expected_draft_revision", src)

    def test_draft_save_request_id_field(self) -> None:
        src = self._js_source()
        self.assertIn("draft_save_request_id", src)

    def test_session_token_header(self) -> None:
        src = self._js_source()
        self.assertIn("X-Edit-Session-Token", src)

    def test_autosave_constant(self) -> None:
        src = self._js_source()
        self.assertIn("AUTOSAVE_MS", src)
        self.assertIn("autosaveIntervalMs", src)
        self.assertIn("10 * 60 * 1000", src)
        self.assertIn('addEventListener("online"', src)
        self.assertIn("navigator.onLine", src)
        self.assertIn("msgAutosavePreviewAgain", src)

    def test_reclaim_support(self) -> None:
        src = self._js_source()
        self.assertIn("reclaim", src)

    def test_cross_tab_coordination(self) -> None:
        src = self._js_source()
        self.assertIn("BroadcastChannel", src)
        self.assertIn("navigator.locks", src)
        self.assertIn("localStorage", src)
        self.assertIn('addEventListener("storage"', src)
        self.assertIn("lock-limit-link", src)
        lock_limit = src[
            src.index("function renderDoctorLockLimit") : src.index(
                "function renderDoctorLockLimit"
            )
            + 900
        ]
        self.assertIn("PANEL.lang", lock_limit)
        self.assertNotIn("/?lang=de", lock_limit)
        start = src.index("function handleSessionErrorResponse")
        handler_end = src.index("\n  try {", start)
        handler = src[start:handler_end]
        # Amend (performStartRevision) routes 409 through this helper.
        self.assertIn("doctor_lock_limit_reached", handler)
        self.assertIn("renderDoctorLockLimit", handler)
        amend = src[
            src.index("function performStartRevision") : src.index(
                "function performStartRevision"
            )
            + 800
        ]
        self.assertIn("handleSessionErrorResponse", amend)
        self.assertIn("publish_preview_revision_stale", handler)
        self.assertIn("msgPublishPreviewRequired", handler)

    def test_edit_after_preview_clears_publish_gate(self) -> None:
        src = self._js_source()
        dirty = src[
            src.index("function markBefundFormDirty") : src.index(
                "function markBefundFormDirty"
            )
            + 280
        ]
        self.assertIn("previewSeenSinceLastSave = false", dirty)
        self.assertIn("setPublishEnabledFromPreviewFlag", dirty)
        self.assertIn('addEventListener("input", markBefundFormDirty)', src)
        self.assertIn('addEventListener("change", markBefundFormDirty)', src)
        click_at = src.index('publishBtn.addEventListener("click"')
        publish_click = src[
            click_at : src.index("document.body.addEventListener", click_at)
        ]
        self.assertGreaterEqual(publish_click.count("handleSessionErrorResponse"), 2)

    # ── Dirty warning kept but no unlock ───────────────────────────────

    def test_beforeunload_dirty_warning_no_unlock(self) -> None:
        src = self._js_source()
        self.assertIn('addEventListener("beforeunload"', src)
        idx = src.index('addEventListener("beforeunload"')
        chunk = src[idx : idx + 350]
        self.assertIn("returnValue", chunk)
        self.assertNotIn("unlock", chunk.lower())

    def test_draft_save_clears_dirty_flag(self) -> None:
        src = self._js_source()
        self.assertIn("befundFormDirty = false", src)

    # ── Intake summary / reception note (unchanged behaviour) ──────────

    def test_intake_summary_renders_reception_note_after_anamnesis(self) -> None:
        src = self._js_source()
        self.assertIn('el("intake-reception-note")', src)
        self.assertIn("insertBefore", src)
        self.assertNotIn("summaryEl.appendChild(noteSlot)", src)
        self.assertIn("CTX.intake_summary && CTX.intake_summary.reception_note", src)
        self.assertIn("whitespace-pre-wrap", src)
        self.assertEqual(src.count("const bodyMapUrl ="), 1)

    def test_intake_summary_reception_note_not_gated_on_revision_or_draft(self) -> None:
        """Empfangsnotiz is painted from CTX on load, including pending revision."""
        src = self._js_source()
        summary_idx = src.index("if (CTX && CTX.intake_summary)")
        note_idx = src.index('el("intake-reception-note")')
        skip_form_idx = src.index("var skipBefundFormUi")
        self.assertLess(summary_idx, note_idx)
        self.assertLess(note_idx, skip_form_idx)
        block = src[summary_idx:skip_form_idx]
        self.assertNotIn("hasPendingRevision", block)
        self.assertNotIn("isDraftAuthoring", block)
        self.assertNotIn("docStatus", block)
