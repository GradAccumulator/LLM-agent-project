from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic, sleep
import re
import secrets
import sys
from typing import Any, Callable, Iterable


class WindowsUiAutomationError(RuntimeError):
    pass


class StaleElementReferenceError(WindowsUiAutomationError):
    pass


@dataclass(frozen=True, slots=True)
class WindowsUiAutomationConfig:
    enabled: bool = True
    backend: str = "uia"
    element_ttl_seconds: float = 180.0
    max_elements: int = 200
    allow_actions: bool = True
    screenshot_directory: Path = Path("screenshots")

    def __post_init__(self) -> None:
        if self.backend != "uia":
            raise ValueError("Only the UI Automation backend 'uia' is supported.")
        if self.element_ttl_seconds <= 0:
            raise ValueError("element_ttl_seconds must be positive.")
        if not 10 <= self.max_elements <= 500:
            raise ValueError("max_elements must be between 10 and 500.")


@dataclass(slots=True)
class _ElementCacheEntry:
    ref: str
    wrapper: Any
    window_id: int
    created_at: float
    expires_at: float
    name: str
    control_type: str
    automation_id: str
    class_name: str
    is_password: bool


_DANGEROUS_INVOKE_PATTERN = re.compile(
    r"(?:삭제|제거|영구|구매|결제|주문|전송|보내기|제출|초기화|재설정|포맷|"
    r"uninstall|delete|remove|purchase|buy|pay|checkout|send|submit|reset|format)",
    flags=re.IGNORECASE,
)


