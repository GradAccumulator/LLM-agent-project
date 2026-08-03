from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.local_rag import LocalRagConfig, LocalRagStore
from src.tools.local_rag_tools import register_local_rag_tools
from src.tools.registry import ToolRegistry


class LocalRagToolTests(unittest.TestCase):
    def test_tools_are_strict_and_default_collection_works(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text(
                "KV cache stores keys and values across decoding steps.",
                encoding="utf-8",
            )
            store = LocalRagStore(
                LocalRagConfig(
                    database=root / "rag.db",
                    roots=(root,),
                    default_collection="Jarvis",
                    chunk_characters=300,
                    chunk_overlap_characters=30,
                )
            )
            registry = ToolRegistry()
            register_local_rag_tools(registry, store)
            try:
                names = set(registry.names)
                self.assertTrue(
                    {
                        "index_local_knowledge",
                        "search_local_knowledge",
                        "get_local_knowledge_chunk",
                        "get_local_knowledge_status",
                    }.issubset(names)
                )
                for schema in registry.schemas:
                    parameters = schema["parameters"]
                    self.assertEqual(
                        set(parameters["properties"]),
                        set(parameters["required"]),
                    )

                indexed = registry.execute(
                    "index_local_knowledge",
                    json.dumps(
                        {
                            "paths": [str(root / "guide.md")],
                            "collection": "",
                            "force": False,
                            "prune_missing": True,
                        },
                        ensure_ascii=False,
                    ),
                )
                self.assertTrue(indexed.success)
                self.assertEqual(
                    json.loads(indexed.output)["collection"],
                    "Jarvis",
                )

                searched = registry.execute(
                    "search_local_knowledge",
                    json.dumps(
                        {
                            "query": "KV cache decoding",
                            "collection": "",
                            "extension": "all",
                            "limit": 0,
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
