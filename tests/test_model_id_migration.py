from __future__ import annotations

import unittest

from src.app.cli import parse_args
from src.model_routing import (
    ModelRoutingConfig,
    normalize_legacy_model_id,
    normalize_reasoning_for_model,
)


class ModelIdConfigurationTests(
    unittest.TestCase
):
    def test_cli_defaults_use_gpt_56_family(
        self,
    ) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )
        self.assertEqual(
            args.llm_model,
            "gpt-5.6-luna",
        )
        self.assertEqual(
            args.routing_balanced_model,
            "gpt-5.6-terra",
        )
        self.assertEqual(
            args.routing_strong_model,
            "gpt-5.6-sol",
        )
        self.assertEqual(
            args.routing_strong_reasoning,
            "xhigh",
        )

    def test_gpt_56_ids_are_not_rewritten(
        self,
    ) -> None:
        for model in (
            "gpt-5.6-luna",
            "gpt-5.6-terra",
            "gpt-5.6-sol",
        ):
            normalized, migration = (
                normalize_legacy_model_id(
                    model
                )
            )
            self.assertEqual(
                normalized,
                model,
            )
            self.assertIsNone(
                migration
            )

    def test_reasoning_supports_max(
        self,
    ) -> None:
        effort, migration = (
            normalize_reasoning_for_model(
                "gpt-5.6-sol",
                "max",
            )
        )
        self.assertEqual(
            effort,
            "max",
        )
        self.assertIsNone(
            migration
        )

    def test_minimal_compatibility_maps_to_low(
        self,
    ) -> None:
        effort, migration = (
            normalize_reasoning_for_model(
                "gpt-5.6-luna",
                "minimal",
            )
        )
        self.assertEqual(
            effort,
            "low",
        )
        self.assertTrue(
            migration
        )

    def test_routing_defaults(
        self,
    ) -> None:
        config = (
            ModelRoutingConfig()
        )
        self.assertEqual(
            config.balanced_model,
            "gpt-5.6-terra",
        )
        self.assertEqual(
            config.strong_model,
            "gpt-5.6-sol",
        )
        self.assertEqual(
            config.strong_reasoning,
            "xhigh",
        )


if __name__ == "__main__":
    unittest.main()
