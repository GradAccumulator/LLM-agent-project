from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import quote_plus

from src.browser import (
    BrowserAutomationConfig,
    BrowserController,
    SystemBrowserController,
)
from src.memory import LocalMemoryStore
from src.google_calendar import GoogleCalendarClient
from src.scheduler import SchedulerStore

from .browser_tools import register_browser_tools
from .registry import ToolRegistry, ToolSpec
from .planning_tools import register_planning_tools
from .memory_tools import register_memory_tools
from .google_calendar_tools import register_google_calendar_tools
from .scheduler_tools import register_scheduler_tools
from .windows_desktop import (
    focus_window,
    get_active_window,
    get_clipboard_text,
    list_open_windows,
    media_control,
    set_clipboard_text,
    set_window_state,
)


_APPLICATION_IDS = (
    "calculator",
    "notepad",
    "file_explorer",
    "settings",
    "browser",
    "vscode",
    "terminal",
)

_WEBSITE_URLS = {
    "youtube": "https://www.youtube.com/",
    "google": "https://www.google.com/",
    "naver": "https://www.naver.com/",
    "github": "https://github.com/",
    "chatgpt": "https://chatgpt.com/",
    "openai": "https://openai.com/",
}

_SEARCH_URLS = {
    "google": "https://www.google.com/search?q={query}",
    "naver": "https://search.naver.com/search.naver?query={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
}


def _empty_parameters() -> dict:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def _require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("This action currently supports Windows only.")


def _spawn(command: list[str]) -> None:
    subprocess.Popen(
        command,
        shell=False,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def get_current_datetime() -> dict:
    now = datetime.now().astimezone()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": str(now.tzinfo),
    }


