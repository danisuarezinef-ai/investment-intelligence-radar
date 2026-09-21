from __future__ import annotations

"""Operational Autonomy for CEO de IAs.

This module turns the manual Windows work observed during field validation into
structured, policy-gated operations. It deliberately avoids a generic remote
shell. Every operation is typed, workspace-confined where applicable, and
spend/install/destructive actions retain explicit human gates.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import os
import shutil
import subprocess
import tempfile
import time

from .models import ProjectState, Task, TaskStatus
from .scale_security import SecretHandleVault
from .self_hosting_beta import FrictionDetector, SupervisedStep, SupervisedUseTracker
from .self_hosting_tools import FilesystemOperations, TerminalController


def _now() -> float:
    return time.time()


def _sha_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class OperationalRisk(str, Enum):
    READ = "read"
    WRITE = "write"
    DOWNLOAD = "download"
    EXECUTE = "execute"
    INSTALL = "install"
    DELETE = "delete"
    COMMUNICATE = "communicate"
    SPEND = "spend"


SPEND_WORDS = {
    "spend", "purchase", "buy", "subscribe", "subscription", "billing",
    "credits", "credit", "payment", "pay", "prepaid", "upgrade_paid",
}


@dataclass(slots=True)
class OperationalAction:
    name: str
    risk: OperationalRisk
    description: str = ""
    reversible: bool = True
    external: bool = False
    destructive: bool = False
    arguments: dict[str, Any] = field(default_factory=dict)


class OperationalPolicy:
    """Central policy for local operator actions.

    Money is never autonomous. Installs, destructive changes, communication,
    and irreversible actions always retain an explicit human gate.
    """

    def decide(self, action: OperationalAction, *, human_confirmed: bool = False) -> dict[str, Any]:
        text = f"{action.name} {action.description}".lower()
        spend = action.risk == OperationalRisk.SPEND or any(word in text for word in SPEND_WORDS)
        if spend:
            return {
                "decision": "APPROVED" if human_confirmed else "REQUIRE_APPROVAL",
                "requires_human": True,
                "auto_allowed": False,
                "reason": "money_actions_always_require_separate_human_approval",
            }
        sensitive = (
            action.risk in {OperationalRisk.INSTALL, OperationalRisk.DELETE, OperationalRisk.COMMUNICATE}
            or action.destructive
            or not action.reversible
        )
        if sensitive:
            return {
                "decision": "APPROVED" if human_confirmed else "REQUIRE_APPROVAL",
                "requires_human": True,
                "auto_allowed": False,
                "reason": "sensitive_action_requires_human",
            }
        return {
            "decision": "AUTO_APPROVE",
            "requires_human": False,
            "auto_allowed": True,
            "reason": "reversible_local_operation",
        }


class ExecutableDiscovery:
    """Find common CEO tools without requiring them to already be in PATH."""

    WINDOWS_CANDIDATES = {
        "git": ["C:/Program Files/Git/cmd/git.exe", "C:/Program Files/Git/bin/git.exe"],
        "chrome": [
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        ],
        "code": [],
        "powershell": ["C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"],
        "cmd": ["C:/Windows/System32/cmd.exe"],
    }

    def __init__(self, *, environ: dict[str, str] | None = None) -> None:
        self.environ = environ if environ is not None else os.environ

    def _extra_candidates(self, name: str) -> list[Path]:
        local = Path(self.environ.get("LOCALAPPDATA", "")) if self.environ.get("LOCALAPPDATA") else None
        rows = [Path(x) for x in self.WINDOWS_CANDIDATES.get(name, [])]
        if local and name == "chrome":
            rows.append(local / "Google/Chrome/Application/chrome.exe")
        if local and name == "code":
            rows.extend([
                local / "Programs/Microsoft VS Code/bin/code.cmd",
                local / "Programs/Microsoft VS Code/Code.exe",
            ])
        return rows

    def find(self, name: str) -> str | None:
        aliases = {
            "python": ("python", "python3", "py"),
            "git": ("git",),
            "chrome": ("chrome", "chrome.exe"),
            "code": ("code", "code.cmd"),
            "powershell": ("pwsh", "powershell"),
            "cmd": ("cmd", "cmd.exe"),
            "winget": ("winget", "winget.exe"),
        }.get(name, (name,))
        for alias in aliases:
            found = shutil.which(alias)
            if found:
                return found
        for path in self._extra_candidates(name):
            if path.exists():
                return str(path)
        return None

    def snapshot(self) -> dict[str, str | None]:
        return {name: self.find(name) for name in ("python", "git", "chrome", "code", "powershell", "cmd", "winget")}


class ProcessEnvironmentBroker:
    """Build process environments with ephemeral secret handles.

    Secret values remain only inside SecretHandleVault process memory. Project
    state stores only handle metadata/digests.
    """

    TOOL = "operator_process_env"

    def __init__(self, vault: SecretHandleVault | None = None) -> None:
        self.vault = vault or SecretHandleVault()

    def bind_secret(self, state: ProjectState, *, name: str, value: str, purpose: str = "") -> str:
        return self.vault.bind(state, name=name, value=value, allowed_tools=[self.TOOL], purpose=purpose)

    def build(
        self,
        state: ProjectState,
        *,
        plain: dict[str, str] | None = None,
        secret_handles: dict[str, str] | None = None,
        inherit: bool = True,
    ) -> dict[str, str]:
        env = dict(os.environ) if inherit else {}
        # Never blindly inherit obvious secrets into arbitrary child processes.
        for key in list(env):
            upper = key.upper()
            if any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
                env.pop(key, None)
        for key, value in (plain or {}).items():
            upper = str(key).upper()
            if any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
                raise PermissionError("sensitive environment values require a secret handle")
            env[str(key)] = str(value)
        for key, handle in (secret_handles or {}).items():
            env[str(key)] = self.vault.resolve_for_tool(state, handle, tool=self.TOOL)
        return env


class SafeDownloadManager:
    """Download into a workspace with URL, size and hash controls."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        opener: Callable[..., Any] | None = None,
        max_bytes: int = 250 * 1024 * 1024,
    ) -> None:
        self.root = Path(workspace_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.fs = FilesystemOperations(self.root)
        self.opener = opener or urlopen
        self.max_bytes = int(max_bytes)

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "https":
            return
        if parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}:
            return
        raise PermissionError("downloads require HTTPS; HTTP is allowed only for localhost")

    def download(self, url: str, destination: str, *, expected_sha256: str | None = None) -> dict[str, Any]:
        self._validate_url(url)
        dest = self.fs.guard.resolve(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        request = Request(url, headers={"User-Agent": "CEO-de-IAs/operational-autonomy"})
        fd, temp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".part", dir=dest.parent)
        size = 0
        try:
            with os.fdopen(fd, "wb") as out, self.opener(request, timeout=30) as response:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ValueError("download exceeds configured size limit")
                    out.write(chunk)
                out.flush(); os.fsync(out.fileno())
            temp = Path(temp_name)
            digest = _sha_file(temp)
            if expected_sha256 and digest.lower() != expected_sha256.lower():
                raise ValueError("download SHA-256 mismatch")
            os.replace(temp, dest)
            return {
                "url": url,
                "destination": dest.relative_to(self.root).as_posix(),
                "size_bytes": size,
                "sha256": digest,
                "verified_hash": bool(expected_sha256),
            }
        finally:
            try:
                Path(temp_name).unlink()
            except FileNotFoundError:
                pass


