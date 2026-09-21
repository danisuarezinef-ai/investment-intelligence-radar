from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.in_app_updater import InAppUpdater  # noqa: E402
from ceo_core.update_progress_telemetry_v2 import enrich_update_progress_v2  # noqa: E402
from ceo_core.update_failure_evidence_v1 import UpdateFailureEvidenceRecorderV1  # noqa: E402
from ceo_core.rollback_guarantee_v2 import verify_rollback_result_v2  # noqa: E402
from ceo_core.startup_watchdog_v3 import StartupWatchdogV3  # noqa: E402
from ceo_core.update_root_cause_triage_v1 import UpdateRootCauseTriageV1  # noqa: E402
from ceo_core.productive_smoke_gate_v1 import run_productive_smoke_gate_v1  # noqa: E402
from ceo_core.dual_activation_gate_v1 import evaluate_dual_activation_gate_v1  # noqa: E402


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            cp = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=5)
            return str(pid) in cp.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _launch(launcher: Path, *, log_path: Path | None = None) -> subprocess.Popen:
    if not launcher.is_file():
        raise FileNotFoundError(str(launcher))
    log_handle = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("ab", buffering=0)
    kwargs = {
        "cwd": str(launcher.parent),
        "stdout": log_handle if log_handle is not None else subprocess.DEVNULL,
        "stderr": subprocess.STDOUT if log_handle is not None else subprocess.DEVNULL,
    }
    # Prefer the Python launcher on every platform. This makes the restart bridge
    # deterministic and testable without relying on shell quoting semantics.
    python_launcher = launcher.parent / "scripts" / "launch_current.py"
    if python_launcher.is_file():
        env = os.environ.copy()
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(launcher.parent) + (os.pathsep + old_pythonpath if old_pythonpath else "")
        extra = {}
        if os.name == "nt":
            extra["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            extra["start_new_session"] = True
        proc = subprocess.Popen([sys.executable, "-u", str(python_launcher)], env=env, **extra, **kwargs)
    elif os.name == "nt":
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        proc = subprocess.Popen([comspec, "/d", "/c", str(launcher)], creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs)
    elif launcher.suffix.lower() in {".sh", ".bash"}:
        proc = subprocess.Popen(["bash", str(launcher)], start_new_session=True, **kwargs)
    else:
        proc = subprocess.Popen([str(launcher)], start_new_session=True, **kwargs)
    if log_handle is not None:
        setattr(proc, "_ceo_log_handle", log_handle)
    return proc


def _terminate_tree(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10)
            return
        except Exception:
            pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _status_url(root: Path, *, not_before: float) -> str | None:
    path = root / "CEO_REAL_WORK_INTERFACE_STATUS.json"
    try:
        stat = path.stat()
        if stat.st_mtime + 0.01 < not_before:
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("status") != "PASS":
            return None
        url = str(row.get("url") or "").strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            return None
        return url.rstrip("/")
    except Exception:
        return None



def _write_restart_progress(updater: InAppUpdater, phase: str, **fields) -> None:
    try:
        fields = enrich_update_progress_v2(phase, dict(fields))
        row = {
            "phase": phase,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "updated_at_epoch": time.time(),
            **fields,
        }
        InAppUpdater._atomic_json(updater.root / "restart-progress.json", row)
        if phase in {"rollback", "rolled_back"} or fields.get("reason"):
            UpdateFailureEvidenceRecorderV1(updater.root).record(
                phase, outcome="restart_supervision", reason=str(fields.get("reason") or ""), progress=row,
                current=updater.current_pointer(), previous=updater.previous_pointer(),
            )
    except Exception:
        pass

def supervise_activation(
    *,
    updater: InAppUpdater,
    version: str,
    activation_id: str,
    launcher: Path,
    fallback_launcher: Path,
    wait_pid: int = 0,
    health_timeout: float = 60.0,
) -> dict:
    _write_restart_progress(updater, "waiting_old_process", version=version, percent=10)
    deadline = time.time() + 45
    while wait_pid and time.time() < deadline and pid_exists(wait_pid):
        time.sleep(0.35)

    pointer = updater.current_pointer() or {}
    if str(pointer.get("version") or "") != version or str(pointer.get("activation_id") or "") != activation_id:
        raise RuntimeError("El puntero de activación cambió antes del reinicio")
    root = Path(str(pointer.get("root") or launcher.parent)).resolve()
    health_path = str(pointer.get("health_path") or "/api/health")
    if not health_path.startswith("/"):
        health_path = "/api/health"

    started_at = time.time()
    proc: subprocess.Popen | None = None
    last_error = "new version did not become healthy"
    try:
        child_log = updater.root / "restart-child-latest.log"
        _write_restart_progress(updater, "launching_new_version", version=version, percent=35, launcher=str(launcher), log=str(child_log))
        proc = _launch(launcher, log_path=child_log)
        watchdog = StartupWatchdogV3(deadline_seconds=max(5.0, health_timeout))
        watchdog_report = watchdog.observe(process_alive=True)
        _write_restart_progress(updater, "health_check", version=version, percent=55, pid=proc.pid, log=str(child_log), watchdog=watchdog_report.to_dict())
        while True:
            alive = proc.poll() is None
            watchdog_report = watchdog.observe(process_alive=alive, reason=last_error)
            if watchdog_report.state == "PROCESS_EXITED":
                last_error = f"new version exited early with code {proc.returncode}"
                break
            if watchdog_report.state == "CORE_HEALTH_TIMEOUT":
                last_error = f"core_health_timeout after {watchdog_report.elapsed_seconds}s"
                break
            base = _status_url(root, not_before=started_at)
            if base:
                try:
                    health = updater.verify_health_url(
                        base + health_path,
                        expected_version=version,
                        activation_id=activation_id,
                        timeout=3.0,
                    )
                    # DEV267: core health alone is necessary but not sufficient.
                    # Before committing the pointer, prove the candidate's local
                    # scheduler can still complete one productive unit. This uses
                    # a local mock provider only; external AI availability and spend
                    # can never decide activation health.
                    productive = run_productive_smoke_gate_v1()
                    dual_gate = evaluate_dual_activation_gate_v1(core_health=health, productive_smoke=productive)
                    if not dual_gate.get("commit_activation"):
                        raise RuntimeError("post_update_productive_smoke_failed")
                    confirmed = updater.confirm_health(version, activation_id=activation_id, health={**health, "productive_smoke": productive})
                    watchdog_report = watchdog.observe(process_alive=True, status_url_seen=True, health_confirmed=True)
                    _write_restart_progress(updater, "healthy", version=version, percent=100, pid=proc.pid, url=base, watchdog=watchdog_report.to_dict(), productive_smoke=productive)
                    return {"ok": True, "confirmed": confirmed, "url": base, "pid": proc.pid, "watchdog": watchdog_report.to_dict(), "productive_smoke": productive, "dual_activation_gate": dual_gate}
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    watchdog_report = watchdog.observe(process_alive=True, status_url_seen=True, reason=last_error)
            time.sleep(0.4)
    except Exception as exc:
        last_error = f"{type(exc).__name__}: {exc}"

    _terminate_tree(proc)
    _write_restart_progress(updater, "rollback", version=version, percent=80, reason=last_error)
    rollback = updater.rollback(reason=last_error, failed_version=version)
    rollback_guarantee = verify_rollback_result_v2(rollback, fallback_launcher=fallback_launcher)
    previous_launcher = rollback.get("launcher_path")
    restart = Path(previous_launcher) if previous_launcher else fallback_launcher
    rollback_proc = None
    try:
        if restart.is_file():
            rollback_proc = _launch(restart)
    except Exception:
        pass
    _write_restart_progress(updater, "rolled_back", version=version, percent=100, reason=last_error, rollback_pid=getattr(rollback_proc, "pid", None))
    triage = UpdateRootCauseTriageV1().classify({"phase": "health_check", "reason": last_error})
    result = {
        "ok": False,
        "rolled_back": True,
        "reason": last_error,
        "triage": triage,
        "watchdog": watchdog_report.to_dict() if "watchdog_report" in locals() else None,
        "rollback": rollback,
        "rollback_guarantee": rollback_guarantee,
        "rollback_pid": getattr(rollback_proc, "pid", None),
    }
    try:
        UpdateFailureEvidenceRecorderV1(updater.root).record(
            "rolled_back", outcome="rollback_verified" if rollback_guarantee.get("usable_recovery_path") else "rollback_path_unusable",
            reason=last_error, version=version, activation_id=activation_id,
            rollback_guarantee=rollback_guarantee,
        )
    except Exception:
        pass
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-pid", type=int, default=0)
    ap.add_argument("--launcher", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--activation-id", required=True)
    ap.add_argument("--fallback-launcher", required=True)
    ap.add_argument("--health-timeout", type=float, default=60.0)
    ns = ap.parse_args()

    updater = InAppUpdater(Path(ns.data_root))
    result = supervise_activation(
        updater=updater,
        version=ns.version,
        activation_id=ns.activation_id,
        launcher=Path(ns.launcher).resolve(),
        fallback_launcher=Path(ns.fallback_launcher).resolve(),
        wait_pid=ns.wait_pid,
        health_timeout=ns.health_timeout,
    )
    log = updater.root / "last-restart-supervision.json"
    try:
        InAppUpdater._atomic_json(log, result)
    except Exception:
        pass
    return 0 if result.get("ok") else 7


if __name__ == "__main__":
    raise SystemExit(main())
