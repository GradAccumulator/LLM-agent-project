from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import quote_plus
import webbrowser

from .registry import ToolRegistry, ToolSpec


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


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

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
            handler=open_application,
        )
    )
    registry.register(
        ToolSpec(
            name="open_website",
            description=(
                "허용 목록에 있는 웹사이트를 기본 브라우저에서 연다."
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
            handler=open_website,
        )
    )
    registry.register(
        ToolSpec(
            name="search_browser",
            description=(
                "사용자가 명시적으로 검색을 요청했을 때 Google, Naver "
                "또는 YouTube 검색 결과를 기본 브라우저에서 연다."
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
            handler=search_browser,
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

    return registry
