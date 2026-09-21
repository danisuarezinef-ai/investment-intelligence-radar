from __future__ import annotations

"""Low-overhead Windows install/update/repair primitives for CEO de IAs.

Design goals:
- never require admin for the normal per-user install;
- never auto-spend or auto-install third-party software;
- stage every update before promotion;
- verify SHA-256 before promotion;
- keep a rollback snapshot;
- prefer prebuilt artifacts so weak Windows hosts do not need to compile CEO.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _which_any(*names: str) -> str | None:
    for name in names:
        p = shutil.which(name)
        if p:
            return p
    return None


@dataclass(slots=True)
class WindowsHostSnapshot:
    python: str | None
    git: str | None
    chrome: str | None
    powershell: str | None
    winget: str | None
    code: str | None
    install_root: str
    active_exists: bool
    rollback_available: bool
    staging_exists: bool
    lightweight_mode: bool
    assessed_at: float


class WindowsPaths:
    def __init__(self, base: str | Path | None = None) -> None:
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        self.base = Path(base) if base else local / "Programs" / "CEO de IAs"
        self.active = self.base / "current"
        self.staging = self.base / "staging"
        self.rollback = self.base / "rollback"
        self.data = local / "CEO de IAs"
        self.logs = self.data / "logs"
        self.venv = self.base / "venv"
        self.launcher = self.base / "CEO-de-IAs.cmd"
        for p in (self.base, self.logs):
            p.mkdir(parents=True, exist_ok=True)


class WindowsPreflight:
    def __init__(self, paths: WindowsPaths | None = None) -> None:
        self.paths = paths or WindowsPaths()

    @staticmethod
    def _chrome() -> str | None:
        p = _which_any("chrome", "chrome.exe")
        if p:
            return p
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    def snapshot(self) -> WindowsHostSnapshot:
        return WindowsHostSnapshot(
            python=_which_any("python", "py"),
            git=_which_any("git"),
            chrome=self._chrome(),
            powershell=_which_any("powershell", "pwsh"),
            winget=_which_any("winget"),
            code=_which_any("code", "code.cmd"),
            install_root=str(self.paths.base),
            active_exists=self.paths.active.exists(),
            rollback_available=self.paths.rollback.exists(),
            staging_exists=self.paths.staging.exists(),
            lightweight_mode=True,
            assessed_at=time.time(),
        )

    def install_plan(self) -> list[dict[str, Any]]:
        s = self.snapshot()
        plan: list[dict[str, Any]] = []
        for component, present, winget_id in (
            ("python", bool(s.python), "Python.Python.3.12"),
            ("git", bool(s.git), "Git.Git"),
            ("chrome", bool(s.chrome), "Google.Chrome"),
        ):
            if not present:
                plan.append({
                    "component": component,
                    "needed": True,
                    "winget_id": winget_id,
                    "automatic": False,
                    "human_approval_required": True,
                    "spend": False,
                })
        return plan


class WindowsPackageInstaller:
    def __init__(self, paths: WindowsPaths | None = None) -> None:
        self.paths = paths or WindowsPaths()

    @staticmethod
    def verify_package(package: Path, expected_sha256: str | None = None) -> dict[str, Any]:
        package = package.resolve()
        if not package.exists() or not package.is_file():
            raise FileNotFoundError(package)
        digest = _sha256(package)
        if expected_sha256 and digest.lower() != expected_sha256.lower():
            raise ValueError("package SHA-256 mismatch")
        return {"path": str(package), "sha256": digest, "size": package.stat().st_size}

    def stage_zip(self, package: Path, expected_sha256: str | None = None) -> dict[str, Any]:
        meta = self.verify_package(package, expected_sha256)
        if self.paths.staging.exists():
            shutil.rmtree(self.paths.staging)
        self.paths.staging.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(package) as z:
            root = self.paths.staging.resolve()
            for info in z.infolist():
                target = (root / info.filename).resolve()
                if target != root and root not in target.parents:
                    raise ValueError("unsafe ZIP path")
            z.extractall(root)
        (self.paths.staging / ".ceo_package.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return {**meta, "staged": True, "staging": str(self.paths.staging), "promoted": False}

    def promote_staged(self, *, human_confirmed: bool) -> dict[str, Any]:
        if not human_confirmed:
            raise PermissionError("explicit human confirmation required")
        if not self.paths.staging.exists():
            raise FileNotFoundError("no staged package")
        if self.paths.rollback.exists():
            shutil.rmtree(self.paths.rollback)
        if self.paths.active.exists():
            shutil.move(str(self.paths.active), str(self.paths.rollback))
        shutil.move(str(self.paths.staging), str(self.paths.active))
        return {"promoted": True, "active": str(self.paths.active), "rollback_available": self.paths.rollback.exists()}

    def rollback_active(self, *, human_confirmed: bool) -> dict[str, Any]:
        if not human_confirmed:
            raise PermissionError("explicit human confirmation required")
        if not self.paths.rollback.exists():
            raise FileNotFoundError("no rollback package")
        failed = self.paths.base / f"failed-{int(time.time())}"
        if self.paths.active.exists():
            shutil.move(str(self.paths.active), str(failed))
        shutil.move(str(self.paths.rollback), str(self.paths.active))
        return {"rolled_back": True, "active": str(self.paths.active), "failed_copy": str(failed) if failed.exists() else None}


class WindowsLightweightLauncher:
    def __init__(self, paths: WindowsPaths | None = None) -> None:
        self.paths = paths or WindowsPaths()

    def discover_entrypoint(self) -> list[str] | None:
        exe = self.paths.active / "CEO-de-IAs.exe"
        if exe.exists():
            return [str(exe)]
        for rel in ("run_ceo.bat", "run_ceo.cmd"):
            p = self.paths.active / rel
            if p.exists():
                return ["cmd", "/c", str(p)]
        py = self.paths.venv / "Scripts" / "python.exe"
        if not py.exists():
            py = Path(sys.executable)
        if (self.paths.active / "ceo_app" / "main.py").exists():
            return [str(py), "-m", "uvicorn", "ceo_app.main:app", "--host", "127.0.0.1", "--port", "8765"]
        return None

    def write_launcher(self) -> Path:
        cmd = self.discover_entrypoint()
        if not cmd:
            raise FileNotFoundError("CEO entrypoint not found in active install")
        quoted = " ".join(f'"{x}"' if " " in x else x for x in cmd)
        self.paths.launcher.write_text(
            "@echo off\r\nsetlocal EnableExtensions\r\n"
            "set \"PYTHONUTF8=1\"\r\nset \"PYTHONIOENCODING=utf-8\"\r\n"
            f"cd /d \"{self.paths.active}\"\r\n"
            f"start \"CEO de IAs\" /b {quoted}\r\n",
            encoding="utf-8",
            newline="",
        )
        return self.paths.launcher


class WindowsRepair:
    def __init__(self, paths: WindowsPaths | None = None) -> None:
        self.paths = paths or WindowsPaths()

    def path_hints(self) -> list[str]:
        candidates = [
            Path("C:/Program Files/Git/cmd"),
            Path("C:/Program Files/Git/bin"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/bin",
        ]
        return [str(p) for p in candidates if p.exists()]

    def diagnostic(self) -> dict[str, Any]:
        pre = WindowsPreflight(self.paths).snapshot()
        return {
            "preflight": asdict(pre),
            "path_hints": self.path_hints(),
            "python_utf8_recommended": True,
            "compile_on_host_required": False,
            "mobile_offload_preferred": True,
            "data_root": str(self.paths.data),
            "log_root": str(self.paths.logs),
            "timestamp": time.time(),
        }
