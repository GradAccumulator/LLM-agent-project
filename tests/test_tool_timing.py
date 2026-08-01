from __future__ import annotations

import json
import time
import unittest

from src.tools.registry import (
    ToolRegistry,
    ToolSpec,
)


class ToolTimingTests(unittest.TestCase):
    def test_execution_time_is_recorded(self) -> None:
        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="slow_test",
                description="test",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=lambda: (
                    time.sleep(0.01)
                    or {"value": 1}
                ),
            )
        )

        result = registry.execute(
            "slow_test",
            "{}",
        )

        self.assertTrue(result.success)
        self.assertGreater(
            result.elapsed_seconds,
            0.0,
        )
        self.assertEqual(
            json.loads(result.output)["value"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
