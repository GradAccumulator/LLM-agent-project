from __future__ import annotations

import unittest

from src.planning import (
    should_plan_request,
    verify_action_result,
)


class PlanningPolicyTests(unittest.TestCase):
    def test_detects_multi_step_request(self) -> None:
        self.assertTrue(
            should_plan_request(
                "유튜브를 열고 킹누를 검색해서 첫 영상을 재생해줘",
                enabled=True,
            )
        )

    def test_single_action_does_not_require_plan(self) -> None:
        self.assertFalse(
            should_plan_request(
                "계산기 켜줘",
                enabled=True,
            )
        )

    def test_browser_navigation_verification(self) -> None:
        result = verify_action_result(
            "browser_open_page",
            {"url": "https://example.com"},
            {
                "url": "https://example.com/",
                "status": 200,
                "title": "Example",
            },
        )
        self.assertTrue(result["verified"])
        self.assertEqual(
            result["strength"],
            "strong",
        )

    def test_failed_browser_status_is_not_verified(self) -> None:
        result = verify_action_result(
            "browser_open_page",
            {"url": "https://example.com"},
            {
                "url": "https://example.com/",
                "status": 500,
            },
        )
        self.assertFalse(result["verified"])


if __name__ == "__main__":
    unittest.main()
