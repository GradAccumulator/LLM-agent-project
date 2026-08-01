from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import re
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


_OFFICIAL_CHANNELS = {
    "msedge",
    "msedge-beta",
    "msedge-dev",
    "msedge-canary",
    "chrome",
    "chrome-beta",
    "chrome-dev",
    "chrome-canary",
}

_BROWSER_SELECTIONS = _OFFICIAL_CHANNELS | {
    "chromium",
    "custom",
}

_BROWSER_LABELS = {
    "msedge": "Microsoft Edge",
    "msedge-beta": "Microsoft Edge Beta",
    "msedge-dev": "Microsoft Edge Dev",
    "msedge-canary": "Microsoft Edge Canary",
    "chrome": "Google Chrome",
    "chrome-beta": "Google Chrome Beta",
    "chrome-dev": "Google Chrome Dev",
    "chrome-canary": "Google Chrome Canary",
    "chromium": "Playwright Chromium",
    "custom": "Custom Chromium-based browser",
}


@dataclass(frozen=True, slots=True)
class BrowserInstallation:
    selection: str
    name: str
    executable_path: Path
    config_mode: str

    def as_dict(self) -> dict[str, str]:
        return {
            "selection": self.selection,
            "name": self.name,
            "executable_path": str(self.executable_path),
            "config_mode": self.config_mode,
        }


def _existing_paths(
    candidates: list[tuple[str, str, Path, str]],
) -> tuple[BrowserInstallation, ...]:
    seen: set[str] = set()
    installations: list[BrowserInstallation] = []

    for selection, name, path, config_mode in candidates:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).casefold()
        if key in seen or not resolved.is_file():
            continue
        seen.add(key)
        installations.append(
            BrowserInstallation(
                selection=selection,
                name=name,
                executable_path=resolved,
                config_mode=config_mode,
            )
        )

    return tuple(installations)


def detect_installed_browsers() -> tuple[BrowserInstallation, ...]:
    """Detect common Windows Chromium-based browser installations."""

    if os.name != "nt":
        return ()

    program_files = Path(
        os.environ.get("ProgramFiles", r"C:\Program Files")
    )
    program_files_x86 = Path(
        os.environ.get(
            "ProgramFiles(x86)",
            r"C:\Program Files (x86)",
        )
    )
    local_app_data = Path(
        os.environ.get("LOCALAPPDATA", "")
    )

    candidates: list[tuple[str, str, Path, str]] = [
        (
            "msedge",
            "Microsoft Edge",
            program_files_x86
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
            'browser = "msedge"',
        ),
        (
            "msedge",
            "Microsoft Edge",
            program_files
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
            'browser = "msedge"',
        ),
        (
            "msedge",
            "Microsoft Edge",
            local_app_data
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
            'browser = "msedge"',
        ),
        (
            "chrome",
            "Google Chrome",
            program_files
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            'browser = "chrome"',
        ),
        (
            "chrome",
            "Google Chrome",
            program_files_x86
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            'browser = "chrome"',
        ),
        (
            "chrome",
            "Google Chrome",
            local_app_data
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            'browser = "chrome"',
        ),
        (
            "custom",
            "Brave",
            program_files
            / "BraveSoftware"
            / "Brave-Browser"
            / "Application"
            / "brave.exe",
            'browser = "custom"',
        ),
        (
            "custom",
            "Brave",
            local_app_data
            / "BraveSoftware"
            / "Brave-Browser"
            / "Application"
            / "brave.exe",
            'browser = "custom"',
        ),
        (
            "custom",
            "Vivaldi",
            local_app_data
            / "Vivaldi"
            / "Application"
            / "vivaldi.exe",
            'browser = "custom"',
        ),
        (
            "custom",
            "Opera",
            local_app_data
            / "Programs"
            / "Opera"
            / "opera.exe",
            'browser = "custom"',
        ),
    ]
    return _existing_paths(candidates)


