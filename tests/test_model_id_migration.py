from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from src.app.cli import parse_args
from src.model_routing import (
    normalize_legacy_model_id,
    normalize_reasoning_for_model,
)


class ModelIdMigrationTests(unittest.TestCase):
    def test_legacy_ids_are_mapped(self) -> None:
        self.assertEqual(
            normalize_legacy_model_id("gpt-5.6-luna")[0],
            "gpt-5.1",
        )
        self.assertEqual(
            normalize_legacy_model_id("gpt-5.6-sol")[0],
            "gpt-5-pro",
        )

    def test_pro_reasoning_is_high(self) -> None:
        self.assertEqual(
            normalize_reasoning_for_model(
                "gpt-5-pro",
                "xhigh",
            )[0],
            "high",
        )

    def test_old_user_config_starts_with_real_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "user.toml"
            path.write_text(
                """
                [llm]
                model = "gpt-5.6-luna"
                reasoning = "low"

                [model_routing]
                balanced_model = "gpt-5.6-terra"
                strong_model = "gpt-5.6-sol"
                balanced_reasoning = "high"
                strong_reasoning = "xhigh"
                """,
                encoding="utf-8",
            )
            args, _ = parse_args(
                [
                    "--config",
                    str(path),
                    "--no-user-config",
                    "--print-config",
                ]
            )
        self.assertEqual(args.llm_model, "gpt-5.1")
        self.assertEqual(args.routing_balanced_model, "gpt-5.1")
        self.assertEqual(args.routing_strong_model, "gpt-5-pro")
        self.assertEqual(args.routing_strong_reasoning, "high")
        self.assertTrue(args.model_migrations)


if __name__ == "__main__":
    unittest.main()
