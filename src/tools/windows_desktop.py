from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from time import sleep
from typing import Any

_WINDOW_STATES = {
    "minimize": 6,
    "maximize": 3,
    "restore": 9,
}

_MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next_track": 0xB0,
    "previous_track": 0xB1,
    "stop": 0xB2,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
}

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_KEYEVENTF_KEYUP = 0x0002
_VK_MENU = 0x12


def _require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError(
            "This desktop-control action supports Windows only."
        )


def _user32() -> Any:
    _require_windows()
    return ctypes.WinDLL("user32", use_last_error=True)


def _kernel32() -> Any:
    _require_windows()
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _window_title(user32: Any, hwnd: int) -> str:
    length = int(user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _process_info(user32: Any, hwnd: int) -> tuple[int, str | None]:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))

    process_name: str | None = None
    try:
        import psutil
        process_name = psutil.Process(process_id.value).name()
    except Exception:
        pass
    return process_id.value, process_name


def _window_state(user32: Any, hwnd: int) -> str:
    if user32.IsIconic(hwnd):
        return "minimized"
    if user32.IsZoomed(hwnd):
        return "maximized"
    return "normal"


def _window_record(user32: Any, hwnd: int) -> dict[str, Any]:
    process_id, process_name = _process_info(user32, hwnd)
    return {
        "window_id": int(hwnd),
        "title": _window_title(user32, hwnd),
        "process_id": process_id,
        "process_name": process_name,
        "state": _window_state(user32, hwnd),
        "is_foreground": int(user32.GetForegroundWindow()) == int(hwnd),
    }


def _validate_window(user32: Any, window_id: int) -> int:
    if window_id <= 0:
        raise ValueError("window_id must be a positive integer.")
    hwnd = int(window_id)
    if not user32.IsWindow(hwnd):
        raise ValueError(f"Window does not exist: {window_id}")
    return hwnd


def get_active_window() -> dict[str, Any]:
    user32 = _user32()
    hwnd = int(user32.GetForegroundWindow())
    if hwnd == 0:
        raise RuntimeError("Windows did not report an active window.")
    return {"window": _window_record(user32, hwnd)}


def list_open_windows(title_contains: str, limit: int) -> dict[str, Any]:
    user32 = _user32()
    query = title_contains.strip().casefold()
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50.")

    windows: list[dict[str, Any]] = []
    callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)

    @callback_type(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        if len(windows) >= limit:
            return False
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(user32, hwnd)
        if not title:
            return True
        if query and query not in title.casefold():
            return True
        windows.append(_window_record(user32, int(hwnd)))
        return True

    user32.EnumWindows(callback, 0)
    return {
        "title_filter": title_contains,
        "count": len(windows),
        "windows": windows,
    }


def focus_window(window_id: int) -> dict[str, Any]:
    user32 = _user32()
    hwnd = _validate_window(user32, window_id)

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, _WINDOW_STATES["restore"])

    # Windows may reject SetForegroundWindow unless the caller recently
    # received user input. Alt is pressed and released without typing text.
    user32.keybd_event(_VK_MENU, 0, 0, 0)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)

    sleep(0.08)
    if int(user32.GetForegroundWindow()) != hwnd:
        raise RuntimeError(
            "Windows refused to focus the requested window."
        )
    return {"focused": True, "window": _window_record(user32, hwnd)}


def set_window_state(window_id: int, state: str) -> dict[str, Any]:
    user32 = _user32()
    hwnd = _validate_window(user32, window_id)
    command = _WINDOW_STATES.get(state)
    if command is None:
        raise ValueError(f"Unsupported window state: {state}")
    user32.ShowWindow(hwnd, command)
    sleep(0.05)
    return {
        "requested_state": state,
        "window": _window_record(user32, hwnd),
    }


def media_control(action: str) -> dict[str, Any]:
    user32 = _user32()
    virtual_key = _MEDIA_KEYS.get(action)
    if virtual_key is None:
        raise ValueError(f"Unsupported media action: {action}")
    user32.keybd_event(virtual_key, 0, 0, 0)
    user32.keybd_event(virtual_key, 0, _KEYEVENTF_KEYUP, 0)
    return {"action": action, "message": "Media key was sent."}


def get_clipboard_text() -> dict[str, Any]:
    user32 = _user32()
    kernel32 = _kernel32()
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.restype = ctypes.c_void_p

    if not user32.OpenClipboard(None):
        raise RuntimeError("The clipboard is currently unavailable.")
    try:
        handle = user32.GetClipboardData(_CF_UNICODETEXT)
        if not handle:
            return {
                "text": "",
                "characters": 0,
                "message": "The clipboard does not contain Unicode text.",
            }
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise RuntimeError("Could not lock clipboard memory.")
        try:
            text = ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

    if len(text) > 10_000:
        raise RuntimeError(
            "Clipboard text exceeds the 10000-character safety limit."
        )
    return {"text": text, "characters": len(text)}


def set_clipboard_text(text: str) -> dict[str, Any]:
    user32 = _user32()
    kernel32 = _kernel32()
    if len(text) > 10_000:
        raise ValueError(
            "Clipboard text must not exceed 10000 characters."
        )

    encoded = (text + "\0").encode("utf-16-le")
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.restype = ctypes.c_void_p
    memory = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(encoded))
    if not memory:
        raise RuntimeError("Could not allocate clipboard memory.")

    transferred = False
    pointer = kernel32.GlobalLock(memory)
    if not pointer:
        kernel32.GlobalFree(memory)
        raise RuntimeError("Could not lock clipboard memory.")
    try:
        ctypes.memmove(pointer, encoded, len(encoded))
    finally:
        kernel32.GlobalUnlock(memory)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(memory)
        raise RuntimeError("The clipboard is currently unavailable.")
    try:
        if not user32.EmptyClipboard():
            raise RuntimeError("Could not clear the clipboard.")
        if not user32.SetClipboardData(_CF_UNICODETEXT, memory):
            raise RuntimeError("Could not write text to the clipboard.")
        transferred = True
    finally:
        user32.CloseClipboard()
        if not transferred:
            kernel32.GlobalFree(memory)

    return {
        "characters": len(text),
        "message": "Clipboard text was updated.",
    }
