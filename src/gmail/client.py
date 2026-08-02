from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from html import unescape
from pathlib import Path
import json
import os
import re
from typing import Any


GMAIL_READONLY_SCOPE = (
    "https://www.googleapis.com/auth/gmail.readonly"
)


class GmailError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GmailConfig:
    enabled: bool = True
    credentials_file: Path = Path(
        "config/gmail_credentials.json"
    )
    token_file: Path = Path(
        "data/gmail_token.json"
    )
    user_id: str = "me"
    max_results: int = 20
    max_body_characters: int = 8_000
    oauth_port: int = 0
    open_browser_for_auth: bool = True

    def __post_init__(self) -> None:
        if not self.user_id.strip():
            raise ValueError(
                "user_id must not be empty."
            )
        if not 1 <= self.max_results <= 500:
            raise ValueError(
                "max_results must be between 1 and 500."
            )
        if not 500 <= self.max_body_characters <= 100_000:
            raise ValueError(
                "max_body_characters must be between "
                "500 and 100000."
            )
        if not 0 <= self.oauth_port <= 65535:
            raise ValueError(
                "oauth_port must be between 0 and 65535."
            )


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _header_map(
    payload: dict[str, Any],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in payload.get("headers", []):
        name = str(item.get("name", "")).strip()
        value = _decode_header(
            str(item.get("value", ""))
        )
        if name:
            result[name.casefold()] = value
    return result


def _decode_base64url(value: str | None) -> str:
    if not value:
        return ""
    padded = value + "=" * (-len(value) % 4)
    try:
        raw = base64.urlsafe_b64decode(
            padded.encode("ascii")
        )
    except (ValueError, UnicodeEncodeError) as exc:
        raise GmailError(
            "Gmail returned invalid base64url message data."
        ) from exc

    for encoding in ("utf-8", "cp949", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


_SCRIPT_STYLE = re.compile(
    r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
    flags=re.IGNORECASE | re.DOTALL,
)
_BREAKS = re.compile(
    r"<(?:br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>",
    flags=re.IGNORECASE,
)
_TAGS = re.compile(r"<[^>]+>")
_MULTI_NEWLINES = re.compile(r"\n{3,}")
_MULTI_SPACES = re.compile(r"[ \t]{2,}")


def _html_to_text(value: str) -> str:
    cleaned = _SCRIPT_STYLE.sub("", value)
    cleaned = _BREAKS.sub("\n", cleaned)
    cleaned = _TAGS.sub("", cleaned)
    cleaned = unescape(cleaned)
    cleaned = "\n".join(
        _MULTI_SPACES.sub(" ", line).strip()
        for line in cleaned.splitlines()
    )
    return _MULTI_NEWLINES.sub(
        "\n\n",
        cleaned,
    ).strip()


def _collect_bodies(
    part: dict[str, Any],
    plain: list[str],
    html: list[str],
) -> None:
    mime_type = str(
        part.get("mimeType", "")
    ).casefold()
    data = (
        part.get("body", {})
        .get("data")
    )

    if data and mime_type == "text/plain":
        text = _decode_base64url(str(data)).strip()
        if text:
            plain.append(text)
    elif data and mime_type == "text/html":
        text = _html_to_text(
            _decode_base64url(str(data))
        )
        if text:
            html.append(text)

    for child in part.get("parts", []) or []:
        if isinstance(child, dict):
            _collect_bodies(
                child,
                plain,
                html,
            )


def _extract_body(
    payload: dict[str, Any],
    *,
    max_characters: int,
) -> tuple[str, bool]:
    plain: list[str] = []
    html: list[str] = []
    _collect_bodies(payload, plain, html)

    if not plain and not html:
        data = payload.get("body", {}).get("data")
        if data:
            mime_type = str(
                payload.get("mimeType", "")
            ).casefold()
            decoded = _decode_base64url(
                str(data)
            )
            if mime_type == "text/html":
                html.append(_html_to_text(decoded))
            else:
                plain.append(decoded.strip())

    body = "\n\n".join(
        item
        for item in (
            plain if plain else html
        )
        if item
    ).strip()
    truncated = len(body) > max_characters
    if truncated:
        body = body[:max_characters].rstrip()
    return body, truncated


def _internal_datetime(
    value: str | int | None,
) -> str | None:
    if value is None:
        return None
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(
        milliseconds / 1000,
        tz=timezone.utc,
    ).isoformat(timespec="seconds")


class GmailClient:
    """Lazy Gmail API client using read-only OAuth."""

    def __init__(
        self,
        config: GmailConfig,
    ) -> None:
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
    def _dependencies() -> tuple[Any, Any, Any, Any]:
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
            raise GmailError(
                "Gmail packages are missing. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc
        return Request, Credentials, InstalledAppFlow, build

    def _save_token(
        self,
        credentials: Any,
    ) -> None:
        path = self.token_path
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _load_token(self) -> Any | None:
        if not self.token_path.is_file():
            return None

        Request, Credentials, _, _ = (
            self._dependencies()
        )
        try:
            credentials = (
                Credentials
                .from_authorized_user_file(
                    str(self.token_path),
                    [GMAIL_READONLY_SCOPE],
                )
            )
        except (
            ValueError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise GmailError(
                "The saved Gmail token is invalid. "
                "Delete it and run --gmail-auth again."
            ) from exc

        if (
            credentials.expired
            and credentials.refresh_token
        ):
            try:
                credentials.refresh(Request())
            except Exception as exc:
                raise GmailError(
                    "Gmail token refresh failed. "
                    "Run --gmail-auth again."
                ) from exc
            self._save_token(credentials)

        return (
            credentials
            if credentials.valid
            else None
        )

    def authorize_interactively(
        self,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise GmailError(
                "Gmail integration is disabled."
            )
        if not self.credentials_path.is_file():
            raise GmailError(
                "OAuth Desktop client JSON was not found: "
                f"{self.credentials_path}. You may copy the "
                "same Desktop OAuth client JSON used for "
                "Google Calendar to this path."
            )

        _, _, InstalledAppFlow, _ = (
            self._dependencies()
        )
        try:
            flow = (
                InstalledAppFlow
                .from_client_secrets_file(
                    str(self.credentials_path),
                    [GMAIL_READONLY_SCOPE],
                )
            )
            credentials = flow.run_local_server(
                port=self.config.oauth_port,
                open_browser=(
                    self.config
                    .open_browser_for_auth
                ),
                success_message=(
                    "Jarvis Gmail authorization completed. "
                    "You can close this browser tab."
                ),
            )
        except Exception as exc:
            raise GmailError(
                "Gmail OAuth authorization failed."
            ) from exc

        self._credentials = credentials
        self._service = None
        self._save_token(credentials)
        return self.status()

    def status(self) -> dict[str, Any]:
        authenticated = False
        error: str | None = None

        if self.enabled:
            try:
                credentials = self._load_token()
                authenticated = bool(
                    credentials is not None
                    and credentials.valid
                )
                if authenticated:
                    self._credentials = credentials
            except GmailError as exc:
                error = str(exc)

        return {
            "enabled": self.enabled,
            "authenticated": authenticated,
            "scope": GMAIL_READONLY_SCOPE,
            "credentials_file": str(
                self.credentials_path
            ),
            "credentials_file_exists": (
                self.credentials_path.is_file()
            ),
            "token_file": str(self.token_path),
            "token_file_exists": (
                self.token_path.is_file()
            ),
            "error": error,
        }

    def _credentials_or_raise(self) -> Any:
        if not self.enabled:
            raise GmailError(
                "Gmail integration is disabled."
            )
        if self._credentials is None:
            self._credentials = self._load_token()
        if self._credentials is None:
            raise GmailError(
                "Gmail is not authorized. Run "
                "`python -m src.main --gmail-auth` first."
            )
        return self._credentials

    def _api(self) -> Any:
        if self._service is not None:
            return self._service

        _, _, _, build = self._dependencies()
        try:
            self._service = build(
                "gmail",
                "v1",
                credentials=(
                    self._credentials_or_raise()
                ),
                cache_discovery=False,
            )
        except Exception as exc:
            raise GmailError(
                "Could not initialize the Gmail API client."
            ) from exc
        return self._service

    def profile(self) -> dict[str, Any]:
        response = (
            self._api()
            .users()
            .getProfile(
                userId=self.config.user_id
            )
            .execute()
        )
        return {
            "email_address": response.get(
                "emailAddress"
            ),
            "messages_total": response.get(
                "messagesTotal"
            ),
            "threads_total": response.get(
                "threadsTotal"
            ),
            "history_id": response.get(
                "historyId"
            ),
        }

    def _get_message(
        self,
        message_id: str,
        *,
        include_body: bool,
        max_body_characters: int,
    ) -> dict[str, Any]:
        if not message_id.strip():
            raise GmailError(
                "message_id must not be empty."
            )
        if not 500 <= max_body_characters <= 100_000:
            raise GmailError(
                "max_body_characters must be between "
                "500 and 100000."
            )

        response = (
            self._api()
            .users()
            .messages()
            .get(
                userId=self.config.user_id,
                id=message_id,
                format=(
                    "full"
                    if include_body
                    else "metadata"
                ),
                metadataHeaders=(
                    None
                    if include_body
                    else [
                        "From",
                        "To",
                        "Cc",
                        "Subject",
                        "Date",
                        "Message-ID",
                    ]
                ),
            )
            .execute()
        )

        payload = response.get(
            "payload",
            {},
        )
        headers = _header_map(payload)
        labels = tuple(
            str(item)
            for item in response.get(
                "labelIds",
                [],
            )
        )

        body = ""
        body_truncated = False
        if include_body:
            body, body_truncated = _extract_body(
                payload,
                max_characters=(
                    max_body_characters
                ),
            )

        return {
            "id": response.get("id"),
            "thread_id": response.get(
                "threadId"
            ),
            "history_id": response.get(
                "historyId"
            ),
            "internal_date": _internal_datetime(
                response.get("internalDate")
            ),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "cc": headers.get("cc", ""),
            "subject": (
                headers.get("subject")
                or "(제목 없음)"
            ),
            "date_header": headers.get(
                "date",
                "",
            ),
            "message_id_header": headers.get(
                "message-id",
                "",
            ),
            "snippet": str(
                response.get("snippet", "")
            ).strip(),
            "label_ids": labels,
            "unread": "UNREAD" in labels,
            "important": "IMPORTANT" in labels,
            "starred": "STARRED" in labels,
            "body": body,
            "body_truncated": body_truncated,
        }

    def get_message(
        self,
        *,
        message_id: str,
        include_body: bool = True,
        max_body_characters: int | None = None,
    ) -> dict[str, Any]:
        return self._get_message(
            message_id,
            include_body=include_body,
            max_body_characters=(
                max_body_characters
                or self.config.max_body_characters
            ),
        )

    def list_messages(
        self,
        *,
        query: str = "",
        max_results: int | None = None,
        include_spam_trash: bool = False,
        include_body: bool = False,
        max_body_characters: int | None = None,
    ) -> dict[str, Any]:
        limit = (
            max_results
            if max_results is not None
            else self.config.max_results
        )
        if not 1 <= limit <= 500:
            raise GmailError(
                "max_results must be between 1 and 500."
            )

        response = (
            self._api()
            .users()
            .messages()
            .list(
                userId=self.config.user_id,
                q=query.strip() or None,
                maxResults=limit,
                includeSpamTrash=include_spam_trash,
            )
            .execute()
        )

        messages = [
            self._get_message(
                str(item["id"]),
                include_body=include_body,
                max_body_characters=(
                    max_body_characters
                    or self.config.max_body_characters
                ),
            )
            for item in response.get(
                "messages",
                [],
            )
            if item.get("id")
        ]
        return {
            "query": query,
            "result_size_estimate": response.get(
                "resultSizeEstimate",
                len(messages),
            ),
            "count": len(messages),
            "messages": messages,
        }

    def unread_count(
        self,
        *,
        query: str = "",
    ) -> dict[str, Any]:
        full_query = "is:unread"
        if query.strip():
            full_query += f" ({query.strip()})"

        response = (
            self._api()
            .users()
            .messages()
            .list(
                userId=self.config.user_id,
                q=full_query,
                maxResults=1,
                includeSpamTrash=False,
            )
            .execute()
        )
        return {
            "query": full_query,
            "unread_count_estimate": int(
                response.get(
                    "resultSizeEstimate",
                    0,
                )
            ),
        }

    def list_labels(self) -> tuple[
        dict[str, Any],
        ...,
    ]:
        response = (
            self._api()
            .users()
            .labels()
            .list(
                userId=self.config.user_id
            )
            .execute()
        )
        return tuple(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
            }
            for item in response.get(
                "labels",
                [],
            )
        )

    def close(self) -> None:
        self._service = None
        self._credentials = None
