from __future__ import annotations

import json
import unittest

from src.edge_cdp import EdgeCdpConfig
from src.tools.edge_cdp_tools import (
    register_edge_cdp_tools,
)
from src.tools.registry import (
    ToolRegistry,
)


class _Controller:
    enabled = True
    allow_tab_close = True
    allow_dom_actions = True
    config = EdgeCdpConfig()

    def __init__(self) -> None:
        self.closed = 0

    def status(self):
        return {
            "connected": True,
        }

    def list_tabs(self, *, limit):
        del limit
        return {
            "count": 1,
            "tabs": [
                {
                    "tab_ref": "tab1",
                    "title": "Example",
                }
            ],
        }

    def select_tab(self, *, tab_ref):
        return {
            "selected": True,
            "tab": {
                "tab_ref": tab_ref,
            },
        }

    def get_page_info(
        self,
        *,
        tab_ref,
        include_text,
    ):
        return {
            "tab_ref": tab_ref,
            "include_text": include_text,
        }

    def list_elements(self, *, tab_ref, kind, limit):
        return {
            "tab_ref": tab_ref,
            "kind": kind,
            "count": 1,
            "elements": [{
                "element_ref": "el1",
                "label": "Example",
                "safety": {"allowed": True},
            }],
        }

    def get_element(self, *, element_ref):
        return {"element_ref": element_ref}

    def click_element(self, *, element_ref):
        return {
            "clicked": True,
            "verified": True,
            "element_ref": element_ref,
        }

    def fill_element(self, *, element_ref, value):
        return {
            "value_set": True,
            "verified": True,
            "element_ref": element_ref,
            "characters": len(value),
        }

    def capture_tab(
        self,
        *,
        tab_ref,
        full_page,
    ):
        return {
            "tab_ref": tab_ref,
            "full_page": full_page,
        }

    def describe_tab(self, tab_ref):
        return f"'{tab_ref}' Edge 탭"

    def close_tab(self, *, tab_ref):
        self.closed += 1
        return {
            "closed": True,
            "tab": {
                "tab_ref": tab_ref,
            },
        }


class EdgeCdpToolTests(
    unittest.TestCase
):
    def test_close_waits_for_approval(
        self,
    ) -> None:
        controller = _Controller()
        registry = ToolRegistry()
        register_edge_cdp_tools(
            registry,
            controller,
        )

        result = registry.execute(
            "edge_cdp_close_tab",
            json.dumps(
                {"tab_ref": "tab1"}
            ),
        )
        self.assertTrue(
            result.confirmation_required
        )
        self.assertEqual(
            controller.closed,
            0,
        )

        executed = (
            registry
            .approve_pending_confirmation()
        )
        self.assertTrue(executed.success)
        self.assertEqual(
            controller.closed,
            1,
        )

    def test_read_tools_registered(self) -> None:
        registry = ToolRegistry()
        register_edge_cdp_tools(
            registry,
            _Controller(),
        )
        self.assertIn(
            "edge_cdp_list_tabs",
            registry.names,
        )
        self.assertIn(
            "edge_cdp_get_page_info",
            registry.names,
        )
        self.assertIn(
            "edge_cdp_capture_tab",
            registry.names,
        )
        self.assertIn(
            "edge_cdp_list_elements",
            registry.names,
        )
        self.assertIn(
            "edge_cdp_click_element",
            registry.names,
        )
        self.assertIn(
            "edge_cdp_fill_element",
            registry.names,
        )


if __name__ == "__main__":
    unittest.main()
