from __future__ import annotations

import base64
import json
import unittest

from src.app.cli import parse_args
from src.gmail import (
    GMAIL_READONLY_SCOPE,
    GmailClient,
    GmailConfig,
    GmailError,
)
from src.tools.gmail_tools import (
    register_gmail_tools,
)
from src.tools.registry import ToolRegistry


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(
        value.encode("utf-8")
    ).decode("ascii").rstrip("=")


class _Executable:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _Messages:
    def __init__(self, messages, details):
        self.messages = messages
        self.details = details
        self.list_kwargs = None
        self.get_kwargs = None

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return _Executable(self.messages)

    def get(self, **kwargs):
        self.get_kwargs = kwargs
        return _Executable(
            self.details[kwargs["id"]]
        )


class _Labels:
    def list(self, **kwargs):
        del kwargs
        return _Executable(
            {
                "labels": [
                    {
                        "id": "INBOX",
                        "name": "INBOX",
                        "type": "system",
                    }
                ]
            }
        )


class _Users:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages

    def labels(self):
        return _Labels()

    def getProfile(self, **kwargs):
        del kwargs
        return _Executable(
            {
                "emailAddress": "test@example.com",
                "messagesTotal": 10,
                "threadsTotal": 7,
                "historyId": "123",
            }
        )


class _Service:
    def __init__(self, messages, details):
        self._messages = _Messages(
            messages,
            details,
        )
        self._users = _Users(
            self._messages
        )

    def users(self):
        return self._users


class GmailReadOnlyTests(unittest.TestCase):
    def _client(self) -> tuple[
        GmailClient,
        _Service,
    ]:
        details = {
            "m1": {
                "id": "m1",
                "threadId": "t1",
                "historyId": "10",
                "internalDate": "1754190000000",
                "labelIds": [
                    "INBOX",
                    "UNREAD",
                    "IMPORTANT",
                ],
                "snippet": "메일 미리보기",
                "payload": {
                    "mimeType": "multipart/alternative",
                    "headers": [
                        {
                            "name": "From",
                            "value": "Sender <sender@example.com>",
                        },
                        {
                            "name": "Subject",
                            "value": "테스트 메일",
                        },
                        {
                            "name": "Date",
                            "value": "Sun, 3 Aug 2025 10:00:00 +0900",
                        },
                    ],
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {
                                "data": _encoded(
                                    "안녕하세요.\n중요한 내용입니다."
                                )
                            },
                        },
                        {
                            "mimeType": "text/html",
                            "body": {
                                "data": _encoded(
                                    "<p>HTML 본문</p>"
                                )
                            },
                        },
                    ],
                },
            }
        }
        service = _Service(
            {
                "messages": [
                    {
                        "id": "m1",
                        "threadId": "t1",
                    }
                ],
                "resultSizeEstimate": 1,
            },
            details,
        )
        client = GmailClient(
            GmailConfig()
        )
        client._service = service
        return client, service

    def test_cli_defaults_and_scope(self) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )
        self.assertTrue(args.gmail_enabled)
        self.assertEqual(
            args.gmail_max_results,
            20,
        )
        self.assertEqual(
            GMAIL_READONLY_SCOPE,
            "https://www.googleapis.com/auth/gmail.readonly",
        )

    def test_lists_and_decodes_message(self) -> None:
        client, service = self._client()

        result = client.list_messages(
            query="is:unread",
            max_results=5,
            include_body=True,
            max_body_characters=2000,
        )

        self.assertEqual(result["count"], 1)
        message = result["messages"][0]
        self.assertEqual(
            message["subject"],
            "테스트 메일",
        )
        self.assertIn(
            "중요한 내용입니다.",
            message["body"],
        )
        self.assertTrue(message["unread"])
        self.assertTrue(message["important"])
        self.assertEqual(
            service._messages.list_kwargs["q"],
            "is:unread",
        )

    def test_unread_count_uses_search(self) -> None:
        client, service = self._client()

        result = client.unread_count(
            query="newer_than:7d"
        )

        self.assertEqual(
            result["unread_count_estimate"],
            1,
        )
        self.assertIn(
            "is:unread",
            service._messages.list_kwargs["q"],
        )

    def test_profile_and_labels(self) -> None:
        client, _ = self._client()

        self.assertEqual(
            client.profile()["email_address"],
            "test@example.com",
        )
        self.assertEqual(
            client.list_labels()[0]["id"],
            "INBOX",
        )

    def test_tools_are_read_only(self) -> None:
        client, _ = self._client()
        registry = ToolRegistry()
        register_gmail_tools(
            registry,
            client,
        )

        self.assertIn(
            "gmail_list_messages",
            registry.names,
        )
        forbidden = {
            "gmail_send_message",
            "gmail_delete_message",
            "gmail_modify_message",
            "gmail_trash_message",
        }
        self.assertTrue(
            forbidden.isdisjoint(
                registry.names
            )
        )

        result = registry.execute(
            "gmail_unread_count",
            json.dumps(
                {"query": ""}
            ),
        )
        self.assertTrue(result.success)

    def test_invalid_limit_rejected(self) -> None:
        client, _ = self._client()
        with self.assertRaises(
            GmailError
        ):
            client.list_messages(
                max_results=0
            )


if __name__ == "__main__":
    unittest.main()
