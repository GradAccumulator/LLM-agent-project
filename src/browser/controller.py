from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_ALLOWED_KEYS = {
    "Enter",
    "Escape",
    "Tab",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "PageUp",
    "PageDown",
    "Home",
    "End",
}

_SENSITIVE_CLICK_TERMS = {
    "구매",
    "결제",
    "송금",
    "이체",
    "삭제",
    "탈퇴",
    "주문",
    "예약 확정",
    "보내기",
    "구독 취소",
    "buy",
    "purchase",
    "pay",
    "checkout",
    "transfer",
    "delete",
    "remove account",
    "send",
    "confirm order",
}

_SENSITIVE_FIELD_TERMS = {
    "비밀번호",
    "패스워드",
    "카드",
    "주민번호",
    "보안코드",
    "인증번호",
    "계좌",
    "password",
    "card number",
    "credit card",
    "cvv",
    "cvc",
    "social security",
    "security code",
    "bank account",
}


@dataclass(frozen=True, slots=True)
class BrowserAutomationConfig:
    enabled: bool = True
    headless: bool = False
    profile_directory: Path = Path("browser_profile")
    navigation_timeout_seconds: float = 20.0
    action_timeout_seconds: float = 10.0
    max_page_text_characters: int = 12_000

    def __post_init__(self) -> None:
        if self.navigation_timeout_seconds <= 0:
            raise ValueError(
                "navigation_timeout_seconds must be positive."
            )
        if self.action_timeout_seconds <= 0:
            raise ValueError(
                "action_timeout_seconds must be positive."
            )
        if self.max_page_text_characters <= 0:
            raise ValueError(
                "max_page_text_characters must be positive."
            )


def validate_browser_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise ValueError("URL must not be empty.")
    if len(value) > 2_048:
        raise ValueError("URL must not exceed 2048 characters.")

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("URL must contain a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials must not be embedded in URLs.")
    return value


def validate_click_text(text: str) -> str:
    value = text.strip()
    if not value:
        raise ValueError("Click text must not be empty.")
    if len(value) > 200:
        raise ValueError("Click text must not exceed 200 characters.")

    lowered = value.casefold()
    if any(term in lowered for term in _SENSITIVE_CLICK_TERMS):
        raise ValueError(
            "Sensitive or consequential browser clicks are blocked."
        )
    return value


def validate_field(name: str, value: str) -> tuple[str, str]:
    field_name = name.strip()
    field_value = value.strip()
    if not field_name:
        raise ValueError("Field name must not be empty.")
    if len(field_name) > 200:
        raise ValueError("Field name must not exceed 200 characters.")
    if len(field_value) > 1_000:
        raise ValueError("Field value must not exceed 1000 characters.")

    lowered = field_name.casefold()
    if any(term in lowered for term in _SENSITIVE_FIELD_TERMS):
        raise ValueError(
            "Password, payment, identity, and banking fields are blocked."
        )
    return field_name, field_value


