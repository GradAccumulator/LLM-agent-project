from __future__ import annotations

from dataclasses import dataclass
import json
import re
from time import perf_counter
from typing import Any, Callable

from src.tools import ToolExecutionResult, ToolRegistry


@dataclass(frozen=True, slots=True)
class FastPathConfig:
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class FastPathToolCall:
    name: str
    arguments: dict[str, Any]
    success: bool
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class FastPathResult:
    route: str
    success: bool
    reply: str
    elapsed_seconds: float
    tool_calls: tuple[FastPathToolCall, ...]


@dataclass(frozen=True, slots=True)
class _MatchedCommand:
    route: str
    executor: Callable[[], FastPathResult]


def _normalize(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def _payload(result: ToolExecutionResult) -> dict[str, Any]:
    try:
        loaded = json.loads(result.output)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _call_record(result: ToolExecutionResult) -> FastPathToolCall:
    return FastPathToolCall(
        name=result.name,
        arguments=result.arguments,
        success=result.success,
        elapsed_seconds=result.elapsed_seconds,
    )


class LocalCommandRouter:
    """Routes unambiguous Korean commands directly to local tools."""

    _APP_ALIASES = {
        "계산기": "calculator",
        "메모장": "notepad",
        "파일탐색기": "file_explorer",
        "탐색기": "file_explorer",
        "설정": "settings",
        "브라우저": "browser",
        "vscode": "vscode",
        "비주얼스튜디오코드": "vscode",
        "터미널": "terminal",
        "명령프롬프트": "terminal",
    }

    _SITE_ALIASES = {
        "유튜브": "youtube",
        "구글": "google",
        "네이버": "naver",
        "깃허브": "github",
        "github": "github",
        "챗지피티": "chatgpt",
        "chatgpt": "chatgpt",
        "오픈에이아이": "openai",
    }

    _MEDIA_COMMANDS = {
        "음악재생해줘": "play_pause",
        "음악재생": "play_pause",
        "음악일시정지해줘": "play_pause",
        "음악일시정지": "play_pause",
        "재생일시정지": "play_pause",
        "다음곡으로넘겨줘": "next_track",
        "다음곡": "next_track",
        "이전곡으로돌아가줘": "previous_track",
        "이전곡": "previous_track",
        "음악정지해줘": "stop",
        "음악정지": "stop",
        "볼륨올려줘": "volume_up",
        "음량올려줘": "volume_up",
        "볼륨내려줘": "volume_down",
        "음량내려줘": "volume_down",
        "음소거해줘": "mute",
        "음소거": "mute",
    }

    _TIME_COMMANDS = {
        "지금몇시야",
        "지금시간알려줘",
        "현재시간알려줘",
        "몇시야",
    }
    _DATE_COMMANDS = {
        "오늘며칠이야",
        "오늘날짜알려줘",
        "현재날짜알려줘",
        "오늘날짜뭐야",
    }
    _SYSTEM_COMMANDS = {
        "시스템상태알려줘",
        "컴퓨터상태알려줘",
        "컴퓨터상태어때",
        "시스템상태",
    }
    _ACTIVE_WINDOW_COMMANDS = {
        "현재창뭐야",
        "활성창뭐야",
        "지금무슨창이야",
        "현재활성창알려줘",
    }
    _WINDOW_LIST_COMMANDS = {
        "열린창목록보여줘",
        "열려있는창보여줘",
        "창목록보여줘",
    }
    _CLIPBOARD_READ_COMMANDS = {
        "클립보드내용읽어줘",
        "클립보드뭐들어있어",
        "클립보드내용알려줘",
    }
    _BROWSER_BACK_COMMANDS = {
        "브라우저뒤로가",
        "웹페이지뒤로가",
        "브라우저뒤로가줘",
    }
    _BROWSER_CLOSE_COMMANDS = {
        "브라우저닫아줘",
        "브라우저창닫아줘",
        "엣지닫아줘",
        "엣지창닫아줘",
        "크롬닫아줘",
        "크롬창닫아줘",
    }
    _AUTOMATION_BROWSER_CLOSE_COMMANDS = {
        "자동화브라우저닫아줘",
        "플레이라이트브라우저닫아줘",
    }
    _BROWSER_INFO_COMMANDS = {
        "현재웹페이지제목알려줘",
        "브라우저페이지정보알려줘",
        "현재페이지정보알려줘",
    }

    _SEARCH_PATTERNS = (
        re.compile(
            r"^(구글|네이버|유튜브)(?:에서|에)?\s*(.+?)\s*"
            r"(?:검색해줘|검색해|검색해주세요|찾아줘|찾아봐|찾아주세요)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(.+?)\s*(구글|네이버|유튜브)(?:에서|에)?\s*"
            r"(?:검색해줘|검색해|검색해주세요|찾아줘|찾아봐|찾아주세요)$",
            re.IGNORECASE,
        ),
    )

    _SAVED_ALIAS_OPEN_PATTERN = re.compile(
        r"^(.+?)(?:을|를)?\s*(?:열어줘|열어|켜줘|켜|실행해줘)$",
        re.IGNORECASE,
    )

    _GENERIC_SEARCH_PATTERN = re.compile(
        r"^(.+?)\s*(?:검색해줘|검색해|찾아줘|찾아봐)$",
        re.IGNORECASE,
    )

    _CLIPBOARD_WRITE_PATTERN = re.compile(
        r"^(.+?)(?:을|를)?\s*클립보드에\s*"
        r"(?:복사해줘|복사해|복사해주세요|저장해줘|저장해)$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        registry: ToolRegistry,
        config: FastPathConfig = FastPathConfig(),
    ) -> None:
        self.registry = registry
        self.config = config

    def _execute_one(
        self,
        route: str,
        tool_name: str,
        arguments: dict[str, Any],
        success_reply: Callable[[dict[str, Any]], str],
    ) -> FastPathResult:
        started = perf_counter()
        result = self.registry.execute(
            tool_name,
            json.dumps(arguments, ensure_ascii=False),
        )
        data = _payload(result)
        if result.success:
            reply = success_reply(data)
        else:
            reply = data.get("error") or "명령 실행에 실패했습니다."
        return FastPathResult(
            route=route,
            success=result.success,
            reply=reply,
            elapsed_seconds=perf_counter() - started,
            tool_calls=(_call_record(result),),
        )

    def _execute_window_state(
        self,
        route: str,
        state: str,
        reply: str,
    ) -> FastPathResult:
        started = perf_counter()
        active = self.registry.execute(
            "get_active_window",
            "{}",
        )
        calls = [_call_record(active)]
        active_data = _payload(active)
        if not active.success:
            return FastPathResult(
                route=route,
                success=False,
                reply=(
                    active_data.get("error")
                    or "현재 창을 찾지 못했습니다."
                ),
                elapsed_seconds=perf_counter() - started,
                tool_calls=tuple(calls),
            )

        window = active_data.get("window") or {}
        window_id = window.get("window_id")
        changed = self.registry.execute(
            "set_window_state",
            json.dumps(
                {"window_id": window_id, "state": state},
                ensure_ascii=False,
            ),
        )
        calls.append(_call_record(changed))
        changed_data = _payload(changed)
        return FastPathResult(
            route=route,
            success=changed.success,
            reply=(
                reply
                if changed.success
                else changed_data.get("error")
                or "창 상태를 변경하지 못했습니다."
            ),
            elapsed_seconds=perf_counter() - started,
            tool_calls=tuple(calls),
        )

    @staticmethod
    def _open_variants(alias: str) -> set[str]:
        return {
            f"{alias}켜줘",
            f"{alias}열어줘",
            f"{alias}실행해줘",
            f"{alias}켜",
            f"{alias}열어",
        }

    def match(self, text: str) -> _MatchedCommand | None:
        if not self.config.enabled:
            return None

        self.registry.begin_request(
            planning_required=False,
            max_steps=1,
            max_repair_attempts=0,
        )


        original = text.strip()
        normalized = _normalize(original)
        if not normalized:
            return None

        if normalized in self._TIME_COMMANDS:
            return _MatchedCommand(
                "time",
                lambda: self._execute_one(
                    "time",
                    "get_current_datetime",
                    {},
                    lambda data: f"지금은 {data.get('time', '?')}입니다.",
                ),
            )
        if normalized in self._DATE_COMMANDS:
            return _MatchedCommand(
                "date",
                lambda: self._execute_one(
                    "date",
                    "get_current_datetime",
                    {},
                    lambda data: (
                        f"오늘은 {data.get('date', '?')}입니다."
                    ),
                ),
            )
        if normalized in self._SYSTEM_COMMANDS:
            def status_reply(data: dict[str, Any]) -> str:
                memory = data.get("memory") or {}
                gpus = data.get("gpus") or []
                parts = [
                    f"CPU 사용률은 {data.get('cpu_percent', '?')}퍼센트",
                    f"메모리는 {memory.get('percent', '?')}퍼센트입니다",
                ]
                if gpus:
                    gpu = gpus[0]
                    parts.append(
                        f"GPU 사용률은 {gpu.get('usage_percent', '?')}퍼센트"
                    )
                return ", ".join(parts) + "."

            return _MatchedCommand(
                "system_status",
                lambda: self._execute_one(
                    "system_status",
                    "get_system_status",
                    {},
                    status_reply,
                ),
            )

        for alias, application in self._APP_ALIASES.items():
            if normalized in self._open_variants(alias):
                return _MatchedCommand(
                    f"open_application:{application}",
                    lambda application=application, alias=alias: self._execute_one(
                        f"open_application:{application}",
                        "open_application",
                        {"application": application},
                        lambda _data, alias=alias: f"{alias}를 열었습니다.",
                    ),
                )

        for alias, site in self._SITE_ALIASES.items():
            if normalized in self._open_variants(alias):
                return _MatchedCommand(
                    f"open_website:{site}",
                    lambda site=site, alias=alias: self._execute_one(
                        f"open_website:{site}",
                        "open_website",
                        {"site": site},
                        lambda _data, alias=alias: f"{alias}를 열었습니다.",
                    ),
                )

        memory_store = self.registry.memory_store
        alias_match = self._SAVED_ALIAS_OPEN_PATTERN.match(original)
        if alias_match and memory_store is not None:
            alias_name = alias_match.group(1).strip()
            if memory_store.resolve_alias(alias_name) is not None:
                return _MatchedCommand(
                    f"saved_alias:{alias_name}",
                    lambda alias_name=alias_name: self._execute_one(
                        f"saved_alias:{alias_name}",
                        "open_saved_alias",
                        {"alias": alias_name},
                        lambda data, alias_name=alias_name: (
                            f"{data.get('alias', alias_name)}을 열었습니다."
                        ),
                    ),
                )

        media_action = self._MEDIA_COMMANDS.get(normalized)
        if media_action is not None:
            replies = {
                "play_pause": "재생 상태를 전환했습니다.",
                "next_track": "다음 곡으로 넘겼습니다.",
                "previous_track": "이전 곡으로 이동했습니다.",
                "stop": "재생을 정지했습니다.",
                "volume_up": "음량을 한 단계 올렸습니다.",
                "volume_down": "음량을 한 단계 내렸습니다.",
                "mute": "음소거 상태를 전환했습니다.",
            }
            return _MatchedCommand(
                f"media:{media_action}",
                lambda: self._execute_one(
                    f"media:{media_action}",
                    "media_control",
                    {"action": media_action},
                    lambda _data: replies[media_action],
                ),
            )

        if normalized in self._ACTIVE_WINDOW_COMMANDS:
            return _MatchedCommand(
                "active_window",
                lambda: self._execute_one(
                    "active_window",
                    "get_active_window",
                    {},
                    lambda data: (
                        "현재 활성 창은 "
                        f"{(data.get('window') or {}).get('title', '알 수 없음')}입니다."
                    ),
                ),
            )
        if normalized in self._WINDOW_LIST_COMMANDS:
            def windows_reply(data: dict[str, Any]) -> str:
                windows = data.get("windows") or []
                titles = [
                    str(item.get("title"))
                    for item in windows[:5]
                    if item.get("title")
                ]
                if not titles:
                    return "표시할 열린 창을 찾지 못했습니다."
                return "열린 창은 " + ", ".join(titles) + "입니다."

            return _MatchedCommand(
                "window_list",
                lambda: self._execute_one(
                    "window_list",
                    "list_open_windows",
                    {"title_contains": "", "limit": 10},
                    windows_reply,
                ),
            )
        if normalized in {"현재창최소화해줘", "현재창최소화"}:
            return _MatchedCommand(
                "window_minimize",
                lambda: self._execute_window_state(
                    "window_minimize",
                    "minimize",
                    "현재 창을 최소화했습니다.",
                ),
            )
        if normalized in {"현재창최대화해줘", "현재창최대화"}:
            return _MatchedCommand(
                "window_maximize",
                lambda: self._execute_window_state(
                    "window_maximize",
                    "maximize",
                    "현재 창을 최대화했습니다.",
                ),
            )
        if normalized in {"현재창복원해줘", "현재창원래대로"}:
            return _MatchedCommand(
                "window_restore",
                lambda: self._execute_window_state(
                    "window_restore",
                    "restore",
                    "현재 창을 복원했습니다.",
                ),
            )

        if normalized in self._CLIPBOARD_READ_COMMANDS:
            return _MatchedCommand(
                "clipboard_read",
                lambda: self._execute_one(
                    "clipboard_read",
                    "get_clipboard_text",
                    {},
                    lambda data: (
                        "클립보드에는 "
                        f"{str(data.get('text', ''))[:500] or '텍스트가 없습니다'}"
                        "라고 들어 있습니다."
                    ),
                ),
            )

        clipboard_match = self._CLIPBOARD_WRITE_PATTERN.match(original)
        if clipboard_match:
            value = clipboard_match.group(1).strip()
            if value:
                return _MatchedCommand(
                    "clipboard_write",
                    lambda: self._execute_one(
                        "clipboard_write",
                        "set_clipboard_text",
                        {"text": value},
                        lambda _data: "클립보드에 복사했습니다.",
                    ),
                )

        if normalized in self._BROWSER_BACK_COMMANDS:
            return _MatchedCommand(
                "browser_back",
                lambda: self._execute_one(
                    "browser_back",
                    "browser_go_back",
                    {},
                    lambda _data: "브라우저에서 뒤로 이동했습니다.",
                ),
            )
        if normalized in self._BROWSER_CLOSE_COMMANDS:
            return _MatchedCommand(
                "normal_browser_close",
                lambda: self._execute_one(
                    "normal_browser_close",
                    "close_jarvis_browser_window",
                    {"window_id": None},
                    lambda data: (
                        f"{data.get('browser_name', '브라우저')} 창을 닫았습니다."
                    ),
                ),
            )
        if normalized in self._AUTOMATION_BROWSER_CLOSE_COMMANDS:
            return _MatchedCommand(
                "browser_close",
                lambda: self._execute_one(
                    "browser_close",
                    "browser_close",
                    {},
                    lambda _data: "자동화 브라우저를 닫았습니다.",
                ),
            )
        if normalized in self._BROWSER_INFO_COMMANDS:
            return _MatchedCommand(
                "browser_info",
                lambda: self._execute_one(
                    "browser_info",
                    "browser_get_page_info",
                    {"include_text": False},
                    lambda data: (
                        f"현재 페이지 제목은 {data.get('title', '알 수 없음')}입니다."
                    ),
                ),
            )

        for pattern in self._SEARCH_PATTERNS:
            match = pattern.match(original)
            if not match:
                continue
            first, second = match.groups()
            if first in {"구글", "네이버", "유튜브"}:
                service, query = first, second
            else:
                query, service = first, second
            engine = {
                "구글": "google",
                "네이버": "naver",
                "유튜브": "youtube",
            }[service]
            query = query.strip()
            if not query:
                return None
            return _MatchedCommand(
                f"search:{engine}",
                lambda: self._execute_one(
                    f"search:{engine}",
                    "search_browser",
                    {"engine": engine, "query": query},
                    lambda _data: f"{service}에서 {query}를 검색했습니다.",
                ),
            )

        generic_search = self._GENERIC_SEARCH_PATTERN.match(original)
        if generic_search and memory_store is not None:
            query = generic_search.group(1).strip()
            engine = (
                memory_store.get_preference("search_engine")
                or memory_store.get_preference("검색 엔진")
            )
            if engine is not None:
                engine = engine.strip().casefold()
                if engine in {"google", "naver", "youtube"} and query:
                    labels = {
                        "google": "구글",
                        "naver": "네이버",
                        "youtube": "유튜브",
                    }
                    return _MatchedCommand(
                        f"preferred_search:{engine}",
                        lambda query=query, engine=engine: self._execute_one(
                            f"preferred_search:{engine}",
                            "search_browser",
                            {"engine": engine, "query": query},
                            lambda _data, query=query, engine=engine: (
                                f"{labels[engine]}에서 {query}를 검색했습니다."
                            ),
                        ),
                    )

        return None

    def try_execute(
        self,
        text: str,
        *,
        on_match: Callable[[str], None] | None = None,
    ) -> FastPathResult | None:
        matched = self.match(text)
        if matched is None:
            return None
        if on_match is not None:
            on_match(matched.route)
        return matched.executor()
