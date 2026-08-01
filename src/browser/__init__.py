from .controller import (
    BrowserAutomationConfig,
    BrowserInstallation,
    detect_installed_browsers,
    format_installed_browsers,
    BrowserController,
    validate_browser_url,
    validate_click_text,
    validate_field,
)

__all__ = [
    "BrowserAutomationConfig",
    "BrowserInstallation",
    "detect_installed_browsers",
    "format_installed_browsers",
    "BrowserController",
    "validate_browser_url",
    "SystemBrowserController",
    "SystemBrowserWindow",
    "validate_click_text",
    "validate_field",
]

from .system_controller import (
    SystemBrowserController,
    SystemBrowserWindow,
)
