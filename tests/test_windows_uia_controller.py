from __future__ import annotations

import unittest

from src.windows_uia import (
    StaleElementReferenceError,
    WindowsUiAutomation,
    WindowsUiAutomationConfig,
    WindowsUiAutomationError,
)


class Rect:
    left, top, right, bottom = 10, 20, 210, 70


class Info:
    def __init__(
        self,
        *,
        name,
        control_type,
        automation_id="",
        class_name="",
        process_id=123,
        handle=None,
        is_password=False,
    ):
        self.name = name
        self.control_type = control_type
        self.automation_id = automation_id
        self.class_name = class_name
        self.process_id = process_id
        self.handle = handle
        self.is_password = is_password
        self.offscreen = False
        self.is_keyboard_focusable = True
        self.rich_text = None


class Invoke:
    def __init__(self, owner): self.owner = owner
    def Invoke(self): self.owner.invoked += 1


class Value:
    def __init__(self, owner): self.owner = owner
    def SetValue(self, value): self.owner.value = value


class Toggle:
    def __init__(self, owner): self.owner = owner
    def Toggle(self): self.owner.toggle_state = 1 - self.owner.toggle_state


class Selection:
    def __init__(self, owner): self.owner = owner
    def Select(self): self.owner.selected = True


class Wrapper:
    def __init__(
        self,
        name,
        control_type,
        *,
        handle=None,
        automation_id="",
        password=False,
        children=None,
    ):
        self.handle = handle
        self.element_info = Info(
            name=name,
            control_type=control_type,
            automation_id=automation_id,
            class_name=control_type + "Class",
            handle=handle,
            is_password=password,
        )
        self._children = children or []
        self.invoked = 0
        self.value = ""
        self.toggle_state = 0
        self.selected = False
        self.focused = False
        self.iface_invoke = Invoke(self)
        self.iface_value = Value(self)
        self.iface_toggle = Toggle(self)
        self.iface_selection_item = Selection(self)

    def window_text(self): return self.element_info.name
    def rectangle(self): return Rect()
    def is_enabled(self): return True
    def is_visible(self): return True
    def has_keyboard_focus(self): return self.focused
    def set_focus(self): self.focused = True
    def children(self): return list(self._children)
    def exists(self, timeout=0): return True
    def get_value(self): return self.value
    def get_toggle_state(self): return self.toggle_state
    def is_selected(self): return self.selected


class Spec:
    def __init__(self, wrapper): self.wrapper = wrapper
    def wrapper_object(self): return self.wrapper


class Desktop:
    def __init__(self, windows): self._windows = windows
    def windows(self): return list(self._windows.values())
    def window(self, *, handle): return Spec(self._windows[handle])


class Clock:
    def __init__(self): self.value = 100.0
    def __call__(self): return self.value


class WindowsUiAutomationControllerTests(unittest.TestCase):
    def setUp(self):
        self.button = Wrapper("저장", "Button", automation_id="save")
        self.edit = Wrapper("검색", "Edit", automation_id="search")
        self.password = Wrapper("비밀번호", "Edit", password=True)
        self.checkbox = Wrapper("다크 모드", "CheckBox")
        self.item = Wrapper("일반", "ListItem")
        self.danger = Wrapper("영구 삭제", "Button")
        self.window = Wrapper(
            "설정",
            "Window",
            handle=100,
            children=[
                self.button,
                self.edit,
                self.password,
                self.checkbox,
                self.item,
                self.danger,
            ],
        )
        desktop = Desktop({100: self.window})
        self.clock = Clock()
        self.controller = WindowsUiAutomation(
            WindowsUiAutomationConfig(
                element_ttl_seconds=30,
                max_elements=100,
            ),
            desktop_factory=lambda **_: desktop,
            platform="win32",
            clock=self.clock,
        )

    def _ref(self, name, control_type):
        result = self.controller.find_elements(
            window_id=100,
            name_contains=name,
            automation_id="",
            control_types=[control_type],
            enabled_only=True,
            visible_only=True,
            max_depth=5,
            limit=10,
        )
        self.assertEqual(result["count"], 1)
        return result["elements"][0]["element_ref"]

    def test_find_windows_and_elements(self):
        windows = self.controller.find_windows(
            title_contains="설정",
            process_contains="",
            limit=10,
        )
        self.assertEqual(windows["windows"][0]["window_id"], 100)
        inspected = self.controller.inspect_window(
            window_id=100,
            max_depth=3,
            limit=50,
            include_offscreen=False,
            include_value=False,
        )
        self.assertGreaterEqual(inspected["count"], 6)
        self.assertTrue(all(item["element_ref"] for item in inspected["elements"]))

    def test_actions_and_verification(self):
        button_ref = self._ref("저장", "Button")
        edit_ref = self._ref("검색", "Edit")
        checkbox_ref = self._ref("다크", "CheckBox")
        item_ref = self._ref("일반", "ListItem")

        self.assertTrue(self.controller.focus_element(element_ref=button_ref)["focused"])
        self.assertTrue(self.controller.invoke_element(element_ref=button_ref)["invoked"])
        self.assertEqual(self.button.invoked, 1)
        self.assertTrue(
            self.controller.set_value(element_ref=edit_ref, value="파이썬")["verified"]
        )
        self.assertEqual(self.edit.value, "파이썬")
        self.assertTrue(self.controller.toggle_element(element_ref=checkbox_ref)["verified"])
        self.assertTrue(self.controller.select_element(element_ref=item_ref)["selected"])

    def test_password_and_danger_are_blocked(self):
        password_ref = self._ref("비밀번호", "Edit")
        danger_ref = self._ref("영구 삭제", "Button")
        with self.assertRaises(WindowsUiAutomationError):
            self.controller.set_value(element_ref=password_ref, value="secret")
        with self.assertRaises(WindowsUiAutomationError):
            self.controller.invoke_element(element_ref=danger_ref)

    def test_reference_expires(self):
        ref = self._ref("저장", "Button")
        self.clock.value += 31
        with self.assertRaises(StaleElementReferenceError):
            self.controller.get_element(element_ref=ref)

    def test_non_windows_is_blocked(self):
        controller = WindowsUiAutomation(platform="linux")
        with self.assertRaises(WindowsUiAutomationError):
            controller.find_windows(limit=1)


if __name__ == "__main__":
    unittest.main()
