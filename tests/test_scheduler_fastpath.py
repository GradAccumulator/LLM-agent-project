from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.fastpath import LocalCommandRouter
from src.scheduler import SchedulerStore, SchedulerStoreConfig
from src.tools.registry import ToolRegistry
from src.tools.scheduler_tools import register_scheduler_tools


class SchedulerFastPathTests(unittest.TestCase):
    def _router(self, directory: str):
        store = SchedulerStore(SchedulerStoreConfig(database=Path(directory) / 'tasks.db'))
        registry = ToolRegistry(scheduler_store=store)
        register_scheduler_tools(registry, store)
        return store, registry, LocalCommandRouter(registry)

    def test_relative_command_bypasses_gpt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, registry, router = self._router(directory)
            try:
                result = router.try_execute('30분 뒤에 물 마시라고 알려줘')
                self.assertIsNotNone(result)
                self.assertTrue(result.success)
                tasks = store.list_tasks(status='active')
                self.assertEqual(len(tasks), 1)
                self.assertEqual(tasks[0].message, '물 마시라고')
            finally:
                registry.close()

    def test_list_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _store, registry, router = self._router(directory)
            try:
                result = router.try_execute('알림 목록 보여줘')
                self.assertIsNotNone(result)
                self.assertTrue(result.success)
            finally:
                registry.close()


if __name__ == '__main__':
    unittest.main()
