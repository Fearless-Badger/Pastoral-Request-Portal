"""Delete prayer requests older than settings.PRAYER_REQUEST_RETENTION_DAYS.

Runs daily from the `purge` service in docker-compose.yml. The privacy page tells
the public requests are deleted on this schedule, so that service is what makes
the sentence true. By hand:

    docker compose exec -T web python src/manage.py purge_old_requests --dry-run
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from lucid.models import PrayerRequest


class Command(BaseCommand):
    help = "Delete prayer requests older than the retention window, whatever their status."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        days = settings.PRAYER_REQUEST_RETENTION_DAYS
        # By age alone. A status-based rule would never touch the requests nobody
        # gets round to archiving, which are exactly the ones that pile up.
        old = PrayerRequest.objects.filter(
            submitted_at__lt=timezone.now() - timedelta(days=days)
        )

        if options["dry_run"]:
            self.stdout.write(
                f"Would delete {old.count()} prayer request(s) older than {days} days."
            )
            return

        deleted, _ = old.delete()

        # SQLite refuses to checkpoint inside an open transaction, which is where
        # a caller's atomic() (or a TestCase) would leave us. Cron never does.
        if deleted and connection.vendor == "sqlite" and not connection.in_atomic_block:
            # secure_delete (settings.py) zeroes the rows in the database file, but
            # earlier copies of those pages can still sit in the WAL until it is
            # reset. TRUNCATE checkpoints and empties it. A gunicorn worker mid-read
            # can block that; it is not an error, the frames get overwritten as the
            # WAL is reused, and tomorrow's run tries again.
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                busy, _, _ = cursor.fetchone()
            if busy:
                self.stderr.write(
                    "WAL checkpoint was blocked by a reader; old pages may linger until reuse."
                )

        self.stdout.write(f"Deleted {deleted} prayer request(s) older than {days} days.")
