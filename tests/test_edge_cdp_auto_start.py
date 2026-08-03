from __future__ import annotations

import unittest

from src.edge_cdp import (
    EdgeCdpConfig,
    EdgeCdpController,
)


class _Managed:
    def __init__(self) -> None:
        self.starts = 0
        self.closed = 0

    def ensure_running(self):
        self.starts += 1
        return {
            "ready": True,
            "launched": True,
        }

    def status(self):
        return {
            "ready": True,
        }

    def close(self):
        self.closed += 1


class _Browser:
    contexts = []

    def is_connected(self):
        return True


class _Playwright:
    def stop(self):
        pass


class EdgeCdpAutoStartTests(
    unittest.TestCase
):
    def test_explicit_managed_launcher_runs_before_attach(
        self,
    ) -> None:
        managed = _Managed()
        controller = EdgeCdpController(
            EdgeCdpConfig(
                auto_start=True
            ),
            managed_launcher=managed,
            connector=lambda *_: (
                _Playwright(),
                _Browser(),
            ),
        )

        status = controller.status()

        self.assertTrue(
            status["connected"]
        )
        self.assertEqual(
            managed.starts,
            1,
        )
        controller.close()
        self.assertEqual(
            managed.closed,
            1,
        )

    def test_injected_connector_skips_real_auto_start(
        self,
    ) -> None:
        controller = EdgeCdpController(
            EdgeCdpConfig(
                auto_start=True
            ),
            connector=lambda *_: (
                _Playwright(),
                _Browser(),
            ),
        )
        status = controller.status()
        self.assertTrue(
            status["connected"]
        )
        controller.close()


if __name__ == "__main__":
    unittest.main()
