from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable
from urllib.request import urlopen


MAX_LOG_BYTES = 256 * 1024
DEFAULT_CDP_PORT = 9227
PORT_SCAN_SPAN = 20

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s\"']+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(cookie\s*[:=]\s*)[^\r\n]+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)((?:api[_-]?key|token|secret|password|passwd|session[_-]?id)\s*[:=]\s*)[^\s,;\"']+"), r"\1<REDACTED>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "<REDACTED>"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"), "<REDACTED>"),
]

REQUIRED_FIRST_TRIAL_FILES = (
    "windows_chatgpt_cdp_driver.ps1",
    "open_chatgpt_profile.ps1",
    "recipes/chatgpt_web.json",
    "run_b09_b14_physical_gate.ps1",
    "run_b15_b18_physical_gate.ps1",
    "run_b15_b18_physical_task.py",
    "run_b20_code_gate.ps1",
    "run_b20_code_gate.py",
    "run_b29_b30_full_field_gate.ps1",
    "finalize_browser_field.py",
    "programming_browser_loop.py",
    "browser_ai_worker.py",
    "simple_browser_task.py",
    "browser_task_state.py",
    "durable_browser_task.py",
    "sandbox_recovery.py",
    "real_code_candidate.py",
    "run_b38_real_ceo_candidate.py",
    "run_b38_real_ceo_candidate.ps1",
)


def redact_secrets(value: str) -> str:
    out = str(value or "")
    for pattern, replacement in _SECRET_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def bounded_text(value: str, max_bytes: int = MAX_LOG_BYTES) -> str:
    raw = redact_secrets(value).encode("utf-8", errors="replace")
    if len(raw) <= max_bytes:
        return raw.decode("utf-8", errors="replace")
    marker = b"\n<CEO_LOG_TRUNCATED>\n"
    keep = max(0, max_bytes - len(marker))
    return (raw[:keep] + marker).decode("utf-8", errors="replace")


