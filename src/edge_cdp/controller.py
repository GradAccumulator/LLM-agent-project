from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import importlib
import re
from pathlib import Path
import secrets
from time import monotonic
from typing import Any, Callable
from urllib.parse import urlparse

from .launcher import (
    ManagedEdgeConfig,
    ManagedEdgeError,
    ManagedEdgeLauncher,
)


class EdgeCdpError(RuntimeError):
    pass


class StaleTabReferenceError(EdgeCdpError):
    pass


class StaleElementReferenceError(EdgeCdpError):
    pass


@dataclass(frozen=True, slots=True)
class EdgeCdpConfig:
    enabled: bool = True
    endpoint_url: str = "http://127.0.0.1:9222"
    connect_timeout_seconds: float = 5.0
    action_timeout_seconds: float = 10.0
    max_page_text_characters: int = 16_000
    tab_ref_ttl_seconds: float = 300.0
    element_ref_ttl_seconds: float = 180.0
    max_elements: int = 100
    max_fill_characters: int = 2_000
    screenshot_directory: Path = Path("screenshots")
    allow_tab_close: bool = True
    allow_dom_actions: bool = True
    auto_start: bool = True
    executable_path: Path | None = None
    profile_directory: Path = Path(
        "data/edge_profile"
    )
    startup_timeout_seconds: float = 15.0
    startup_poll_seconds: float = 0.2
    startup_url: str | None = None
    restore_last_session: bool = True
    keep_running_on_exit: bool = True

    def __post_init__(self) -> None:
        _validate_local_endpoint(self.endpoint_url)
        if self.connect_timeout_seconds <= 0:
            raise ValueError(
                "connect_timeout_seconds must be positive."
            )
        if self.action_timeout_seconds <= 0:
            raise ValueError(
                "action_timeout_seconds must be positive."
            )
        if self.max_page_text_characters <= 0:
            raise ValueError(
                "max_page_text_characters must be positive."
            )
        if self.tab_ref_ttl_seconds <= 0:
            raise ValueError(
                "tab_ref_ttl_seconds must be positive."
            )
        if self.element_ref_ttl_seconds <= 0:
            raise ValueError(
                "element_ref_ttl_seconds must be positive."
            )
        if not 1 <= self.max_elements <= 500:
            raise ValueError(
                "max_elements must be between 1 and 500."
            )
        if not 1 <= self.max_fill_characters <= 20_000:
            raise ValueError(
                "max_fill_characters must be between 1 and 20000."
            )
        if self.startup_timeout_seconds <= 0:
            raise ValueError(
                "startup_timeout_seconds must be positive."
            )
        if not 0.05 <= self.startup_poll_seconds <= 5:
            raise ValueError(
                "startup_poll_seconds must be between "
                "0.05 and 5 seconds."
            )


@dataclass(slots=True)
class _TabEntry:
    ref: str
    page: Any
    created_at: float
    expires_at: float


@dataclass(slots=True)
class _ElementEntry:
    ref: str
    tab_ref: str
    page: Any
    locator: Any
    created_at: float
    expires_at: float
    fingerprint: tuple[str, ...]
    metadata: dict[str, Any]


_ELEMENT_SELECTORS = {
    "all": (
        "a:visible, button:visible, input:visible, textarea:visible, "
        "[role='button']:visible, [contenteditable='true']:visible"
    ),
    "link": "a:visible",
    "button": (
        "button:visible, input[type='button']:visible, "
        "input[type='submit']:visible, [role='button']:visible"
    ),
    "textbox": (
        "input:visible, textarea:visible, "
        "[contenteditable='true']:visible"
    ),
}

_BLOCKED_ACTION_TERMS = {
    "로그인", "로그아웃", "제출", "전송", "보내기", "게시",
    "업로드", "구매", "결제", "주문", "예약", "확정", "삭제",
    "탈퇴", "송금", "이체", "구독",
    "login", "log in", "sign in", "sign out", "submit", "send",
    "publish", "post", "upload", "buy", "purchase", "checkout",
    "pay", "payment", "order", "reserve", "confirm", "delete",
    "remove", "transfer", "unsubscribe",
}

_BLOCKED_FIELD_TERMS = {
    "비밀번호", "패스워드", "카드", "보안코드", "인증번호", "주민번호",
    "계좌", "송금", "로그인",
    "password", "passcode", "card number", "credit card", "cvv",
    "cvc", "security code", "one-time code", "otp", "social security",
    "bank account", "routing number", "login", "sign in",
}

