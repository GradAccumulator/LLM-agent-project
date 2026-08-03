from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.app.cli import parse_args


class LocalRagSettingsTests(unittest.TestCase):
    def test_toml_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "user.toml"
            config.write_text(
                """
                [local_rag]
                enabled = true
                database = "data/custom_rag.db"
                roots = ["papers", "src"]
                default_collection = "LLM"
                auto_index_on_startup = true
                max_file_bytes = 123456
                chunk_characters = 900
                chunk_overlap_characters = 100
                max_files = 123
                max_chunks = 456
                default_search_limit = 7
                prune_missing = false
                """,
                encoding="utf-8",
            )
            args, _ = parse_args([
                "--config",
                str(config),
                "--print-config",
            ])
            self.assertTrue(args.local_rag_enabled)
            self.assertEqual(args.local_rag_database, Path("data/custom_rag.db"))
            self.assertEqual(args.local_rag_roots, (Path("papers"), Path("src")))
            self.assertEqual(args.local_rag_default_collection, "LLM")
            self.assertTrue(args.local_rag_auto_index)
            self.assertEqual(args.local_rag_chunk_characters, 900)
            self.assertEqual(args.local_rag_chunk_overlap_characters, 100)
            self.assertFalse(args.local_rag_prune_missing)


if __name__ == "__main__":
    unittest.main()
