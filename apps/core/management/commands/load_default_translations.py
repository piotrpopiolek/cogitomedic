from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.translation_loader import seed_for_management_command


class Command(BaseCommand):
    help = "Seed translation tables from apps/core/translation_data/*.json (idempotent get_or_create)."

    @transaction.atomic
    def handle(self, *args, **options):
        created = seed_for_management_command()
        self.stdout.write(
            self.style.SUCCESS(
                f"Translation seed finished. New TranslationValue rows created: {created}."
            )
        )
