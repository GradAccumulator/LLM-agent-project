from __future__ import annotations

import unittest

from src.edge_cdp import (
    EdgeCdpConfig,
    EdgeCdpController,
    EdgeWorkflowCoordinator,
)


class _Element:
    def __init__(
        self,
        page,
        metadata,
        *,
        on_click=None,
    ) -> None:
        self.page = page
        self.metadata = dict(metadata)
        self.value = ""
        self.attached = True
        self.on_click = on_click

    def count(self):
        return (
            1
            if self.attached
            else 0
        )

    def evaluate(self, script):
        if "checked:" in script:
            return {
                "checked": None,
                "value": self.value,
                "aria_pressed": None,
                "aria_expanded": None,
                "aria_selected": None,
                "text": self.metadata.get(
                    "text",
                    "",
                ),
            }
        if "String(element.innerText" in script:
            return self.value
        return dict(self.metadata)

    def click(self, *, timeout):
        del timeout
        if self.on_click is not None:
            self.on_click()

    def fill(self, value, *, timeout):
        del timeout
        self.value = value

    def input_value(self, *, timeout):
        del timeout
        return self.value


class _Collection:
    def __init__(self, items):
        self.items = list(items)

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class _Body:
    def __init__(self, page):
        self.page = page

    def inner_text(self):
        return self.page.body_text


