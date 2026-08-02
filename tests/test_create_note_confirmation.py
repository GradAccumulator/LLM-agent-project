from __future__ import annotations

import unittest

from src.tools import (
    build_default_tool_registry,
)


class CreateNoteConfirmationTests(
    unittest.TestCase
):
    def test_create_note_is_protected(
        self,
    ) -> None:
        registry = (
            build_default_tool_registry()
        )
        try:
            self.assertTrue(
                registry
                .confirmation_required_for(
                    "create_note"
                )
            )
        finally:
            registry.close()


if __name__ == "__main__":
    unittest.main()
