from __future__ import annotations

import unittest

from src.tools import (
    ToolRegistry,
    ToolSpec,
    register_edge_cdp_tools,
)


class _Config:
    max_elements = 100


class _Controller:
    config = _Config()
    allow_dom_actions = True
    allow_tab_close = False

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
            "tab": {"tab_ref": tab_ref},
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

    def get_element(self, *, element_ref):
        del element_ref
        return {}

    def click_element(self, *, element_ref):
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


class StrictToolSchemaTests(unittest.TestCase):
    def test_rejects_missing_required_property(self) -> None:
        registry = ToolRegistry()
        with self.assertRaisesRegex(
            ValueError,
            "workflow_ref",
        ):
            registry.register(
                ToolSpec(
                    name="bad_tool",
                    description="bad",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tab_ref": {
                                "type": "string",
                            },
                            "workflow_ref": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },
                        },
                        "required": [
                            "tab_ref",
                        ],
                        "additionalProperties": False,
                    },
                    handler=lambda **_: {},
                )
            )

    def test_edge_schemas_require_every_property(self) -> None:
        registry = ToolRegistry()
        register_edge_cdp_tools(
            registry,
            _Controller(),
        )
        try:
            for tool in registry.schemas:
                schema = tool["parameters"]
                self.assertEqual(
                    set(schema["properties"]),
                    set(schema["required"]),
                    tool["name"],
                )
        finally:
            registry.close()

    def test_nullable_workflow_fields_are_required(self) -> None:
        registry = ToolRegistry()
        register_edge_cdp_tools(
            registry,
            _Controller(),
        )
        try:
            by_name = {
                tool["name"]: tool
                for tool in registry.schemas
            }
            expected = {
                "edge_cdp_select_tab": {
                    "tab_ref",
                    "workflow_ref",
                },
                "edge_cdp_begin_workflow": {
                    "goal",
                    "tab_ref",
                },
                "edge_cdp_click_element": {
                    "element_ref",
                    "workflow_ref",
                },
                "edge_cdp_fill_element": {
                    "element_ref",
                    "value",
                    "workflow_ref",
                },
            }
            for name, required in expected.items():
                self.assertEqual(
                    set(
                        by_name[name]
                        ["parameters"]
                        ["required"]
                    ),
                    required,
                )
        finally:
            registry.close()


if __name__ == "__main__":
    unittest.main()