class WindowsUiAutomation:
    """Safe wrapper around pywinauto's Microsoft UI Automation backend."""

    def __init__(
        self,
        config: WindowsUiAutomationConfig = WindowsUiAutomationConfig(),
        *,
        desktop_factory: Callable[..., Any] | None = None,
        platform: str | None = None,
        clock: Callable[[], float] = monotonic,
        screenshot_capture: (
            Callable[
                [dict[str, int], Path],
                Path,
            ]
            | None
        ) = None,
    ) -> None:
        self.config = config
        self._desktop_factory = desktop_factory
        self._platform = platform or sys.platform
        self._clock = clock
        self._screenshot_capture = (
            screenshot_capture
        )
        self._cache: dict[str, _ElementCacheEntry] = {}

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def allow_actions(self) -> bool:
        return self.config.allow_actions

    def _require_windows(self) -> None:
        if self._platform != "win32":
            raise WindowsUiAutomationError(
                "Windows UI Automation is available on Windows only."
            )

    def _desktop(self) -> Any:
        self._require_windows()
        if not self.enabled:
            raise WindowsUiAutomationError(
                "Windows UI Automation is disabled."
            )
        if self._desktop_factory is not None:
            return self._desktop_factory(backend=self.config.backend)
        try:
            from pywinauto import Desktop
        except ImportError as exc:
            raise WindowsUiAutomationError(
                "pywinauto is missing. Run `python -m pip install -r requirements.txt`."
            ) from exc
        return Desktop(backend=self.config.backend)

    @staticmethod
    def _safe_call(callable_: Callable[[], Any], default: Any = None) -> Any:
        try:
            return callable_()
        except Exception:
            return default

    @staticmethod
    def _rectangle(wrapper: Any) -> dict[str, int] | None:
        rectangle = WindowsUiAutomation._safe_call(wrapper.rectangle)
        if rectangle is None:
            return None
        values: dict[str, int] = {}
        for name in ("left", "top", "right", "bottom"):
            value = getattr(rectangle, name, None)
            if value is None:
                return None
            values[name] = int(value)
        values["width"] = max(0, values["right"] - values["left"])
        values["height"] = max(0, values["bottom"] - values["top"])
        return values

    @staticmethod
    def _element_info(wrapper: Any) -> Any:
        return getattr(wrapper, "element_info", None)

    @classmethod
    def _name(cls, wrapper: Any) -> str:
        info = cls._element_info(wrapper)
        name = getattr(info, "name", None) if info is not None else None
        if not name:
            name = cls._safe_call(wrapper.window_text, "")
        return " ".join(str(name or "").split())[:300]

    @classmethod
    def _control_type(cls, wrapper: Any) -> str:
        info = cls._element_info(wrapper)
        value = getattr(info, "control_type", None) if info is not None else None
        if not value:
            value = cls._safe_call(wrapper.friendly_class_name, "")
        return str(value or "Unknown")[:100]

    @classmethod
    def _automation_id(cls, wrapper: Any) -> str:
        info = cls._element_info(wrapper)
        value = getattr(info, "automation_id", None) if info is not None else None
        return str(value or "")[:200]

    @classmethod
    def _class_name(cls, wrapper: Any) -> str:
        info = cls._element_info(wrapper)
        value = getattr(info, "class_name", None) if info is not None else None
        if not value:
            value = cls._safe_call(wrapper.class_name, "")
        return str(value or "")[:200]

    @classmethod
    def _process_id(cls, wrapper: Any) -> int | None:
        info = cls._element_info(wrapper)
        value = getattr(info, "process_id", None) if info is not None else None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _handle(cls, wrapper: Any) -> int | None:
        for value in (
            getattr(wrapper, "handle", None),
            getattr(cls._element_info(wrapper), "handle", None),
        ):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
        return None

    @classmethod
    def _is_password(cls, wrapper: Any) -> bool:
        info = cls._element_info(wrapper)
        value = getattr(info, "is_password", None) if info is not None else None
        if value is not None:
            return bool(value)
        return bool(cls._safe_call(lambda: wrapper.is_password(), False))

    @classmethod
    def _element_record(
        cls,
        wrapper: Any,
        *,
        depth: int,
        ref: str | None = None,
        include_value: bool = False,
        window_id: int | None = None,
    ) -> dict[str, Any]:
        info = cls._element_info(wrapper)
        password = cls._is_password(wrapper)
        value: str | None = None
        if include_value and not password:
            raw = cls._safe_call(lambda: wrapper.get_value(), None)
            if raw is None and info is not None:
                raw = getattr(info, "rich_text", None)
            if raw is not None:
                value = str(raw)[:500]
        return {
            "element_ref": ref,
            "window_id": window_id,
            "name": cls._name(wrapper),
            "control_type": cls._control_type(wrapper),
            "automation_id": cls._automation_id(wrapper),
            "class_name": cls._class_name(wrapper),
            "process_id": cls._process_id(wrapper),
            "depth": depth,
            "enabled": bool(cls._safe_call(wrapper.is_enabled, False)),
            "visible": bool(cls._safe_call(wrapper.is_visible, False)),
            "offscreen": bool(getattr(info, "offscreen", False)) if info else False,
            "focusable": bool(getattr(info, "is_keyboard_focusable", False)) if info else False,
            "focused": bool(cls._safe_call(wrapper.has_keyboard_focus, False)),
            "password": password,
            "bounds": cls._rectangle(wrapper),
            "value": value,
        }

    def _purge_expired(self) -> None:
        now = self._clock()
        for ref in [
            ref for ref, entry in self._cache.items() if now >= entry.expires_at
        ]:
            self._cache.pop(ref, None)

    def _cache_wrapper(self, wrapper: Any, *, window_id: int) -> str:
        self._purge_expired()
        ref = "uia_" + secrets.token_hex(6)
        now = self._clock()
        entry = _ElementCacheEntry(
            ref=ref,
            wrapper=wrapper,
            window_id=window_id,
            created_at=now,
            expires_at=now + self.config.element_ttl_seconds,
            name=self._name(wrapper),
            control_type=self._control_type(wrapper),
            automation_id=self._automation_id(wrapper),
            class_name=self._class_name(wrapper),
            is_password=self._is_password(wrapper),
        )
        self._cache[ref] = entry
        return ref

    def _resolve(self, element_ref: str) -> _ElementCacheEntry:
        self._purge_expired()
        ref = element_ref.strip()
        entry = self._cache.get(ref)
        if entry is None:
            raise StaleElementReferenceError(
                "UI element reference is missing or expired. Inspect the window again."
            )
        exists = self._safe_call(lambda: entry.wrapper.exists(timeout=0), True)
        if exists is False:
            self._cache.pop(ref, None)
            raise StaleElementReferenceError(
                "The referenced UI element no longer exists. Inspect the window again."
            )
        return entry

    def _window(self, window_id: int) -> Any:
        if int(window_id) <= 0:
            raise WindowsUiAutomationError("window_id must be positive.")
        desktop = self._desktop()
        try:
            wrapper = desktop.window(handle=int(window_id)).wrapper_object()
        except Exception as exc:
            raise WindowsUiAutomationError(
                f"Could not connect to window_id {window_id}."
            ) from exc
        if not self._safe_call(lambda: wrapper.exists(timeout=0), True):
            raise WindowsUiAutomationError(
                f"Window no longer exists: {window_id}"
            )
        return wrapper

    @staticmethod
    def _process_name(process_id: int | None) -> str | None:
        if process_id is None:
            return None
        try:
            import psutil
            return psutil.Process(process_id).name()
        except Exception:
            return None

    def find_windows(
        self,
        *,
        title_contains: str = "",
        process_contains: str = "",
        limit: int = 30,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise WindowsUiAutomationError("limit must be between 1 and 100.")
        title_query = title_contains.strip().casefold()
        process_query = process_contains.strip().casefold()
        windows: list[dict[str, Any]] = []
        try:
            candidates = self._desktop().windows()
        except Exception as exc:
            raise WindowsUiAutomationError(
                "Could not enumerate Windows UI Automation windows."
            ) from exc
        for wrapper in candidates:
            handle = self._handle(wrapper)
            if handle is None:
                continue
            title = self._name(wrapper)
            process_id = self._process_id(wrapper)
            process_name = self._process_name(process_id)
            if title_query and title_query not in title.casefold():
                continue
            if process_query and process_query not in (process_name or "").casefold():
                continue
            windows.append({
                "window_id": handle,
                "title": title,
                "process_id": process_id,
                "process_name": process_name,
                "class_name": self._class_name(wrapper),
                "enabled": bool(self._safe_call(wrapper.is_enabled, False)),
                "visible": bool(self._safe_call(wrapper.is_visible, False)),
                "focused": bool(self._safe_call(wrapper.has_keyboard_focus, False)),
                "bounds": self._rectangle(wrapper),
            })
            if len(windows) >= limit:
                break
        return {
            "title_filter": title_contains,
            "process_filter": process_contains,
            "count": len(windows),
            "windows": windows,
        }

    def _walk(self, root: Any, max_depth: int) -> Iterable[tuple[Any, int]]:
        stack: list[tuple[Any, int]] = [(root, 0)]
        while stack:
            wrapper, depth = stack.pop()
            yield wrapper, depth
            if depth >= max_depth:
                continue
            children = self._safe_call(wrapper.children, []) or []
            for child in reversed(list(children)):
                stack.append((child, depth + 1))

    def inspect_window(
        self,
        *,
        window_id: int,
        max_depth: int = 5,
        limit: int | None = None,
        include_offscreen: bool = False,
        include_value: bool = False,
    ) -> dict[str, Any]:
        if not 1 <= max_depth <= 12:
            raise WindowsUiAutomationError("max_depth must be between 1 and 12.")
        effective_limit = limit or self.config.max_elements
        if not 1 <= effective_limit <= self.config.max_elements:
            raise WindowsUiAutomationError(
                f"limit must be between 1 and {self.config.max_elements}."
            )
        window = self._window(window_id)
        elements: list[dict[str, Any]] = []
        for wrapper, depth in self._walk(window, max_depth):
            info = self._element_info(wrapper)
            offscreen = bool(getattr(info, "offscreen", False)) if info else False
            if offscreen and not include_offscreen:
                continue
            ref = self._cache_wrapper(wrapper, window_id=int(window_id))
            elements.append(self._element_record(
                wrapper,
                depth=depth,
                ref=ref,
                include_value=include_value,
                window_id=int(window_id),
            ))
            if len(elements) >= effective_limit:
                break
        return {
            "window_id": int(window_id),
            "element_ttl_seconds": self.config.element_ttl_seconds,
            "count": len(elements),
            "truncated": len(elements) >= effective_limit,
            "elements": elements,
        }

    def _capture_bounds(
        self,
        bounds: dict[str, int],
        path: Path,
    ) -> Path:
        if self._screenshot_capture is not None:
            result = self._screenshot_capture(
                bounds,
                path,
            )
            return Path(result)

        try:
            import mss
            import mss.tools
        except ImportError as exc:
            raise WindowsUiAutomationError(
                "mss is missing. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        region = {
            "left": bounds["left"],
            "top": bounds["top"],
            "width": bounds["width"],
            "height": bounds["height"],
        }
        try:
            with mss.mss() as capture:
                image = capture.grab(region)
                mss.tools.to_png(
                    image.rgb,
                    image.size,
                    output=str(path),
                )
        except Exception as exc:
            raise WindowsUiAutomationError(
                "Could not capture the selected window."
            ) from exc
        return path

    def capture_window_context(
        self,
        *,
        window_id: int,
        max_depth: int = 6,
        limit: int = 120,
        include_value: bool = False,
    ) -> dict[str, Any]:
        window = self._window(window_id)
        bounds = self._rectangle(window)
        if (
            bounds is None
            or bounds["width"] <= 0
            or bounds["height"] <= 0
        ):
            raise WindowsUiAutomationError(
                "The selected window has no capturable bounds."
            )

        inspection = self.inspect_window(
            window_id=window_id,
            max_depth=max_depth,
            limit=limit,
            include_offscreen=False,
            include_value=include_value,
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
            / f"{timestamp}_window_{int(window_id)}.png"
        ).resolve()
        path = self._capture_bounds(
            bounds,
            path,
        ).resolve()
        if not path.is_file():
            raise WindowsUiAutomationError(
                "Window screenshot was not created."
            )

        return {
            "window_id": int(window_id),
            "window_title": self._name(window),
            "window_bounds": bounds,
            "image_path": str(path),
            "mime_type": "image/png",
            "element_count": inspection["count"],
            "elements": inspection["elements"],
            "truncated": inspection["truncated"],
            "element_ttl_seconds": (
                self.config.element_ttl_seconds
            ),
            "message": (
                "창 스크린샷과 UI Automation 요소 정보를 함께 "
                "캡처했습니다. 이미지와 요소 좌표·이름을 교차 분석하세요."
            ),
        }

    def find_elements(
        self,
        *,
        window_id: int,
        name_contains: str = "",
        automation_id: str = "",
        control_types: list[str] | None = None,
        enabled_only: bool = True,
        visible_only: bool = True,
        max_depth: int = 10,
        limit: int = 50,
    ) -> dict[str, Any]:
        if not 1 <= limit <= min(100, self.config.max_elements):
            raise WindowsUiAutomationError(
                f"limit must be between 1 and {min(100, self.config.max_elements)}."
            )
        if not 1 <= max_depth <= 12:
            raise WindowsUiAutomationError("max_depth must be between 1 and 12.")
        name_query = name_contains.strip().casefold()
        automation_query = automation_id.strip().casefold()
        type_set = {item.strip().casefold() for item in (control_types or []) if item.strip()}
        window = self._window(window_id)
        matches: list[dict[str, Any]] = []
        for wrapper, depth in self._walk(window, max_depth):
            name = self._name(wrapper)
            current_id = self._automation_id(wrapper)
            control_type = self._control_type(wrapper)
            if name_query and name_query not in name.casefold():
                continue
            if automation_query and automation_query != current_id.casefold():
                continue
            if type_set and control_type.casefold() not in type_set:
                continue
            if enabled_only and not self._safe_call(wrapper.is_enabled, False):
                continue
            if visible_only and not self._safe_call(wrapper.is_visible, False):
                continue
            ref = self._cache_wrapper(wrapper, window_id=int(window_id))
            matches.append(self._element_record(
                wrapper,
                depth=depth,
                ref=ref,
                window_id=int(window_id),
            ))
            if len(matches) >= limit:
                break
        return {
            "window_id": int(window_id),
            "name_filter": name_contains,
            "automation_id_filter": automation_id,
            "control_types": list(control_types or []),
            "count": len(matches),
            "elements": matches,
        }

    def get_element(self, *, element_ref: str, include_value: bool = False) -> dict[str, Any]:
        entry = self._resolve(element_ref)
        return {
            "element": self._element_record(
                entry.wrapper,
                depth=0,
                ref=entry.ref,
                include_value=include_value,
                window_id=entry.window_id,
            ),
            "remaining_ttl_seconds": round(
                max(0.0, entry.expires_at - self._clock()),
                1,
            ),
        }

    def describe_ref(self, element_ref: str) -> str:
        entry = self._resolve(element_ref)
        label = entry.name or entry.automation_id or entry.class_name or "이름 없는 요소"
        return f"'{label[:100]}' {entry.control_type} UI 요소"

    def _require_actions(self) -> None:
        if not self.allow_actions:
            raise WindowsUiAutomationError(
                "Windows UI Automation actions are disabled."
            )

    def focus_element(self, *, element_ref: str) -> dict[str, Any]:
        self._require_actions()
        entry = self._resolve(element_ref)
        try:
            entry.wrapper.set_focus()
        except Exception as exc:
            raise WindowsUiAutomationError(
                "The UI element could not receive keyboard focus."
            ) from exc
        sleep(0.05)
        focused = bool(self._safe_call(entry.wrapper.has_keyboard_focus, True))
        return {
            "focused": focused,
            "element_ref": entry.ref,
            "name": entry.name,
            "control_type": entry.control_type,
        }

    def invoke_element(self, *, element_ref: str) -> dict[str, Any]:
        self._require_actions()
        entry = self._resolve(element_ref)
        label = " ".join((entry.name, entry.automation_id, entry.control_type))
        if _DANGEROUS_INVOKE_PATTERN.search(label):
            raise WindowsUiAutomationError(
                "This button looks destructive, transactional, or externally consequential. "
                "It is blocked in this stage instead of being invoked."
            )
        try:
            interface = getattr(entry.wrapper, "iface_invoke", None)
            if interface is not None:
                interface.Invoke()
            else:
                entry.wrapper.invoke()
        except Exception as exc:
            raise WindowsUiAutomationError(
                "The element does not support the UI Automation Invoke pattern."
            ) from exc
        return {
            "invoked": True,
            "element_ref": entry.ref,
            "name": entry.name,
            "control_type": entry.control_type,
        }

    def set_value(self, *, element_ref: str, value: str) -> dict[str, Any]:
        self._require_actions()
        entry = self._resolve(element_ref)
        if entry.is_password:
            raise WindowsUiAutomationError(
                "Password fields are blocked. Jarvis will not type secrets into UI elements."
            )
        if len(value) > 2000:
            raise WindowsUiAutomationError("UI text must not exceed 2000 characters.")
        try:
            interface = getattr(entry.wrapper, "iface_value", None)
            if interface is not None:
                interface.SetValue(value)
            else:
                entry.wrapper.set_edit_text(value)
        except Exception as exc:
            raise WindowsUiAutomationError(
                "The element does not support the UI Automation Value pattern."
            ) from exc
        actual = self._safe_call(lambda: entry.wrapper.get_value(), value)
        verified = str(actual) == value
        return {
            "value_set": True,
            "verified": verified,
            "characters": len(value),
            "element_ref": entry.ref,
            "name": entry.name,
            "control_type": entry.control_type,
        }

    def toggle_element(self, *, element_ref: str) -> dict[str, Any]:
        self._require_actions()
        entry = self._resolve(element_ref)
        before = self._safe_call(lambda: entry.wrapper.get_toggle_state(), None)
        try:
            interface = getattr(entry.wrapper, "iface_toggle", None)
            if interface is not None:
                interface.Toggle()
            else:
                entry.wrapper.toggle()
        except Exception as exc:
            raise WindowsUiAutomationError(
                "The element does not support the UI Automation Toggle pattern."
            ) from exc
        after = self._safe_call(lambda: entry.wrapper.get_toggle_state(), None)
        return {
            "toggled": True,
            "verified": before is None or after != before,
            "state_before": before,
            "state_after": after,
            "element_ref": entry.ref,
            "name": entry.name,
            "control_type": entry.control_type,
        }

    def select_element(self, *, element_ref: str) -> dict[str, Any]:
        self._require_actions()
        entry = self._resolve(element_ref)
        try:
            interface = getattr(entry.wrapper, "iface_selection_item", None)
            if interface is not None:
                interface.Select()
            else:
                entry.wrapper.select()
        except Exception as exc:
            raise WindowsUiAutomationError(
                "The element does not support the UI Automation SelectionItem pattern."
            ) from exc
        selected = bool(self._safe_call(entry.wrapper.is_selected, True))
        return {
            "selected": selected,
            "element_ref": entry.ref,
            "name": entry.name,
            "control_type": entry.control_type,
        }

    def close(self) -> None:
        self._cache.clear()