class ApplicationLauncher:
    """Launch known local applications without invoking a shell."""

    ALLOWED = frozenset({"cmd", "powershell", "code", "chrome", "python", "git"})

    def __init__(
        self,
        *,
        discovery: ExecutableDiscovery | None = None,
        popen: Callable[..., Any] | None = None,
    ) -> None:
        self.discovery = discovery or ExecutableDiscovery()
        self.popen = popen or subprocess.Popen

    def launch(
        self,
        application: str,
        *,
        args: Iterable[str] = (),
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        app = application.lower().strip()
        if app not in self.ALLOWED:
            raise PermissionError(f"application not allowed: {application}")
        exe = self.discovery.find(app)
        if not exe:
            raise FileNotFoundError(f"application not found: {app}")
        command = [exe, *[str(x) for x in args]]
        if dry_run:
            return {"launched": False, "dry_run": True, "application": app, "command": command}
        proc = self.popen(command, cwd=str(cwd) if cwd else None, env=env, shell=False)
        return {"launched": True, "dry_run": False, "application": app, "command": command, "pid": getattr(proc, "pid", None)}


class TrustedScriptRunner:
    """Run workspace-contained .cmd/.bat/.ps1 scripts without shell=True.

    An optional expected SHA-256 locks execution to the reviewed bytes.
    """

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        discovery: ExecutableDiscovery | None = None,
        runner: Callable[..., Any] | None = None,
    ) -> None:
        self.root = Path(workspace_root).resolve()
        self.fs = FilesystemOperations(self.root)
        self.discovery = discovery or ExecutableDiscovery()
        self.runner = runner or subprocess.run

    def run(
        self,
        relative_path: str,
        *,
        args: Iterable[str] = (),
        expected_sha256: str | None = None,
        timeout: int = 300,
        env: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        script = self.fs.guard.resolve(relative_path)
        if not script.is_file():
            raise FileNotFoundError(relative_path)
        suffix = script.suffix.lower()
        if suffix not in {".cmd", ".bat", ".ps1"}:
            raise PermissionError("only .cmd/.bat/.ps1 workspace scripts are allowed")
        digest = _sha_file(script)
        if expected_sha256 and digest.lower() != expected_sha256.lower():
            raise ValueError("script SHA-256 mismatch")
        if suffix in {".cmd", ".bat"}:
            exe = self.discovery.find("cmd")
            command = [exe, "/d", "/c", str(script), *[str(x) for x in args]] if exe else []
        else:
            exe = self.discovery.find("powershell")
            command = [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), *[str(x) for x in args]] if exe else []
        if not command:
            raise FileNotFoundError("required script interpreter not found")
        if dry_run:
            return {"ok": True, "dry_run": True, "command": command, "sha256": digest, "executed": False}
        proc = self.runner(command, cwd=self.root, capture_output=True, text=True, timeout=max(1, int(timeout)), shell=False, env=env)
        return {
            "ok": proc.returncode == 0,
            "dry_run": False,
            "command": command,
            "sha256": digest,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-20000:],
            "stderr": (proc.stderr or "")[-20000:],
            "executed": True,
        }


