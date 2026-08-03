from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import json
import os
from typing import Any, Iterable, Mapping


READONLY_SCOPE = (
    "https://www.googleapis.com/auth/calendar.readonly"
)
EVENTS_SCOPE = (
    "https://www.googleapis.com/auth/calendar.events"
)
REQUIRED_SCOPES = (
    READONLY_SCOPE,
    EVENTS_SCOPE,
)


class GoogleCalendarError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GoogleCalendarConfig:
    enabled: bool = True
    credentials_file: Path = Path(
        "config/google_calendar_credentials.json"
    )
    token_file: Path = Path(
        "data/google_calendar_token.json"
    )
    default_calendar_id: str = "primary"
    max_results: int = 50
    oauth_port: int = 0
    open_browser_for_auth: bool = True
    allow_writes: bool = True

    def __post_init__(self) -> None:
        if not self.default_calendar_id.strip():
            raise ValueError(
                "default_calendar_id must not be empty."
            )
        if not 1 <= self.max_results <= 2500:
            raise ValueError(
                "max_results must be between 1 and 2500."
            )
        if not 0 <= self.oauth_port <= 65535:
            raise ValueError(
                "oauth_port must be between 0 and 65535."
            )


def _parse_datetime(value: str) -> datetime:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise GoogleCalendarError(
            "Use an ISO 8601 date-time such as "
            "2026-08-03T09:00:00+09:00."
        ) from exc
    if result.tzinfo is None:
        result = result.replace(
            tzinfo=datetime.now().astimezone().tzinfo
        )
    return result


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _clock(value: str) -> time:
    try:
        result = time.fromisoformat(
            value.strip()
        )
    except ValueError as exc:
        raise GoogleCalendarError(
            "Working hours must use HH:MM."
        ) from exc
    if result.tzinfo is not None:
        raise GoogleCalendarError(
            "Working hours must not include timezone."
        )
    return result


