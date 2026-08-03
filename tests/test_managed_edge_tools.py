from __future__ import annotations

import unittest

from src.tools.edge_cdp_tools import (
    register_edge_cdp_tools,
)
from src.tools.registry import ToolRegistry


class _Controller:
    enabled = True
    allow_tab_close = False

    def status(self):
        return {}

    def managed_edge_status(self):
        return {
            "ready": False,
        }

    def start_managed_edge(self):
        return {
            "ready": True,
            "launched": True,
        }

    def list_tabs(self, *, limit):
        del limit
        return {}

    def select_tab(self, *, tab_ref):
        return {
            "tab_ref": tab_ref
        }

    def get_page_info(
        self,
        *,
        tab_ref,
        include_text,
    ):
        return {}

    def capture_tab(
        self,
        *,
        tab_ref,
        full_page,
    ):
        return {}


class ManagedEdgeToolTests(
    unittest.TestCase
):
    def test_managed_tools_are_registered(
        self,
    ) -> None:
        registry = ToolRegistry()
        register_edge_cdp_tools(
            registry,
            _Controller(),
        )

        self.assertIn(
            "edge_cdp_managed_status",
            registry.names,
        )
        self.assertIn(
            "edge_cdp_start_managed",
            registry.names,
        )

        result = registry.execute(
            "edge_cdp_start_managed",
            "{}",
        )
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
