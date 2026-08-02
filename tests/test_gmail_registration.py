from __future__ import annotations

import unittest

from src.gmail import (
    GmailClient,
    GmailConfig,
)
from src.tools import (
    build_default_tool_registry,
)


class GmailRegistrationTests(
    unittest.TestCase
):
    def test_read_only_tools_registered(self) -> None:
        client = GmailClient(
            GmailConfig()
        )
        registry = build_default_tool_registry(
            gmail_client=client
        )
        try:
            self.assertIn(
                "gmail_list_messages",
                registry.names,
            )
            self.assertIn(
                "gmail_unread_count",
                registry.names,
            )
            self.assertNotIn(
                "gmail_send_message",
                registry.names,
            )
        finally:
            registry.close()


if __name__ == "__main__":
    unittest.main()