class BrowserController:
    """Lazy, stateful Playwright Chromium controller."""

    def __init__(self, config: BrowserAutomationConfig) -> None:
        self.config = config
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None

    @property
    def started(self) -> bool:
        return self._context is not None

    def _require_enabled(self) -> None:
        if not self.config.enabled:
            raise RuntimeError("Browser automation is disabled.")

    def _ensure_page(self) -> Any:
        self._require_enabled()
        if self._page is not None and not self._page.is_closed():
            return self._page

        try:
            sync_api = importlib.import_module("playwright.sync_api")
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run "
                "`python -m pip install -r requirements.txt` and then "
                "`python -m playwright install chromium`."
            ) from exc

        try:
            self.config.profile_directory.mkdir(
                parents=True,
                exist_ok=True,
            )
            self._playwright = sync_api.sync_playwright().start()
            self._context = (
                self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(
                        self.config.profile_directory.resolve()
                    ),
                    headless=self.config.headless,
                    accept_downloads=False,
                    no_viewport=True,
                )
            )
            self._context.set_default_timeout(
                self.config.action_timeout_seconds * 1_000
            )
            self._context.set_default_navigation_timeout(
                self.config.navigation_timeout_seconds * 1_000
            )
            self._page = (
                self._context.pages[0]
                if self._context.pages
                else self._context.new_page()
            )
            return self._page
        except Exception as exc:
            self.close()
            message = str(exc).strip()
            if "Executable doesn't exist" in message:
                raise RuntimeError(
                    "Playwright Chromium is not installed. Run "
                    "`python -m playwright install chromium`."
                ) from exc
            raise RuntimeError(
                f"Could not start Playwright Chromium: "
                f"{message or type(exc).__name__}"
            ) from exc

    def open_page(self, url: str) -> dict[str, Any]:
        page = self._ensure_page()
        target = validate_browser_url(url)
        try:
            response = page.goto(
                target,
                wait_until="domcontentloaded",
            )
        except Exception as exc:
            raise RuntimeError(
                f"Browser navigation failed: {exc}"
            ) from exc

        return {
            "url": page.url,
            "title": page.title(),
            "status": (
                response.status if response is not None else None
            ),
        }

    def get_page_info(self, include_text: bool) -> dict[str, Any]:
        page = self._ensure_page()
        result: dict[str, Any] = {
            "url": page.url,
            "title": page.title(),
        }
        if include_text:
            try:
                text = page.locator("body").inner_text()
            except Exception as exc:
                raise RuntimeError(
                    f"Could not read page text: {exc}"
                ) from exc

            normalized = " ".join(text.split())
            limit = self.config.max_page_text_characters
            result["text"] = normalized[:limit]
            result["text_truncated"] = len(normalized) > limit
            result["text_characters"] = len(normalized)
        return result

    def list_elements(
        self,
        kind: str,
        limit: int,
    ) -> dict[str, Any]:
        page = self._ensure_page()
        if kind not in {"all", "link", "button", "textbox"}:
            raise ValueError(f"Unsupported element kind: {kind}")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50.")

        selectors = {
            "all": (
                "a:visible, button:visible, input:visible, "
                "textarea:visible, [contenteditable='true']:visible"
            ),
            "link": "a:visible",
            "button": "button:visible, input[type='button']:visible, input[type='submit']:visible",
            "textbox": "input:visible, textarea:visible, [contenteditable='true']:visible",
        }
        locator = page.locator(selectors[kind])
        count = min(locator.count(), limit)
        elements: list[dict[str, Any]] = []
        for index in range(count):
            item = locator.nth(index)
            try:
                tag = item.evaluate("element => element.tagName.toLowerCase()")
                label = (
                    item.get_attribute("aria-label")
                    or item.get_attribute("placeholder")
                    or item.get_attribute("title")
                    or item.inner_text()
                    or item.get_attribute("value")
                    or ""
                )
                label = " ".join(str(label).split())[:200]
                href = item.get_attribute("href") if tag == "a" else None
                elements.append(
                    {
                        "index": index,
                        "tag": tag,
                        "label": label,
                        "href": href,
                    }
                )
            except Exception:
                continue

        return {
            "kind": kind,
            "count": len(elements),
            "elements": elements,
        }

    def click_text(self, text: str, exact: bool) -> dict[str, Any]:
        page = self._ensure_page()
        target = validate_click_text(text)
        try:
            locator = page.get_by_text(
                target,
                exact=exact,
            ).first
            locator.click()
        except Exception as exc:
            raise RuntimeError(
                f"Could not click visible text '{target}': {exc}"
            ) from exc

        return {
            "clicked_text": target,
            "exact": exact,
            "url": page.url,
            "title": page.title(),
        }

    def fill_field(
        self,
        method: str,
        name: str,
        value: str,
    ) -> dict[str, Any]:
        page = self._ensure_page()
        field_name, field_value = validate_field(name, value)
        if method == "label":
            locator = page.get_by_label(field_name).first
        elif method == "placeholder":
            locator = page.get_by_placeholder(field_name).first
        else:
            raise ValueError(
                "method must be label or placeholder."
            )

        try:
            locator.fill(field_value)
        except Exception as exc:
            raise RuntimeError(
                f"Could not fill browser field '{field_name}': {exc}"
            ) from exc

        return {
            "method": method,
            "field": field_name,
            "characters": len(field_value),
            "url": page.url,
        }

    def press_key(self, key: str) -> dict[str, Any]:
        page = self._ensure_page()
        if key not in _ALLOWED_KEYS:
            raise ValueError(
                "Unsupported browser key. Allowed: "
                + ", ".join(sorted(_ALLOWED_KEYS))
            )
        try:
            page.keyboard.press(key)
        except Exception as exc:
            raise RuntimeError(
                f"Could not press browser key {key}: {exc}"
            ) from exc
        return {"key": key, "url": page.url}

    def go_back(self) -> dict[str, Any]:
        page = self._ensure_page()
        try:
            response = page.go_back(wait_until="domcontentloaded")
        except Exception as exc:
            raise RuntimeError(
                f"Browser back navigation failed: {exc}"
            ) from exc
        return {
            "url": page.url,
            "title": page.title(),
            "navigated": response is not None,
        }

    def close(self) -> dict[str, Any]:
        was_started = self.started
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._page = None
        self._context = None
        self._playwright = None
        return {
            "closed": was_started,
            "message": (
                "Playwright browser was closed."
                if was_started
                else "Playwright browser was not running."
            ),
        }
