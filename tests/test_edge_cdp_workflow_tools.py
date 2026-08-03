from __future__ import annotations

import unittest

from src.tools import ToolRegistry
from src.tools.edge_cdp_tools import (
    register_edge_cdp_tools,
)


class _Controller:
    allow_dom_actions = True
    allow_tab_close = False

    class _Config:
        max_elements = 100

    config = _Config()

    def status(self):
        return {}

    def managed_edge_status(self):
        return {}

    def start_managed_edge(self):
        return {}

    def list_tabs(self, *, limit):
        del limit
        return {
            "tabs": [],
            "selected_tab_ref": None,
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
        del tab_ref, include_text
        return {}

    def list_elements(
        self,
        *,
        tab_ref,
        kind,
        limit,
    ):
        del tab_ref, kind, limit
        return {
            "elements": [],
            "tab_ref": None,
        }

    def get_element(
        self,
        *,
        element_ref,
    ):
        del element_ref
        return {}

    def click_element(
        self,
        *,
        element_ref,
    ):
        del element_ref
        return {
            "clicked": True,
            "verified": True,
        }

    def fill_element(
        self,
        *,
        element_ref,
        value,
    ):
        del element_ref, value
        return {
            "value_set": True,
            "verified": True,
        }

    def capture_tab(
        self,
        *,
        tab_ref,
        full_page,
    ):
        del tab_ref, full_page
        return {}

    def close(self):
        pass


class EdgeWorkflowToolTests(
    unittest.TestCase
):
    def test_workflow_tools_registered(
        self,
    ) -> None:
        registry = ToolRegistry()
        register_edge_cdp_tools(
            registry,
            _Controller(),
        )
        names = set(
            registry.names
        )
        self.assertIn(
            "edge_cdp_find_tabs",
            names,
        )
        self.assertIn(
            "edge_cdp_find_element",
            names,
        )
        self.assertIn(
            "edge_cdp_begin_workflow",
            names,
        )
        self.assertIn(
            "edge_cdp_get_workflow",
            names,
        )
        self.assertIn(
            "edge_cdp_verify_workflow",
            names,
        )
        registry.close()


if __name__ == "__main__":
    unittest.main()
