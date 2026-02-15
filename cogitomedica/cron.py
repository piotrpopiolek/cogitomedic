from datetime import datetime, timedelta
from django.db.models import Q
from django.utils import timezone
from django_cron import CronJobBase, Schedule
from pathlib import Path
from results.models import User, LabResults
import os
import time
import logging

BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_ROOT = os.path.join(BASE_DIR, 'pdf_files/results_files')

LOG_DIR = os.path.join(Path(BASE_DIR).resolve().parent, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, 'cron_cleaner.log')

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

class CronCleaner(CronJobBase):
    RUN_EVERY_MINS = 1
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'cleaner'

    def do(self):
        logging.info('Cron działa')

        DAYS_THRESHOLD = 180

        self.delete_old_results_and_users(DAYS_THRESHOLD)

        now = time.time()

        for root, dirs, files in os.walk(MEDIA_ROOT):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_creation_time = os.path.getctime(file_path)
                    if (now - file_creation_time) > (DAYS_THRESHOLD * 86400):
                        os.remove(file_path)
                except Exception as e:
                    logging.error(f"Nie udało się usunąć pliku {file_path}: {e}")

    def delete_old_results_and_users(self, days: int):
        threshold_date = timezone.now() - timedelta(days=days)

        logging.info(f'Usuwanie wyników i użytkowników starszych niż {days} dni: {threshold_date}')

        old_results = LabResults.objects.filter(date_created__lt=threshold_date)
        old_results_count = old_results.count()
        old_results.delete()

        users = User.objects.filter(is_staff=False)
        users_to_delete = []

        for user in users:
            has_results = LabResults.objects.filter(
                Q(owner=user) | Q(creator=user)
            ).exists()

            if not has_results:
                users_to_delete.append(user.id)

        deleted_users = User.objects.filter(id__in=users_to_delete)
        deleted_users_count = deleted_users.count()
        # deleted_users.delete()

        logging.info(f'Usunięto {old_results_count} starych wyników i {deleted_users_count} użytkowników bez wyników.')

        return {
            'labresults_deleted': old_results_count,
            'users_deleted': deleted_users_count,
        }