def _http_status(exc: Exception) -> int | None:
    response = getattr(exc, "resp", None)
    status = getattr(response, "status", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _clean_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None
    return value.strip()


def _event_time_body(
    *,
    start: str,
    end: str,
    all_day: bool,
    timezone_name: str | None,
) -> tuple[dict[str, str], dict[str, str]]:
    if all_day:
        try:
            start_date = date.fromisoformat(
                start.strip()
            )
            end_date = date.fromisoformat(
                end.strip()
            )
        except ValueError as exc:
            raise GoogleCalendarError(
                "All-day events require YYYY-MM-DD "
                "start and exclusive end dates."
            ) from exc
        if end_date <= start_date:
            raise GoogleCalendarError(
                "All-day event end date must be "
                "later than its start date."
            )
        return (
            {"date": start_date.isoformat()},
            {"date": end_date.isoformat()},
        )

    start_datetime = _parse_datetime(start)
    end_datetime = _parse_datetime(end)
    if end_datetime <= start_datetime:
        raise GoogleCalendarError(
            "Event end must be later than start."
        )

    start_body = {
        "dateTime": start_datetime.isoformat(
            timespec="seconds"
        )
    }
    end_body = {
        "dateTime": end_datetime.isoformat(
            timespec="seconds"
        )
    }
    timezone_value = (
        timezone_name.strip()
        if timezone_name
        else ""
    )
    if timezone_value:
        start_body["timeZone"] = timezone_value
        end_body["timeZone"] = timezone_value
    return start_body, end_body


def _map_event(
    item: Mapping[str, Any],
    *,
    calendar_id: str,
    fallback_timezone=None,
) -> dict[str, Any]:
    start_data = dict(item.get("start") or {})
    end_data = dict(item.get("end") or {})
    all_day = "date" in start_data

    if all_day:
        start_value = str(
            start_data.get("date") or ""
        )
        end_value = str(
            end_data.get("date") or ""
        )
    else:
        start_raw = str(
            start_data.get("dateTime") or ""
        )
        end_raw = str(
            end_data.get("dateTime") or ""
        )
        if start_raw:
            start_datetime = _parse_datetime(
                start_raw
            )
            if fallback_timezone is not None:
                start_datetime = (
                    start_datetime.astimezone(
                        fallback_timezone
                    )
                )
            start_value = (
                start_datetime.isoformat(
                    timespec="seconds"
                )
            )
        else:
            start_value = ""

        if end_raw:
            end_datetime = _parse_datetime(
                end_raw
            )
            if fallback_timezone is not None:
                end_datetime = (
                    end_datetime.astimezone(
                        fallback_timezone
                    )
                )
            end_value = (
                end_datetime.isoformat(
                    timespec="seconds"
                )
            )
        else:
            end_value = ""

    organizer = item.get("organizer") or {}
    return {
        "id": item.get("id"),
        "calendar_id": calendar_id,
        "summary": (
            item.get("summary")
            or "(제목 없음)"
        ),
        "description": item.get(
            "description"
        ),
        "location": item.get("location"),
        "start": start_value,
        "end": end_value,
        "all_day": all_day,
        "timezone": (
            start_data.get("timeZone")
            or end_data.get("timeZone")
        ),
        "status": item.get("status"),
        "html_link": item.get("htmlLink"),
        "organizer": (
            organizer.get("displayName")
            or organizer.get("email")
        ),
        "attendee_count": len(
            item.get("attendees", []) or []
        ),
        "etag": item.get("etag"),
        "updated": item.get("updated"),
    }


class GoogleCalendarClient:
    def __init__(
        self,
        config: GoogleCalendarConfig,
    ) -> None:
        self.config = config
        self._credentials: Any | None = None
        self._service: Any | None = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def credentials_path(self) -> Path:
        return (
            self.config
            .credentials_file
            .expanduser()
        )

    @property
    def token_path(self) -> Path:
        return self.config.token_file.expanduser()

    @staticmethod
    def _deps():
        try:
            from google.auth.transport.requests import (
                Request,
            )
            from google.oauth2.credentials import (
                Credentials,
            )
            from google_auth_oauthlib.flow import (
                InstalledAppFlow,
            )
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GoogleCalendarError(
                "Google Calendar packages are missing. "
                "Run `python -m pip install "
                "-r requirements.txt`."
            ) from exc
        return (
            Request,
            Credentials,
            InstalledAppFlow,
            build,
        )

    def _save_token(
        self,
        credentials: Any,
    ) -> None:
        self.token_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.token_path.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )
        try:
            os.chmod(
                self.token_path,
                0o600,
            )
        except OSError:
            pass

    def _load_token(self):
        if not self.token_path.is_file():
            return None

        Request, Credentials, _, _ = (
            self._deps()
        )
        try:
            credentials = (
                Credentials
                .from_authorized_user_file(
                    str(self.token_path)
                )
            )
        except (
            ValueError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise GoogleCalendarError(
                "Saved Calendar token is invalid. "
                "Delete it and authenticate again."
            ) from exc

        if (
            credentials.expired
            and credentials.refresh_token
        ):
            try:
                credentials.refresh(Request())
            except Exception as exc:
                raise GoogleCalendarError(
                    "Calendar token refresh failed. "
                    "Authenticate again."
                ) from exc
            self._save_token(credentials)

        return (
            credentials
            if credentials.valid
            else None
        )

    def _stored_scope_values(self) -> set[str]:
        if not self.token_path.is_file():
            return set()
        try:
            payload = json.loads(
                self.token_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
        ):
            return set()

        raw = payload.get("scopes")
        if isinstance(raw, str):
            return {
                item
                for item in raw.split()
                if item
            }
        if isinstance(raw, list):
            return {
                str(item)
                for item in raw
                if item
            }
        return set()

    def _granted_scopes(
        self,
        credentials: Any | None,
    ) -> set[str]:
        result = self._stored_scope_values()
        if credentials is None:
            return result

        for attribute in (
            "scopes",
            "granted_scopes",
        ):
            values = getattr(
                credentials,
                attribute,
                None,
            )
            if values:
                result.update(
                    str(item)
                    for item in values
                )
        return result

    def _missing_scopes(
        self,
        credentials: Any | None,
    ) -> tuple[str, ...]:
        if credentials is None:
            return REQUIRED_SCOPES

        try:
            if credentials.has_scopes(
                REQUIRED_SCOPES
            ):
                return ()
        except Exception:
            pass

        granted = self._granted_scopes(
            credentials
        )
        return tuple(
            scope
            for scope in REQUIRED_SCOPES
            if scope not in granted
        )

    def authorize_interactively(
        self,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise GoogleCalendarError(
                "Google Calendar is disabled."
            )
        if not self.credentials_path.is_file():
            raise GoogleCalendarError(
                "OAuth Desktop client JSON not found: "
                f"{self.credentials_path}"
            )

        _, _, InstalledAppFlow, _ = (
            self._deps()
        )
        try:
            flow = (
                InstalledAppFlow
                .from_client_secrets_file(
                    str(
                        self.credentials_path
                    ),
                    list(REQUIRED_SCOPES),
                )
            )
            credentials = flow.run_local_server(
                port=self.config.oauth_port,
                open_browser=(
                    self.config
                    .open_browser_for_auth
                ),
                prompt="consent",
                access_type="offline",
                success_message=(
                    "Jarvis Calendar authorization "
                    "completed. You may close this tab."
                ),
            )
        except Exception as exc:
            raise GoogleCalendarError(
                "Google Calendar OAuth failed."
            ) from exc

        self._credentials = credentials
        self._service = None
        self._save_token(credentials)
        return self.status()

    def status(self) -> dict[str, Any]:
        authenticated = False
        error: str | None = None
        credentials = None

        if self.enabled:
            try:
                credentials = self._load_token()
                authenticated = bool(
                    credentials
                    and credentials.valid
                )
                if authenticated:
                    self._credentials = (
                        credentials
                    )
            except GoogleCalendarError as exc:
                error = str(exc)

        granted = sorted(
            self._granted_scopes(
                credentials
            )
        )
        missing = list(
            self._missing_scopes(
                credentials
            )
        )
        ready = (
            authenticated
            and not missing
        )
        return {
            "enabled": self.enabled,
            "authenticated": authenticated,
            "ready": ready,
            "scope": " ".join(
                REQUIRED_SCOPES
            ),
            "required_scopes": list(
                REQUIRED_SCOPES
            ),
            "granted_scopes": granted,
            "missing_scopes": missing,
            "reauthorization_required": (
                authenticated
                and bool(missing)
            ),
            "allow_writes": (
                self.config.allow_writes
            ),
            "write_ready": (
                ready
                and self.config.allow_writes
            ),
            "credentials_file": str(
                self.credentials_path
            ),
            "credentials_file_exists": (
                self.credentials_path.is_file()
            ),
            "token_file": str(
                self.token_path
            ),
            "token_file_exists": (
                self.token_path.is_file()
            ),
            "error": error,
        }

    def _credentials_or_raise(self):
        if not self.enabled:
            raise GoogleCalendarError(
                "Google Calendar is disabled."
            )
        if self._credentials is None:
            self._credentials = (
                self._load_token()
            )
        if self._credentials is None:
            raise GoogleCalendarError(
                "Google Calendar is not authorized. "
                "Run `python -m src.main "
                "--google-calendar-auth`."
            )
        return self._credentials

    def _ensure_write_ready(self) -> None:
        if not self.config.allow_writes:
            raise GoogleCalendarError(
                "Google Calendar writes are disabled."
            )
        credentials = (
            self._credentials_or_raise()
        )
        missing = self._missing_scopes(
            credentials
        )
        if missing:
            raise GoogleCalendarError(
                "The saved Calendar token is "
                "read-only or missing event-write "
                "permission. Run `python -m src.main "
                "--google-calendar-auth` again. "
                "Missing scope: "
                + ", ".join(missing)
            )

    def _api(self):
        if self._service is not None:
            return self._service

        _, _, _, build = self._deps()
        try:
            self._service = build(
                "calendar",
                "v3",
                credentials=(
                    self._credentials_or_raise()
                ),
                cache_discovery=False,
            )
        except Exception as exc:
            raise GoogleCalendarError(
                "Could not initialize "
                "Google Calendar API."
            ) from exc
        return self._service

    def _calendar_id(
        self,
        calendar_id: str | None,
    ) -> str:
        result = (
            calendar_id
            or self.config.default_calendar_id
        ).strip()
        if not result:
            raise GoogleCalendarError(
                "calendar_id must not be empty."
            )
        return result

    def list_calendars(
        self,
        max_results: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= max_results <= 250:
            raise GoogleCalendarError(
                "max_results must be 1..250."
            )
        response = (
            self._api()
            .calendarList()
            .list(
                maxResults=max_results,
                showHidden=False,
            )
            .execute()
        )
        return tuple(
            {
                "id": item.get("id"),
                "summary": item.get(
                    "summary"
                ),
                "primary": bool(
                    item.get("primary")
                ),
                "selected": bool(
                    item.get("selected")
                ),
                "access_role": item.get(
                    "accessRole"
                ),
                "timezone": item.get(
                    "timeZone"
                ),
            }
            for item in response.get(
                "items",
                [],
            )
        )

    def get_event(
        self,
        *,
        event_id: str,
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        clean_id = event_id.strip()
        if not clean_id:
            raise GoogleCalendarError(
                "event_id must not be empty."
            )
        selected_calendar = (
            self._calendar_id(calendar_id)
        )
        try:
            response = (
                self._api()
                .events()
                .get(
                    calendarId=(
                        selected_calendar
                    ),
                    eventId=clean_id,
                )
                .execute()
            )
        except Exception as exc:
            if _http_status(exc) in {
                404,
                410,
            }:
                raise GoogleCalendarError(
                    "Calendar event was not found."
                ) from exc
            raise
        return _map_event(
            response,
            calendar_id=selected_calendar,
        )

    def list_events(
        self,
        *,
        time_min: str,
        time_max: str,
        calendar_id: str | None = None,
        max_results: int | None = None,
        query: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        start = _parse_datetime(time_min)
        end = _parse_datetime(time_max)
        if end <= start:
            raise GoogleCalendarError(
                "time_max must be after time_min."
            )
        limit = (
            max_results
            or self.config.max_results
        )
        if not 1 <= limit <= 2500:
            raise GoogleCalendarError(
                "max_results must be 1..2500."
            )
        selected_calendar = (
            self._calendar_id(calendar_id)
        )

        response = (
            self._api()
            .events()
            .list(
                calendarId=selected_calendar,
                timeMin=_utc(start),
                timeMax=_utc(end),
                maxResults=limit,
                singleEvents=True,
                orderBy="startTime",
                q=(
                    query.strip()
                    if query
                    else None
                ),
            )
            .execute()
        )

        return tuple(
            _map_event(
                item,
                calendar_id=selected_calendar,
                fallback_timezone=start.tzinfo,
            )
            for item in response.get(
                "items",
                [],
            )
            if item.get("status")
            != "cancelled"
        )

    def find_free_slots(
        self,
        *,
        time_min: str,
        time_max: str,
        duration_minutes: int,
        calendar_ids: Iterable[str] | None = None,
        working_hours_start: str = "09:00",
        working_hours_end: str = "18:00",
        max_slots: int = 10,
    ) -> tuple[dict[str, Any], ...]:
        start = _parse_datetime(time_min)
        end = _parse_datetime(time_max)
        if end <= start:
            raise GoogleCalendarError(
                "time_max must be after time_min."
            )
        if not 1 <= duration_minutes <= 1440:
            raise GoogleCalendarError(
                "duration_minutes must be 1..1440."
            )
        work_start = _clock(
            working_hours_start
        )
        work_end = _clock(
            working_hours_end
        )
        if work_end <= work_start:
            raise GoogleCalendarError(
                "Working-hour end must be after start."
            )
        ids = [
            item.strip()
            for item in (
                calendar_ids
                or [
                    self.config
                    .default_calendar_id
                ]
            )
            if item and item.strip()
        ]
        response = (
            self._api()
            .freebusy()
            .query(
                body={
                    "timeMin": _utc(start),
                    "timeMax": _utc(end),
                    "items": [
                        {"id": item}
                        for item in ids
                    ],
                }
            )
            .execute()
        )

        busy: list[
            tuple[datetime, datetime]
        ] = []
        for calendar_id in ids:
            data = (
                response.get(
                    "calendars",
                    {},
                )
                .get(
                    calendar_id,
                    {},
                )
            )
            if data.get("errors"):
                raise GoogleCalendarError(
                    "Free/busy failed for "
                    f"{calendar_id}: "
                    f"{data['errors']}"
                )
            for item in data.get(
                "busy",
                [],
            ):
                busy.append(
                    (
                        _parse_datetime(
                            item["start"]
                        ).astimezone(
                            start.tzinfo
                        ),
                        _parse_datetime(
                            item["end"]
                        ).astimezone(
                            start.tzinfo
                        ),
                    )
                )

        busy.sort()
        merged: list[list[datetime]] = []
        for left, right in busy:
            if (
                not merged
                or left > merged[-1][1]
            ):
                merged.append(
                    [left, right]
                )
            else:
                merged[-1][1] = max(
                    merged[-1][1],
                    right,
                )

        duration = timedelta(
            minutes=duration_minutes
        )
        slots: list[
            dict[str, Any]
        ] = []
        day = start.date()

        while (
            day <= end.date()
            and len(slots) < max_slots
        ):
            left = max(
                start,
                datetime.combine(
                    day,
                    work_start,
                    tzinfo=start.tzinfo,
                ),
            )
            right = min(
                end,
                datetime.combine(
                    day,
                    work_end,
                    tzinfo=start.tzinfo,
                ),
            )
            cursor = left

            if right > left:
                for (
                    busy_left,
                    busy_right,
                ) in merged:
                    if busy_right <= cursor:
                        continue
                    if busy_left >= right:
                        break
                    if (
                        busy_left - cursor
                        >= duration
                    ):
                        slots.append(
                            {
                                "start": (
                                    cursor
                                    .isoformat(
                                        timespec=(
                                            "seconds"
                                        )
                                    )
                                ),
                                "end": (
                                    cursor
                                    + duration
                                ).isoformat(
                                    timespec=(
                                        "seconds"
                                    )
                                ),
                                "duration_minutes": (
                                    duration_minutes
                                ),
                            }
                        )
                        if (
                            len(slots)
                            >= max_slots
                        ):
                            break
                    cursor = max(
                        cursor,
                        min(
                            busy_right,
                            right,
                        ),
                    )

                if (
                    len(slots)
                    < max_slots
                    and right - cursor
                    >= duration
                ):
                    slots.append(
                        {
                            "start": (
                                cursor.isoformat(
                                    timespec=(
                                        "seconds"
                                    )
                                )
                            ),
                            "end": (
                                cursor
                                + duration
                            ).isoformat(
                                timespec=(
                                    "seconds"
                                )
                            ),
                            "duration_minutes": (
                                duration_minutes
                            ),
                        }
                    )

            day += timedelta(days=1)

        return tuple(slots)

    def create_event(
        self,
        *,
        summary: str,
        start: str,
        end: str,
        all_day: bool,
        timezone_name: str | None = None,
        description: str | None = None,
        location: str | None = None,
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_write_ready()
        clean_summary = " ".join(
            summary.strip().split()
        )
        if not clean_summary:
            raise GoogleCalendarError(
                "Event summary must not be empty."
            )

        start_body, end_body = (
            _event_time_body(
                start=start,
                end=end,
                all_day=all_day,
                timezone_name=timezone_name,
            )
        )
        selected_calendar = (
            self._calendar_id(calendar_id)
        )
        body: dict[str, Any] = {
            "summary": clean_summary,
            "start": start_body,
            "end": end_body,
        }
        clean_description = (
            _clean_optional_text(
                description
            )
        )
        clean_location = (
            _clean_optional_text(location)
        )
        if clean_description is not None:
            body["description"] = (
                clean_description
            )
        if clean_location is not None:
            body["location"] = (
                clean_location
            )

        response = (
            self._api()
            .events()
            .insert(
                calendarId=(
                    selected_calendar
                ),
                body=body,
                sendUpdates="none",
            )
            .execute()
        )
        event_id = str(
            response.get("id") or ""
        ).strip()
        if not event_id:
            raise GoogleCalendarError(
                "Google Calendar did not return "
                "the created event ID."
            )

        event = self.get_event(
            event_id=event_id,
            calendar_id=selected_calendar,
        )
        verified = (
            event.get("id") == event_id
            and event.get("summary")
            == clean_summary
        )
        return {
            "created": True,
            "verified": verified,
            "event": event,
            "message": (
                "Google Calendar 일정을 "
                "생성하고 다시 조회해 "
                "검증했습니다."
            ),
        }

    def update_event(
        self,
        *,
        event_id: str,
        calendar_id: str | None = None,
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        all_day: bool | None = None,
        timezone_name: str | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_write_ready()
        clean_id = event_id.strip()
        if not clean_id:
            raise GoogleCalendarError(
                "event_id must not be empty."
            )

        selected_calendar = (
            self._calendar_id(calendar_id)
        )
        changes: dict[str, Any] = {}

        if summary is not None:
            clean_summary = " ".join(
                summary.strip().split()
            )
            if not clean_summary:
                raise GoogleCalendarError(
                    "Event summary must not be empty."
                )
            changes["summary"] = (
                clean_summary
            )

        if description is not None:
            changes["description"] = (
                description.strip()
            )
        if location is not None:
            changes["location"] = (
                location.strip()
            )

        time_values = (
            start is not None,
            end is not None,
        )
        if any(time_values):
            if not all(time_values):
                raise GoogleCalendarError(
                    "Changing event time requires "
                    "both start and end."
                )
            effective_all_day = bool(
                all_day
            )
            start_body, end_body = (
                _event_time_body(
                    start=str(start),
                    end=str(end),
                    all_day=(
                        effective_all_day
                    ),
                    timezone_name=(
                        timezone_name
                    ),
                )
            )
            changes["start"] = start_body
            changes["end"] = end_body
        elif all_day is not None:
            raise GoogleCalendarError(
                "all_day can only change together "
                "with start and end."
            )

        if not changes:
            raise GoogleCalendarError(
                "At least one event field must change."
            )

        (
            self._api()
            .events()
            .patch(
                calendarId=(
                    selected_calendar
                ),
                eventId=clean_id,
                body=changes,
                sendUpdates="none",
            )
            .execute()
        )
        event = self.get_event(
            event_id=clean_id,
            calendar_id=selected_calendar,
        )

        verified = (
            event.get("id") == clean_id
        )
        if "summary" in changes:
            verified = (
                verified
                and event.get("summary")
                == changes["summary"]
            )
        if "description" in changes:
            verified = (
                verified
                and (
                    event.get("description")
                    or ""
                )
                == changes["description"]
            )
        if "location" in changes:
            verified = (
                verified
                and (
                    event.get("location")
                    or ""
                )
                == changes["location"]
            )
        if "start" in changes:
            expected_all_day = (
                "date" in changes["start"]
            )
            verified = (
                verified
                and event.get("all_day")
                is expected_all_day
            )

        return {
            "updated": True,
            "verified": verified,
            "changed_fields": sorted(
                changes
            ),
            "event": event,
            "message": (
                "Google Calendar 일정을 "
                "수정하고 다시 조회해 "
                "검증했습니다."
            ),
        }

    def delete_event(
        self,
        *,
        event_id: str,
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_write_ready()
        clean_id = event_id.strip()
        if not clean_id:
            raise GoogleCalendarError(
                "event_id must not be empty."
            )
        selected_calendar = (
            self._calendar_id(calendar_id)
        )
        before = self.get_event(
            event_id=clean_id,
            calendar_id=selected_calendar,
        )

        (
            self._api()
            .events()
            .delete(
                calendarId=(
                    selected_calendar
                ),
                eventId=clean_id,
                sendUpdates="none",
            )
            .execute()
        )

        deletion_verified = False
        try:
            (
                self._api()
                .events()
                .get(
                    calendarId=(
                        selected_calendar
                    ),
                    eventId=clean_id,
                )
                .execute()
            )
        except Exception as exc:
            if _http_status(exc) in {
                404,
                410,
            }:
                deletion_verified = True
            else:
                raise

        return {
            "deleted": True,
            "deletion_verified": (
                deletion_verified
            ),
            "deleted_event": before,
            "message": (
                "Google Calendar 일정을 "
                "삭제하고 존재하지 않는 것을 "
                "다시 확인했습니다."
            ),
        }

    def close(self) -> None:
        self._service = None
        self._credentials = None
