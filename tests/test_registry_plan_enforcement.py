from __future__ import annotations

import json
import unittest

import src.planning.policy as policy
from src.tools.planning_tools import register_planning_tools
from src.tools.registry import ToolRegistry, ToolSpec


class RegistryPlanEnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_actions = set(policy.ACTION_TOOLS)
        policy.ACTION_TOOLS.add("test_action")

    def tearDown(self) -> None:
        policy.ACTION_TOOLS.clear()
        policy.ACTION_TOOLS.update(self.original_actions)

    def _registry(self, handler=None) -> ToolRegistry:
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
                handler=handler or (lambda: {"message": "done"}),
            )
        )
        return registry

    def _begin(self, registry):
        registry.begin_request(
            planning_required=True,
            max_steps=6,
            max_repair_attempts=2,
            max_plan_revisions=3,
            max_same_failure_repeats=2,
            tool_switching_enabled=True,
        )

    def test_action_is_blocked_before_plan(self) -> None:
        registry = self._registry()
        self._begin(registry)
        result = registry.execute("test_action", "{}")
        self.assertFalse(result.success)
        self.assertIn("begin_task_plan", json.loads(result.output)["error"])

    def test_verified_action_advances_plan(self) -> None:
        registry = self._registry()
        self._begin(registry)
        registry.execute(
            "begin_task_plan",
            json.dumps({"goal": "test", "steps": ["first", "second"]}),
        )
        action = registry.execute("test_action", "{}")
        self.assertTrue(action.success)
        self.assertTrue(action.verified)
        self.assertEqual(action.plan_progress["current_step"], 2)

    def test_action_is_blocked_until_plan_is_repaired(self) -> None:
        registry = self._registry(handler=lambda: {})
        self._begin(registry)
        registry.execute(
            "begin_task_plan",
            json.dumps({"goal": "test", "steps": ["first", "second"]}),
        )
        failed = registry.execute("test_action", "{}")
        self.assertFalse(failed.success)
        self.assertEqual(failed.plan_progress["status"], "repairing")
        blocked = registry.execute("test_action", "{}")
        self.assertFalse(blocked.success)
        self.assertIn("repair_task_plan", json.loads(blocked.output)["error"])


if __name__ == "__main__":
    unittest.main()