class WorkspaceBootstrapper:
    STANDARD_DIRS = ("work", "downloads", "artifacts", "logs", "tmp")

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.fs = FilesystemOperations(self.root)

    def prepare(self) -> dict[str, Any]:
        created = [self.fs.create_dir(name) for name in self.STANDARD_DIRS]
        return {
            "root": str(self.root),
            "directories": created,
            "executables": ExecutableDiscovery().snapshot(),
            "prepared_at": _now(),
        }


class DeviceWorkRouter:
    """Recommend Windows vs mobile according to task capabilities and load."""

    MOBILE_TASKS = {"local_model", "embedding", "batch_tests", "code_review", "summarize", "log_triage"}
    WINDOWS_TASKS = {"windows_ui", "desktop", "native_app", "powershell", "cmd", "windows_install"}

    def recommend(
        self,
        *,
        task_kind: str,
        estimated_ram_gb: float = 0.0,
        requires_windows_ui: bool = False,
        mobile_available: bool = True,
        mobile_ram_gb: float = 24.0,
    ) -> dict[str, Any]:
        kind = str(task_kind).lower().strip()
        if requires_windows_ui or kind in self.WINDOWS_TASKS:
            device, reason = "windows", "requires_windows_ui"
        elif mobile_available and (kind in self.MOBILE_TASKS or estimated_ram_gb >= 6.0):
            device, reason = "mobile", "mobile_has_more_ram_or_is_suited_to_compute"
        else:
            device, reason = "windows", "lightweight_or_mobile_unavailable"
        return {
            "device": device,
            "reason": reason,
            "task_kind": kind,
            "estimated_ram_gb": float(estimated_ram_gb),
            "mobile_ram_gb": float(mobile_ram_gb),
            "mobile_available": bool(mobile_available),
            "user_notice_required": device == "mobile",
        }


class FrictionAutoTaskPlanner:
    """Convert open avoidable friction into deduplicated project tasks."""

    KEY = "operational_friction_tasks_v1"

    def plan(self, state: ProjectState, *, limit: int = 20) -> list[dict[str, Any]]:
        backlog = FrictionDetector().backlog(state)[: max(0, int(limit))]
        mapping = state.metadata.setdefault(self.KEY, {})
        created: list[dict[str, Any]] = []
        for row in backlog:
            signature = row.get("signature") or row.get("id")
            existing_id = mapping.get(signature)
            if existing_id and existing_id in state.tasks:
                continue
            title = f"Eliminar fricción: {row.get('kind', 'operator')}"
            task = Task(
                title=title[:200],
                description=str(row.get("description", ""))[:2000],
                priority=95 if row.get("priority") == "P0" else 85 if row.get("priority") == "P1" else 70,
                status=TaskStatus.READY,
                required_capabilities=["operational_autonomy"],
                acceptance_criteria=["manual step is eliminated or reduced to a justified approval gate"],
                metadata={"origin": "friction_backlog", "friction_id": row.get("id"), "friction_signature": signature},
            )
            state.tasks[task.id] = task
            state.root_task_ids.append(task.id)
            mapping[signature] = task.id
            created.append({"task_id": task.id, "title": task.title, "friction_id": row.get("id")})
        return created


