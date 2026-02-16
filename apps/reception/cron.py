from __future__ import annotations

from django_cron import CronJobBase, Schedule


class DailyImportCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=60)
    code = "reception.daily_import_cron"

    def do(self) -> None:
        # Placeholder for scheduled import orchestration.
        return
