from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.edge_cdp import (
    ManagedEdgeConfig,
    ManagedEdgeError,
    ManagedEdgeLauncher,
)


class _Process:
    pid = 4242

    def __init__(self) -> None:
        self.return_code = None
        self.terminated = False

    def poll(self):
        return self.return_code

    def terminate(self) -> None:
        self.terminated = True


def _cdp(port: int) -> dict:
    return {
        "Browser": "Edg/142",
        "webSocketDebuggerUrl": (
            f"ws://127.0.0.1:{port}"
            "/devtools/browser/a"
        ),
    }


class ManagedEdgeLauncherTests(
    unittest.TestCase
):
    def test_launches_dedicated_profile_and_waits(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            executable = (
                temp_path / "msedge.exe"
            )
            executable.write_bytes(b"edge")
            profile = (
                temp_path / "profile"
            )
            ready = {"value": False}
            commands: list[list[str]] = []
            process = _Process()

            def probe(endpoint, timeout):
                del timeout
                if (
                    ready["value"]
                    and endpoint.endswith(
                        ":9222"
                    )
                ):
                    return _cdp(9222)
                return None

            def launch(command):
                commands.append(command)
                ready["value"] = True
                return process

            launcher = ManagedEdgeLauncher(
                ManagedEdgeConfig(
                    executable_path=executable,
                    profile_directory=profile,
                    startup_timeout_seconds=5,
                    startup_poll_seconds=0.1,
                ),
                platform="win32",
                probe=probe,
                port_probe=lambda *_: False,
                process_launcher=launch,
                process_inspector=lambda *_: [],
                sleeper=lambda _: None,
            )

            result = launcher.ensure_running()

            self.assertTrue(result["ready"])
            self.assertTrue(result["launched"])
            self.assertTrue(profile.is_dir())
            self.assertTrue(
                (
                    profile
                    / "jarvis_edge_profile.json"
                ).is_file()
            )
            self.assertEqual(
                commands[0][0],
                str(executable.resolve()),
            )
            self.assertIn(
                "--remote-debugging-port=9222",
                commands[0],
            )
            self.assertIn(
                f"--user-data-dir={profile.resolve()}",
                commands[0],
            )
            self.assertIn(
                "--profile-directory=Default",
                commands[0],
            )

    def test_reuses_only_matching_profile(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            profile = (
                Path(temp) / "profile"
            ).resolve()

            launcher = ManagedEdgeLauncher(
                ManagedEdgeConfig(
                    profile_directory=profile,
                ),
                platform="win32",
                probe=lambda endpoint, _: (
                    _cdp(9222)
                    if endpoint.endswith(
                        ":9222"
                    )
                    else None
                ),
                process_inspector=lambda host, port: [
                    {
                        "pid": 22,
                        "name": "msedge.exe",
                        "exe": "C:/Edge/msedge.exe",
                        "cmdline": [
                            "msedge.exe",
                            (
                                "--remote-debugging-port="
                                f"{port}"
                            ),
                            (
                                "--user-data-dir="
                                f"{profile}"
                            ),
                        ],
                    }
                ],
                process_launcher=lambda _: (
                    self.fail(
                        "must not launch"
                    )
                ),
            )

            result = launcher.ensure_running()

            self.assertTrue(
                result["already_running"]
            )
            self.assertTrue(
                result["profile_verified"]
            )
            self.assertEqual(
                result["endpoint_url"],
                "http://127.0.0.1:9222",
            )

    def test_normal_edge_on_9222_uses_9223(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            executable = (
                temp_path / "msedge.exe"
            )
            executable.write_bytes(b"edge")
            profile = (
                temp_path / "jarvis"
            ).resolve()
            normal_profile = (
                temp_path / "normal"
            ).resolve()
            launched = {"value": False}
            commands: list[list[str]] = []

            def probe(endpoint, timeout):
                del timeout
                if endpoint.endswith(":9222"):
                    return _cdp(9222)
                if (
                    endpoint.endswith(":9223")
                    and launched["value"]
                ):
                    return _cdp(9223)
                return None

            def inspect(host, port):
                del host
                if port == 9222:
                    return [
                        {
                            "pid": 10,
                            "name": "msedge.exe",
                            "exe": "C:/Edge/msedge.exe",
                            "cmdline": [
                                "msedge.exe",
                                "--remote-debugging-port=9222",
                                (
                                    "--user-data-dir="
                                    f"{normal_profile}"
                                ),
                            ],
                        }
                    ]
                return []

            def launch(command):
                commands.append(command)
                launched["value"] = True
                return _Process()

            launcher = ManagedEdgeLauncher(
                ManagedEdgeConfig(
                    executable_path=executable,
                    profile_directory=profile,
                ),
                platform="win32",
                probe=probe,
                port_probe=lambda host, port, timeout: (
                    port == 9222
                ),
                process_inspector=inspect,
                process_launcher=launch,
                sleeper=lambda _: None,
            )

            result = launcher.ensure_running()

            self.assertTrue(result["launched"])
            self.assertTrue(
                result["fallback_port_used"]
            )
            self.assertEqual(
                result["endpoint_url"],
                "http://127.0.0.1:9223",
            )
            self.assertIn(
                "--remote-debugging-port=9223",
                commands[0],
            )
            self.assertIn(
                f"--user-data-dir={profile}",
                commands[0],
            )

    def test_environment_lookup_is_case_insensitive(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            program_files = Path(temp)
            executable = (
                program_files
                / "Microsoft"
                / "Edge"
                / "Application"
                / "msedge.exe"
            )
            executable.parent.mkdir(
                parents=True
            )
            executable.write_bytes(b"edge")

            launcher = ManagedEdgeLauncher(
                ManagedEdgeConfig(),
                environ={
                    "PROGRAMFILES(X86)": (
                        str(program_files)
                    ),
                },
            )

            self.assertEqual(
                launcher.resolve_executable(),
                executable.resolve(),
            )

    def test_no_free_port_raises_without_killing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            executable = (
                Path(temp) / "msedge.exe"
            )
            executable.write_bytes(b"edge")
            launcher = ManagedEdgeLauncher(
                ManagedEdgeConfig(
                    executable_path=executable,
                    profile_directory=(
                        Path(temp) / "profile"
                    ),
                    port_search_count=2,
                ),
                platform="win32",
                probe=lambda *_: None,
                port_probe=lambda *_: True,
                process_launcher=lambda _: (
                    self.fail(
                        "must not launch"
                    )
                ),
            )

            with self.assertRaises(
                ManagedEdgeError
            ):
                launcher.ensure_running()

    def test_non_windows_does_not_launch(
        self,
    ) -> None:
        launcher = ManagedEdgeLauncher(
            ManagedEdgeConfig(),
            platform="linux",
            probe=lambda *_: None,
        )
        with self.assertRaises(
            ManagedEdgeError
        ):
            launcher.ensure_running()

    def test_keep_running_does_not_terminate(
        self,
    ) -> None:
        process = _Process()
        launcher = ManagedEdgeLauncher(
            ManagedEdgeConfig(
                keep_running_on_exit=True
            )
        )
        launcher._process = process
        launcher.close()
        self.assertFalse(
            process.terminated
        )


if __name__ == "__main__":
    unittest.main()
