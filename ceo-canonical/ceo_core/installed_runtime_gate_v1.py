from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any


def inspect_installed_runtime_v1(
    updates_root: str | Path,
    *,
    min_free_bytes: int = 256 * 1024 * 1024,
    os_name: str | None = None,
    architecture: str | None = None,
    python_version: tuple[int, int] | None = None,
    free_bytes: int | None = None,
) -> dict[str, Any]:
    """Read-only admission snapshot for the currently installed Windows runtime.

    The function intentionally does not create files, repair pointers or mutate the
    installation.  Tests may override host facts so Windows rules can be qualified
    on non-Windows CI.
    """
    root = Path(updates_root)
    current_path = root / "current.json"
    current: dict[str, Any] = {}
    if current_path.is_file():
        try:
            import json
            row = json.loads(current_path.read_text(encoding="utf-8-sig"))
            if isinstance(row, dict):
                current = row
        except Exception:
            current = {}
    active_root = Path(str(current.get("root") or "")) if current.get("root") else None
    launcher = str(current.get("launcher") or "ABRIR_CEO.cmd")
    launcher_path = (active_root / launcher) if active_root else None
    host_os = (os_name or platform.system() or os.name).lower()
    arch = (architecture or platform.machine() or "unknown").lower()
    py = python_version or (sys.version_info.major, sys.version_info.minor)
    if free_bytes is None:
        try:
            free_bytes = int(shutil.disk_usage(root if root.exists() else Path.cwd()).free)
        except Exception:
            free_bytes = 0
    problems: list[str] = []
    if not current_path.is_file(): problems.append("current_pointer_missing")
    if not active_root or not active_root.is_dir(): problems.append("active_root_missing")
    if not launcher_path or not launcher_path.is_file(): problems.append("active_launcher_missing")
    if py < (3, 10): problems.append("python_too_old")
    if int(free_bytes or 0) < int(min_free_bytes): problems.append("insufficient_free_space")
    if host_os not in {"windows", "win32", "nt"}: problems.append("not_windows_host")
    if arch not in {"amd64", "x86_64", "arm64", "aarch64"}: problems.append("unsupported_architecture")
    return {
        "schema_version": 1,
        "ok": not problems,
        "read_only": True,
        "problems": problems,
        "current_version": str(current.get("version") or ""),
        "current_status": str(current.get("status") or ""),
        "active_root_exists": bool(active_root and active_root.is_dir()),
        "launcher_exists": bool(launcher_path and launcher_path.is_file()),
        "os": host_os,
        "architecture": arch,
        "python": f"{py[0]}.{py[1]}",
        "free_bytes": int(free_bytes or 0),
        "min_free_bytes": int(min_free_bytes),
        "side_effects_executed": False,
    }
