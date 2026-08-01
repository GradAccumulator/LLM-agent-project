from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.scheduler import SchedulerStore, SchedulerStoreConfig
from src.tools.registry import ToolRegistry
from src.tools.scheduler_tools import register_scheduler_tools


class SchedulerToolTests(unittest.TestCase):
    def test_relative_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SchedulerStore(SchedulerStoreConfig(database=Path(directory) / 'tasks.db'))
            registry = ToolRegistry(scheduler_store=store)
            register_scheduler_tools(registry, store)
            try:
                result = registry.execute(
                    'schedule_relative_reminder',
                    json.dumps({'message': '물 마시기', 'delay_seconds': 60}, ensure_ascii=False),
                )
                self.assertTrue(result.success)
                self.assertTrue(json.loads(result.output)['scheduled'])
            finally:
                registry.close()


if __name__ == '__main__':
    unittest.main()
