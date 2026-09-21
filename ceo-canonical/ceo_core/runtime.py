from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if frozen() and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def _platform_user_data_root() -> Path:
    """Return a per-user writable data directory, never the source/bundle tree.

    This matters both for installed builds and for development/test processes running
    under a different account than the checkout owner. The application bundle is
    read-only from CEO's point of view; DBs, checkpoints, profiles and validation
    evidence belong to the OS user-data area.
    """
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "CEO de IAs"
    base = Path(os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / "ceo-de-ias"


def user_data_root() -> Path:
    override = os.getenv("CEO_DATA_DIR")
    root = Path(override).expanduser() if override else _platform_user_data_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return root
    except OSError:
        # Restricted CI/sandbox fallback. It is deliberately outside the bundle tree.
        # Installed desktop builds should normally never need this branch.
        fallback = Path(tempfile.gettempdir()) / f"ceo-de-ias-{getattr(os, 'getuid', lambda: 'user')()}"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def configure_playwright_runtime() -> Path | None:
    explicit = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if explicit:
        return Path(explicit)
    if frozen():
        candidate = Path(sys.executable).resolve().parent / "playwright-browsers"
        if candidate.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
            return candidate
    return None
