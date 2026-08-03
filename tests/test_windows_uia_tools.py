from __future__ import annotations

import json
import unittest

from src.tools.registry import ToolRegistry
from src.tools.windows_uia_tools import register_windows_uia_tools


class Controller:
    enabled = True
    allow_actions = True

    def __init__(self): self.invoked = 0
    def close(self): pass
    def find_windows(self, **kwargs): return {"count": 0, "windows": []}
    def inspect_window(self, **kwargs): return {"count": 0, "elements": []}
    def find_elements(self, **kwargs): return {"count": 0, "elements": []}
    def get_element(self, **kwargs): return {"element": {}}
    def focus_element(self, **kwargs): return {"focused": True}
    def describe_ref(self, ref): return "'저장' Button UI 요소"
    def invoke_element(self, **kwargs):
        self.invoked += 1
        return {"invoked": True, "name": "저장", "element_ref": kwargs["element_ref"]}
    def set_value(self, **kwargs): return {"value_set": True, "verified": True}
    def toggle_element(self, **kwargs): return {"toggled": True, "verified": True}
    def select_element(self, **kwargs): return {"selected": True}


class WindowsUiAutomationToolTests(unittest.TestCase):
    def test_read_tools_and_confirmed_actions(self):
        controller = Controller()
        registry = ToolRegistry()
        register_windows_uia_tools(registry, controller)

        self.assertIn("uia_find_windows", registry.names)
        self.assertIn("uia_invoke_element", registry.names)
        pending = registry.execute(
            "uia_invoke_element",
            json.dumps({"element_ref": "uia_ref"}),
        )
        self.assertTrue(pending.confirmation_required)
        self.assertEqual(controller.invoked, 0)
        executed = registry.approve_pending_confirmation()
        self.assertTrue(executed.success)
        self.assertEqual(controller.invoked, 1)

    def test_action_kill_switch(self):
        controller = Controller()
        controller.allow_actions = False
        registry = ToolRegistry()
        register_windows_uia_tools(registry, controller)
        self.assertIn("uia_find_elements", registry.names)
        self.assertNotIn("uia_invoke_element", registry.names)


if __name__ == "__main__":
    unittest.main()