def _query_nvidia_gpus() -> list[dict]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return []

    command = [
        executable,
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,"
        "temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    gpus: list[dict] = []
    for index, line in enumerate(completed.stdout.splitlines()):
        values = [value.strip() for value in line.split(",")]
        if len(values) != 6:
            continue
        name, usage, used, total, temperature, power = values
        gpus.append(
            {
                "index": index,
                "name": name,
                "usage_percent": usage,
                "memory_used_mib": used,
                "memory_total_mib": total,
                "temperature_c": temperature,
                "power_w": power,
            }
        )
    return gpus


def get_system_status() -> dict:
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError(
            "psutil is not installed. Run "
            "`python -m pip install -r requirements.txt`."
        ) from exc

    memory = psutil.virtual_memory()
    disk_root = Path.home().anchor or os.path.abspath(os.sep)
    disk = psutil.disk_usage(disk_root)
    battery = psutil.sensors_battery()

    result = {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "memory": {
            "used_gib": round(memory.used / (1024 ** 3), 2),
            "total_gib": round(memory.total / (1024 ** 3), 2),
            "percent": memory.percent,
        },
        "disk": {
            "root": disk_root,
            "used_gib": round(disk.used / (1024 ** 3), 2),
            "total_gib": round(disk.total / (1024 ** 3), 2),
            "percent": disk.percent,
        },
        "gpus": _query_nvidia_gpus(),
    }

    if battery is not None:
        result["battery"] = {
            "percent": battery.percent,
            "plugged_in": battery.power_plugged,
            "seconds_left": battery.secsleft,
        }

    return result


def open_application(application: str) -> dict:
    _require_windows()

    if application not in _APPLICATION_IDS:
        raise ValueError(f"Unsupported application: {application}")

    if application == "calculator":
        _spawn(["calc.exe"])
    elif application == "notepad":
        _spawn(["notepad.exe"])
    elif application == "file_explorer":
        _spawn(["explorer.exe"])
    elif application == "settings":
        os.startfile("ms-settings:")  # type: ignore[attr-defined]
    elif application == "browser":
        if not webbrowser.open("about:blank", new=2):
            raise RuntimeError("The default browser could not be opened.")
    elif application == "vscode":
        executable = shutil.which("code") or shutil.which("code.cmd")
        if executable is None:
            raise RuntimeError(
                "VS Code command 'code' was not found in PATH."
            )
        _spawn([executable])
    elif application == "terminal":
        executable = shutil.which("wt.exe") or shutil.which("cmd.exe")
        if executable is None:
            raise RuntimeError("Windows Terminal or cmd.exe was not found.")
        _spawn([executable])

    return {
        "application": application,
        "message": "Application launch request was sent.",
    }


def open_website(site: str) -> dict:
    url = _WEBSITE_URLS.get(site)
    if url is None:
        raise ValueError(f"Unsupported website: {site}")
    if not webbrowser.open(url, new=2):
        raise RuntimeError("The default browser could not open the website.")
    return {
        "site": site,
        "url": url,
        "message": "Website open request was sent.",
    }


def search_browser(engine: str, query: str) -> dict:
    query = query.strip()
    if engine not in _SEARCH_URLS:
        raise ValueError(f"Unsupported search engine: {engine}")
    if not query:
        raise ValueError("Search query must not be empty.")
    if len(query) > 200:
        raise ValueError("Search query must not exceed 200 characters.")

    url = _SEARCH_URLS[engine].format(query=quote_plus(query))
    if not webbrowser.open(url, new=2):
        raise RuntimeError("The default browser could not open the search.")
    return {
        "engine": engine,
        "query": query,
        "url": url,
        "message": "Browser search request was sent.",
    }


def _safe_note_name(title: str) -> str:
    normalized = re.sub(r"[^\w가-힣-]+", "_", title, flags=re.UNICODE)
    normalized = normalized.strip("_")
    return normalized[:40] or "note"


def create_note(title: str, content: str) -> dict:
    title = title.strip()
    content = content.strip()

    if not title:
        raise ValueError("Note title must not be empty.")
    if not content:
        raise ValueError("Note content must not be empty.")
    if len(title) > 80:
        raise ValueError("Note title must not exceed 80 characters.")
    if len(content) > 2_000:
        raise ValueError("Note content must not exceed 2000 characters.")

    notes_directory = Path("notes")
    notes_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{_safe_note_name(title)}.md"
    path = notes_directory / filename
    body = f"# {title}\n\n{content}\n"
    path.write_text(body, encoding="utf-8")

    return {
        "title": title,
        "path": str(path.resolve()),
        "message": "Note was saved.",
    }



def inspect_screen(display: str) -> dict:
    """Capture the current screen so the multimodal model can inspect it."""

    try:
        import mss
        import mss.tools
    except ImportError as exc:
        raise RuntimeError(
            "mss is not installed. Run "
            "`python -m pip install -r requirements.txt`."
        ) from exc

    if display not in {"primary", "all"}:
        raise ValueError("display must be 'primary' or 'all'.")

    screenshot_directory = Path("screenshots")
    screenshot_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = screenshot_directory / f"{timestamp}_screen.png"

    with mss.mss() as capture:
        # monitors[0] is the complete virtual desktop.
        # monitors[1] is the primary display.
        monitor_index = 0 if display == "all" else 1
        if len(capture.monitors) <= monitor_index:
            raise RuntimeError(
                f"Requested display is unavailable: {display}"
            )

        monitor = capture.monitors[monitor_index]
        image = capture.grab(monitor)
        mss.tools.to_png(
            image.rgb,
            image.size,
            output=str(output_path),
        )

    absolute_path = output_path.resolve()
    return {
        "display": display,
        "image_path": str(absolute_path),
        "mime_type": "image/png",
        "width": image.width,
        "height": image.height,
        "message": (
            "The current screen was captured. Inspect the attached image "
            "and answer the user's original question."
        ),
    }


def build_default_tool_registry(
    browser_config: BrowserAutomationConfig | None = None,
    *,
    browser_control_mode: str = "system",
    memory_store: LocalMemoryStore | None = None,
    scheduler_store: SchedulerStore | None = None,
    google_calendar_client: GoogleCalendarClient | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(
        memory_store=memory_store,
        scheduler_store=scheduler_store,
    )
    register_planning_tools(registry)

    effective_browser_config = (
        browser_config or BrowserAutomationConfig()
    )
    browser_controller = BrowserController(
        effective_browser_config
    )
    system_browser_controller = SystemBrowserController(
        effective_browser_config
    )
    if browser_control_mode not in {"system", "automation"}:
        raise ValueError("Invalid browser_control_mode.")

    def open_selected_page(url: str) -> dict:
        if browser_control_mode == "system":
            return system_browser_controller.open_page(url)
        return browser_controller.open_page(url)

    if memory_store is not None and memory_store.enabled:
        register_memory_tools(
            registry,
            memory_store,
            open_url=open_selected_page,
        )
        registry.register_closer(memory_store.close)

    if scheduler_store is not None and scheduler_store.enabled:
        register_scheduler_tools(registry, scheduler_store)
        registry.register_closer(scheduler_store.close)

    def open_application_selected(
        application: str,
    ) -> dict:
        if application != "browser":
            return open_application(application)

        result = open_selected_page(
            "https://www.google.com/"
        )
        return {
            "application": "browser",
            **result,
            "message": (
                f"{effective_browser_config.display_name} "
                "launch request was sent."
            ),
        }

    def open_website_selected(site: str) -> dict:
        url = _WEBSITE_URLS.get(site)
        if url is None:
            raise ValueError(
                f"Unsupported website: {site}"
            )
        result = open_selected_page(url)
        return {
            "site": site,
            **result,
            "message": (
                f"Website opened in "
                f"{effective_browser_config.display_name}."
            ),
        }

    def search_browser_selected(
        engine: str,
        query: str,
    ) -> dict:
        query = query.strip()
        if engine not in _SEARCH_URLS:
            raise ValueError(
                f"Unsupported search engine: {engine}"
            )
        if not query:
            raise ValueError(
                "Search query must not be empty."
            )
        if len(query) > 200:
            raise ValueError(
                "Search query must not exceed 200 characters."
            )

        url = _SEARCH_URLS[engine].format(
            query=quote_plus(query)
        )
        result = open_selected_page(url)
        return {
            "engine": engine,
            "query": query,
            **result,
            "message": (
                f"Search opened in "
                f"{effective_browser_config.display_name}."
            ),
        }

    registry.register(
        ToolSpec(
            name="get_current_datetime",
            description=(
                "현재 컴퓨터의 로컬 날짜, 시간, 요일과 시간대를 조회한다. "
                "현재 시각이나 오늘 날짜를 물을 때 사용한다."
            ),
            parameters=_empty_parameters(),
            handler=get_current_datetime,
        )
    )
    registry.register(
        ToolSpec(
            name="get_system_status",
            description=(
                "현재 PC의 CPU, 메모리, 디스크, 배터리 및 NVIDIA GPU "
                "사용률과 온도를 조회한다."
            ),
            parameters=_empty_parameters(),
            handler=get_system_status,
        )
    )
    registry.register(
        ToolSpec(
            name="open_application",
            description=(
                "Windows에서 허용된 앱 하나를 연다. 임의 명령어나 "
                "임의 실행 파일은 실행할 수 없다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "enum": list(_APPLICATION_IDS),
                        "description": (
                            "calculator=계산기, notepad=메모장, "
                            "file_explorer=파일 탐색기, settings=설정, "
                            "browser=브라우저, vscode=VS Code, "
                            "terminal=터미널"
                        ),
                    }
                },
                "required": ["application"],
                "additionalProperties": False,
            },
            handler=open_application_selected,
        )
    )
    registry.register(
        ToolSpec(
            name="open_website",
            description=(
                "허용 목록의 웹사이트를 설정에서 선택한 브라우저에서 연다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "site": {
                        "type": "string",
                        "enum": list(_WEBSITE_URLS),
                        "description": "열 웹사이트 식별자",
                    }
                },
                "required": ["site"],
                "additionalProperties": False,
            },
            handler=open_website_selected,
        )
    )
    registry.register(
        ToolSpec(
            name="search_browser",
            description=(
                "사용자가 검색 결과를 화면의 브라우저 창에 열어 달라고 "
                "명시했을 때만 Google, Naver 또는 YouTube 검색 결과를 연다. "
                "정보 조사나 최신 사실 확인에는 사용하지 않는다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "engine": {
                        "type": "string",
                        "enum": list(_SEARCH_URLS),
                        "description": "검색에 사용할 서비스",
                    },
                    "query": {
                        "type": "string",
                        "description": "검색할 문구. 최대 200자.",
                    },
                },
                "required": ["engine", "query"],
                "additionalProperties": False,
            },
            handler=search_browser_selected,
        )
    )
    registry.register(
        ToolSpec(
            name="create_note",
            description=(
                "사용자가 명시적으로 메모 저장을 요청하면 프로젝트의 "
                "notes 폴더에 Markdown 메모를 생성한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "80자 이하의 짧은 메모 제목",
                    },
                    "content": {
                        "type": "string",
                        "description": "2000자 이하의 메모 내용",
                    },
                },
                "required": ["title", "content"],
                "additionalProperties": False,
            },
            handler=create_note,
        )
    )


    registry.register(
        ToolSpec(
            name="inspect_screen",
            description=(
                "현재 화면의 내용, 오류 메시지, 코드, 앱 UI 또는 시각적 "
                "상태를 실제로 보고 답변해야 할 때 사용한다. 사용자가 "
                "'화면 봐줘', '이 오류 뭐야', '지금 뭐가 보여'처럼 "
                "현재 화면을 기준으로 질문하면 추측하지 말고 이 도구를 "
                "호출한다. primary는 주 모니터, all은 모든 모니터다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "display": {
                        "type": "string",
                        "enum": ["primary", "all"],
                        "description": (
                            "보통 primary를 사용한다. 사용자가 모든 모니터 "
                            "또는 다른 화면까지 명시하면 all을 사용한다."
                        ),
                    }
                },
                "required": ["display"],
                "additionalProperties": False,
            },
            handler=inspect_screen,
        )
    )


    registry.register(
        ToolSpec(
            name="get_active_window",
            description=(
                "현재 Windows에서 사용자가 보고 있는 활성 창의 제목, "
                "프로세스와 창 ID를 조회한다."
            ),
            parameters=_empty_parameters(),
            handler=get_active_window,
        )
    )
    registry.register(
        ToolSpec(
            name="list_open_windows",
            description=(
                "현재 보이는 Windows 창 목록을 조회한다. 창 전환이나 "
                "최소화·최대화 전에 window_id를 찾을 때 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title_contains": {
                        "type": "string",
                        "description": (
                            "창 제목 필터. 전체 목록은 빈 문자열을 사용한다."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "반환할 최대 창 수",
                    },
                },
                "required": ["title_contains", "limit"],
                "additionalProperties": False,
            },
            handler=list_open_windows,
        )
    )
    registry.register(
        ToolSpec(
            name="focus_window",
            description=(
                "사용자가 명시적으로 요청한 기존 Windows 창을 앞으로 "
                "가져온다. list_open_windows가 반환한 window_id만 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "window_id": {
                        "type": "integer",
                        "description": "대상 창의 window_id",
                    }
                },
                "required": ["window_id"],
                "additionalProperties": False,
            },
            handler=focus_window,
        )
    )
    registry.register(
        ToolSpec(
            name="set_window_state",
            description=(
                "사용자가 명시적으로 요청한 Windows 창을 최소화, 최대화 "
                "또는 복원한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "window_id": {
                        "type": "integer",
                        "description": "대상 창의 window_id",
                    },
                    "state": {
                        "type": "string",
                        "enum": ["minimize", "maximize", "restore"],
                    },
                },
                "required": ["window_id", "state"],
                "additionalProperties": False,
            },
            handler=set_window_state,
        )
    )
    registry.register(
        ToolSpec(
            name="media_control",
            description=(
                "사용자가 명시적으로 요청했을 때 재생·일시정지, 다음 곡, "
                "이전 곡, 정지 또는 시스템 음량 키를 누른다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "play_pause",
                            "next_track",
                            "previous_track",
                            "stop",
                            "volume_up",
                            "volume_down",
                            "mute",
                        ],
                    }
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            handler=media_control,
        )
    )
    registry.register(
        ToolSpec(
            name="get_clipboard_text",
            description=(
                "사용자가 클립보드 내용을 읽어 달라고 명시적으로 요청한 "
                "경우에만 현재 텍스트를 조회한다."
            ),
            parameters=_empty_parameters(),
            handler=get_clipboard_text,
        )
    )
    registry.register(
        ToolSpec(
            name="set_clipboard_text",
            description=(
                "사용자가 명시적으로 복사를 요청한 텍스트를 Windows "
                "클립보드에 넣는다. 임의로 클립보드를 덮어쓰지 않는다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "maxLength": 10000,
                        "description": "클립보드에 저장할 텍스트",
                    }
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=set_clipboard_text,
        )
    )

    registry.register(
        ToolSpec(
            name="list_jarvis_browser_windows",
            description="Jarvis가 연 일반 브라우저 창 목록을 조회한다.",
            parameters=_empty_parameters(),
            handler=system_browser_controller.list_owned_windows,
        )
    )
    registry.register(
        ToolSpec(
            name="close_jarvis_browser_window",
            description="Jarvis가 직접 연 일반 브라우저 창만 닫는다.",
            parameters={
                "type": "object",
                "properties": {
                    "window_id": {
                        "type": ["integer", "null"],
                    }
                },
                "required": ["window_id"],
                "additionalProperties": False,
            },
            handler=system_browser_controller.close_owned_window,
        )
    )
    if google_calendar_client is not None and google_calendar_client.enabled:
        register_google_calendar_tools(registry, google_calendar_client)
        registry.register_closer(google_calendar_client.close)

    register_browser_tools(registry, browser_controller)
    registry.register_closer(browser_controller.close)
    registry.register_closer(system_browser_controller.close)

    return registry
