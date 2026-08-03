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
from typing import Any, Callable
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


class ManagedEdgeLauncher:
    """Starts a persistent, isolated Edge profile for Jarvis."""

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
        sleeper: Callable[[float], None] = sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.config = config
        self._platform = platform
        source_environ = os.environ if environ is None else environ
        self._environ = {
            str(key).casefold(): str(value)
            for key, value in source_environ.items()
        }
        self._probe = probe
        self._port_probe = port_probe
        self._process_launcher = (
            process_launcher
        )
        self._sleeper = sleeper
        self._clock = clock
        self._process: Any | None = None
        self._last_result: dict[
            str,
            Any,
        ] | None = None

    @property
    def profile_directory(self) -> Path:
        return (
            self.config
            .profile_directory
            .expanduser()
            .resolve()
        )

    @property
    def endpoint(self):
        return urlparse(
            self.config.endpoint_url
        )

    def _probe_endpoint(
        self,
    ) -> dict[str, Any] | None:
        return self._probe(
            self.config.endpoint_url,
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

    def command(
        self,
        executable: Path | None = None,
    ) -> list[str]:
        executable = (
            executable
            or self.resolve_executable()
        )
        port = self.endpoint.port
        if port is None:
            raise ManagedEdgeError(
                "CDP endpoint has no port."
            )

        profile = self.profile_directory
        command = [
            str(executable),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if self.config.restore_last_session:
            command.append(
                "--restore-last-session"
            )
        startup_url = (
            self.config.startup_url
            or ""
        ).strip()
        if startup_url:
            command.append(startup_url)
        return command

    def _metadata_path(self) -> Path:
        return (
            self.profile_directory
            / "jarvis_edge_launch.json"
        )

    def _write_metadata(
        self,
        *,
        executable: Path,
        command: list[str],
        pid: int | None,
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
            "endpoint_url": (
                self.config.endpoint_url
            ),
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

    def status(self) -> dict[str, Any]:
        payload = self._probe_endpoint()
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
            "ready": payload is not None,
            "browser": (
                payload.get("Browser")
                if payload
                else None
            ),
            "endpoint_url": (
                self.config.endpoint_url
            ),
            "auto_start": (
                self.config.auto_start
            ),
            "profile_directory": str(
                self.profile_directory
            ),
            "profile_exists": (
                self.profile_directory
                .is_dir()
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
        existing = self._probe_endpoint()
        if existing is not None:
            result = {
                "ready": True,
                "launched": False,
                "already_running": True,
                "browser": existing.get(
                    "Browser"
                ),
                "endpoint_url": (
                    self.config.endpoint_url
                ),
                "profile_directory": str(
                    self.profile_directory
                ),
                "launcher_pid": getattr(
                    self._process,
                    "pid",
                    None,
                ),
                "message": (
                    "Jarvis 전용 Edge가 이미 "
                    "CDP 연결 대기 중입니다."
                ),
            }
            self._last_result = result
            return result

        if self._platform != "win32":
            raise ManagedEdgeError(
                "Managed Microsoft Edge auto-start "
                "is available on Windows only."
            )

        host = (
            self.endpoint.hostname
            or "127.0.0.1"
        )
        port = self.endpoint.port
        if port is None:
            raise ManagedEdgeError(
                "CDP endpoint has no port."
            )

        if self._port_probe(
            host,
            port,
            0.3,
        ):
            raise ManagedEdgeError(
                f"Port {port} is already occupied, "
                "but it is not exposing a compatible "
                "Edge CDP /json/version endpoint. "
                "Change edge_cdp.endpoint_url or stop "
                "the conflicting process."
            )

        executable = (
            self.resolve_executable()
        )
        profile = self.profile_directory
        profile.mkdir(
            parents=True,
            exist_ok=True,
        )
        command = self.command(
            executable
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
        )

        deadline = (
            self._clock()
            + self.config
            .startup_timeout_seconds
        )
        payload = None
        while self._clock() < deadline:
            payload = self._probe_endpoint()
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

        result = {
            "ready": True,
            "launched": True,
            "already_running": False,
            "browser": payload.get(
                "Browser"
            ),
            "endpoint_url": (
                self.config.endpoint_url
            ),
            "profile_directory": str(
                profile
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
