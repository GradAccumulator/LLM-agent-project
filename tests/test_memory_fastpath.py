from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.fastpath import (
    FastPathConfig,
    LocalCommandRouter,
)
from src.memory import (
    LocalMemoryStore,
    MemoryStoreConfig,
)
from src.tools.memory_tools import (
    register_memory_tools,
)
from src.tools.registry import (
    ToolRegistry,
    ToolSpec,
)


class MemoryFastPathTests(unittest.TestCase):
    def test_saved_alias_opens_without_gpt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalMemoryStore(
                MemoryStoreConfig(
                    database=(
                        Path(directory) / 'memory.db'
                    )
                )
            )
            store.remember_alias(
                '학교 사이트',
                'https://www.inha.ac.kr',
                'url',
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
                    or {'url': url, 'message': 'ok'}
                ),
            )
            router = LocalCommandRouter(
                registry,
                FastPathConfig(enabled=True),
            )
            try:
                result = router.try_execute(
                    '학교 사이트 열어줘'
                )
                self.assertIsNotNone(result)
                self.assertTrue(result.success)
                self.assertEqual(
                    opened,
                    ['https://www.inha.ac.kr'],
                )
            finally:
                registry.close()
                store.close()

    def test_preferred_search_engine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalMemoryStore(
                MemoryStoreConfig(
                    database=(
                        Path(directory) / 'memory.db'
                    )
                )
            )
            store.remember_preference(
                'search_engine',
                'google',
            )
            calls: list[tuple[str, str]] = []
            registry = ToolRegistry(
                memory_store=store
            )
            registry.register(
                ToolSpec(
                    name='search_browser',
                    description='test',
                    parameters={
                        'type': 'object',
                        'properties': {
                            'engine': {'type': 'string'},
                            'query': {'type': 'string'},
                        },
                        'required': ['engine', 'query'],
                        'additionalProperties': False,
                    },
                    handler=lambda engine, query: (
                        calls.append((engine, query))
                        or {'message': 'searched'}
                    ),
                )
            )
            router = LocalCommandRouter(registry)
            try:
                result = router.try_execute(
                    'Faster Whisper 검색해줘'
                )
                self.assertIsNotNone(result)
                self.assertTrue(result.success)
                self.assertEqual(
                    calls,
                    [('google', 'Faster Whisper')],
                )
            finally:
                registry.close()
                store.close()


if __name__ == '__main__':
    unittest.main()
