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

            probes = [
                None,
                None,
                {
                    "Browser": "Edg/142",
                    "webSocketDebuggerUrl": (
                        "ws://127.0.0.1:9222/devtools/browser/a"
                    ),
                },
            ]
            commands: list[list[str]] = []
            process = _Process()

            launcher = ManagedEdgeLauncher(
                ManagedEdgeConfig(
                    executable_path=executable,
                    profile_directory=profile,
                    startup_timeout_seconds=5,
                    startup_poll_seconds=0.1,
                ),
                platform="win32",
                probe=lambda *_: (
                    probes.pop(0)
                    if probes
                    else {
                        "Browser": "Edg/142",
                        "webSocketDebuggerUrl": "ws://ready",
                    }
                ),
                port_probe=lambda *_: False,
                process_launcher=lambda command: (
                    commands.append(command)
                    or process
                ),
                sleeper=lambda _: None,
            )

            result = launcher.ensure_running()

            self.assertTrue(result["ready"])
            self.assertTrue(result["launched"])
            self.assertTrue(profile.is_dir())
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
                "--restore-last-session",
                commands[0],
            )

    def test_reuses_existing_endpoint(
        self,
    ) -> None:
        launches = []
        launcher = ManagedEdgeLauncher(
            ManagedEdgeConfig(),
            platform="win32",
            probe=lambda *_: {
                "Browser": "Edg/142",
                "webSocketDebuggerUrl": "ws://ready",
            },
            process_launcher=lambda command: (
                launches.append(command)
            ),
        )

        result = launcher.ensure_running()

        self.assertTrue(
            result["already_running"]
        )
        self.assertFalse(
            result["launched"]
        )
        self.assertEqual(launches, [])

    def test_port_collision_is_not_killed(
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
