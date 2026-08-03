from __future__ import annotations

import unittest

from src.planning import is_action_tool, verify_action_result


class WindowsUiAutomationPlanningTests(unittest.TestCase):
    def test_actions_are_classified(self):
        for name in (
            "uia_focus_element",
            "uia_invoke_element",
            "uia_set_value",
            "uia_toggle_element",
            "uia_select_element",
        ):
            self.assertTrue(is_action_tool(name))

    def test_value_verification_is_strong(self):
        result = verify_action_result(
            "uia_set_value",
            {"element_ref": "uia_ref", "value": "hello"},
            {
                "value_set": True,
                "verified": True,
                "characters": 5,
                "element_ref": "uia_ref",
            },
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["strength"], "strong")


if __name__ == "__main__":
    unittest.main()
