from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.llm.agent import (
    AgentConfig,
    JarvisAgent,
)
from src.memory import (
    LocalMemoryStore,
    MemoryStoreConfig,
)
from src.tools.registry import ToolRegistry


class MemoryAgentContextTests(unittest.TestCase):
    def test_explicit_memory_is_injected_as_data(self) -> None:
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
            agent = JarvisAgent.__new__(
                JarvisAgent
            )
            agent.config = AgentConfig()
            agent._tool_registry = ToolRegistry(
                memory_store=store
            )
            agent._memory_store = store
            agent._planning_required = False
            agent._request_instructions = ''

            agent._prepare_request(
                '구글 검색 설정으로 오늘 뉴스 알려줘'
            )

            self.assertIn(
                '로컬 메모리 데이터(JSON)',
                agent._request_instructions,
            )
            self.assertIn(
                'search_engine',
                agent._request_instructions,
            )
            self.assertIn(
                '참고 데이터',
                agent._request_instructions,
            )
            store.close()


if __name__ == '__main__':
    unittest.main()
