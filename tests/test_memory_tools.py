from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.memory import (
    LocalMemoryStore,
    MemoryStoreConfig,
)
from src.tools.memory_tools import (
    register_memory_tools,
)
from src.tools.registry import ToolRegistry


class MemoryToolTests(unittest.TestCase):
    def test_register_store_open_and_forget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalMemoryStore(
                MemoryStoreConfig(
                    database=(
                        Path(directory) / 'memory.db'
                    )
                )
            )
            opened: list[str] = []
            registry = ToolRegistry(
                memory_store=store
            )
            register_memory_tools(
                registry,
                store,
                open_url=lambda url: (
                    opened.append(url)
                    or {
                        'url': url,
                        'message': 'opened',
                    }
                ),
            )
            try:
                saved = registry.execute(
                    'remember_alias',
                    json.dumps(
                        {
                            'alias': '학교 사이트',
                            'target': 'https://www.inha.ac.kr',
                            'target_type': 'url',
                        },
                        ensure_ascii=False,
                    ),
                )
                self.assertTrue(saved.success)

                opened_result = registry.execute(
                    'open_saved_alias',
                    json.dumps(
                        {'alias': '학교 사이트'},
                        ensure_ascii=False,
                    ),
                )
                self.assertTrue(opened_result.success)
                self.assertEqual(
                    opened,
                    ['https://www.inha.ac.kr'],
                )

                forgotten = registry.execute(
                    'forget_saved_memory',
                    json.dumps(
                        {
                            'kind': 'alias',
                            'name': '학교 사이트',
                        },
                        ensure_ascii=False,
                    ),
                )
                self.assertTrue(forgotten.success)
                self.assertIsNone(
                    store.resolve_alias(
                        '학교 사이트'
                    )
                )
            finally:
                registry.close()
                store.close()


if __name__ == '__main__':
    unittest.main()
