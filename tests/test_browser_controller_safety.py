from __future__ import annotations

import unittest

from src.browser import (
    validate_browser_url,
    validate_click_text,
    validate_field,
)


class BrowserControllerSafetyTests(unittest.TestCase):
    def test_http_and_https_urls_are_allowed(self) -> None:
        self.assertEqual(
            validate_browser_url("https://example.com/path"),
            "https://example.com/path",
        )

    def test_unsafe_url_schemes_are_blocked(self) -> None:
        for url in (
            "file:///C:/secret.txt",
            "javascript:alert(1)",
            "data:text/html,test",
        ):
            with self.assertRaises(ValueError):
                validate_browser_url(url)

    def test_sensitive_clicks_are_blocked(self) -> None:
        with self.assertRaises(ValueError):
            validate_click_text("결제하기")
        with self.assertRaises(ValueError):
            validate_click_text("Delete account")

    def test_sensitive_fields_are_blocked(self) -> None:
        with self.assertRaises(ValueError):
            validate_field("비밀번호", "secret")
        with self.assertRaises(ValueError):
            validate_field("Card number", "1234")


if __name__ == "__main__":
    unittest.main()
