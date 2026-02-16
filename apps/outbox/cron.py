from __future__ import annotations

from django_cron import CronJobBase, Schedule


class OutboxCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=1)
    code = "outbox.process_events"

    def do(self) -> None:
        # Outbox processing orchestration will be implemented in step 5.
        return


class RetentionCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=60)
    code = "outbox.retention_cleanup"

    def do(self) -> None:
        # Retention logic will be implemented in step 5.
        return
