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
            "endpoint_url": (
                "http://127.0.0.1:9223"
            ),
        }

    def status(self):
        return {
            "ready": True,
            "endpoint_url": (
                "http://127.0.0.1:9223"
            ),
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
    def test_selected_fallback_endpoint_is_used_for_attach(
        self,
    ) -> None:
        managed = _Managed()
        endpoints: list[str] = []

        def connector(endpoint, timeout):
            del timeout
            endpoints.append(endpoint)
            return (
                _Playwright(),
                _Browser(),
            )

        controller = EdgeCdpController(
            EdgeCdpConfig(
                auto_start=True
            ),
            managed_launcher=managed,
            connector=connector,
        )

        status = controller.status()

        self.assertTrue(
            status["connected"]
        )
        self.assertEqual(
            managed.starts,
            1,
        )
        self.assertEqual(
            endpoints,
            [
                "http://127.0.0.1:9223"
            ],
        )
        self.assertEqual(
            status["endpoint_url"],
            "http://127.0.0.1:9223",
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
