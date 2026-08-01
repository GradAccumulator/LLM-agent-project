from __future__ import annotations

from pathlib import Path
import tempfile
import time
import unittest

from src.scheduler import (
    ReminderScheduler,
    ReminderSchedulerConfig,
    SchedulerStore,
    SchedulerStoreConfig,
)


class SchedulerEngineTests(unittest.TestCase):
    def test_background_poll_queues_due_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SchedulerStore(SchedulerStoreConfig(database=Path(directory) / 'tasks.db'))
            scheduler = ReminderScheduler(store, ReminderSchedulerConfig(poll_interval_seconds=0.02))
            try:
                task = store.schedule_after(message='빠른 알림', delay_seconds=0.08)
                scheduler.start()
                deadline = time.monotonic() + 2.0
                items = ()
                while time.monotonic() < deadline:
                    items = scheduler.drain(limit=10)
                    if items:
                        break
                    time.sleep(0.02)
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0].task.id, task.id)
            finally:
                scheduler.stop()
                store.close()


if __name__ == '__main__':
    unittest.main()
