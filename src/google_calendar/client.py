from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import json
import os
from typing import Any, Iterable

READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


class GoogleCalendarError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GoogleCalendarConfig:
    enabled: bool = True
    credentials_file: Path = Path("config/google_calendar_credentials.json")
    token_file: Path = Path("data/google_calendar_token.json")
    default_calendar_id: str = "primary"
    max_results: int = 50
    oauth_port: int = 0
    open_browser_for_auth: bool = True

    def __post_init__(self) -> None:
        if not self.default_calendar_id.strip():
            raise ValueError("default_calendar_id must not be empty.")
        if not 1 <= self.max_results <= 2500:
            raise ValueError("max_results must be between 1 and 2500.")
        if not 0 <= self.oauth_port <= 65535:
            raise ValueError("oauth_port must be between 0 and 65535.")


def _parse_datetime(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GoogleCalendarError(
            "Use ISO 8601 date-time, e.g. 2026-08-03T09:00:00+09:00."
        ) from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return result


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _clock(value: str) -> time:
    try:
        result = time.fromisoformat(value.strip())
    except ValueError as exc:
        raise GoogleCalendarError("Working hours must use HH:MM.") from exc
    if result.tzinfo is not None:
        raise GoogleCalendarError("Working hours must not include timezone.")
    return result


class GoogleCalendarClient:
    def __init__(self, config: GoogleCalendarConfig) -> None:
        self.config = config
        self._credentials: Any | None = None
        self._service: Any | None = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def credentials_path(self) -> Path:
        return self.config.credentials_file.expanduser()

    @property
    def token_path(self) -> Path:
        return self.config.token_file.expanduser()

    @staticmethod
    def _deps():
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GoogleCalendarError(
                "Google Calendar packages are missing. "
                "Run `python -m pip install -r requirements.txt`."
            ) from exc
        return Request, Credentials, InstalledAppFlow, build

    def _save_token(self, credentials: Any) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        try:
            os.chmod(self.token_path, 0o600)
        except OSError:
            pass

    def _load_token(self):
        if not self.token_path.is_file():
            return None
        Request, Credentials, _, _ = self._deps()
        try:
            credentials = Credentials.from_authorized_user_file(
                str(self.token_path), [READONLY_SCOPE]
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            raise GoogleCalendarError(
                "Saved Calendar token is invalid. Delete it and authenticate again."
            ) from exc
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception as exc:
                raise GoogleCalendarError(
                    "Calendar token refresh failed. Authenticate again."
                ) from exc
            self._save_token(credentials)
        return credentials if credentials.valid else None

    def authorize_interactively(self) -> dict[str, Any]:
        if not self.credentials_path.is_file():
            raise GoogleCalendarError(
                f"OAuth Desktop client JSON not found: {self.credentials_path}"
            )
        _, _, InstalledAppFlow, _ = self._deps()
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), [READONLY_SCOPE]
            )
            credentials = flow.run_local_server(
                port=self.config.oauth_port,
                open_browser=self.config.open_browser_for_auth,
                success_message=(
                    "Jarvis Calendar authorization completed. "
                    "You may close this tab."
                ),
            )
        except Exception as exc:
            raise GoogleCalendarError("Google Calendar OAuth failed.") from exc
        self._credentials = credentials
        self._service = None
        self._save_token(credentials)
        return self.status()

    def status(self) -> dict[str, Any]:
        authenticated = False
        error = None
        if self.enabled:
            try:
                credentials = self._load_token()
                authenticated = bool(credentials and credentials.valid)
                if authenticated:
                    self._credentials = credentials
            except GoogleCalendarError as exc:
                error = str(exc)
        return {
            "enabled": self.enabled,
            "authenticated": authenticated,
            "scope": READONLY_SCOPE,
            "credentials_file": str(self.credentials_path),
            "credentials_file_exists": self.credentials_path.is_file(),
            "token_file": str(self.token_path),
            "token_file_exists": self.token_path.is_file(),
            "error": error,
        }

    def _credentials_or_raise(self):
        if not self.enabled:
            raise GoogleCalendarError("Google Calendar is disabled.")
        if self._credentials is None:
            self._credentials = self._load_token()
        if self._credentials is None:
            raise GoogleCalendarError(
                "Google Calendar is not authorized. Run "
                "`python -m src.main --google-calendar-auth`."
            )
        return self._credentials

    def _api(self):
        if self._service is not None:
            return self._service
        _, _, _, build = self._deps()
        try:
            self._service = build(
                "calendar", "v3",
                credentials=self._credentials_or_raise(),
                cache_discovery=False,
            )
        except Exception as exc:
            raise GoogleCalendarError(
                "Could not initialize Google Calendar API."
            ) from exc
        return self._service

    def list_calendars(self, max_results: int = 100) -> tuple[dict[str, Any], ...]:
        if not 1 <= max_results <= 250:
            raise GoogleCalendarError("max_results must be 1..250.")
        response = self._api().calendarList().list(
            maxResults=max_results,
            showHidden=False,
        ).execute()
        return tuple({
            "id": item.get("id"),
            "summary": item.get("summary"),
            "primary": bool(item.get("primary")),
            "selected": bool(item.get("selected")),
            "access_role": item.get("accessRole"),
            "timezone": item.get("timeZone"),
        } for item in response.get("items", []))

    def list_events(
        self,
        *,
        time_min: str,
        time_max: str,
        calendar_id: str | None = None,
        max_results: int | None = None,
        query: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        start, end = _parse_datetime(time_min), _parse_datetime(time_max)
        if end <= start:
            raise GoogleCalendarError("time_max must be after time_min.")
        limit = max_results or self.config.max_results
        if not 1 <= limit <= 2500:
            raise GoogleCalendarError("max_results must be 1..2500.")
        cal_id = (calendar_id or self.config.default_calendar_id).strip()

        response = self._api().events().list(
            calendarId=cal_id,
            timeMin=_utc(start),
            timeMax=_utc(end),
            maxResults=limit,
            singleEvents=True,
            orderBy="startTime",
            q=query.strip() if query else None,
        ).execute()

        result = []
        for item in response.get("items", []):
            if item.get("status") == "cancelled":
                continue
            start_data = item.get("start", {})
            end_data = item.get("end", {})
            all_day = "date" in start_data
            if all_day:
                event_start = datetime.combine(
                    date.fromisoformat(start_data["date"]),
                    time.min,
                    tzinfo=start.tzinfo,
                )
                event_end = datetime.combine(
                    date.fromisoformat(end_data["date"]),
                    time.min,
                    tzinfo=start.tzinfo,
                )
            else:
                event_start = _parse_datetime(start_data["dateTime"])
                event_end = _parse_datetime(end_data["dateTime"])
            result.append({
                "id": item.get("id"),
                "calendar_id": cal_id,
                "summary": item.get("summary") or "(제목 없음)",
                "description": item.get("description"),
                "location": item.get("location"),
                "start": event_start.isoformat(timespec="seconds"),
                "end": event_end.isoformat(timespec="seconds"),
                "all_day": all_day,
                "organizer": (
                    item.get("organizer", {}).get("displayName")
                    or item.get("organizer", {}).get("email")
                ),
                "attendee_count": len(item.get("attendees", [])),
            })
        return tuple(result)

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
        start, end = _parse_datetime(time_min), _parse_datetime(time_max)
        if end <= start:
            raise GoogleCalendarError("time_max must be after time_min.")
        if not 1 <= duration_minutes <= 1440:
            raise GoogleCalendarError("duration_minutes must be 1..1440.")
        work_start, work_end = _clock(working_hours_start), _clock(working_hours_end)
        if work_end <= work_start:
            raise GoogleCalendarError("Working-hour end must be after start.")
        ids = [x.strip() for x in (
            calendar_ids or [self.config.default_calendar_id]
        ) if x and x.strip()]
        response = self._api().freebusy().query(body={
            "timeMin": _utc(start),
            "timeMax": _utc(end),
            "items": [{"id": x} for x in ids],
        }).execute()

        busy = []
        for cal_id in ids:
            data = response.get("calendars", {}).get(cal_id, {})
            if data.get("errors"):
                raise GoogleCalendarError(
                    f"Free/busy failed for {cal_id}: {data['errors']}"
                )
            for item in data.get("busy", []):
                busy.append((
                    _parse_datetime(item["start"]).astimezone(start.tzinfo),
                    _parse_datetime(item["end"]).astimezone(start.tzinfo),
                ))
        busy.sort()
        merged = []
        for left, right in busy:
            if not merged or left > merged[-1][1]:
                merged.append([left, right])
            else:
                merged[-1][1] = max(merged[-1][1], right)

        duration = timedelta(minutes=duration_minutes)
        slots = []
        day = start.date()
        while day <= end.date() and len(slots) < max_slots:
            left = max(start, datetime.combine(day, work_start, tzinfo=start.tzinfo))
            right = min(end, datetime.combine(day, work_end, tzinfo=start.tzinfo))
            cursor = left
            if right > left:
                for busy_left, busy_right in merged:
                    if busy_right <= cursor:
                        continue
                    if busy_left >= right:
                        break
                    if busy_left - cursor >= duration:
                        slots.append({
                            "start": cursor.isoformat(timespec="seconds"),
                            "end": (cursor + duration).isoformat(timespec="seconds"),
                            "duration_minutes": duration_minutes,
                        })
                        if len(slots) >= max_slots:
                            break
                    cursor = max(cursor, min(busy_right, right))
                if len(slots) < max_slots and right - cursor >= duration:
                    slots.append({
                        "start": cursor.isoformat(timespec="seconds"),
                        "end": (cursor + duration).isoformat(timespec="seconds"),
                        "duration_minutes": duration_minutes,
                    })
            day += timedelta(days=1)
        return tuple(slots)

    def close(self) -> None:
        self._service = None
        self._credentials = None