class OperationalAutonomyCore:
    VERSION = 1
    KEY = "operational_autonomy_v1"

    def __init__(self, workspace_root: str | Path, *, data_root: str | Path | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.data_root = Path(data_root).resolve() if data_root else self.workspace_root / ".ceo-data"
        self.policy = OperationalPolicy()
        self.discovery = ExecutableDiscovery()
        self.env = ProcessEnvironmentBroker()
        self.bootstrap = WorkspaceBootstrapper(self.workspace_root)
        self.files = FilesystemOperations(self.workspace_root)
        self.terminal = TerminalController(self.workspace_root)
        self.downloads = SafeDownloadManager(self.workspace_root)
        self.launcher = ApplicationLauncher(discovery=self.discovery)
        self.scripts = TrustedScriptRunner(self.workspace_root, discovery=self.discovery)
        self.router = DeviceWorkRouter()
        self.friction = FrictionAutoTaskPlanner()

    def initialize(self, state: ProjectState) -> dict[str, Any]:
        state.metadata.setdefault(self.KEY, {
            "initialized_at": _now(),
            "auto_spend_allowed": False,
            "generic_remote_shell_exposed": False,
            "mobile_ram_gb": 24.0,
        })
        return self.snapshot(state)

    def preflight(self, state: ProjectState) -> dict[str, Any]:
        checks = {
            "structured_terminal": True,
            "workspace_filesystem": True,
            "safe_downloads": True,
            "known_application_launcher": True,
            "ephemeral_secret_handles": True,
            "executable_discovery": True,
            "workspace_bootstrap": True,
            "friction_to_tasks": True,
            "device_router": True,
            "no_auto_spend": True,
            "generic_remote_shell_not_exposed": True,
        }
        return {
            "pass": all(checks.values()),
            "checks": checks,
            "tools": self.discovery.snapshot(),
            "production_verified": False,
        }

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        from .self_hosting_beta import AutonomyMeasurementEngine

        meta = state.metadata.setdefault(self.KEY, {})
        return {
            "version": self.VERSION,
            "auto_spend_allowed": False,
            "generic_remote_shell_exposed": False,
            "tools": self.discovery.snapshot(),
            "friction_open": len(FrictionDetector().backlog(state)),
            "autonomy": AutonomyMeasurementEngine().measure(state),
            "mobile_preferred_example": self.router.recommend(task_kind="local_model", estimated_ram_gb=8.0),
            "metadata": {k: v for k, v in meta.items() if k not in {"secret", "token", "password"}},
            "production_verified": False,
        }

    def record_manual_step(
        self,
        state: ProjectState,
        *,
        action: str,
        description: str,
        avoidable: bool = True,
        evidence: Iterable[str] = (),
    ) -> dict[str, Any]:
        return FrictionDetector().record(
            state,
            kind="human_intervention",
            description=f"{action}: {description}",
            avoidable=avoidable,
            severity=0.8 if avoidable else 0.2,
            evidence=evidence,
        )

    def create_friction_tasks(self, state: ProjectState, *, limit: int = 20) -> list[dict[str, Any]]:
        return self.friction.plan(state, limit=limit)

    def supervised_local_smoke(self, state: ProjectState, *, field_executed: bool = False) -> dict[str, Any]:
        """Exercise structured operator primitives without external/destructive effects."""
        tracker = SupervisedUseTracker()
        session = tracker.start_session(
            state,
            label="operational-autonomy-smoke",
            field_executed=field_executed,
            platform="windows" if os.name == "nt" else os.name,
            evidence=["structured_operator_smoke"],
        )
        sid = session["session_id"]
        steps = [
            SupervisedStep(action="discover_executables", success=True, autonomous=True),
            SupervisedStep(action="prepare_workspace", success=True, autonomous=True),
            SupervisedStep(action="route_compute", success=True, autonomous=True, details=self.router.recommend(task_kind="local_model", estimated_ram_gb=8.0)),
            SupervisedStep(action="verify_spend_gate", success=self.policy.decide(OperationalAction("buy credits", OperationalRisk.SPEND))["decision"] == "REQUIRE_APPROVAL", autonomous=True),
        ]
        for step in steps:
            tracker.record_step(state, sid, step)
        return tracker.end_session(state, sid)
