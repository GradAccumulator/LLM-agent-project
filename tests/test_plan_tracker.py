from __future__ import annotations

import unittest

from src.planning import TaskPlanTracker


class PlanTrackerTests(unittest.TestCase):
    def _tracker(self, repairs=2):
        tracker = TaskPlanTracker()
        tracker.begin_request(
            required=True,
            max_steps=6,
            max_repair_attempts=repairs,
            max_plan_revisions=3,
            max_same_failure_repeats=2,
            tool_switching_enabled=True,
        )
        tracker.begin_plan(
            "테스트 작업",
            ["첫 작업", "둘째 작업"],
        )
        return tracker

    def test_verified_actions_advance_plan(self) -> None:
        tracker = self._tracker()
        first = tracker.record_action(
            tool_name="test_action",
            verified=True,
            verification={"verified": True},
        )
        self.assertEqual(first["current_step"], 2)
        second = tracker.record_action(
            tool_name="test_action",
            verified=True,
            verification={"verified": True},
        )
        self.assertEqual(second["status"], "completed")

    def test_failed_verification_waits_for_repair(self) -> None:
        tracker = self._tracker()
        snapshot = tracker.record_action(
            tool_name="test_action",
            verified=False,
            verification={"verified": False},
            error="verification failed",
        )
        self.assertEqual(snapshot["status"], "repairing")
        self.assertEqual(snapshot["current_step"], 1)
        self.assertEqual(snapshot["steps"][0]["attempts"], 1)

    def test_attempt_budget_marks_plan_failed(self) -> None:
        tracker = self._tracker(repairs=1)
        tracker.record_action(
            tool_name="test_action",
            verified=False,
            verification={"verified": False},
            error="verification failed A",
        )
        tracker.repair_current_step(
            reason="different approach",
            strategy="switch_tool",
            replacement_steps=None,
            preferred_tool="other_action",
            expected_evidence="state change",
        )
        snapshot = tracker.record_action(
            tool_name="other_action",
            verified=False,
            verification={"verified": False},
            error="verification failed B",
        )
        self.assertEqual(snapshot["status"], "failed")


if __name__ == "__main__":
    unittest.main()
