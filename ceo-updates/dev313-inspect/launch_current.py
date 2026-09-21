from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ceo_core.startup_diagnostics import StartupDiagnostics
from ceo_core.in_app_updater import InAppUpdater

STATUS = ROOT / "CEO_LAUNCHER_STATUS.json"
FAILURE = ROOT / "CEO_LAUNCHER_FAILURE.txt"
DIAGNOSTICS = StartupDiagnostics()


def user_data_root() -> Path:
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "CEO de IAs"
    return Path(os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "ceo-de-ias"


def _probe_existing_ceo() -> str | None:
    for port in range(8765, 8781):
        url = f"http://127.0.0.1:{port}"
        try:
            req = urllib.request.Request(url + "/api/health", headers={"User-Agent": "CEO-de-IAs-Launcher/1"})
            with urllib.request.urlopen(req, timeout=0.45) as resp:
                raw = resp.read(512 * 1024)
            row = json.loads(raw.decode("utf-8"))
            if isinstance(row, dict) and row.get("ok") is True and str(row.get("version") or "").strip():
                return url
        except Exception:
            continue
    return None


def _open_existing_as_app(url: str) -> str:
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        for exe in candidates:
            try:
                if exe.is_file():
                    subprocess.Popen(
                        [str(exe), f"--app={url}", "--start-maximized"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    return str(exe)
            except Exception:
                pass
    webbrowser.open(url, new=1)
    return "default-browser"


def _write_status(payload: dict) -> None:
    row = dict(payload)
    row.setdefault("generated_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    row.setdefault("production_verified", False)
    try:
        STATUS.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    try:
        DIAGNOSTICS.record(str(row.get("status") or "UNKNOWN"), component="launcher", **{k: v for k, v in row.items() if k != "status"})
    except Exception:
        pass


def _safe_pointer() -> tuple[Path, Path] | None:
    """Return (root, launcher) only for a valid activated update.

    Invalid/stale pointers must never stop CEO from opening; the bundled version is
    the guaranteed fallback.
    """
    pointer = user_data_root() / "updates" / "current.json"
    try:
        row = json.loads(pointer.read_text(encoding="utf-8"))
        root_text = str(row.get("root") or "").strip()
        launcher_text = str(row.get("launcher") or "ABRIR_CEO.cmd").strip() or "ABRIR_CEO.cmd"
        if not root_text:
            return None
        root = Path(root_text).expanduser().resolve()
        launcher = (root / launcher_text).resolve()
        # Require a real staged/installed payload. A dead pointer is ignored.
        if not root.is_dir() or not launcher.is_file():
            return None
        return root, launcher
    except Exception:
        return None


def _python_entry(root: Path) -> Path | None:
    # The dependency-light work-mode server is the canonical Windows entrypoint.
    p = root / "scripts" / "ceo_stdlib_work_mode.py"
    return p if p.is_file() else None


def _run_python_entry(root: Path, entry: Path) -> int:
    env = os.environ.copy()
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) + (os.pathsep + old if old else "")
    print(f"[CEO] Version root: {root}")
    print(f"[CEO] Entry point: {entry}")
    print(f"[CEO] Python: {sys.executable}")
    sys.stdout.flush()
    return subprocess.call([sys.executable, "-u", str(entry)], cwd=str(root), env=env)


def _run_batch(root: Path, launcher: Path) -> int:
    if os.name != "nt":
        return subprocess.call([str(launcher)], cwd=str(root))
    comspec = os.environ.get("COMSPEC") or "cmd.exe"
    # The launcher path is passed as its own argv item. Avoid /S + CALL here:
    # that combination can preserve escaped quotes around paths with spaces and
    # make CMD report the quoted path as an unknown command.
    print(f"[CEO] Launcher fallback: {launcher}")
    sys.stdout.flush()
    return subprocess.call([comspec, "/d", "/c", str(launcher)], cwd=str(root))


def main() -> int:
    try:
        # Normal shortcut behavior is single-instance: if CEO is already healthy,
        # open/focus that backend in an app-style browser window instead of
        # starting a second scheduler on another localhost port.
        existing = _probe_existing_ceo()
        if existing:
            browser = _open_existing_as_app(existing)
            _write_status({
                "status": "EXISTING_INSTANCE_OPENED",
                "url": existing,
                "browser": browser,
                "single_instance": True,
            })
            return 0

        # Heal stale .part/extraction directories and a cut-over that never
        # completed health confirmation. Fresh pending activations are preserved.
        updater = InAppUpdater(user_data_root())
        recovery = updater.recover_interrupted_update()
        activated = _safe_pointer()
        if activated is None:
            root = ROOT
            source = "bundled-fallback"
            launcher = ROOT / "ABRIR_CEO_DEV19.cmd"
        else:
            root, launcher = activated
            source = "activated-update"

        entry = _python_entry(root)
        _write_status({
            "status": "STARTING",
            "source": source,
            "root": str(root),
            "launcher": str(launcher),
            "python_entry": str(entry) if entry else None,
            "update_recovery": recovery,
        })

        # Avoid nested ABRIR_CEO.cmd -> launch_current.py -> ABRIR_CEO.cmd loops.
        # When the standard Python entry exists, execute it directly with the same
        # interpreter that already proved usable by reaching this script.
        if entry is not None:
            rc = _run_python_entry(root, entry)
        elif launcher.is_file():
            rc = _run_batch(root, launcher)
        else:
            print(f"[BLOCKED] No se encontró un entrypoint CEO válido en {root}")
            rc = 6

        _write_status({
            "status": "EXITED" if rc == 0 else "BLOCKED",
            "returncode": rc,
            "source": source,
            "root": str(root),
            "launcher": str(launcher),
            "python_entry": str(entry) if entry else None,
        })
        return int(rc)
    except KeyboardInterrupt:
        _write_status({"status": "STOPPED_BY_USER", "returncode": 130})
        return 130
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
        try:
            FAILURE.write_text(text, encoding="utf-8")
        except Exception:
            pass
        try:
            DIAGNOSTICS.exception(exc, component="launcher")
        except Exception:
            pass
        _write_status({"status": "BLOCKED", "error": str(exc), "failure_file": str(FAILURE)})
        print(f"[BLOCKED] {exc}")
        print(f"[CEO] Diagnóstico: {FAILURE}")
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