def _base_metadata():
    return {
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


class _Page:
    def __init__(
        self,
        title,
        url,
        context=None,
    ) -> None:
        self._title = title
        self.url = url
        self.context = context
        self.closed = False
        self.body_text = (
            f"{title} page text"
        )
        self.elements = []
        self.body = _Body(self)

    def title(self):
        return self._title

    def is_closed(self):
        return self.closed

    def bring_to_front(self):
        if self.context is not None:
            self.context.front = self

    def locator(self, selector):
        if selector == "body":
            return self.body
        if selector.startswith("a:visible") and "button" not in selector:
            return _Collection([
                item
                for item in self.elements
                if item.metadata.get("tag")
                == "a"
                and item.attached
            ])
        if selector.startswith("button:visible"):
            return _Collection([
                item
                for item in self.elements
                if item.metadata.get("tag")
                == "button"
                and item.attached
            ])
        if selector.startswith("input:visible"):
            return _Collection([
                item
                for item in self.elements
                if item.metadata.get("tag")
                in {
                    "input",
                    "textarea",
                }
                and item.attached
            ])
        return _Collection([
            item
            for item in self.elements
            if item.attached
        ])

    def wait_for_load_state(self, *args, **kwargs):
        pass

    def wait_for_timeout(self, value):
        del value


class _Context:
    def __init__(self) -> None:
        self.pages = []
        self.front = None

    def add(self, page):
        page.context = self
        self.pages.append(page)
        if self.front is None:
            self.front = page

    def set_default_timeout(self, value):
        del value


class _Browser:
    def __init__(self, context):
        self.contexts = [context]

    def is_connected(self):
        return True


class _Playwright:
    def stop(self):
        pass


class EdgeCdpWorkflowTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.context = _Context()
        self.page = _Page(
            "Search",
            "https://example.com/search",
        )
        self.context.add(self.page)
        self.controller = EdgeCdpController(
            EdgeCdpConfig(
                auto_start=False,
            ),
            connector=lambda *_: (
                _Playwright(),
                _Browser(
                    self.context
                ),
            ),
        )
        self.workflow = (
            EdgeWorkflowCoordinator(
                self.controller
            )
        )

    def tearDown(self) -> None:
        self.controller.close()

    def _add_safe_link(
        self,
        label,
        href,
        on_click=None,
    ):
        element = _Element(
            self.page,
            {
                **_base_metadata(),
                "tag": "a",
                "type": "",
                "label": label,
                "text": label,
                "href": href,
                "dom_path": (
                    "html > body > a"
                ),
            },
            on_click=on_click,
        )
        self.page.elements.append(
            element
        )
        return element

    def test_find_tabs_and_elements(
        self,
    ) -> None:
        self._add_safe_link(
            "문서 보기",
            "https://example.com/docs",
        )
        tab = self.workflow.find_tabs(
            query="Search",
            limit=10,
        )
        self.assertTrue(
            tab["unique_best"]
        )

        element = (
            self.workflow
            .find_element(
                tab_ref=None,
                kind="link",
                query="문서 보기",
                limit=10,
            )
        )
        self.assertTrue(
            element["unique_best"]
        )
        self.assertTrue(
            element[
                "best_element_ref"
            ]
        )

    def test_stale_reference_recovers_uniquely(
        self,
    ) -> None:
        old = self._add_safe_link(
            "문서 보기",
            "https://example.com/docs",
        )
        listed = (
            self.workflow
            .list_elements(
                tab_ref=None,
                kind="link",
                limit=10,
            )
        )
        old_ref = listed[
            "elements"
        ][0]["element_ref"]
        old.attached = False

        replacement = self._add_safe_link(
            "문서 보기",
            "https://example.com/docs",
            on_click=lambda: setattr(
                self.page,
                "url",
                "https://example.com/docs",
            ),
        )

        result = (
            self.workflow
            .click_element(
                element_ref=old_ref,
                workflow_ref=None,
            )
        )
        self.assertTrue(
            result["clicked"]
        )
        self.assertTrue(
            result["recovery"][
                "recovered"
            ]
        )
        self.assertNotEqual(
            result[
                "effective_element_ref"
            ],
            old_ref,
        )
        self.assertTrue(
            replacement.attached
        )

    def test_ambiguous_recovery_is_blocked(
        self,
    ) -> None:
        old = self._add_safe_link(
            "문서 보기",
            "https://example.com/docs",
        )
        old_ref = (
            self.workflow
            .list_elements(
                tab_ref=None,
                kind="link",
                limit=10,
            )["elements"][0][
                "element_ref"
            ]
        )
        old.attached = False
        self._add_safe_link(
            "문서 보기",
            "https://example.com/docs",
        )
        self._add_safe_link(
            "문서 보기",
            "https://example.com/docs",
        )

        with self.assertRaisesRegex(
            Exception,
            "ambiguous",
        ):
            self.workflow.click_element(
                element_ref=old_ref,
                workflow_ref=None,
            )

    def test_new_tab_is_detected_and_selected(
        self,
    ) -> None:
        def open_new_tab():
            page = _Page(
                "Docs",
                "https://example.com/docs",
            )
            page.body_text = (
                "GQA documentation"
            )
            self.context.add(page)

        self._add_safe_link(
            "문서 보기",
            "https://example.com/docs",
            on_click=open_new_tab,
        )
        element_ref = (
            self.workflow
            .list_elements(
                tab_ref=None,
                kind="link",
                limit=10,
            )["elements"][0][
                "element_ref"
            ]
        )
        result = (
            self.workflow
            .click_element(
                element_ref=element_ref,
                workflow_ref=None,
            )
        )

        self.assertEqual(
            result["new_tab_count"],
            1,
        )
        self.assertTrue(
            result["selected_new_tab"]
        )
        self.assertTrue(
            result["verified"]
        )

    def test_workflow_records_and_verifies(
        self,
    ) -> None:
        self._add_safe_link(
            "문서 보기",
            "https://example.com/docs",
            on_click=lambda: (
                setattr(
                    self.page,
                    "url",
                    "https://example.com/docs",
                ),
                setattr(
                    self.page,
                    "_title",
                    "Docs",
                ),
                setattr(
                    self.page,
                    "body_text",
                    "GQA documentation",
                ),
            ),
        )
        flow = (
            self.workflow
            .begin_workflow(
                goal=(
                    "문서 페이지 열기"
                ),
                tab_ref=None,
            )
        )
        element_ref = (
            self.workflow
            .find_element(
                tab_ref=None,
                kind="link",
                query="문서 보기",
                limit=10,
            )[
                "best_element_ref"
            ]
        )
        self.workflow.click_element(
            element_ref=element_ref,
            workflow_ref=flow[
                "workflow_ref"
            ],
        )
        verified = (
            self.workflow
            .verify_workflow(
                workflow_ref=flow[
                    "workflow_ref"
                ],
                expected_url_contains=(
                    "/docs"
                ),
                expected_title_contains=(
                    "Docs"
                ),
                expected_text_contains=(
                    "GQA"
                ),
                minimum_tab_count=1,
                require_all_steps_verified=True,
            )
        )

        self.assertTrue(
            verified["verified"]
        )
        self.assertEqual(
            verified["status"],
            "completed",
        )
        self.assertEqual(
            verified["step_count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
