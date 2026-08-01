from __future__ import annotations

import unittest

from src.planning import TaskPlanTracker


class PlanTrackerTests(unittest.TestCase):
    def test_verified_actions_advance_plan(self) -> None:
        tracker = TaskPlanTracker()
        tracker.begin_request(
            required=True,
            max_steps=6,
            max_repair_attempts=2,
        )
        tracker.begin_plan(
            "테스트 작업",
            ["첫 작업", "둘째 작업"],
        )

        first = tracker.record_action(
            tool_name="test_action",
            verified=True,
            verification={"verified": True},
        )
        self.assertEqual(
            first["current_step"],
            2,
        )

        second = tracker.record_action(
            tool_name="test_action",
            verified=True,
            verification={"verified": True},
        )
        self.assertEqual(
            second["status"],
            "completed",
        )

    def test_failed_verification_stays_on_step(self) -> None:
        tracker = TaskPlanTracker()
        tracker.begin_request(
            required=True,
            max_steps=6,
            max_repair_attempts=2,
        )
        tracker.begin_plan(
            "테스트 작업",
            ["첫 작업", "둘째 작업"],
        )

        snapshot = tracker.record_action(
            tool_name="test_action",
            verified=False,
            verification={"verified": False},
        )

        self.assertEqual(
            snapshot["status"],
            "active",
        )
        self.assertEqual(
            snapshot["current_step"],
            1,
        )
        self.assertEqual(
            snapshot["steps"][0]["attempts"],
            1,
        )

    def test_repair_limit_marks_plan_failed(self) -> None:
        tracker = TaskPlanTracker()
        tracker.begin_request(
            required=True,
            max_steps=6,
            max_repair_attempts=1,
        )
        tracker.begin_plan(
            "테스트 작업",
            ["첫 작업", "둘째 작업"],
        )

        tracker.record_action(
            tool_name="test_action",
            verified=False,
            verification={"verified": False},
        )
        snapshot = tracker.record_action(
            tool_name="test_action",
            verified=False,
            verification={"verified": False},
        )

        self.assertEqual(
            snapshot["status"],
            "failed",
        )


if __name__ == "__main__":
    unittest.main()
