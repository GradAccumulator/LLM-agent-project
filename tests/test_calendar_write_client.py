from __future__ import annotations

import unittest

from src.google_calendar import (
    EVENTS_SCOPE,
    READONLY_SCOPE,
    REQUIRED_SCOPES,
    GoogleCalendarClient,
    GoogleCalendarConfig,
    GoogleCalendarError,
)


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status


class _NotFound(Exception):
    def __init__(self) -> None:
        self.resp = _Response(404)


class _Credentials:
    valid = True
    expired = False
    refresh_token = "refresh"
    scopes = list(REQUIRED_SCOPES)
    granted_scopes = list(
        REQUIRED_SCOPES
    )

    def has_scopes(self, scopes) -> bool:
        return set(scopes).issubset(
            set(self.scopes)
        )


class _Executable:
    def __init__(
        self,
        callback,
    ) -> None:
        self._callback = callback

    def execute(self):
        return self._callback()


class _Events:
    def __init__(self) -> None:
        self.items = {
            "existing": {
                "id": "existing",
                "summary": "기존 일정",
                "status": "confirmed",
                "start": {
                    "dateTime": (
                        "2026-08-03T10:00:00+09:00"
                    )
                },
                "end": {
                    "dateTime": (
                        "2026-08-03T11:00:00+09:00"
                    )
                },
            }
        }
        self.insert_calls = 0
        self.patch_calls = 0
        self.delete_calls = 0

    def get(
        self,
        *,
        calendarId,
        eventId,
    ):
        del calendarId

        def callback():
            if eventId not in self.items:
                raise _NotFound()
            return dict(
                self.items[eventId]
            )

        return _Executable(callback)

    def insert(
        self,
        *,
        calendarId,
        body,
        sendUpdates,
    ):
        del calendarId
        assert sendUpdates == "none"

        def callback():
            self.insert_calls += 1
            event = {
                "id": "created",
                "status": "confirmed",
                **body,
            }
            self.items["created"] = event
            return dict(event)

        return _Executable(callback)

    def patch(
        self,
        *,
        calendarId,
        eventId,
        body,
        sendUpdates,
    ):
        del calendarId
        assert sendUpdates == "none"

        def callback():
            self.patch_calls += 1
            self.items[eventId].update(
                body
            )
            return dict(
                self.items[eventId]
            )

        return _Executable(callback)

    def delete(
        self,
        *,
        calendarId,
        eventId,
        sendUpdates,
    ):
        del calendarId
        assert sendUpdates == "none"

        def callback():
            self.delete_calls += 1
            self.items.pop(
                eventId,
                None,
            )
            return None

        return _Executable(callback)


class _Service:
    def __init__(self) -> None:
        self.events_resource = _Events()

    def events(self):
        return self.events_resource


class CalendarWriteClientTests(
    unittest.TestCase
):
    def _client(self):
        client = GoogleCalendarClient(
            GoogleCalendarConfig(
                allow_writes=True
            )
        )
        service = _Service()
        client._credentials = _Credentials()
        client._service = service
        return client, service

    def test_required_scopes_are_least_split(self) -> None:
        self.assertEqual(
            REQUIRED_SCOPES,
            (
                READONLY_SCOPE,
                EVENTS_SCOPE,
            ),
        )

    def test_create_and_verify(self) -> None:
        client, service = self._client()

        result = client.create_event(
            summary="병원",
            start=(
                "2026-08-03T15:00:00+09:00"
            ),
            end=(
                "2026-08-03T16:00:00+09:00"
            ),
            all_day=False,
            timezone_name="Asia/Seoul",
            description=None,
            location="서울",
        )

        self.assertTrue(result["created"])
        self.assertTrue(result["verified"])
        self.assertEqual(
            result["event"]["id"],
            "created",
        )
        self.assertEqual(
            service
            .events_resource
            .insert_calls,
            1,
        )

    def test_update_and_verify(self) -> None:
        client, service = self._client()

        result = client.update_event(
            event_id="existing",
            summary="변경된 일정",
            start=None,
            end=None,
            all_day=None,
            description=None,
            location=None,
        )

        self.assertTrue(result["updated"])
        self.assertTrue(result["verified"])
        self.assertEqual(
            result["event"]["summary"],
            "변경된 일정",
        )
        self.assertEqual(
            service
            .events_resource
            .patch_calls,
            1,
        )

    def test_delete_and_verify(self) -> None:
        client, service = self._client()

        result = client.delete_event(
            event_id="existing"
        )

        self.assertTrue(result["deleted"])
        self.assertTrue(
            result["deletion_verified"]
        )
        self.assertEqual(
            service
            .events_resource
            .delete_calls,
            1,
        )

    def test_write_scope_is_required(self) -> None:
        class ReadOnlyCredentials(
            _Credentials
        ):
            scopes = [READONLY_SCOPE]
            granted_scopes = [
                READONLY_SCOPE
            ]

        client = GoogleCalendarClient(
            GoogleCalendarConfig()
        )
        client._credentials = (
            ReadOnlyCredentials()
        )
        client._service = _Service()

        with self.assertRaises(
            GoogleCalendarError
        ):
            client.create_event(
                summary="병원",
                start=(
                    "2026-08-03T15:00:00+09:00"
                ),
                end=(
                    "2026-08-03T16:00:00+09:00"
                ),
                all_day=False,
            )

    def test_write_kill_switch(self) -> None:
        client = GoogleCalendarClient(
            GoogleCalendarConfig(
                allow_writes=False
            )
        )
        client._credentials = _Credentials()
        client._service = _Service()

        with self.assertRaises(
            GoogleCalendarError
        ):
            client.delete_event(
                event_id="existing"
            )


if __name__ == "__main__":
    unittest.main()
