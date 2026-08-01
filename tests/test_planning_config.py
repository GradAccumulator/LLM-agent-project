from __future__ import annotations

import unittest

from src.app.cli import parse_args
from src.llm.agent import JarvisAgent


class PlanningConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )

        self.assertTrue(
            args.planning_enabled
        )
        self.assertEqual(
            args.planning_max_steps,
            6,
        )
        self.assertEqual(
            args.planning_max_repair_attempts,
            2,
        )
        self.assertEqual(
            args.llm_max_tool_rounds,
            12,
        )

    def test_agent_heuristic(self) -> None:
        self.assertTrue(
            JarvisAgent.should_plan_text(
                "브라우저를 열고 검색해서 결과를 클릭해줘"
            )
        )
        self.assertFalse(
            JarvisAgent.should_plan_text(
                "현재 화면 설명해줘"
            )
        )


if __name__ == "__main__":
    unittest.main()
