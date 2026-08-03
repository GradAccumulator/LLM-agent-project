from __future__ import annotations

import unittest

from src.tools import ToolRegistry
from src.tools.planning_tools import register_planning_tools


class PlanningToolsV2Tests(unittest.TestCase):
    def test_recovery_tools_and_strict_schemas(self) -> None:
        registry = ToolRegistry()
        register_planning_tools(registry)
        names = set(registry.names)
        self.assertIn("get_plan_recovery", names)
        self.assertIn("repair_task_plan", names)
        for schema in registry.schemas:
            parameters = schema["parameters"]
            self.assertEqual(
                set(parameters["properties"]),
                set(parameters["required"]),
                schema["name"],
            )
        registry.close()


if __name__ == "__main__":
    unittest.main()
