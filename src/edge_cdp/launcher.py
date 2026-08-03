from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from time import monotonic, sleep
from typing import Any, Callable, Iterable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen


class ManagedEdgeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ManagedEdgeConfig:
    endpoint_url: str = "http://127.0.0.1:9222"
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
    auto_select_port: bool = True
    port_search_count: int = 50

    def __post_init__(self) -> None:
        parsed = urlparse(
            self.endpoint_url.strip()
        )
        if parsed.scheme not in {
            "http",
            "https",
        }:
            raise ValueError(
                "Managed Edge auto-start requires an "
                "HTTP(S) CDP endpoint."
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
                "Managed Edge is restricted to a "
                "local CDP endpoint."
            )
        if parsed.port is None:
            raise ValueError(
                "Managed Edge endpoint must include "
                "a TCP port."
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
        if not 1 <= self.port_search_count <= 200:
            raise ValueError(
                "port_search_count must be between 1 and 200."
            )


def _default_probe(
    endpoint_url: str,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    url = (
        endpoint_url.rstrip("/")
        + "/json/version"
    )
    try:
        with urlopen(
            url,
            timeout=timeout_seconds,
        ) as response:
            payload = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )
    except (
        OSError,
        URLError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None

    if not isinstance(payload, dict):
        return None
    if not payload.get(
        "webSocketDebuggerUrl"
    ):
        return None
    return payload


def _default_port_probe(
    host: str,
    port: int,
    timeout_seconds: float,
) -> bool:
    try:
        with socket.create_connection(
            (host, port),
            timeout=timeout_seconds,
        ):
            return True
    except OSError:
        return False


def _default_process_launcher(
    command: list[str],
) -> subprocess.Popen[Any]:
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        )
    return subprocess.Popen(
        command,
        **kwargs,
    )


def _default_process_inspector(
    host: str,
    port: int,
) -> list[dict[str, Any]]:
    del host
    try:
        import psutil
    except ImportError:
        return []

    results: list[dict[str, Any]] = []
    seen: set[int] = set()
    try:
        connections = psutil.net_connections(
            kind="tcp"
        )
    except Exception:
        return []

    listen_value = getattr(
        psutil,
        "CONN_LISTEN",
        "LISTEN",
    )
    for connection in connections:
        local = getattr(
            connection,
            "laddr",
            None,
        )
        if not local:
            continue
        local_port = getattr(
            local,
            "port",
            None,
        )
        if local_port is None:
            try:
                local_port = local[1]
            except Exception:
                continue
        if int(local_port) != int(port):
            continue

        status = getattr(
            connection,
            "status",
            None,
        )
        if (
            status
            and status != listen_value
            and str(status).upper()
            != "LISTEN"
        ):
            continue

        pid = getattr(
            connection,
            "pid",
            None,
        )
        if not pid or int(pid) in seen:
            continue
        seen.add(int(pid))

        try:
            process = psutil.Process(
                int(pid)
            )
            results.append(
                {
                    "pid": int(pid),
                    "name": process.name(),
                    "exe": process.exe(),
                    "cmdline": (
                        process.cmdline()
                        or []
                    ),
                }
            )
        except Exception:
            results.append(
                {
                    "pid": int(pid),
                    "name": None,
                    "exe": None,
                    "cmdline": [],
                }
            )
    return results


def _clean_cli_path(value: str) -> str:
    return value.strip().strip(
        "\"'"
    )


def _argument_value(
    arguments: Iterable[str],
    name: str,
) -> str | None:
    items = [
        str(item)
        for item in arguments
    ]
    prefix = name + "="
    for index, item in enumerate(items):
        if item.casefold().startswith(
            prefix.casefold()
        ):
            return _clean_cli_path(
                item[len(prefix):]
            )
        if (
            item.casefold()
            == name.casefold()
            and index + 1 < len(items)
        ):
            return _clean_cli_path(
                items[index + 1]
            )
    return None


def _normalized_path(value: str | Path) -> str:
    return str(
        Path(value)
        .expanduser()
        .resolve(
            strict=False
        )
    ).rstrip("\\/").casefold()


class ManagedEdgeLauncher:
    """Starts and verifies a dedicated Edge profile for Jarvis."""

    def __init__(
        self,
        config: ManagedEdgeConfig = (
            ManagedEdgeConfig()
        ),
        *,
        platform: str = sys.platform,
        environ: dict[str, str] | None = None,
        probe: Callable[
            [str, float],
            dict[str, Any] | None,
        ] = _default_probe,
        port_probe: Callable[
            [str, int, float],
            bool,
        ] = _default_port_probe,
        process_launcher: Callable[
            [list[str]],
            Any,
        ] = _default_process_launcher,
        process_inspector: Callable[
            [str, int],
            list[dict[str, Any]],
        ] = _default_process_inspector,
        sleeper: Callable[[float], None] = sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.config = config
        self._platform = platform

        # Windows environment-variable names are case-insensitive.
        # Converting os.environ to a normal dict removes that behavior,
        # so normalize all keys before reading ProgramFiles values.
        source_environ = (
            os.environ
            if environ is None
            else environ
        )
        self._environ = {
            str(key).casefold(): str(value)
            for key, value
            in source_environ.items()
        }

        self._probe = probe
        self._port_probe = port_probe
        self._process_launcher = (
            process_launcher
        )
        self._process_inspector = (
            process_inspector
        )
        self._sleeper = sleeper
        self._clock = clock
        self._process: Any | None = None
        self._last_result: (
            dict[str, Any] | None
        ) = None
        self._active_endpoint_url: (
            str | None
        ) = None

    @property
    def profile_directory(self) -> Path:
        return (
            self.config
            .profile_directory
            .expanduser()
            .resolve()
        )

    @property
    def preferred_endpoint_url(self) -> str:
        return self.config.endpoint_url.rstrip(
            "/"
        )

    @property
    def active_endpoint_url(self) -> str:
        return (
            self._active_endpoint_url
            or self.preferred_endpoint_url
        )

    @property
    def endpoint(self):
        return urlparse(
            self.active_endpoint_url
        )

    def _endpoint_for_port(
        self,
        port: int,
    ) -> str:
        parsed = urlparse(
            self.preferred_endpoint_url
        )
        host = (
            parsed.hostname
            or "127.0.0.1"
        )
        if ":" in host and not host.startswith(
            "["
        ):
            host = f"[{host}]"
        return (
            f"{parsed.scheme}://"
            f"{host}:{int(port)}"
        )

    def _candidate_endpoints(
        self,
    ) -> tuple[str, ...]:
        parsed = urlparse(
            self.preferred_endpoint_url
        )
        preferred_port = parsed.port
        if preferred_port is None:
            raise ManagedEdgeError(
                "CDP endpoint has no port."
            )
        count = (
            self.config.port_search_count
            if self.config.auto_select_port
            else 1
        )
        return tuple(
            self._endpoint_for_port(
                preferred_port + offset
            )
            for offset in range(count)
        )

    def _probe_endpoint(
        self,
        endpoint_url: str | None = None,
    ) -> dict[str, Any] | None:
        return self._probe(
            (
                endpoint_url
                or self.active_endpoint_url
            ),
            min(
                1.0,
                self.config
                .startup_poll_seconds,
            ),
        )

    def _candidate_executables(
        self,
    ) -> list[Path]:
        explicit = (
            self.config.executable_path
        )
        candidates: list[Path] = []
        if explicit is not None:
            candidates.append(
                explicit.expanduser()
            )

        program_x86 = self._environ.get(
            "programfiles(x86)"
        )
        program_files = self._environ.get(
            "programfiles"
        )
        local_app_data = self._environ.get(
            "localappdata"
        )

        if program_x86:
            candidates.append(
                Path(program_x86)
                / "Microsoft"
                / "Edge"
                / "Application"
                / "msedge.exe"
            )
        if program_files:
            candidates.append(
                Path(program_files)
                / "Microsoft"
                / "Edge"
                / "Application"
                / "msedge.exe"
            )
        if local_app_data:
            candidates.extend(
                [
                    Path(local_app_data)
                    / "Microsoft"
                    / "Edge"
                    / "Application"
                    / "msedge.exe",
                    Path(local_app_data)
                    / "Microsoft"
                    / "Edge SxS"
                    / "Application"
                    / "msedge.exe",
                ]
            )

        found = shutil.which(
            "msedge.exe"
        ) or shutil.which(
            "msedge"
        )
        if found:
            candidates.append(
                Path(found)
            )

        unique: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(
                candidate.resolve(
                    strict=False
                )
            ).casefold()
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return unique

    def resolve_executable(self) -> Path:
        for candidate in (
            self._candidate_executables()
        ):
            if candidate.is_file():
                return candidate.resolve()

        explicit = (
            self.config.executable_path
        )
        if explicit is not None:
            raise ManagedEdgeError(
                "Configured Microsoft Edge executable "
                f"does not exist: {explicit}"
            )
        raise ManagedEdgeError(
            "Microsoft Edge executable was not found. "
            "Set edge_cdp.executable_path or "
            "--edge-cdp-executable."
        )

    def _endpoint_processes(
        self,
        endpoint_url: str,
    ) -> list[dict[str, Any]]:
        parsed = urlparse(
            endpoint_url
        )
        port = parsed.port
        if port is None:
            return []
        host = (
            parsed.hostname
            or "127.0.0.1"
        )
        try:
            return list(
                self._process_inspector(
                    host,
                    int(port),
                )
            )
        except Exception:
            return []

    def _ownership(
        self,
        endpoint_url: str,
    ) -> dict[str, Any]:
        expected_profile = (
            _normalized_path(
                self.profile_directory
            )
        )
        parsed = urlparse(
            endpoint_url
        )
        expected_port = parsed.port
        processes = (
            self._endpoint_processes(
                endpoint_url
            )
        )

        public_processes: list[
            dict[str, Any]
        ] = []
        for process in processes:
            arguments = [
                str(item)
                for item in (
                    process.get(
                        "cmdline"
                    )
                    or []
                )
            ]
            profile_value = (
                _argument_value(
                    arguments,
                    "--user-data-dir",
                )
            )
            port_value = (
                _argument_value(
                    arguments,
                    "--remote-debugging-port",
                )
            )
            profile_matches = False
            if profile_value:
                try:
                    profile_matches = (
                        _normalized_path(
                            profile_value
                        )
                        == expected_profile
                    )
                except Exception:
                    profile_matches = False

            port_matches = (
                str(port_value)
                == str(expected_port)
            )
            name = str(
                process.get("name")
                or ""
            )
            exe = str(
                process.get("exe")
                or ""
            )
            edge_process = (
                name.casefold()
                == "msedge.exe"
                or Path(exe).name.casefold()
                == "msedge.exe"
            )

            public_processes.append(
                {
                    "pid": process.get(
                        "pid"
                    ),
                    "name": (
                        name or None
                    ),
                    "profile_directory": (
                        profile_value
                    ),
                    "remote_debugging_port": (
                        port_value
                    ),
                    "profile_matches": (
                        profile_matches
                    ),
                }
            )
            if (
                edge_process
                and profile_matches
                and port_matches
            ):
                return {
                    "managed": True,
                    "owner_pid": process.get(
                        "pid"
                    ),
                    "owner_profile_directory": (
                        profile_value
                    ),
                    "processes": (
                        public_processes
                    ),
                }

        return {
            "managed": False,
            "owner_pid": None,
            "owner_profile_directory": None,
            "processes": public_processes,
        }

    def _discover_existing_managed(
        self,
    ) -> tuple[
        str,
        dict[str, Any],
        dict[str, Any],
    ] | None:
        for endpoint_url in (
            self._candidate_endpoints()
        ):
            payload = (
                self._probe_endpoint(
                    endpoint_url
                )
            )
            if payload is None:
                continue
            ownership = self._ownership(
                endpoint_url
            )
            if ownership["managed"]:
                self._active_endpoint_url = (
                    endpoint_url
                )
                return (
                    endpoint_url,
                    payload,
                    ownership,
                )
        return None

    def _select_launch_endpoint(
        self,
    ) -> tuple[
        str,
        list[dict[str, Any]],
    ]:
        conflicts: list[
            dict[str, Any]
        ] = []
        for endpoint_url in (
            self._candidate_endpoints()
        ):
            payload = (
                self._probe_endpoint(
                    endpoint_url
                )
            )
            ownership = (
                self._ownership(
                    endpoint_url
                )
                if payload is not None
                else {
                    "managed": False,
                    "processes": [],
                }
            )
            if (
                payload is not None
                and ownership.get(
                    "managed"
                )
            ):
                self._active_endpoint_url = (
                    endpoint_url
                )
                return (
                    endpoint_url,
                    conflicts,
                )

            parsed = urlparse(
                endpoint_url
            )
            host = (
                parsed.hostname
                or "127.0.0.1"
            )
            port = parsed.port
            if port is None:
                continue

            occupied = (
                payload is not None
                or self._port_probe(
                    host,
                    int(port),
                    0.3,
                )
            )
            if occupied:
                conflicts.append(
                    {
                        "endpoint_url": (
                            endpoint_url
                        ),
                        "cdp_detected": (
                            payload is not None
                        ),
                        "managed_profile": (
                            ownership.get(
                                "managed",
                                False,
                            )
                        ),
                        "processes": (
                            ownership.get(
                                "processes",
                                [],
                            )
                        ),
                    }
                )
                continue

            self._active_endpoint_url = (
                endpoint_url
            )
            return (
                endpoint_url,
                conflicts,
            )

        raise ManagedEdgeError(
            "No free local CDP port was found in "
            f"{self.config.port_search_count} attempts "
            f"starting at {self.preferred_endpoint_url}. "
            "Stop the conflicting process or change "
            "edge_cdp.endpoint_url."
        )

    def command(
        self,
        executable: Path | None = None,
        *,
        endpoint_url: str | None = None,
    ) -> list[str]:
        executable = (
            executable
            or self.resolve_executable()
        )
        selected_endpoint = (
            endpoint_url
            or self.active_endpoint_url
        )
        parsed = urlparse(
            selected_endpoint
        )
        port = parsed.port
        if port is None:
            raise ManagedEdgeError(
                "CDP endpoint has no port."
            )

        profile = self.profile_directory
        return [
            str(executable),
            (
                "--remote-debugging-address="
                "127.0.0.1"
            ),
            (
                "--remote-debugging-port="
                f"{port}"
            ),
            (
                "--user-data-dir="
                f"{profile}"
            ),
            "--profile-directory=Default",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            *(
                ["--restore-last-session"]
                if (
                    self.config
                    .restore_last_session
                )
                else []
            ),
            *(
                [
                    self.config
                    .startup_url
                    .strip()
                ]
                if (
                    self.config
                    .startup_url
                    and self.config
                    .startup_url
                    .strip()
                )
                else []
            ),
        ]

    def _metadata_path(self) -> Path:
        return (
            self.profile_directory
            / "jarvis_edge_launch.json"
        )

    def _marker_path(self) -> Path:
        return (
            self.profile_directory
            / "jarvis_edge_profile.json"
        )

    def _write_marker(self) -> None:
        payload = {
            "managed_by": (
                "LLM-agent-project"
            ),
            "profile_directory": str(
                self.profile_directory
            ),
        }
        self._marker_path().write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _write_metadata(
        self,
        *,
        executable: Path,
        command: list[str],
        pid: int | None,
        endpoint_url: str,
    ) -> None:
        payload = {
            "started_at": (
                datetime.now()
                .astimezone()
                .isoformat(
                    timespec="seconds"
                )
            ),
            "executable_path": str(
                executable
            ),
            "profile_directory": str(
                self.profile_directory
            ),
            "preferred_endpoint_url": (
                self.preferred_endpoint_url
            ),
            "endpoint_url": endpoint_url,
            "pid": pid,
            "command": command,
        }
        path = self._metadata_path()
        try:
            path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _own_process_is_running(self) -> bool:
        if self._process is None:
            return False
        try:
            return self._process.poll() is None
        except Exception:
            return False

    def _reuse_current_process(
        self,
    ) -> dict[str, Any] | None:
        if not self._own_process_is_running():
            return None
        payload = self._probe_endpoint(
            self.active_endpoint_url
        )
        if payload is None:
            return None
        return {
            "ready": True,
            "launched": False,
            "already_running": True,
            "browser": payload.get("Browser"),
            "preferred_endpoint_url": (
                self.preferred_endpoint_url
            ),
            "endpoint_url": (
                self.active_endpoint_url
            ),
            "fallback_port_used": (
                self.active_endpoint_url
                != self.preferred_endpoint_url
            ),
            "profile_directory": str(
                self.profile_directory
            ),
            "profile_verified": True,
            "owner_pid": getattr(
                self._process,
                "pid",
                None,
            ),
            "launcher_pid": getattr(
                self._process,
                "pid",
                None,
            ),
            "message": (
                "현재 Jarvis 프로세스가 시작한 "
                "전용 Edge 세션을 재사용했습니다."
            ),
        }

    def status(self) -> dict[str, Any]:
        own_process = (
            self._reuse_current_process()
        )
        if own_process is not None:
            endpoint_url = str(
                own_process["endpoint_url"]
            )
            payload = {
                "Browser": own_process.get(
                    "browser"
                )
            }
            ownership = {
                "managed": True,
                "owner_pid": (
                    own_process.get(
                        "owner_pid"
                    )
                ),
                "processes": [],
            }
        else:
            discovered = (
                self._discover_existing_managed()
            )
            if discovered is not None:
                (
                    endpoint_url,
                    payload,
                    ownership,
                ) = discovered
            else:
                endpoint_url = (
                    self.active_endpoint_url
                )
                payload = (
                    self._probe_endpoint(
                        endpoint_url
                    )
                )
                ownership = (
                    self._ownership(
                        endpoint_url
                    )
                    if payload is not None
                    else {
                        "managed": False,
                        "processes": [],
                    }
                )

        executable: str | None = None
        executable_error: str | None = None
        try:
            executable = str(
                self.resolve_executable()
            )
        except ManagedEdgeError as exc:
            executable_error = str(exc)

        process_running: bool | None = None
        if self._process is not None:
            try:
                process_running = (
                    self._process.poll()
                    is None
                )
            except Exception:
                process_running = None

        return {
            "managed": True,
            "platform": self._platform,
            "ready": (
                payload is not None
                and ownership.get(
                    "managed",
                    False,
                )
            ),
            "browser": (
                payload.get("Browser")
                if payload
                else None
            ),
            "preferred_endpoint_url": (
                self.preferred_endpoint_url
            ),
            "endpoint_url": endpoint_url,
            "fallback_port_used": (
                endpoint_url
                != self.preferred_endpoint_url
            ),
            "profile_verified": (
                ownership.get(
                    "managed",
                    False,
                )
            ),
            "profile_directory": str(
                self.profile_directory
            ),
            "profile_exists": (
                self.profile_directory
                .is_dir()
            ),
            "profile_marker_exists": (
                self._marker_path()
                .is_file()
            ),
            "owner_pid": (
                ownership.get(
                    "owner_pid"
                )
            ),
            "detected_processes": (
                ownership.get(
                    "processes",
                    []
                )
            ),
            "auto_start": (
                self.config.auto_start
            ),
            "auto_select_port": (
                self.config.auto_select_port
            ),
            "executable_path": executable,
            "executable_error": (
                executable_error
            ),
            "launcher_pid": getattr(
                self._process,
                "pid",
                None,
            ),
            "launcher_process_running": (
                process_running
            ),
            "restore_last_session": (
                self.config
                .restore_last_session
            ),
            "keep_running_on_exit": (
                self.config
                .keep_running_on_exit
            ),
            "last_launch": (
                self._last_result
            ),
        }

    def ensure_running(
        self,
    ) -> dict[str, Any]:
        own_process = (
            self._reuse_current_process()
        )
        if own_process is not None:
            self._last_result = own_process
            return own_process

        discovered = (
            self._discover_existing_managed()
        )
        if discovered is not None:
            (
                endpoint_url,
                payload,
                ownership,
            ) = discovered
            result = {
                "ready": True,
                "launched": False,
                "already_running": True,
                "browser": payload.get(
                    "Browser"
                ),
                "preferred_endpoint_url": (
                    self.preferred_endpoint_url
                ),
                "endpoint_url": (
                    endpoint_url
                ),
                "fallback_port_used": (
                    endpoint_url
                    != self.preferred_endpoint_url
                ),
                "profile_directory": str(
                    self.profile_directory
                ),
                "profile_verified": True,
                "owner_pid": (
                    ownership.get(
                        "owner_pid"
                    )
                ),
                "launcher_pid": getattr(
                    self._process,
                    "pid",
                    None,
                ),
                "message": (
                    "Jarvis 전용 Edge 프로필을 "
                    "확인하고 기존 CDP 세션을 "
                    "재사용했습니다."
                ),
            }
            self._last_result = result
            return result

        if self._platform != "win32":
            raise ManagedEdgeError(
                "Managed Microsoft Edge auto-start "
                "is available on Windows only."
            )

        (
            endpoint_url,
            conflicts,
        ) = self._select_launch_endpoint()

        # _select_launch_endpoint can discover a managed instance
        # while scanning, so reuse it instead of launching again.
        payload = self._probe_endpoint(
            endpoint_url
        )
        ownership = (
            self._ownership(
                endpoint_url
            )
            if payload is not None
            else {
                "managed": False,
            }
        )
        if (
            payload is not None
            and ownership.get(
                "managed"
            )
        ):
            return self.ensure_running()

        executable = (
            self.resolve_executable()
        )
        profile = self.profile_directory
        profile.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._write_marker()
        command = self.command(
            executable,
            endpoint_url=endpoint_url,
        )

        try:
            self._process = (
                self._process_launcher(
                    command
                )
            )
        except Exception as exc:
            raise ManagedEdgeError(
                "Could not start Microsoft Edge: "
                f"{str(exc).strip() or type(exc).__name__}"
            ) from exc

        pid = getattr(
            self._process,
            "pid",
            None,
        )
        self._write_metadata(
            executable=executable,
            command=command,
            pid=pid,
            endpoint_url=endpoint_url,
        )

        deadline = (
            self._clock()
            + self.config
            .startup_timeout_seconds
        )
        payload = None
        while self._clock() < deadline:
            payload = self._probe_endpoint(
                endpoint_url
            )
            if payload is not None:
                break

            try:
                return_code = (
                    self._process.poll()
                )
            except Exception:
                return_code = None
            if return_code is not None:
                raise ManagedEdgeError(
                    "Microsoft Edge exited before "
                    "the CDP endpoint became ready. "
                    f"Exit code: {return_code}."
                )
            self._sleeper(
                self.config
                .startup_poll_seconds
            )

        if payload is None:
            raise ManagedEdgeError(
                "Microsoft Edge started, but the CDP "
                "endpoint did not become ready before "
                f"{self.config.startup_timeout_seconds:.1f}s. "
                "Check edge://policy for "
                "RemoteDebuggingAllowed and confirm that "
                "security software is not blocking the port."
            )

        ownership = self._ownership(
            endpoint_url
        )
        # A newly launched process is still trusted when Windows
        # temporarily withholds command-line inspection. Blind reuse
        # is the dangerous path; new launches always contain the
        # dedicated --user-data-dir in `command`.
        profile_verified = bool(
            ownership.get("managed")
        )
        result = {
            "ready": True,
            "launched": True,
            "already_running": False,
            "browser": payload.get(
                "Browser"
            ),
            "preferred_endpoint_url": (
                self.preferred_endpoint_url
            ),
            "endpoint_url": endpoint_url,
            "fallback_port_used": (
                endpoint_url
                != self.preferred_endpoint_url
            ),
            "profile_directory": str(
                profile
            ),
            "profile_verified": (
                profile_verified
            ),
            "owner_pid": (
                ownership.get(
                    "owner_pid"
                )
            ),
            "executable_path": str(
                executable
            ),
            "launcher_pid": pid,
            "restore_last_session": (
                self.config
                .restore_last_session
            ),
            "keep_running_on_exit": (
                self.config
                .keep_running_on_exit
            ),
            "port_conflicts": conflicts,
            "command": command,
            "message": (
                "Jarvis 전용 Edge 프로필을 "
                "remote debugging이 활성화된 "
                "상태로 시작했습니다."
            ),
        }
        self._last_result = result
        return result

    def close(self) -> None:
        if (
            self.config.keep_running_on_exit
            or self._process is None
        ):
            self._process = None
            return

        try:
            if self._process.poll() is None:
                self._process.terminate()
        except Exception:
            pass
        self._process = None
