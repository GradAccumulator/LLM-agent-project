from __future__ import annotations

import unittest

from src.edge_cdp import (
    EdgeCdpConfig,
    EdgeCdpController,
    EdgeCdpError,
    StaleElementReferenceError,
)


class _Element:
    def __init__(self, metadata, page) -> None:
        self.metadata = dict(metadata)
        self.page = page
        self.value = ""
        self.count_value = 1
        self.clicks = 0

    def evaluate(self, script):
        if "checked:" in script:
            return {
                "checked": None,
                "value": self.value,
                "aria_pressed": None,
                "aria_expanded": None,
                "aria_selected": None,
                "text": self.metadata.get("text", ""),
            }
        if "String(element.innerText" in script:
            return self.value
        return dict(self.metadata)

    def count(self):
        return self.count_value

    def click(self, *, timeout):
        del timeout
        self.clicks += 1
        self.page.url = self.metadata.get(
            "after_url",
            self.page.url,
        )

    def fill(self, value, *, timeout):
        del timeout
        self.value = value

    def input_value(self, *, timeout):
        del timeout
        return self.value


class _Collection:
    def __init__(self, elements) -> None:
        self.elements = elements

    def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]


class _Page:
    def __init__(self) -> None:
        self.url = "https://example.com/"
        self._title = "Example"
        self.closed = False
        self.context = None
        base = {
            "role": "",
            "title": "",
            "name": "",
            "placeholder": "",
            "autocomplete": "",
            "contenteditable": False,
            "disabled": False,
            "form_action": "",
            "form_method": "",
            "form_submits": False,
        }
        self.link = _Element(
            {
                **base,
                "tag": "a",
                "type": "",
                "label": "문서 보기",
                "text": "문서 보기",
                "href": "https://example.com/docs",
                "dom_path": "html > body > a",
                "after_url": "https://example.com/docs",
            },
            self,
        )
        self.submit = _Element(
            {
                **base,
                "tag": "button",
                "type": "submit",
                "label": "보내기",
                "text": "보내기",
                "href": "",
                "form_action": "https://example.com/send",
                "form_submits": True,
                "dom_path": "html > body > form > button",
            },
            self,
        )
        self.textbox = _Element(
            {
                **base,
                "tag": "textarea",
                "type": "",
                "label": "메모",
                "text": "",
                "href": "",
                "placeholder": "메모",
                "dom_path": "html > body > textarea",
            },
            self,
        )
        self.password = _Element(
            {
                **base,
                "tag": "input",
                "type": "password",
                "label": "비밀번호",
                "text": "",
                "href": "",
                "autocomplete": "current-password",
                "dom_path": "html > body > input",
            },
            self,
        )
        self.body = _Body()

    def title(self):
        return self._title

    def is_closed(self):
        return self.closed

    def bring_to_front(self):
        pass

    def locator(self, selector):
        if selector == "body":
            return self.body
        if selector.startswith("a:visible") and "button" not in selector:
            return _Collection([self.link])
        if selector.startswith("button:visible"):
            return _Collection([self.submit])
        if selector.startswith("input:visible"):
            return _Collection([self.textbox, self.password])
        return _Collection([
            self.link,
            self.submit,
            self.textbox,
            self.password,
        ])

    def wait_for_load_state(self, *args, **kwargs):
        pass

    def wait_for_timeout(self, value):
        del value


class _Body:
    def inner_text(self):
        return "hello"


class _Context:
    def __init__(self, page) -> None:
        self.pages = [page]
        page.context = self

    def set_default_timeout(self, value):
        del value


class _Browser:
    def __init__(self, page) -> None:
        self.contexts = [_Context(page)]

    def is_connected(self):
        return True


class _Playwright:
    def stop(self):
        pass


class EdgeCdpDomActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.page = _Page()
        self.controller = EdgeCdpController(
            EdgeCdpConfig(
                auto_start=False,
            ),
            connector=lambda *_: (
                _Playwright(),
                _Browser(self.page),
            ),
        )
        self.tab_ref = self.controller.list_tabs(
            limit=10
        )["tabs"][0]["tab_ref"]

    def tearDown(self) -> None:
        self.controller.close()

    def test_lists_refs_and_safety(self) -> None:
        result = self.controller.list_elements(
            tab_ref=self.tab_ref,
            kind="all",
            limit=10,
        )
        self.assertEqual(result["count"], 4)
        safety = {
            item["label"]: item["safety"]["allowed"]
            for item in result["elements"]
        }
        self.assertTrue(safety["문서 보기"])
        self.assertFalse(safety["보내기"])
        self.assertTrue(safety["메모"])
        self.assertFalse(safety["비밀번호"])

    def test_safe_click_verifies_navigation(self) -> None:
        element = self.controller.list_elements(
            tab_ref=self.tab_ref,
            kind="link",
            limit=10,
        )["elements"][0]
        result = self.controller.click_element(
            element_ref=element["element_ref"]
        )
        self.assertTrue(result["clicked"])
        self.assertTrue(result["observed_change"])
        self.assertEqual(
            result["after"]["url"],
            "https://example.com/docs",
        )

    def test_click_without_observed_change_is_not_verified(self) -> None:
        self.page.link.metadata["after_url"] = self.page.url
        element = self.controller.list_elements(
            tab_ref=self.tab_ref,
            kind="link",
            limit=10,
        )["elements"][0]
        result = self.controller.click_element(
            element_ref=element["element_ref"]
        )
        self.assertTrue(result["clicked"])
        self.assertFalse(result["verified"])
        self.assertFalse(result["observed_change"])
        self.assertEqual(
            result["verification_strength"],
            "unverified",
        )

    def test_limit_above_config_is_rejected(self) -> None:
        with self.assertRaises(EdgeCdpError):
            self.controller.list_elements(
                tab_ref=self.tab_ref,
                kind="all",
                limit=101,
            )

    def test_submit_click_is_blocked(self) -> None:
        element = self.controller.list_elements(
            tab_ref=self.tab_ref,
            kind="button",
            limit=10,
        )["elements"][0]
        with self.assertRaises(EdgeCdpError):
            self.controller.click_element(
                element_ref=element["element_ref"]
            )
        self.assertEqual(self.page.submit.clicks, 0)

    def test_safe_fill_is_verified_without_submission(self) -> None:
        element = self.controller.list_elements(
            tab_ref=self.tab_ref,
            kind="textbox",
            limit=10,
        )["elements"][0]
        result = self.controller.fill_element(
            element_ref=element["element_ref"],
            value="초안 내용",
        )
        self.assertTrue(result["value_set"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["characters"], 5)

    def test_password_fill_is_blocked(self) -> None:
        elements = self.controller.list_elements(
            tab_ref=self.tab_ref,
            kind="textbox",
            limit=10,
        )["elements"]
        password = next(
            item for item in elements
            if item["label"] == "비밀번호"
        )
        with self.assertRaises(EdgeCdpError):
            self.controller.fill_element(
                element_ref=password["element_ref"],
                value="secret",
            )

    def test_reference_is_invalid_after_page_change(self) -> None:
        element = self.controller.list_elements(
            tab_ref=self.tab_ref,
            kind="link",
            limit=10,
        )["elements"][0]
        self.page.link.metadata["label"] = "다른 링크"
        with self.assertRaises(StaleElementReferenceError):
            self.controller.get_element(
                element_ref=element["element_ref"]
            )


if __name__ == "__main__":
    unittest.main()
