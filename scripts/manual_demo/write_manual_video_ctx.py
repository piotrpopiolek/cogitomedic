"""Write manual-video ctx JSON for Playwright containers with SCREENSHOT_SKIP_DJANGO=1."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.manual_demo.django_setup import setup_django


def main() -> int:
    setup_django()
    from scripts.manual_demo.seed import seed_manual_demo

    ctx: dict = {}
    seed_manual_demo(ctx)
    out = {
        "password": ctx.get("password", "ScreenshotDemo2026!"),
        "medical_document_id": ctx.get("medical_document_id"),
        "queue_entry_err_id": ctx.get("queue_entry_err_id"),
        "queue_entry_tablet_id": ctx.get("queue_entry_tablet_id"),
        "intake_form_tablet_id": ctx.get("intake_form_tablet_id"),
        "intake_form_done_id": ctx.get("intake_form_done_id"),
        "session_otp_key": ctx.get("session_otp_key"),
        "session_doc_key": ctx.get("session_doc_key"),
        "portal_phone": ctx.get("portal_phone"),
        "portal_dob": ctx.get("portal_dob"),
        "portal_published_doc_id": ctx.get("portal_published_doc_id"),
    }
    path = _REPO / "docs" / "manual" / "_build" / "manual-video-ctx.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK ctx → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
