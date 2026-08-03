from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.memory import LocalMemoryStore, MemoryStoreConfig
from src.tools.memory_tools import register_memory_tools
from src.tools.registry import ToolRegistry


class MemoryV2ToolTests(unittest.TestCase):
    def test_tools_and_strict_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalMemoryStore(
                MemoryStoreConfig(
                    database=Path(directory) / "memory.db"
                )
            )
            registry = ToolRegistry(memory_store=store)
            register_memory_tools(
                registry,
                store,
                open_url=lambda url: {"url": url},
            )
            try:
                names = set(registry.names)
                for name in (
                    "remember_memory_item",
                    "search_saved_memory",
                    "get_project_memory",
                    "set_saved_memory_status",
                    "list_memory_conflicts",
                    "resolve_memory_conflict",
                    "review_memory_health",
                    "get_memory_history",
                ):
                    self.assertIn(name, names)
                for schema in registry.schemas:
                    parameters = schema["parameters"]
                    if parameters.get("type") == "object":
                        self.assertEqual(
                            set(parameters["properties"]),
                            set(parameters["required"]),
                        )
                saved = registry.execute(
                    "remember_memory_item",
                    json.dumps(
                        {
                            "kind": "todo",
                            "scope": "Jarvis",
                            "name": "RAG 구현",
                            "value": "로컬 문서 검색",
                            "notes": "",
                            "status": "pending",
                            "importance": 4,
                            "confidence": 1.0,
                            "replace_existing": False,
                        },
                        ensure_ascii=False,
                    ),
                )
                self.assertTrue(saved.success)
                self.assertTrue(json.loads(saved.output)["stored"])
                searched = registry.execute(
                    "search_saved_memory",
                    json.dumps(
                        {
                            "query": "RAG",
                            "scope": "Jarvis",
                            "kind": "all",
                            "status": "current",
                            "limit": 10,
                        },
                        ensure_ascii=False,
                    ),
                )
                self.assertTrue(searched.success)
                self.assertEqual(json.loads(searched.output)["count"], 1)
            finally:
                registry.close()
                store.close()


if __name__ == "__main__":
    unittest.main()