def atomic_json(path: str | Path, row: dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    payload = json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        temp.write_text(payload, encoding="utf-8")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest()


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        try:
            s.bind((host, int(port)))
        except OSError:
            return False
    return True


def cdp_endpoint_looks_like_ceo(port: int, expected_profile: str | Path | None = None) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{int(port)}/json/version", timeout=0.5) as resp:
            row = json.loads(resp.read(128 * 1024).decode("utf-8"))
        browser = str(row.get("Browser") or "")
        ws = str(row.get("webSocketDebuggerUrl") or "")
        return bool(browser and ws)
    except Exception:
        return False


def choose_cdp_port(preferred: int = DEFAULT_CDP_PORT, span: int = PORT_SCAN_SPAN) -> tuple[int, str]:
    preferred = int(preferred)
    if is_port_free(preferred):
        return preferred, "preferred-free"
    if cdp_endpoint_looks_like_ceo(preferred):
        return preferred, "existing-cdp"
    for port in range(preferred + 1, preferred + max(1, int(span)) + 1):
        if is_port_free(port):
            return port, "fallback-free"
    raise RuntimeError("no safe CDP port available in bounded scan")


def find_browser_executable() -> str | None:
    names = ("chrome.exe", "msedge.exe") if os.name == "nt" else ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")
    for name in names:
        p = shutil.which(name)
        if p:
            return p
    if os.name == "nt":
        roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
        rels = (
            Path("Google/Chrome/Application/chrome.exe"),
            Path("Microsoft/Edge/Application/msedge.exe"),
        )
        for root in roots:
            if not root:
                continue
            for rel in rels:
                p = Path(root) / rel
                if p.is_file():
                    return str(p)
    return None


def find_tool(name: str) -> str | None:
    return shutil.which(name)


def windows_processes_using_profile(profile_dir: str | Path) -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    profile = str(Path(profile_dir).expanduser().resolve()).lower()
    script = (
        "$p=Get-CimInstance Win32_Process | "
        "Where-Object {$_.CommandLine -and ($_.Name -match 'chrome|msedge|python|powershell|cmd|wscript|cscript')} | "
        "Select-Object ProcessId,Name,CommandLine; "
        "$p | ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        data = json.loads(proc.stdout)
        if isinstance(data, dict):
            data = [data]
        out = []
        for row in data if isinstance(data, list) else []:
            cmd = str(row.get("CommandLine") or "")
            if profile in cmd.lower():
                out.append({
                    "pid": int(row.get("ProcessId") or 0),
                    "name": str(row.get("Name") or ""),
                    "command_line": bounded_text(cmd, 4000),
                })
        return out
    except Exception:
        return []


def profile_marker_status(profile_dir: str | Path) -> dict[str, Any]:
    profile = Path(profile_dir).expanduser().resolve()
    marker = profile / "CEO_BROWSER_PROFILE.json"
    session = profile / "CEO_BROWSER_SESSION.json"
    out = {
        "profile_dir": str(profile),
        "profile_exists": profile.exists(),
        "writable": False,
        "marker_present": marker.is_file(),
        "session_present": session.is_file(),
        "exclusive_profile": False,
        "session_ready": False,
    }
    try:
        profile.mkdir(parents=True, exist_ok=True)
        probe = profile / ".ceo-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        out["writable"] = True
    except Exception:
        pass
    if marker.is_file():
        try:
            row = json.loads(marker.read_text(encoding="utf-8-sig"))
            out["exclusive_profile"] = bool(row.get("exclusive_profile"))
        except Exception:
            pass
    if session.is_file():
        try:
            row = json.loads(session.read_text(encoding="utf-8-sig"))
            out["session_ready"] = bool(row.get("ok")) and row.get("status") == "SESSION_READY"
        except Exception:
            pass
    return out


def audit_first_trial_package(base_dir: str | Path) -> dict[str, Any]:
    root = Path(base_dir).resolve()
    missing = []
    hashes = {}
    for rel in REQUIRED_FIRST_TRIAL_FILES:
        path = root / rel
        if not path.is_file():
            missing.append(rel)
        else:
            hashes[rel] = sha256_file(path)
    return {
        "root": str(root),
        "required_count": len(REQUIRED_FIRST_TRIAL_FILES),
        "present_count": len(REQUIRED_FIRST_TRIAL_FILES) - len(missing),
        "missing": missing,
        "hashes": hashes,
        "ok": not missing,
    }


@dataclass
class Check:
    id: str
    ok: bool
    required: bool = True
    detail: str = ""
    status: str = "PASS"

    def __post_init__(self) -> None:
        if not self.ok:
            self.status = "FAIL" if self.required else "WARN"


@dataclass
class FirstTrialReport:
    schema_version: int = 1
    trial_id: str = ""
    created_at_epoch: int = 0
    status: str = "NO_GO"
    checks: list[dict[str, Any]] = field(default_factory=list)
    selected_cdp_port: int = 0
    evidence_dir: str = ""
    profile_dir: str = ""
    next_action: str = ""

    def finalize(self) -> None:
        required_fail = [x for x in self.checks if x.get("required") and not x.get("ok")]
        self.status = "GO" if not required_fail else "NO_GO"
        self.next_action = (
            "Run B29-B30 physical field gate. Do not run B38 automatically."
            if self.status == "GO"
            else "Correct failed preflight checks before any physical browser trial."
        )


def make_trial_id() -> str:
    return time.strftime("TRIAL-%Y%m%d-%H%M%S") + f"-{os.getpid()}"


def run_preflight(
    *,
    browser_ai_dir: str | Path,
    profile_dir: str | Path,
    evidence_dir: str | Path,
    preferred_port: int = DEFAULT_CDP_PORT,
) -> FirstTrialReport:
    root = Path(browser_ai_dir).resolve()
    profile = Path(profile_dir).expanduser().resolve()
    evidence = Path(evidence_dir).expanduser().resolve()
    evidence.mkdir(parents=True, exist_ok=True)

    report = FirstTrialReport(
        trial_id=make_trial_id(),
        created_at_epoch=int(time.time()),
        evidence_dir=str(evidence),
        profile_dir=str(profile),
    )

    def add(id_: str, ok: bool, detail: str, required: bool = True) -> None:
        report.checks.append(asdict(Check(id=id_, ok=ok, detail=bounded_text(detail, 8000), required=required)))

    package = audit_first_trial_package(root)
    add("package-manifest", package["ok"], json.dumps({k:v for k,v in package.items() if k != "hashes"}, ensure_ascii=False))

    py = find_tool("python.exe" if os.name == "nt" else "python3") or find_tool("python") or find_tool("py.exe")
    add("python", bool(py), py or "Python not found")
    git_tool = find_tool("git.exe" if os.name == "nt" else "git")
    add("git", bool(git_tool), git_tool or "Git not found")
    browser = find_browser_executable()
    add("browser", bool(browser), browser or "Chrome/Edge not found")

    try:
        port, reason = choose_cdp_port(preferred_port)
        report.selected_cdp_port = port
        add("cdp-port", True, f"{port} ({reason})")
    except Exception as exc:
        add("cdp-port", False, f"{type(exc).__name__}: {exc}")

    pstat = profile_marker_status(profile)
    add("profile-writable", bool(pstat["writable"]), json.dumps(pstat, ensure_ascii=False))
    if pstat["marker_present"]:
        add("exclusive-profile", bool(pstat["exclusive_profile"]), json.dumps(pstat, ensure_ascii=False))
    else:
        add("exclusive-profile", True, "Fresh CEO profile; marker will be created by login helper.", required=False)

    procs = windows_processes_using_profile(profile)
    duplicate_browser = [p for p in procs if re.search(r"chrome|msedge", p["name"], re.I)]
    add(
        "duplicate-owned-browser",
        len(duplicate_browser) <= 1,
        json.dumps(duplicate_browser, ensure_ascii=False),
        required=False,
    )

    try:
        stat = shutil.disk_usage(evidence)
        free_mb = stat.free // (1024 * 1024)
        add("disk-space", free_mb >= 256, f"free_mb={free_mb}")
    except Exception as exc:
        add("disk-space", False, str(exc), required=False)

    # Boundary assertions: first-trial orchestration may never itself promote code.
    joined = ""
    for rel in ("run_b29_b30_full_field_gate.ps1", "run_b38_real_ceo_candidate.py", "real_code_candidate.py"):
        p = root / rel
        if p.is_file():
            joined += "\n" + p.read_text(encoding="utf-8", errors="replace")
    add("no-openai-api", "api.openai.com" not in joined.lower() and "OPENAI_API_KEY" not in joined, "zero-API source boundary")
    add("no-automatic-promotion", "git push" not in joined.lower() and "git merge" not in joined.lower(), "no push/merge in first-trial candidate sources")
    add("separate-b38", True, "B29-B30 launcher is separate from B38 launcher; no automatic handoff.")

    report.finalize()
    atomic_json(evidence / "FIRST_TRIAL_PREFLIGHT.json", asdict(report))
    return report


def go_criteria(report: FirstTrialReport, field_state: dict[str, Any] | None = None) -> dict[str, Any]:
    preflight_go = report.status == "GO"
    field_verified = bool(field_state and field_state.get("BROWSER_FIELD_VERIFIED") is True)
    criteria = {
        "preflight_go": preflight_go,
        "field_verified": field_verified,
        "api_calls_required": 0 if not field_state else field_state.get("api_calls_required"),
        "production_promotion_allowed": False if not field_state else field_state.get("production_promotion_allowed"),
        "automatic_merge_allowed": False if not field_state else field_state.get("automatic_merge_allowed"),
        "first_autodevelopment_launch_allowed": bool(
            preflight_go
            and field_verified
            and int(field_state.get("api_calls_required", -1)) == 0
            and field_state.get("production_promotion_allowed") is False
            and field_state.get("automatic_merge_allowed") is False
        ) if field_state else False,
    }
    return criteria