_BLOCKED_URL_TERMS = {
    "/login", "/signin", "/sign-in", "/auth", "/checkout",
    "/payment", "/pay", "/order", "/transfer", "/delete",
    "/unsubscribe",
}


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _element_kind(metadata: dict[str, Any]) -> str:
    tag = _normalized(metadata.get("tag"))
    role = _normalized(metadata.get("role"))
    input_type = _normalized(metadata.get("type"))
    if tag == "a":
        return "link"
    if (
        tag == "button"
        or role == "button"
        or input_type in {"button", "submit", "reset", "image"}
    ):
        return "button"
    if (
        tag in {"input", "textarea"}
        or metadata.get("contenteditable") is True
    ):
        return "textbox"
    return "other"


def _element_fingerprint(metadata: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        _normalized(metadata.get(key))
        for key in (
            "tag", "role", "type", "label", "name", "placeholder",
            "href", "form_action", "dom_path",
        )
    )


def _safety_for_element(metadata: dict[str, Any]) -> dict[str, Any]:
    kind = _element_kind(metadata)
    metadata["kind"] = kind
    if metadata.get("disabled") is True:
        return {
            "allowed": False,
            "category": "disabled",
            "reason": "비활성화된 요소입니다.",
        }

    combined = " ".join(
        _normalized(metadata.get(key))
        for key in (
            "label", "text", "title", "name", "placeholder",
            "href", "form_action", "autocomplete",
        )
    )

    if kind in {"link", "button"}:
        input_type = _normalized(metadata.get("type"))
        if input_type == "submit" or metadata.get("form_submits") is True:
            return {
                "allowed": False,
                "category": "submission",
                "reason": "폼 제출 요소는 자동 실행하지 않습니다.",
            }
        if any(term in combined for term in _BLOCKED_ACTION_TERMS):
            return {
                "allowed": False,
                "category": "sensitive_action",
                "reason": "로그인·전송·구매·결제·삭제 등의 동작은 차단됩니다.",
            }
        href = _normalized(metadata.get("href"))
        if any(term in href for term in _BLOCKED_URL_TERMS):
            return {
                "allowed": False,
                "category": "sensitive_navigation",
                "reason": "민감한 로그인·결제·계정 경로로의 자동 이동은 차단됩니다.",
            }
        return {
            "allowed": True,
            "category": "low_risk_navigation",
            "reason": "저위험 링크 또는 버튼으로 분류됐습니다.",
        }

    if kind == "textbox":
        input_type = _normalized(metadata.get("type"))
        autocomplete = _normalized(metadata.get("autocomplete"))
        if input_type in {"password", "hidden", "file"}:
            return {
                "allowed": False,
                "category": "sensitive_field",
                "reason": "비밀번호·숨김·파일 입력 필드는 차단됩니다.",
            }
        if (
            "password" in autocomplete
            or autocomplete.startswith("cc-")
            or autocomplete == "one-time-code"
        ):
            return {
                "allowed": False,
                "category": "sensitive_field",
                "reason": "인증 또는 결제 자동완성 필드는 차단됩니다.",
            }
        if any(term in combined for term in _BLOCKED_FIELD_TERMS):
            return {
                "allowed": False,
                "category": "sensitive_field",
                "reason": "비밀번호·결제·신원·계좌·로그인 필드는 차단됩니다.",
            }
        form_action = _normalized(metadata.get("form_action"))
        if any(term in form_action for term in _BLOCKED_URL_TERMS):
            return {
                "allowed": False,
                "category": "sensitive_form",
                "reason": "로그인·결제 등 민감한 폼 입력은 차단됩니다.",
            }
        return {
            "allowed": True,
            "category": "draft_text",
            "reason": "제출하지 않는 일반 텍스트 초안 입력으로 분류됐습니다.",
        }

    return {
        "allowed": False,
        "category": "unsupported",
        "reason": "지원되는 링크·버튼·텍스트 입력 요소가 아닙니다.",
    }


def _validate_local_endpoint(value: str) -> str:
    endpoint = value.strip()
    parsed = urlparse(endpoint)
    if parsed.scheme not in {
        "http",
        "https",
        "ws",
        "wss",
    }:
        raise ValueError(
            "Edge CDP endpoint must use http, https, ws, or wss."
        )
    hostname = (
        parsed.hostname or ""
    ).casefold()
    if hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError(
            "Edge CDP is restricted to a local endpoint."
        )
    if parsed.username or parsed.password:
        raise ValueError(
            "Credentials must not be embedded in the CDP endpoint."
        )
    return endpoint


def _safe_title(page: Any) -> str:
    try:
        return " ".join(
            str(page.title() or "").split()
        )[:300]
    except Exception:
        return ""


def _safe_url(page: Any) -> str:
    try:
        return str(page.url or "")[:4_096]
    except Exception:
        return ""