def format_installed_browsers() -> str:
    installations = detect_installed_browsers()
    if not installations:
        return (
            "No supported installed browsers were detected automatically.\n"
            "Edge/Chrome may still work through their Playwright channel, "
            "or configure a Chromium-based browser with executable_path."
        )

    lines = ["Detected browsers:"]
    for item in installations:
        lines.append(
            f"- {item.name}: {item.executable_path}"
        )
        lines.append(f"  {item.config_mode}")
        if item.selection == "custom":
            lines.append(
                "  executable_path = "
                + repr(str(item.executable_path))
            )
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class BrowserAutomationConfig:
    enabled: bool = True
    headless: bool = False
    browser: str = "msedge"
    executable_path: Path | None = None
    profile_directory: Path = Path("browser_profiles")
    navigation_timeout_seconds: float = 20.0
    action_timeout_seconds: float = 10.0
    max_page_text_characters: int = 12_000

    def __post_init__(self) -> None:
        normalized = self.browser.strip().casefold()
        object.__setattr__(self, "browser", normalized)

        if normalized not in _BROWSER_SELECTIONS:
            choices = ", ".join(sorted(_BROWSER_SELECTIONS))
            raise ValueError(
                f"Unsupported browser selection: {normalized}. "
                f"Allowed: {choices}."
            )
        if normalized == "custom" and self.executable_path is None:
            raise ValueError(
                "browser='custom' requires executable_path."
            )
        if (
            normalized != "custom"
            and self.executable_path is not None
        ):
            raise ValueError(
                "executable_path is only valid when browser='custom'."
            )
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

    @property
    def display_name(self) -> str:
        if self.browser != "custom":
            return _BROWSER_LABELS[self.browser]
        assert self.executable_path is not None
        return self.executable_path.stem or _BROWSER_LABELS["custom"]

    @property
    def profile_key(self) -> str:
        if self.browser != "custom":
            return self.browser
        assert self.executable_path is not None
        stem = self.executable_path.stem.casefold()
        safe = re.sub(r"[^a-z0-9_-]+", "-", stem).strip("-")
        return f"custom-{safe or 'browser'}"

    @property
    def effective_profile_directory(self) -> Path:
        # Keep Edge, Chrome, and custom-browser cookies separate.
        return self.profile_directory / self.profile_key

    def launch_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "headless": self.headless,
            "accept_downloads": False,
            "no_viewport": True,
        }

        if self.browser in _OFFICIAL_CHANNELS:
            options["channel"] = self.browser
        elif self.browser == "custom":
            assert self.executable_path is not None
            path = self.executable_path.expanduser()
            if not path.is_file():
                raise RuntimeError(
                    f"Custom browser executable does not exist: {path}"
                )
            options["executable_path"] = str(path.resolve())
        # browser='chromium' deliberately uses Playwright's bundled build.

        return options


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
    """Lazy controller for the configured installed browser."""

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
            sync_api = importlib.import_module(
                "playwright.sync_api"
            )
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        try:
            profile = (
                self.config.effective_profile_directory
                .expanduser()
                .resolve()
            )
            profile.mkdir(parents=True, exist_ok=True)

            self._playwright = (
                sync_api.sync_playwright().start()
            )
            launch_options = self.config.launch_options()
            self._context = (
                self._playwright.chromium
                .launch_persistent_context(
                    user_data_dir=str(profile),
                    **launch_options,
                )
            )
            self._context.set_default_timeout(
                self.config.action_timeout_seconds * 1_000
            )
            self._context.set_default_navigation_timeout(
                self.config.navigation_timeout_seconds
                * 1_000
            )
            self._page = (
                self._context.pages[0]
                if self._context.pages
                else self._context.new_page()
            )
            return self._page
        except Exception as exc:
            selected = self.config.browser
            display_name = self.config.display_name
            self.close()
            message = str(exc).strip()

            if selected == "chromium" and (
                "Executable doesn't exist" in message
                or "executable doesn't exist" in message.casefold()
            ):
                raise RuntimeError(
                    "Playwright Chromium is not installed. Run "
                    "`python -m playwright install chromium`, "
                    "or set browser='msedge'/'chrome'."
                ) from exc

            if selected in _OFFICIAL_CHANNELS:
                raise RuntimeError(
                    f"Could not start installed {display_name} "
                    f"(channel={selected}). Make sure it is installed "
                    "and not blocked by an enterprise policy. "
                    f"Details: {message or type(exc).__name__}"
                ) from exc

            if selected == "custom":
                raise RuntimeError(
                    "Could not start the custom Chromium-based browser. "
                    "Playwright does not guarantee compatibility with "
                    "arbitrary executables. "
                    f"Details: {message or type(exc).__name__}"
                ) from exc

            raise RuntimeError(
                f"Could not start selected browser '{selected}': "
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
            "browser": self.config.browser,
            "browser_name": self.config.display_name,
            "url": page.url,
            "title": page.title(),
            "status": (
                response.status if response is not None else None
            ),
        }

    def get_page_info(self, include_text: bool) -> dict[str, Any]:
        page = self._ensure_page()
        result: dict[str, Any] = {
            "browser": self.config.browser,
            "browser_name": self.config.display_name,
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
                f"{self.config.display_name} automation window was closed."
                if was_started
                else "The automation browser was not running."
            ),
        }
