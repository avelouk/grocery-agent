"""Jumbo agent config: site URL, credentials, browser path."""
import os
from pathlib import Path

SITE = "https://www.jumbo.cl"


def get_credentials() -> tuple[str, str]:
    """Return (email, password) from env. Load .env before calling."""
    return (
        os.environ.get("JUMBO_EMAIL", ""),
        os.environ.get("JUMBO_PASSWORD", ""),
    )


def get_browser_executable() -> str | None:
    """Browser path from BROWSER_EXECUTABLE_PATH or auto-detect Chromium on macOS."""
    path = os.environ.get("BROWSER_EXECUTABLE_PATH")
    if path and Path(path).exists():
        return path
    default = Path("/Applications/Chromium.app/Contents/MacOS/Chromium")
    return str(default) if default.exists() else None
