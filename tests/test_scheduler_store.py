from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from src.scheduler import SchedulerStore, SchedulerStoreConfig, utc_iso


class SchedulerStoreTests(unittest.TestCase):
    def _store(self, directory: str) -> SchedulerStore:
        return SchedulerStore(SchedulerStoreConfig(database=Path(directory) / 'tasks.db'))

    def test_schedule_cancel_and_snooze(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self._store(directory) as store:
                task = store.schedule_after(message='테스트', delay_seconds=60)
                self.assertEqual(task.status, 'active')
                cancelled = store.cancel(task.id)
                self.assertEqual(cancelled.status, 'cancelled')
                snoozed = store.snooze(task_id=task.id, delay_minutes=10)
                self.assertEqual(snoozed.status, 'active')

    def test_due_one_time_is_completed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self._store(directory) as store:
                now = datetime.now(timezone.utc)
                task = store.schedule_at(message='곧 실행', run_at=utc_iso(now + timedelta(seconds=10)))
                due = store.claim_due(now=now + timedelta(seconds=11))
                self.assertEqual(len(due), 1)
                self.assertEqual(due[0].task.id, task.id)
                self.assertEqual(store.get(task.id).status, 'completed')

    def test_daily_task_skips_missed_occurrences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self._store(directory) as store:
                now = datetime.now(timezone.utc)
                task = store.schedule_at(
                    message='매일',
                    run_at=utc_iso(now + timedelta(seconds=10)),
                    recurrence='daily',
                    interval=1,
                )
                claim_time = now + timedelta(days=3, seconds=11)
                due = store.claim_due(now=claim_time)
                self.assertEqual(len(due), 1)
                current = store.get(task.id)
                self.assertEqual(current.status, 'active')
                self.assertGreater(current.next_run_datetime, claim_time)


if __name__ == '__main__':
    unittest.main()
