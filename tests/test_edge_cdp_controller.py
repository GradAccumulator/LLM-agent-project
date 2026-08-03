from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.edge_cdp import (
    EdgeCdpConfig,
    EdgeCdpController,
    EdgeCdpError,
)


class _Locator:
    def __init__(self, text: str) -> None:
        self.text = text

    def inner_text(self) -> str:
        return self.text


class _Page:
    def __init__(
        self,
        title: str,
        url: str,
        body: str,
    ) -> None:
        self._title = title
        self.url = url
        self.body = body
        self.closed = False
        self.front = False

    def title(self) -> str:
        return self._title

    def is_closed(self) -> bool:
        return self.closed

    def bring_to_front(self) -> None:
        self.front = True

    def locator(self, selector: str):
        if selector != "body":
            raise AssertionError(selector)
        return _Locator(self.body)

    def screenshot(
        self,
        *,
        path: str,
        full_page: bool,
        type: str,
    ) -> None:
        del full_page, type
        Path(path).write_bytes(b"PNG")

    def close(
        self,
        *,
        run_before_unload: bool,
    ) -> None:
        self.closed = True


class _Context:
    def __init__(self, pages) -> None:
        self.pages = pages
        self.timeout = None

    def set_default_timeout(
        self,
        timeout: float,
    ) -> None:
        self.timeout = timeout


class _Browser:
    def __init__(self, pages) -> None:
        self.contexts = [
            _Context(pages)
        ]

    def is_connected(self) -> bool:
        return True


class _Playwright:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class EdgeCdpControllerTests(
    unittest.TestCase
):
    def _controller(self):
        self.temp = tempfile.TemporaryDirectory()
        pages = [
            _Page(
                "Example",
                "https://example.com/",
                "hello world",
            ),
            _Page(
                "Docs",
                "https://docs.example.com/",
                "documentation text",
            ),
        ]
        playwright = _Playwright()
        browser = _Browser(pages)

        def connector(endpoint, timeout):
            self.assertEqual(
                endpoint,
                "http://127.0.0.1:9222",
            )
            self.assertEqual(timeout, 5.0)
            return playwright, browser

        controller = EdgeCdpController(
            EdgeCdpConfig(
                screenshot_directory=Path(
                    self.temp.name
                )
            ),
            connector=connector,
        )
        return (
            controller,
            pages,
            playwright,
        )

    def tearDown(self) -> None:
        if hasattr(self, "temp"):
            self.temp.cleanup()

    def test_list_select_and_read_dom(self) -> None:
        controller, pages, _ = (
            self._controller()
        )

        listing = controller.list_tabs(
            limit=10
        )
        self.assertEqual(
            listing["count"],
            2,
        )
        ref = listing["tabs"][1][
            "tab_ref"
        ]

        selected = controller.select_tab(
            tab_ref=ref
        )
        self.assertTrue(
            selected["selected"]
        )
        self.assertTrue(pages[1].front)

        info = controller.get_page_info(
            tab_ref=None,
            include_text=True,
        )
        self.assertIn(
            "documentation",
            info["text"],
        )

    def test_capture_and_close(self) -> None:
        controller, _, playwright = (
            self._controller()
        )
        ref = (
            controller.list_tabs(
                limit=10
            )["tabs"][0]["tab_ref"]
        )

        capture = controller.capture_tab(
            tab_ref=ref,
            full_page=False,
        )
        self.assertTrue(
            Path(
                capture["image_path"]
            ).is_file()
        )

        result = controller.close_tab(
            tab_ref=ref
        )
        self.assertTrue(result["closed"])
        controller.close()
        self.assertTrue(
            playwright.stopped
        )

    def test_remote_endpoint_is_blocked(self) -> None:
        with self.assertRaises(
            ValueError
        ):
            EdgeCdpConfig(
                endpoint_url=(
                    "http://192.0.2.10:9222"
                )
            )

    def test_internal_page_text_is_blocked(self) -> None:
        page = _Page(
            "Settings",
            "edge://settings/",
            "",
        )
        controller = EdgeCdpController(
            EdgeCdpConfig(),
            connector=lambda *_: (
                _Playwright(),
                _Browser([page]),
            ),
        )
        ref = (
            controller.list_tabs(
                limit=10
            )["tabs"][0]["tab_ref"]
        )
        with self.assertRaises(
            EdgeCdpError
        ):
            controller.get_page_info(
                tab_ref=ref,
                include_text=True,
            )


if __name__ == "__main__":
    unittest.main()
