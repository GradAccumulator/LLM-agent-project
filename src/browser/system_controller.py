from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys
from threading import RLock
from time import monotonic, sleep
from typing import Any

from .controller import (
    BrowserAutomationConfig,
    detect_installed_browsers,
    validate_browser_url,
)


_WM_CLOSE = 0x0010


@dataclass(frozen=True, slots=True)
class SystemBrowserWindow:
    window_id: int
    title: str
    process_id: int
    process_name: str | None
    is_foreground: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "title": self.title,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "is_foreground": self.is_foreground,
        }


def _require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError(
            "Normal browser control supports Windows only."
        )


def _user32() -> Any:
    _require_windows()
    return ctypes.WinDLL("user32", use_last_error=True)


def _title(user32: Any, hwnd: int) -> str:
    length = int(user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _process(user32: Any, hwnd: int) -> tuple[int, str | None]:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(
        hwnd,
        ctypes.byref(process_id),
    )
    name: str | None = None
    try:
        import psutil

        name = psutil.Process(process_id.value).name()
    except Exception:
        pass
    return process_id.value, name


def _windows(process_names: set[str]) -> tuple[SystemBrowserWindow, ...]:
    user32 = _user32()
    wanted = {name.casefold() for name in process_names}
    foreground = int(user32.GetForegroundWindow())
    result: list[SystemBrowserWindow] = []
    callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)

    @callback_type(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _title(user32, int(hwnd))
        if not title:
            return True
        process_id, process_name = _process(user32, int(hwnd))
        if (
            process_name is None
            or process_name.casefold() not in wanted
        ):
            return True
        result.append(
            SystemBrowserWindow(
                window_id=int(hwnd),
                title=title,
                process_id=process_id,
                process_name=process_name,
                is_foreground=int(hwnd) == foreground,
            )
        )
        return True

    user32.EnumWindows(callback, 0)
    return tuple(result)


def _executable(config: BrowserAutomationConfig) -> Path:
    if config.browser == "custom":
        assert config.executable_path is not None
        path = config.executable_path.expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(
                f"Browser executable does not exist: {path}"
            )
        return path
    if config.browser == "chromium":
        raise RuntimeError(
            "Normal-profile mode cannot use Playwright Chromium."
        )

    for item in detect_installed_browsers():
        if item.selection == config.browser:
            return item.executable_path

    command = (
        "msedge.exe"
        if config.browser.startswith("msedge")
        else "chrome.exe"
    )
    found = shutil.which(command)
    if found:
        return Path(found).resolve()
    raise RuntimeError(
        f"{config.display_name} was not found on this PC."
    )


def _process_names(config: BrowserAutomationConfig) -> set[str]:
    if config.browser == "custom":
        assert config.executable_path is not None
        return {config.executable_path.name.casefold()}
    if config.browser.startswith("msedge"):
        return {"msedge.exe"}
    if config.browser.startswith("chrome"):
        return {"chrome.exe"}
    raise RuntimeError(
        "Selected browser is unsupported in normal-profile mode."
    )


class SystemBrowserController:
    """Opens ordinary user-profile browser windows and tracks ownership."""

    def __init__(self, config: BrowserAutomationConfig) -> None:
        self.config = config
        self._owned: list[int] = []
        self._lock = RLock()

    @property
    def browser_name(self) -> str:
        return self.config.display_name

    def open_page(self, url: str) -> dict[str, Any]:
        url = validate_browser_url(url)
        names = _process_names(self.config)
        before = {window.window_id for window in _windows(names)}

        subprocess.Popen(
            [str(_executable(self.config)), "--new-window", url],
            shell=False,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        selected: SystemBrowserWindow | None = None
        latest: tuple[SystemBrowserWindow, ...] = ()
        deadline = monotonic() + 6.0
        while monotonic() < deadline:
            latest = _windows(names)
            created = [
                window
                for window in latest
                if window.window_id not in before
            ]
            if created:
                selected = next(
                    (
                        window
                        for window in created
                        if window.is_foreground
                    ),
                    created[-1],
                )
                break
            sleep(0.10)

        if selected is None:
            selected = next(
                (
                    window
                    for window in latest
                    if window.is_foreground
                ),
                None,
            )
        if selected is None:
            raise RuntimeError(
                "The browser opened, but Jarvis could not identify "
                "the new window."
            )

        with self._lock:
            if selected.window_id not in self._owned:
                self._owned.append(selected.window_id)

        return {
            "browser": self.config.browser,
            "browser_name": self.browser_name,
            "url": url,
            "window": selected.as_dict(),
            "normal_profile": True,
            "message": (
                f"Opened a normal {self.browser_name} window "
                "using the user's regular profile."
            ),
        }

    def list_owned_windows(self) -> dict[str, Any]:
        current = {
            window.window_id: window
            for window in _windows(_process_names(self.config))
        }
        with self._lock:
            self._owned = [
                item for item in self._owned if item in current
            ]
            windows = [
                current[item].as_dict() for item in self._owned
            ]
        return {
            "browser": self.config.browser,
            "browser_name": self.browser_name,
            "count": len(windows),
            "windows": windows,
        }

    def close_owned_window(
        self,
        window_id: int | None,
    ) -> dict[str, Any]:
        user32 = _user32()
        current = {
            window.window_id: window
            for window in _windows(_process_names(self.config))
        }
        with self._lock:
            self._owned = [
                item for item in self._owned if item in current
            ]
            if window_id is None:
                if not self._owned:
                    raise RuntimeError(
                        "Jarvis has not opened a normal browser "
                        "window in this session."
                    )
                target_id = self._owned[-1]
            else:
                target_id = int(window_id)
                if target_id not in self._owned:
                    raise ValueError(
                        "Jarvis can only close browser windows "
                        "that it opened."
                    )

        target = current.get(target_id)
        if target is None:
            raise RuntimeError("The tracked browser window is gone.")
        if not user32.PostMessageW(target_id, _WM_CLOSE, 0, 0):
            raise RuntimeError("Windows rejected the close request.")

        deadline = monotonic() + 4.0
        while monotonic() < deadline and user32.IsWindow(target_id):
            sleep(0.05)
        if user32.IsWindow(target_id):
            raise RuntimeError(
                "The browser window did not close."
            )

        with self._lock:
            self._owned = [
                item for item in self._owned if item != target_id
            ]
        return {
            "browser": self.config.browser,
            "browser_name": self.browser_name,
            "closed": True,
            "window": target.as_dict(),
            "message": (
                f"Closed the {self.browser_name} window "
                "opened by Jarvis."
            ),
        }

    def close(self) -> None:
        # Ordinary windows stay open when Jarvis exits.
        pass
