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


if __name__ == "__main__":
    unittest.main()
