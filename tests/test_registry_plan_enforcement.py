from __future__ import annotations

import json
import unittest

import src.planning.policy as policy
from src.tools.planning_tools import (
    register_planning_tools,
)
from src.tools.registry import (
    ToolRegistry,
    ToolSpec,
)


class RegistryPlanEnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_actions = set(
            policy.ACTION_TOOLS
        )
        policy.ACTION_TOOLS.add(
            "test_action"
        )

    def tearDown(self) -> None:
        policy.ACTION_TOOLS.clear()
        policy.ACTION_TOOLS.update(
            self.original_actions
        )

    def _registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        register_planning_tools(registry)
        registry.register(
            ToolSpec(
                name="test_action",
                description="test",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=lambda: {
                    "message": "done"
                },
            )
        )
        return registry

    def test_action_is_blocked_before_plan(self) -> None:
        registry = self._registry()
        registry.begin_request(
            planning_required=True,
            max_steps=6,
            max_repair_attempts=2,
        )

        result = registry.execute(
            "test_action",
            "{}",
        )

        self.assertFalse(result.success)
        payload = json.loads(result.output)
        self.assertIn(
            "begin_task_plan",
            payload["error"],
        )

    def test_verified_action_advances_plan(self) -> None:
        registry = self._registry()
        registry.begin_request(
            planning_required=True,
            max_steps=6,
            max_repair_attempts=2,
        )
        begin = registry.execute(
            "begin_task_plan",
            json.dumps(
                {
                    "goal": "test",
                    "steps": [
                        "first",
                        "second",
                    ],
                }
            ),
        )
        self.assertTrue(begin.success)

        action = registry.execute(
            "test_action",
            "{}",
        )

        self.assertTrue(action.success)
        self.assertTrue(action.verified)
        self.assertEqual(
            action.plan_progress[
                "current_step"
            ],
            2,
        )


if __name__ == "__main__":
    unittest.main()
