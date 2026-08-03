from __future__ import annotations

import unittest

from src.planning import (
    FailureCategory,
    TaskPlanTracker,
    assess_failure,
)


class PlannerV2RecoveryTests(unittest.TestCase):
    def _tracker(self, **kwargs) -> TaskPlanTracker:
        tracker = TaskPlanTracker()
        tracker.begin_request(
            required=True,
            max_steps=6,
            max_repair_attempts=2,
            max_plan_revisions=kwargs.get("max_plan_revisions", 3),
            max_same_failure_repeats=kwargs.get("max_same_failure_repeats", 2),
            tool_switching_enabled=True,
        )
        tracker.begin_plan(
            "브라우저 작업",
            ["링크 찾기", "내용 확인"],
        )
        return tracker

    def test_classifies_stale_edge_reference(self) -> None:
        assessment = assess_failure(
            tool_name="edge_cdp_click_element",
            verification={"verified": False},
            error="Stale element reference expired",
        )
        self.assertEqual(
            assessment.category,
            FailureCategory.STALE_REFERENCE,
        )
        self.assertIn(
            "edge_cdp_find_element",
            assessment.recommended_tools,
        )

    def test_edge_verification_failure_recommends_uia_or_vision(self) -> None:
        assessment = assess_failure(
            tool_name="edge_cdp_click_element",
            verification={
                "verified": False,
                "strength": "unverified",
            },
            error="Postcondition verification failed.",
        )
        self.assertEqual(
            assessment.recommended_strategy,
            "switch_tool_channel",
        )
        self.assertIn(
            "uia_capture_window_context",
            assessment.recommended_tools,
        )

    def test_failure_enters_repairing(self) -> None:
        tracker = self._tracker()
        snapshot = tracker.record_action(
            tool_name="edge_cdp_click_element",
            verified=False,
            verification={"verified": False},
            error="No observed change",
        )
        self.assertEqual(snapshot["status"], "repairing")
        self.assertTrue(snapshot["recovery_required"])
        report = tracker.recovery_report()
        self.assertTrue(report["repair_required"])

    def test_partial_replan_preserves_completed_prefix(self) -> None:
        tracker = self._tracker()
        tracker.record_action(
            tool_name="edge_cdp_find_element",
            verified=True,
            verification={"verified": True},
        )
        tracker.record_action(
            tool_name="edge_cdp_click_element",
            verified=False,
            verification={"verified": False},
            error="No observed change",
        )
        repaired = tracker.repair_current_step(
            reason="DOM 클릭 검증 실패",
            strategy="replace_remaining",
            replacement_steps=[
                "UIA로 창 구조 확인",
                "검증 가능한 요소 실행",
            ],
            preferred_tool="uia_capture_window_context",
            expected_evidence="화면과 UIA 상태 변화",
        )
        self.assertEqual(repaired["status"], "active")
        self.assertEqual(repaired["completed_steps"], 1)
        self.assertEqual(repaired["current_step"], 2)
        self.assertEqual(
            repaired["steps"][0]["instruction"],
            "링크 찾기",
        )
        self.assertEqual(repaired["revision_count"], 1)

    def test_repeated_same_failure_requires_tool_switch(self) -> None:
        tracker = self._tracker(max_same_failure_repeats=2)
        for attempt in range(2):
            tracker.record_action(
                tool_name="edge_cdp_click_element",
                verified=False,
                verification={"verified": False},
                error="No observed change",
            )
            if attempt == 0:
                tracker.repair_current_step(
                    reason="새 DOM 상태로 재시도",
                    strategy="retry",
                    replacement_steps=None,
                    preferred_tool="edge_cdp_click_element",
                    expected_evidence="URL 변화",
                )
        report = tracker.recovery_report()
        self.assertIn(
            "edge_cdp_click_element",
            report["blocked_tools"],
        )
        with self.assertRaisesRegex(ValueError, "same failure"):
            tracker.repair_current_step(
                reason="동일 도구 다시 시도",
                strategy="retry",
                replacement_steps=None,
                preferred_tool="edge_cdp_click_element",
                expected_evidence="URL 변화",
            )
        switched = tracker.repair_current_step(
            reason="UIA로 전환",
            strategy="switch_tool",
            replacement_steps=None,
            preferred_tool="uia_capture_window_context",
            expected_evidence="창 구조와 화면",
        )
        self.assertEqual(switched["status"], "active")

    def test_safety_failure_is_not_auto_recoverable(self) -> None:
        tracker = self._tracker()
        snapshot = tracker.record_action(
            tool_name="edge_cdp_fill_element",
            verified=False,
            verification={"verified": False},
            error="Blocked password field by safety policy",
        )
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(
            snapshot["steps"][0]["last_failure"]["category"],
            "safety_block",
        )

    def test_finish_requires_verified_evidence(self) -> None:
        tracker = self._tracker()
        tracker.complete_current_step("링크 목록 확인")
        tracker.complete_current_step("본문 확인")
        result = tracker.finish_plan("완료")
        self.assertTrue(result["audit"]["passed"])


if __name__ == "__main__":
    unittest.main()
