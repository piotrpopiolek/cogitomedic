from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


class QueueEntryPublishedStatusGuardTests(SimpleTestCase):
    def test_queue_entry_status_published_not_used_outside_allowed_migrations(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        dead_status_token = "QueueEntryStatus." + "PUBLISHED"
        allowed = {
            Path("apps/reception/migrations/0001_initial.py"),
            Path(
                "apps/reception/migrations/0035_alter_patientformsession_options_and_more.py"
            ),
            Path("apps/reception/migrations/0037_drop_queue_entry_status_published.py"),
        }
        offenders: list[str] = []
        for path in root.joinpath("apps").rglob("*.py"):
            rel_path = path.relative_to(root)
            if rel_path in allowed:
                continue
            if dead_status_token in path.read_text(encoding="utf-8"):
                offenders.append(str(rel_path))

        self.assertEqual(
            offenders,
            [],
            msg=(
                "Dead queue-entry status token should remain only in historical migrations. "
                f"Found in: {offenders}"
            ),
        )
