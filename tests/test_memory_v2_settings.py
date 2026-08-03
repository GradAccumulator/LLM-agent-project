from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.app.cli import parse_args


class MemoryV2SettingsTests(unittest.TestCase):
    def test_toml_memory_v2_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "user.toml"
            path.write_text(
                """
                [long_term_memory]
                relevance_search_enabled = false
                stale_after_days = 45
                max_history_entries = 321
                max_conflicts = 12
                include_completed_todos_in_context = true
                """,
                encoding="utf-8",
            )
            args, _ = parse_args(
                ["--config", str(path), "--print-config"]
            )
            self.assertFalse(args.memory_relevance_search)
            self.assertEqual(args.memory_stale_after_days, 45)
            self.assertEqual(args.memory_max_history_entries, 321)
            self.assertEqual(args.memory_max_conflicts, 12)
            self.assertTrue(args.memory_include_completed_todos)


if __name__ == "__main__":
    unittest.main()
