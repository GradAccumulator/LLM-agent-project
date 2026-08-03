from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import importlib
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


@dataclass(frozen=True, slots=True)
class EdgeCdpConfig:
    enabled: bool = True
    endpoint_url: str = "http://127.0.0.1:9222"
    connect_timeout_seconds: float = 5.0
    action_timeout_seconds: float = 10.0
    max_page_text_characters: int = 16_000
    tab_ref_ttl_seconds: float = 300.0
    screenshot_directory: Path = Path("screenshots")
    allow_tab_close: bool = True
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
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._selected_ref: str | None = None
        self._tabs: dict[str, _TabEntry] = {}
        self._page_refs: dict[int, str] = {}

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def allow_tab_close(self) -> bool:
        return self.config.allow_tab_close

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
                self.config.endpoint_url,
                self.config.connect_timeout_seconds,
            )
        except Exception as exc:
            self._playwright = None
            self._browser = None
            raise EdgeCdpError(
                "Could not connect to Microsoft Edge CDP at "
                f"{self.config.endpoint_url}. Start Edge with "
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

    def _purge(self) -> None:
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
                    self.config.endpoint_url
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
                self.config.endpoint_url
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
                self.config.endpoint_url
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