def _is_internal_url(url: str) -> bool:
    scheme = urlparse(url).scheme.casefold()
    return scheme in {
        "edge",
        "chrome",
        "devtools",
        "about",
    }


class EdgeCdpController:
    """Read-mostly bridge to an existing local Edge CDP session."""

    def __init__(
        self,
        config: EdgeCdpConfig = EdgeCdpConfig(),
        *,
        connector: (
            Callable[[str, float], tuple[Any, Any]]
            | None
        ) = None,
        clock: Callable[[], float] = monotonic,
        managed_launcher: (
            ManagedEdgeLauncher | None
        ) = None,
    ) -> None:
        self.config = config
        self._connector = connector
        self._clock = clock
        self._managed_launcher_explicit = (
            managed_launcher is not None
        )
        self._managed_launcher = (
            managed_launcher
            or ManagedEdgeLauncher(
                ManagedEdgeConfig(
                    endpoint_url=(
                        config.endpoint_url
                    ),
                    auto_start=(
                        config.auto_start
                    ),
                    executable_path=(
                        config.executable_path
                    ),
                    profile_directory=(
                        config.profile_directory
                    ),
                    startup_timeout_seconds=(
                        config
                        .startup_timeout_seconds
                    ),
                    startup_poll_seconds=(
                        config
                        .startup_poll_seconds
                    ),
                    startup_url=(
                        config.startup_url
                    ),
                    restore_last_session=(
                        config
                        .restore_last_session
                    ),
                    keep_running_on_exit=(
                        config
                        .keep_running_on_exit
                    ),
                )
            )
        )
        self._last_managed_launch: (
            dict[str, Any] | None
        ) = None
        self._active_endpoint_url = (
            config.endpoint_url
        )
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._selected_ref: str | None = None
        self._tabs: dict[str, _TabEntry] = {}
        self._page_refs: dict[int, str] = {}
        self._elements: dict[str, _ElementEntry] = {}

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def allow_tab_close(self) -> bool:
        return self.config.allow_tab_close

    @property
    def allow_dom_actions(self) -> bool:
        return self.config.allow_dom_actions

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise EdgeCdpError(
                "Edge CDP bridge is disabled."
            )

    def _default_connector(
        self,
        endpoint: str,
        timeout_seconds: float,
    ) -> tuple[Any, Any]:
        try:
            sync_api = importlib.import_module(
                "playwright.sync_api"
            )
        except ImportError as exc:
            raise EdgeCdpError(
                "Playwright is missing. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        playwright = (
            sync_api.sync_playwright().start()
        )
        try:
            browser = (
                playwright.chromium
                .connect_over_cdp(
                    endpoint,
                    timeout=(
                        timeout_seconds * 1_000
                    ),
                )
            )
        except Exception:
            try:
                playwright.stop()
            except Exception:
                pass
            raise
        return playwright, browser

    def start_managed_edge(
        self,
    ) -> dict[str, Any]:
        self._require_enabled()
        try:
            self._last_managed_launch = (
                self._managed_launcher
                .ensure_running()
            )
        except ManagedEdgeError as exc:
            raise EdgeCdpError(
                str(exc)
            ) from exc
        self._active_endpoint_url = str(
            self._last_managed_launch.get(
                "endpoint_url"
            )
            or self.config.endpoint_url
        )
        return dict(
            self._last_managed_launch
        )

    def managed_edge_status(
        self,
    ) -> dict[str, Any]:
        return (
            self._managed_launcher
            .status()
        )

    def _ensure_connection(self) -> Any:
        self._require_enabled()
        if self._browser is not None:
            try:
                connected = bool(
                    self._browser.is_connected()
                )
            except Exception:
                connected = True
            if connected:
                return self._browser
            self._browser = None

        should_auto_start = (
            self.config.auto_start
            and (
                self._connector is None
                or self._managed_launcher_explicit
            )
        )
        if should_auto_start:
            self.start_managed_edge()

        connector = (
            self._connector
            or self._default_connector
        )
        try:
            (
                self._playwright,
                self._browser,
            ) = connector(
                self._active_endpoint_url,
                self.config.connect_timeout_seconds,
            )
        except Exception as exc:
            self._playwright = None
            self._browser = None
            raise EdgeCdpError(
                "Could not connect to Microsoft Edge CDP at "
                f"{self._active_endpoint_url}. Start Edge with "
                "remote debugging enabled, then retry. "
                f"Details: {str(exc).strip() or type(exc).__name__}"
            ) from exc
        return self._browser

    def _all_pages(self) -> list[Any]:
        browser = self._ensure_connection()
        pages: list[Any] = []
        try:
            contexts = list(
                browser.contexts
            )
        except Exception as exc:
            raise EdgeCdpError(
                "Could not enumerate Edge browser contexts."
            ) from exc

        for context in contexts:
            try:
                context.set_default_timeout(
                    self.config
                    .action_timeout_seconds
                    * 1_000
                )
            except Exception:
                pass
            try:
                candidates = list(
                    context.pages
                )
            except Exception:
                continue
            for page in candidates:
                try:
                    if page.is_closed():
                        continue
                except Exception:
                    pass
                pages.append(page)
        return pages

    def _purge_elements(self) -> None:
        now = self._clock()
        stale: list[str] = []
        for ref, entry in self._elements.items():
            if now >= entry.expires_at:
                stale.append(ref)
                continue
            try:
                if entry.page.is_closed():
                    stale.append(ref)
            except Exception:
                pass
        for ref in stale:
            self._elements.pop(ref, None)

    def _clear_elements_for_tab(self, tab_ref: str) -> None:
        for ref in [
            ref
            for ref, entry in self._elements.items()
            if entry.tab_ref == tab_ref
        ]:
            self._elements.pop(ref, None)

    def _purge(self) -> None:
        self._purge_elements()
        now = self._clock()
        stale: list[str] = []
        for ref, entry in self._tabs.items():
            if now >= entry.expires_at:
                stale.append(ref)
                continue
            try:
                if entry.page.is_closed():
                    stale.append(ref)
            except Exception:
                pass
        for ref in stale:
            entry = self._tabs.pop(
                ref,
                None,
            )
            if entry is not None:
                self._page_refs.pop(
                    id(entry.page),
                    None,
                )
            self._clear_elements_for_tab(ref)
            if self._selected_ref == ref:
                self._selected_ref = None

    def _ref_for_page(self, page: Any) -> str:
        self._purge()
        page_key = id(page)
        existing = self._page_refs.get(
            page_key
        )
        if existing in self._tabs:
            entry = self._tabs[existing]
            entry.expires_at = (
                self._clock()
                + self.config
                .tab_ref_ttl_seconds
            )
            return existing

        ref = (
            "edge_tab_"
            + secrets.token_hex(6)
        )
        now = self._clock()
        self._tabs[ref] = _TabEntry(
            ref=ref,
            page=page,
            created_at=now,
            expires_at=(
                now
                + self.config
                .tab_ref_ttl_seconds
            ),
        )
        self._page_refs[page_key] = ref
        return ref

    def _resolve(
        self,
        tab_ref: str,
    ) -> _TabEntry:
        self._purge()
        ref = tab_ref.strip()
        entry = self._tabs.get(ref)
        if entry is None:
            raise StaleTabReferenceError(
                "Edge tab reference is missing or expired. "
                "List the tabs again."
            )
        try:
            if entry.page.is_closed():
                raise StaleTabReferenceError(
                    "The Edge tab is already closed."
                )
        except StaleTabReferenceError:
            self._tabs.pop(ref, None)
            self._page_refs.pop(
                id(entry.page),
                None,
            )
            raise
        except Exception:
            pass
        return entry

    def _tab_record(
        self,
        page: Any,
        *,
        ref: str,
    ) -> dict[str, Any]:
        url = _safe_url(page)
        return {
            "tab_ref": ref,
            "title": _safe_title(page),
            "url": url,
            "selected": (
                ref == self._selected_ref
            ),
            "dom_readable": (
                bool(url)
                and not _is_internal_url(url)
            ),
        }

    def status(self) -> dict[str, Any]:
        try:
            pages = self._all_pages()
        except EdgeCdpError as exc:
            return {
                "enabled": self.enabled,
                "connected": False,
                "endpoint_url": (
                    self._active_endpoint_url
                ),
                "tab_count": 0,
                "error": str(exc),
                "managed_edge": (
                    self.managed_edge_status()
                ),
            }

        return {
            "enabled": self.enabled,
            "connected": True,
            "endpoint_url": (
                self._active_endpoint_url
            ),
            "tab_count": len(pages),
            "selected_tab_ref": (
                self._selected_ref
            ),
            "error": None,
            "managed_edge": (
                self.managed_edge_status()
            ),
        }

    def list_tabs(
        self,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 200:
            raise EdgeCdpError(
                "limit must be between 1 and 200."
            )

        pages = self._all_pages()
        tabs = [
            self._tab_record(
                page,
                ref=self._ref_for_page(
                    page
                ),
            )
            for page in pages[:limit]
        ]
        if (
            self._selected_ref is None
            and tabs
        ):
            self._selected_ref = (
                tabs[0]["tab_ref"]
            )
            tabs[0]["selected"] = True

        return {
            "endpoint_url": (
                self._active_endpoint_url
            ),
            "count": len(tabs),
            "tabs": tabs,
            "tab_ref_ttl_seconds": (
                self.config
                .tab_ref_ttl_seconds
            ),
        }

    def describe_tab(
        self,
        tab_ref: str,
    ) -> str:
        entry = self._resolve(tab_ref)
        title = _safe_title(
            entry.page
        ) or "제목 없는 탭"
        url = _safe_url(entry.page)
        host = (
            urlparse(url).hostname
            if url
            else None
        )
        suffix = (
            f" ({host})"
            if host
            else ""
        )
        return (
            f"'{title[:120]}' Edge 탭"
            f"{suffix}"
        )

    def select_tab(
        self,
        *,
        tab_ref: str,
    ) -> dict[str, Any]:
        entry = self._resolve(tab_ref)
        try:
            entry.page.bring_to_front()
        except Exception as exc:
            raise EdgeCdpError(
                "Could not bring the Edge tab to the front."
            ) from exc
        self._selected_ref = entry.ref
        return {
            "selected": True,
            "tab": self._tab_record(
                entry.page,
                ref=entry.ref,
            ),
            "message": (
                "Edge 탭을 앞으로 가져왔습니다."
            ),
        }

    def _selected_page(
        self,
        tab_ref: str | None,
    ) -> tuple[str, Any]:
        if tab_ref:
            entry = self._resolve(
                tab_ref
            )
            return entry.ref, entry.page

        if self._selected_ref:
            try:
                entry = self._resolve(
                    self._selected_ref
                )
                return entry.ref, entry.page
            except StaleTabReferenceError:
                self._selected_ref = None

        listing = self.list_tabs(
            limit=200
        )
        tabs = listing["tabs"]
        if not tabs:
            raise EdgeCdpError(
                "No attachable Edge tabs were found."
            )
        ref = str(
            tabs[0]["tab_ref"]
        )
        entry = self._resolve(ref)
        self._selected_ref = ref
        return ref, entry.page

    def get_page_info(
        self,
        *,
        tab_ref: str | None,
        include_text: bool,
    ) -> dict[str, Any]:
        ref, page = self._selected_page(
            tab_ref
        )
        url = _safe_url(page)
        result: dict[str, Any] = {
            "tab_ref": ref,
            "title": _safe_title(page),
            "url": url,
            "dom_readable": (
                bool(url)
                and not _is_internal_url(url)
            ),
        }

        if include_text:
            if _is_internal_url(url):
                raise EdgeCdpError(
                    "Edge internal pages do not expose normal DOM "
                    "text through this bridge."
                )
            try:
                text = (
                    page.locator("body")
                    .inner_text()
                )
            except Exception as exc:
                raise EdgeCdpError(
                    "Could not read the selected tab DOM text."
                ) from exc

            normalized = " ".join(
                str(text).split()
            )
            limit = (
                self.config
                .max_page_text_characters
            )
            result["text"] = (
                normalized[:limit]
            )
            result["text_truncated"] = (
                len(normalized) > limit
            )
            result["text_characters"] = (
                len(normalized)
            )
        return result

    def _element_metadata(
        self,
        locator: Any,
    ) -> dict[str, Any]:
        script = """
        element => {
          const form = element.closest ? element.closest('form') : null;
          const labels = element.labels ? Array.from(element.labels) : [];
          const labelText = labels.map(item => item.innerText || item.textContent || '').join(' ');
          const tag = (element.tagName || '').toLowerCase();
          const type = (element.getAttribute('type') || '').toLowerCase();
          const role = element.getAttribute('role') || '';
          const text = element.innerText || element.textContent || '';
          const label = element.getAttribute('aria-label') ||
            element.getAttribute('placeholder') ||
            element.getAttribute('title') || labelText || text ||
            element.getAttribute('value') || element.getAttribute('name') || '';
          const parts = [];
          let current = element;
          while (current && current.nodeType === 1 && parts.length < 8) {
            let part = (current.tagName || '').toLowerCase();
            if (current.id) {
              part += '#' + current.id;
              parts.unshift(part);
              break;
            }
            const parent = current.parentElement;
            if (parent) {
              const siblings = Array.from(parent.children).filter(
                item => item.tagName === current.tagName
              );
              if (siblings.length > 1) {
                part += ':nth-of-type(' + (siblings.indexOf(current) + 1) + ')';
              }
            }
            parts.unshift(part);
            current = parent;
          }
          const buttonLike = tag === 'button' || role === 'button' ||
            ['button', 'submit', 'reset', 'image'].includes(type);
          const formSubmits = Boolean(form && buttonLike &&
            (type === '' || type === 'submit'));
          return {
            tag,
            type,
            role,
            label: String(label || '').trim(),
            text: String(text || '').trim(),
            title: element.getAttribute('title') || '',
            name: element.getAttribute('name') || '',
            placeholder: element.getAttribute('placeholder') || '',
            href: element.href || element.getAttribute('href') || '',
            autocomplete: element.getAttribute('autocomplete') || '',
            contenteditable: Boolean(element.isContentEditable),
            disabled: Boolean(element.disabled || element.getAttribute('aria-disabled') === 'true'),
            form_action: form ? (form.action || form.getAttribute('action') || '') : '',
            form_method: form ? (form.method || form.getAttribute('method') || '') : '',
            form_submits: formSubmits,
            dom_path: parts.join(' > '),
          };
        }
        """
        try:
            raw = locator.evaluate(script)
        except Exception as exc:
            raise EdgeCdpError(
                "Could not inspect the Edge DOM element."
            ) from exc
        if not isinstance(raw, dict):
            raise EdgeCdpError(
                "Edge DOM inspection returned an invalid element record."
            )
        metadata = {
            key: value
            for key, value in raw.items()
            if key in {
                "tag", "type", "role", "label", "text", "title",
                "name", "placeholder", "href", "autocomplete",
                "contenteditable", "disabled", "form_action",
                "form_method", "form_submits", "dom_path",
            }
        }
        for key in (
            "label", "text", "title", "name", "placeholder", "href",
            "autocomplete", "form_action", "form_method", "dom_path",
        ):
            metadata[key] = " ".join(
                str(metadata.get(key) or "").split()
            )[:1_000]
        metadata["kind"] = _element_kind(metadata)
        metadata["safety"] = _safety_for_element(metadata)
        return metadata

    def _register_element(
        self,
        *,
        tab_ref: str,
        page: Any,
        locator: Any,
        metadata: dict[str, Any],
    ) -> str:
        ref = "edge_el_" + secrets.token_hex(6)
        now = self._clock()
        self._elements[ref] = _ElementEntry(
            ref=ref,
            tab_ref=tab_ref,
            page=page,
            locator=locator,
            created_at=now,
            expires_at=(
                now + self.config.element_ref_ttl_seconds
            ),
            fingerprint=_element_fingerprint(metadata),
            metadata=dict(metadata),
        )
        return ref

    def _public_element_record(
        self,
        entry: _ElementEntry,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = dict(metadata or entry.metadata)
        label = str(current.get("label") or current.get("text") or "")
        return {
            "element_ref": entry.ref,
            "tab_ref": entry.tab_ref,
            "kind": current.get("kind"),
            "tag": current.get("tag"),
            "type": current.get("type"),
            "role": current.get("role"),
            "label": label[:300],
            "href": str(current.get("href") or "")[:1_000] or None,
            "placeholder": str(current.get("placeholder") or "")[:300] or None,
            "disabled": bool(current.get("disabled")),
            "safety": current.get("safety"),
            "expires_in_seconds": self.config.element_ref_ttl_seconds,
        }

    def _resolve_element(
        self,
        element_ref: str,
    ) -> tuple[_ElementEntry, dict[str, Any]]:
        self._purge_elements()
        ref = element_ref.strip()
        entry = self._elements.get(ref)
        if entry is None:
            raise StaleElementReferenceError(
                "Edge element reference is missing or expired. "
                "List the page elements again."
            )
        try:
            if entry.page.is_closed():
                raise StaleElementReferenceError(
                    "The Edge tab containing this element is closed."
                )
        except StaleElementReferenceError:
            self._elements.pop(ref, None)
            raise
        except Exception:
            pass

        try:
            if int(entry.locator.count()) <= 0:
                raise StaleElementReferenceError(
                    "The Edge DOM element is no longer attached."
                )
        except StaleElementReferenceError:
            self._elements.pop(ref, None)
            raise
        except Exception:
            pass

        metadata = self._element_metadata(entry.locator)
        if _element_fingerprint(metadata) != entry.fingerprint:
            self._elements.pop(ref, None)
            raise StaleElementReferenceError(
                "The page changed and the Edge element reference no longer "
                "identifies the same element. List elements again."
            )
        entry.metadata = dict(metadata)
        entry.expires_at = (
            self._clock() + self.config.element_ref_ttl_seconds
        )
        return entry, metadata

    def list_elements(
        self,
        *,
        tab_ref: str | None,
        kind: str,
        limit: int,
    ) -> dict[str, Any]:
        if kind not in _ELEMENT_SELECTORS:
            raise EdgeCdpError(
                "kind must be all, link, button, or textbox."
            )
        if not 1 <= limit <= self.config.max_elements:
            raise EdgeCdpError(
                f"limit must be between 1 and {self.config.max_elements}."
            )
        effective_limit = limit

        resolved_tab_ref, page = self._selected_page(tab_ref)
        url = _safe_url(page)
        if _is_internal_url(url):
            raise EdgeCdpError(
                "Edge internal pages do not expose normal DOM elements "
                "through this bridge."
            )

        self._clear_elements_for_tab(resolved_tab_ref)
        try:
            locator = page.locator(_ELEMENT_SELECTORS[kind])
            count = min(int(locator.count()), effective_limit)
        except Exception as exc:
            raise EdgeCdpError(
                "Could not enumerate visible Edge DOM elements."
            ) from exc

        elements: list[dict[str, Any]] = []
        for index in range(count):
            item = locator.nth(index)
            try:
                metadata = self._element_metadata(item)
                ref = self._register_element(
                    tab_ref=resolved_tab_ref,
                    page=page,
                    locator=item,
                    metadata=metadata,
                )
                elements.append(
                    self._public_element_record(
                        self._elements[ref]
                    )
                )
            except EdgeCdpError:
                continue

        return {
            "tab_ref": resolved_tab_ref,
            "title": _safe_title(page),
            "url": url,
            "kind": kind,
            "count": len(elements),
            "elements": elements,
            "element_ref_ttl_seconds": self.config.element_ref_ttl_seconds,
            "message": (
                "요소의 safety.allowed가 true인 대상만 클릭하거나 "
                "일반 텍스트를 입력할 수 있습니다."
            ),
        }

    def get_element(
        self,
        *,
        element_ref: str,
    ) -> dict[str, Any]:
        entry, metadata = self._resolve_element(element_ref)
        return self._public_element_record(entry, metadata)

    def describe_element(self, element_ref: str) -> str:
        entry, metadata = self._resolve_element(element_ref)
        label = str(metadata.get("label") or metadata.get("text") or "")
        return f"'{label[:120] or metadata.get('kind')}' Edge 요소"

    def _action_state(self, locator: Any) -> dict[str, Any]:
        script = """
        element => ({
          checked: 'checked' in element ? Boolean(element.checked) : null,
          value: 'value' in element ? String(element.value || '') : '',
          aria_pressed: element.getAttribute('aria-pressed'),
          aria_expanded: element.getAttribute('aria-expanded'),
          aria_selected: element.getAttribute('aria-selected'),
          text: String(element.innerText || element.textContent || '').trim(),
        })
        """
        try:
            value = locator.evaluate(script)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def click_element(
        self,
        *,
        element_ref: str,
    ) -> dict[str, Any]:
        if not self.allow_dom_actions:
            raise EdgeCdpError(
                "Edge DOM actions are disabled."
            )
        entry, metadata = self._resolve_element(element_ref)
        safety = metadata.get("safety") or {}
        if safety.get("allowed") is not True:
            raise EdgeCdpError(
                str(safety.get("reason") or "This Edge element is blocked.")
            )
        if metadata.get("kind") not in {"link", "button"}:
            raise EdgeCdpError(
                "Only safe link and button elements can be clicked."
            )

        page = entry.page
        before_url = _safe_url(page)
        before_title = _safe_title(page)
        before_state = self._action_state(entry.locator)
        try:
            context = page.context
            before_pages = len(list(context.pages))
        except Exception:
            context = None
            before_pages = 0

        try:
            entry.locator.click(
                timeout=(
                    self.config.action_timeout_seconds * 1_000
                )
            )
        except Exception as exc:
            raise EdgeCdpError(
                "Could not click the selected Edge element."
            ) from exc

        try:
            page.wait_for_load_state(
                "domcontentloaded",
                timeout=min(
                    2_000,
                    int(self.config.action_timeout_seconds * 1_000),
                ),
            )
        except Exception:
            pass
        try:
            page.wait_for_timeout(100)
        except Exception:
            pass

        after_url = _safe_url(page)
        after_title = _safe_title(page)
        after_state = self._action_state(entry.locator)
        try:
            after_pages = len(list(context.pages)) if context is not None else 0
        except Exception:
            after_pages = before_pages

        observed_change = bool(
            after_url != before_url
            or after_title != before_title
            or after_state != before_state
            or after_pages > before_pages
        )
        record = self._public_element_record(entry, metadata)
        self._clear_elements_for_tab(entry.tab_ref)
        return {
            "clicked": True,
            "verified": observed_change,
            "verification_strength": (
                "strong" if observed_change else "unverified"
            ),
            "observed_change": observed_change,
            "element": record,
            "before": {
                "url": before_url,
                "title": before_title,
                "state": before_state,
                "tab_count": before_pages,
            },
            "after": {
                "url": after_url,
                "title": after_title,
                "state": after_state,
                "tab_count": after_pages,
            },
            "message": (
                "안전한 Edge 요소를 클릭하고 실행 결과를 확인했습니다. "
                "다음 요소 작업 전에는 페이지 요소를 다시 조회하세요."
            ),
        }

    def fill_element(
        self,
        *,
        element_ref: str,
        value: str,
    ) -> dict[str, Any]:
        if not self.allow_dom_actions:
            raise EdgeCdpError(
                "Edge DOM actions are disabled."
            )
        if len(value) > self.config.max_fill_characters:
            raise EdgeCdpError(
                f"value must not exceed {self.config.max_fill_characters} characters."
            )
        entry, metadata = self._resolve_element(element_ref)
        safety = metadata.get("safety") or {}
        if safety.get("allowed") is not True:
            raise EdgeCdpError(
                str(safety.get("reason") or "This Edge field is blocked.")
            )
        if metadata.get("kind") != "textbox":
            raise EdgeCdpError(
                "Only safe text fields can be filled."
            )

        try:
            entry.locator.fill(
                value,
                timeout=(
                    self.config.action_timeout_seconds * 1_000
                ),
            )
        except Exception as exc:
            raise EdgeCdpError(
                "Could not fill the selected Edge text field."
            ) from exc

        try:
            current = str(
                entry.locator.input_value(
                    timeout=(
                        self.config.action_timeout_seconds * 1_000
                    )
                )
            )
        except Exception:
            try:
                current = str(
                    entry.locator.evaluate(
                        "element => String(element.innerText || element.textContent || '')"
                    )
                )
            except Exception:
                current = ""
        verified = current == value
        record = self._public_element_record(entry, metadata)
        self._clear_elements_for_tab(entry.tab_ref)
        return {
            "value_set": True,
            "verified": verified,
            "characters": len(value),
            "element": record,
            "url": _safe_url(entry.page),
            "message": (
                "일반 텍스트 초안을 입력하고 필드 값을 확인했습니다. "
                "제출·전송은 수행하지 않았습니다."
            ),
        }

    def capture_tab(
        self,
        *,
        tab_ref: str | None,
        full_page: bool = False,
    ) -> dict[str, Any]:
        ref, page = self._selected_page(
            tab_ref
        )
        directory = (
            self.config
            .screenshot_directory
            .expanduser()
        )
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        timestamp = (
            datetime.now()
            .strftime(
                "%Y%m%d_%H%M%S_%f"
            )
        )
        path = (
            directory
            / f"{timestamp}_edge_tab.png"
        ).resolve()
        try:
            page.screenshot(
                path=str(path),
                full_page=full_page,
                type="png",
            )
        except Exception as exc:
            raise EdgeCdpError(
                "Could not capture the selected Edge tab."
            ) from exc

        if not path.is_file():
            raise EdgeCdpError(
                "Edge screenshot was not created."
            )
        return {
            "tab_ref": ref,
            "title": _safe_title(page),
            "url": _safe_url(page),
            "image_path": str(path),
            "mime_type": "image/png",
            "full_page": full_page,
            "message": (
                "선택한 Edge 탭 화면을 캡처했습니다. "
                "첨부 이미지와 DOM 정보를 함께 분석하세요."
            ),
        }

    def close_tab(
        self,
        *,
        tab_ref: str,
    ) -> dict[str, Any]:
        if not self.allow_tab_close:
            raise EdgeCdpError(
                "Edge tab closing is disabled."
            )

        entry = self._resolve(tab_ref)
        before = self._tab_record(
            entry.page,
            ref=entry.ref,
        )
        try:
            entry.page.close(
                run_before_unload=True
            )
        except Exception as exc:
            raise EdgeCdpError(
                "Could not close the Edge tab. "
                "The page may have blocked closing or shown "
                "a before-unload prompt."
            ) from exc

        try:
            closed = bool(
                entry.page.is_closed()
            )
        except Exception:
            closed = True

        if closed:
            self._clear_elements_for_tab(entry.ref)
            self._tabs.pop(
                entry.ref,
                None,
            )
            self._page_refs.pop(
                id(entry.page),
                None,
            )
            if (
                self._selected_ref
                == entry.ref
            ):
                self._selected_ref = None

        return {
            "closed": closed,
            "tab": before,
            "message": (
                "Edge 탭을 닫았습니다."
                if closed
                else (
                    "Edge 탭 닫기 요청을 보냈지만 "
                    "닫힘을 확인하지 못했습니다."
                )
            ),
        }

    def close(self) -> None:
        # Do not call browser.close(): that would close the user's
        # externally started Edge instance. Stopping Playwright only
        # disconnects this local bridge.
        self._elements.clear()
        self._tabs.clear()
        self._page_refs.clear()
        self._selected_ref = None
        self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = None
        self._managed_launcher.close()
