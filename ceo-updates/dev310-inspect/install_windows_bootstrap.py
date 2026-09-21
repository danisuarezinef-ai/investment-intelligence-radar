from __future__ import annotations

"""One-time Windows bootstrap whose purpose is to make future installs updates.

This installer never touches CEO user projects/data.  It places a stable bootstrap
under LocalAppData/Programs, installs an app-private Python runtime, preconfigures
the signed update channel, and optionally creates shortcuts.  Future application
versions remain side-by-side under the updater's user-data tree.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ceo_core.version_identity import current_version
APP_VERSION = current_version()
PY_RUNTIME_URL = "https://www.python.org/ftp/python/3.13.5/python-3.13.5-embeddable-amd64.zip"
PY_RUNTIME_SHA256 = "1786304c00011679a533d3644176b3694f2035b4cc37b0dc09dd226ad9ff5f26"
RUNTIME_REQUIREMENTS = (
    "httpx>=0.27",
    "cryptography>=44.0",
    "pydantic>=2.8",
    "psutil>=6.0",
    "playwright>=1.50",
    "pywinauto>=0.6.9; platform_system=='Windows'",
    "pyautogui>=0.9.54; platform_system=='Windows'",
)


def _local_appdata() -> Path:
    return Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def install_root() -> Path:
    return _local_appdata() / "Programs" / "CEO de IAs"


def data_root() -> Path:
    return _local_appdata() / "CEO de IAs"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _download_verified(url: str, expected_sha256: str, dest: Path) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    part.unlink(missing_ok=True)
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CEO-de-IAs-Bootstrap/1"})
        with urllib.request.urlopen(req, timeout=120) as resp, part.open("wb") as out:
            for block in iter(lambda: resp.read(1024 * 1024), b""):
                h.update(block); out.write(block)
            out.flush(); os.fsync(out.fileno())
        if h.hexdigest().lower() != expected_sha256.lower():
            raise RuntimeError("SHA-256 del runtime Python no coincide con el valor fijado")
        os.replace(part, dest)
    except Exception:
        part.unlink(missing_ok=True)
        raise


def _configure_embedded_python(runtime: Path) -> None:
    pth = next(runtime.glob("python*._pth"), None)
    if pth is None:
        raise RuntimeError("El runtime Python no contiene archivo ._pth")
    lines = [x.strip() for x in pth.read_text(encoding="utf-8").splitlines() if x.strip()]
    wanted = [".", "Lib\\site-packages", "import site"]
    for item in wanted:
        if item not in lines:
            lines.append(item)
    pth.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (runtime / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)


def _install_private_runtime(root: Path) -> Path:
    runtime = root / "runtime"
    py = runtime / "python.exe"
    if py.is_file():
        return py
    temp = Path(tempfile.mkdtemp(prefix="ceo-runtime-"))
    try:
        archive = temp / "python-runtime.zip"
        _download_verified(PY_RUNTIME_URL, PY_RUNTIME_SHA256, archive)
        candidate = temp / "runtime"
        candidate.mkdir()
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(candidate)
        _configure_embedded_python(candidate)
        # Use the already available bootstrap Python only to populate the private
        # target. It does not modify the global interpreter or global site-packages.
        target = candidate / "Lib" / "site-packages"
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade", "--target", str(target), *RUNTIME_REQUIREMENTS]
        cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        if cp.returncode != 0:
            raise RuntimeError("No se pudieron preparar dependencias del runtime privado:\n" + cp.stdout[-5000:])
        test = subprocess.run([str(candidate / "python.exe"), "-c", "import httpx,cryptography,pydantic,psutil; print('CEO_RUNTIME_OK')"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        if test.returncode != 0 or "CEO_RUNTIME_OK" not in test.stdout:
            raise RuntimeError("El runtime privado no superó su self-test:\n" + test.stdout[-3000:])
        if runtime.exists():
            shutil.rmtree(runtime)
        os.replace(candidate, runtime)
        return runtime / "python.exe"
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def _copy_payload(source: Path, root: Path) -> Path:
    target = root / "bootstrap"
    temp = root / (".bootstrap-staging-" + str(os.getpid()))
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True, exist_ok=True)
    exact = {"ABRIR_CEO.cmd", "pyproject.toml", "CEO_UPDATE_PACKAGE.json", "RC1_FREEZE_POLICY.json"}
    dirs = {"ceo_core", "scripts", "schemas", "ceo_app", "assets"}
    copied = 0
    for src in source.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(source)
        if any(part in {"__pycache__", ".pytest_cache", ".git"} for part in rel.parts):
            continue
        if rel.as_posix() not in exact and (not rel.parts or rel.parts[0] not in dirs):
            continue
        if src.name.upper().startswith(("ABRIR_CEO_", "VALIDAR_", "REANUDAR_")):
            continue
        if "private.key" in rel.as_posix().lower():
            continue
        dst = temp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst); copied += 1
    if copied < 20 or not (temp / "scripts" / "launch_current.py").is_file():
        raise RuntimeError("Payload bootstrap incompleto")
    backup = None
    if target.exists():
        backup = root / ("bootstrap.previous-" + str(os.getpid()))
        shutil.rmtree(backup, ignore_errors=True)
        os.replace(target, backup)
    try:
        os.replace(temp, target)
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        if backup and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    return target


def _write_root_launcher(root: Path) -> Path:
    launcher = root / "ABRIR_CEO.cmd"
    text = r'''@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CEO de IAs
set "PYEXE=%~dp0runtime\python.exe"
if not exist "%PYEXE%" (
  echo [BLOCKED] Runtime privado de CEO no encontrado.
  echo Diagnostico: "%LOCALAPPDATA%\CEO de IAs\diagnostics\startup-latest.json"
  pause
  exit /b 6
)
"%PYEXE%" -u "%~dp0bootstrap\scripts\launch_current.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [BLOCKED] CEO no pudo iniciarse. Codigo %RC%.
  echo Diagnostico: "%LOCALAPPDATA%\CEO de IAs\diagnostics\startup-latest.json"
  pause
)
exit /b %RC%
'''
    launcher.write_text(text, encoding="utf-8", newline="\r\n")
    return launcher


def _preconfigure_channel(source: Path) -> None:
    trust = json.loads((source / "ceo_core" / "update_trust.json").read_text(encoding="utf-8"))
    ch = trust.get("channel") if isinstance(trust.get("channel"), dict) else {}
    url = str(ch.get("manifest_url") or "").strip()
    if not url.startswith("https://"):
        raise RuntimeError("El bootstrap no contiene un canal HTTPS válido")
    updates = data_root() / "updates"
    updates.mkdir(parents=True, exist_ok=True)
    config = {
        "manifest_url": url,
        "channel": str(ch.get("name") or "stable"),
        "auto_check": True,
        "saved_at": "bootstrap-install",
    }
    tmp = updates / "config.json.tmp"
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, updates / "config.json")


def _create_shortcuts(root: Path, source_root: Path) -> None:
    # Normal user launch is console-free and uses the product icon. The diagnostic
    # ABRIR_CEO.cmd remains available for troubleshooting.
    try:
        from ceo_core.windows_shell import ensure_modern_windows_shell
        ensure_modern_windows_shell(source_root)
    except Exception:
        pass


def install(source: Path, *, with_runtime: bool = True, shortcuts: bool = True) -> dict:
    root = install_root()
    root.mkdir(parents=True, exist_ok=True)
    target = _copy_payload(source, root)
    runtime = _install_private_runtime(root) if with_runtime else None
    launcher = _write_root_launcher(root)
    _preconfigure_channel(target)
    if shortcuts:
        _create_shortcuts(root, target)
    receipt = {
        "app_version": APP_VERSION,
        "install_root": str(root),
        "bootstrap_root": str(target),
        "launcher": str(launcher),
        "runtime": str(runtime) if runtime else None,
        "data_root": str(data_root()),
        "user_data_preserved": True,
        "future_updates_in_app": True,
    }
    (root / "INSTALL_RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--skip-runtime", action="store_true")
    ap.add_argument("--no-shortcuts", action="store_true")
    ns = ap.parse_args()
    if os.name != "nt":
        print("[BLOCKED] Este instalador sólo debe ejecutarse en Windows.")
        return 6
    try:
        receipt = install(Path(ns.source).resolve(), with_runtime=not ns.skip_runtime, shortcuts=not ns.no_shortcuts)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"[BLOCKED] {type(exc).__name__}: {exc}")
        return 7


if __name__ == "__main__":
    raise SystemExit(main())
