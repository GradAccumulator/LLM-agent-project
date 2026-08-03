from __future__ import annotations

import unittest

from src.planning import (
    is_action_tool,
    verify_action_result,
)


class EdgeCdpDomPlanningTests(unittest.TestCase):
    def test_actions_are_classified(self) -> None:
        self.assertTrue(is_action_tool("edge_cdp_click_element"))
        self.assertTrue(is_action_tool("edge_cdp_fill_element"))

    def test_click_verification(self) -> None:
        result = verify_action_result(
            "edge_cdp_click_element",
            {"element_ref": "el1"},
            {
                "clicked": True,
                "verified": True,
                "verification_strength": "strong",
                "observed_change": True,
            },
        )
        self.assertTrue(result["verified"])

    def test_fill_verification(self) -> None:
        result = verify_action_result(
            "edge_cdp_fill_element",
            {"element_ref": "el1", "value": "hello"},
            {
                "value_set": True,
                "verified": True,
                "characters": 5,
            },
        )
        self.assertTrue(result["verified"])


if __name__ == "__main__":
    unittest.main()
