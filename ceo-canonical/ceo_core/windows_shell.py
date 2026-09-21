from __future__ import annotations

"""Windows shell integration for a console-free CEO launch experience.

The diagnostic .cmd launcher remains available, but normal user shortcuts target a
small VBScript wrapper that starts CEO through pythonw.exe without a console window.
All operations are best-effort and limited to the current user's local install and
shortcuts; failures never block CEO runtime startup.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _local_appdata() -> Path:
    return Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def _install_root() -> Path:
    return _local_appdata() / "Programs" / "CEO de IAs"


def _desktop_dir() -> Path:
    if os.name != "nt":
        return Path.home() / "Desktop"
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        # CSIDL_DESKTOPDIRECTORY = 0x0010
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    except Exception:
        pass
    return Path(os.getenv("USERPROFILE") or str(Path.home())) / "Desktop"


def _start_menu_dir() -> Path:
    roaming = Path(os.getenv("APPDATA") or (_local_appdata().parent / "Roaming"))
    return roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _write_hidden_launcher(install_root: Path) -> Path:
    launcher = install_root / "CEO_DE_IAS.vbs"
    diagnostic_launcher = install_root / "ABRIR_CEO.cmd"
    # Run the proven diagnostic launcher hidden. This preserves normal python.exe
    # stdout/stderr semantics while WScript keeps the console window invisible.
    text = (
        'Option Explicit\r\n'
        'Dim sh, cmd\r\n'
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'cmd = Chr(34) & "{str(diagnostic_launcher).replace(chr(34), chr(34)+chr(34))}" & Chr(34)\r\n'
        'sh.Run cmd, 0, False\r\n'
    )
    launcher.write_text(text, encoding="utf-8", newline="")
    return launcher


def _copy_icon(source_root: Path, install_root: Path) -> Path | None:
    src = source_root / "assets" / "CEO_DE_IAS.ico"
    if not src.is_file():
        return None
    dst = install_root / "CEO_DE_IAS.ico"
    try:
        shutil.copy2(src, dst)
        return dst
    except Exception:
        return None


def _create_shortcut(link: Path, *, vbs: Path, install_root: Path, icon: Path | None) -> bool:
    ps = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not ps:
        return False
    link.parent.mkdir(parents=True, exist_ok=True)
    wscript = Path(os.getenv("WINDIR") or r"C:\Windows") / "System32" / "wscript.exe"
    def q(value: str) -> str:
        return value.replace("'", "''")
    icon_line = f"$s.IconLocation='{q(str(icon))},0';" if icon else ""
    script = (
        "$w=New-Object -ComObject WScript.Shell;"
        f"$s=$w.CreateShortcut('{q(str(link))}');"
        f"$s.TargetPath='{q(str(wscript))}';"
        f"$s.Arguments='\"{q(str(vbs))}\"';"
        f"$s.WorkingDirectory='{q(str(install_root))}';"
        f"{icon_line}"
        "$s.Description='CEO de IAs - orquestador autónomo';"
        "$s.Save()"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cp = subprocess.run(
        [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
        creationflags=flags,
    )
    return cp.returncode == 0 and link.is_file()


def ensure_modern_windows_shell(source_root: Path) -> dict[str, Any]:
    """Ensure icon + console-free shortcuts for the current-user install.

    This is intentionally idempotent and fail-soft. It never changes the update
    trust root, projects, or active version pointer.
    """
    result: dict[str, Any] = {"supported": os.name == "nt", "ok": False, "changes": []}
    if os.name != "nt":
        return result
    try:
        install_root = _install_root()
        install_root.mkdir(parents=True, exist_ok=True)
        diagnostic_launcher = install_root / "ABRIR_CEO.cmd"
        runtime = install_root / "runtime" / "python.exe"
        bootstrap = install_root / "bootstrap" / "scripts" / "launch_current.py"
        if not diagnostic_launcher.is_file() or not runtime.is_file() or not bootstrap.is_file():
            result["reason"] = "installed launcher/runtime/bootstrap not found"
            return result
        vbs = _write_hidden_launcher(install_root)
        result["changes"].append("hidden_launcher")
        icon = _copy_icon(Path(source_root), install_root)
        if icon:
            result["changes"].append("modern_icon")
        desktop_link = _desktop_dir() / "CEO de IAs.lnk"
        start_link = _start_menu_dir() / "CEO de IAs.lnk"
        desktop_ok = _create_shortcut(desktop_link, vbs=vbs, install_root=install_root, icon=icon)
        start_ok = _create_shortcut(start_link, vbs=vbs, install_root=install_root, icon=icon)
        if desktop_ok:
            result["changes"].append("desktop_shortcut")
        if start_ok:
            result["changes"].append("start_menu_shortcut")
        result.update({
            "ok": bool(desktop_ok and start_ok),
            "launcher": str(vbs),
            "icon": str(icon) if icon else None,
            "desktop_shortcut": str(desktop_link),
            "start_shortcut": str(start_link),
            "console_free": True,
        })
        try:
            receipt = _local_appdata() / "CEO de IAs" / "diagnostics" / "shell-integration-latest.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
