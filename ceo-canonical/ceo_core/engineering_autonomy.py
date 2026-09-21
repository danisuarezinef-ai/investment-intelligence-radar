from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable

from .execution_integrity import IdempotencyRegistry, WorkspaceGuard
from .models import ProjectState
from .production_intelligence import ToolRegistry
from .security_governance_v2 import PermissionBroker
from .integrity_engineering import IntegrityEngineeringCore, SideEffectDefinition
from .scale_security import PermissionLeaseManager, SecretHandleVault


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-._")
    return value[:80] or "task"


@dataclass(slots=True)
class GitOperationResult:
    ok: bool
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class GitWorkspaceManager:
    """Local Git coordinator for task-isolated changes.

    It deliberately performs no network operation. Branching, commits, diffs and merges
    are local-only; pushing or opening PRs belongs to an explicit external tool adapter.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        WorkspaceGuard(self.root)

    def _run(self, *args: str, check: bool = True) -> GitOperationResult:
        proc = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True, timeout=60
        )
        result = GitOperationResult(proc.returncode == 0, ["git", *args], proc.stdout, proc.stderr, proc.returncode)
        if check and not result.ok:
            raise RuntimeError(f"git command failed: {' '.join(result.command)}\n{result.stderr.strip()}")
        return result

    def initialize(self, default_branch: str = "main") -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self._run("init", "-b", _slug(default_branch))
        # Repository-local identity only. No global config mutation.
        if not self._run("config", "user.email", check=False).stdout.strip():
            self._run("config", "user.email", "ceo-local@invalid.example")
        if not self._run("config", "user.name", check=False).stdout.strip():
            self._run("config", "user.name", "CEO de IAs Local")

    def current_branch(self) -> str:
        return self._run("branch", "--show-current").stdout.strip()

    def is_clean(self) -> bool:
        return not self._run("status", "--porcelain").stdout.strip()

    def create_task_branch(self, task_id: str, *, base_ref: str = "HEAD", require_clean: bool = True) -> str:
        if require_clean and not self.is_clean():
            raise RuntimeError("workspace is dirty; refusing to create task branch")
        branch = f"ceo/task-{_slug(task_id)}"
        existing = self._run("branch", "--list", branch).stdout.strip()
        if existing:
            self._run("switch", branch)
        else:
            self._run("switch", "-c", branch, base_ref)
        return branch

    def commit_all(self, message: str) -> str | None:
        self._run("add", "-A")
        if self.is_clean():
            return None
        self._run("commit", "-m", message[:240])
        return self._run("rev-parse", "HEAD").stdout.strip()

    def changed_paths(self, base_ref: str = "HEAD~1") -> list[str]:
        result = self._run("diff", "--name-only", f"{base_ref}..HEAD", check=False)
        if not result.ok:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def diff(self, base_ref: str = "HEAD~1") -> str:
        return self._run("diff", f"{base_ref}..HEAD").stdout

    def merge_local(self, branch: str, *, target_branch: str = "main", no_ff: bool = True) -> GitOperationResult:
        if not self.is_clean():
            raise RuntimeError("workspace is dirty; refusing merge")
        self._run("switch", target_branch)
        args = ["merge"] + (["--no-ff"] if no_ff else []) + [branch, "-m", f"Merge {branch}"]
        return self._run(*args)

    def local_audit(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "is_repo": (self.root / ".git").exists(),
            "branch": self.current_branch() if (self.root / ".git").exists() else None,
            "clean": self.is_clean() if (self.root / ".git").exists() else None,
            "network_actions_performed": False,
        }


@dataclass(slots=True)
class PathClaim:
    task_id: str
    paths: list[str]
    acquired_at: float = field(default_factory=time.time)


class ChangeSetCoordinator:
    """Prevents multiple agents from editing overlapping paths concurrently."""

    KEY = "path_claims_v1"

    @staticmethod
    def _overlap(a: str, b: str) -> bool:
        pa, pb = Path(a), Path(b)
        return pa == pb or pa in pb.parents or pb in pa.parents

    def acquire(self, state: ProjectState, task_id: str, paths: Iterable[str]) -> dict[str, Any]:
        wanted = sorted({_slug_path(x) for x in paths if str(x).strip()})
        claims = state.metadata.setdefault(self.KEY, {})
        conflicts = []
        for other_id, row in claims.items():
            if other_id == task_id:
                continue
            for a in wanted:
                for b in row.get("paths", []):
                    if self._overlap(a, b):
                        conflicts.append({"task_id": other_id, "requested": a, "claimed": b})
        if conflicts:
            return {"acquired": False, "conflicts": conflicts}
        claims[task_id] = asdict(PathClaim(task_id, wanted))
        return {"acquired": True, "paths": wanted, "conflicts": []}

    def release(self, state: ProjectState, task_id: str) -> bool:
        return state.metadata.setdefault(self.KEY, {}).pop(task_id, None) is not None


def _slug_path(value: str) -> str:
    p = str(value).replace("\\", "/").strip("/")
    parts = [x for x in p.split("/") if x not in {"", "."}]
    if any(x == ".." for x in parts):
        raise ValueError("parent traversal not allowed in claimed paths")
    return "/".join(parts)


@dataclass(slots=True)
class SandboxResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    timed_out: bool
    workspace_deleted: bool


class LocalSandboxExecutor:
    """Disposable local execution sandbox.

    This is a containment layer, not a VM. It copies source to a temporary directory,
    never uses a shell, scrubs secret-looking environment variables, restricts the
    executable allowlist and destroys the copy after execution.
    """

    SECRET_KEYS = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)", re.I)

    def __init__(self, allowed_executables: Iterable[str] = ("python", "python3", "pytest")):
        self.allowed = {Path(x).name.lower() for x in allowed_executables}

    def _safe_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not self.SECRET_KEYS.search(k)}
        # Deterministic safety hint for code that honors this project convention.
        env["CEO_SANDBOX"] = "1"
        env["CEO_NETWORK_DISABLED"] = "1"
        for k, v in (extra or {}).items():
            if self.SECRET_KEYS.search(k):
                continue
            env[str(k)] = str(v)
        return env

    def run(self, source_root: str | Path, argv: list[str], *, timeout: int = 120, extra_env: dict[str, str] | None = None) -> SandboxResult:
        if not argv:
            raise ValueError("argv required")
        exe = Path(argv[0]).name.lower()
        if exe not in self.allowed:
            raise PermissionError(f"executable not allowed in sandbox: {exe}")
        source = Path(source_root).resolve()
        started = time.monotonic()
        timed_out = False
        stdout = stderr = ""
        returncode = -1
        deleted = False
        temp_path = None
        try:
            temp_path = Path(tempfile.mkdtemp(prefix="ceo-sandbox-"))
            work = temp_path / "workspace"
            shutil.copytree(
                source,
                work,
                ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "browser_profiles", "data", "*.db", "*.sqlite*"),
            )
            try:
                proc = subprocess.run(argv, cwd=work, capture_output=True, text=True, timeout=max(1, timeout), env=self._safe_env(extra_env), shell=False)
                returncode, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        finally:
            if temp_path:
                shutil.rmtree(temp_path, ignore_errors=True)
                deleted = not temp_path.exists()
        return SandboxResult(returncode == 0 and not timed_out, returncode, stdout, stderr, round(time.monotonic() - started, 4), timed_out, deleted)


class ToolExecutionBroker:
    """Executes in-process tool adapters only after registry + capability authorization."""

    def __init__(self):
        self.adapters: dict[str, Callable[..., Any]] = {}
        self.permission_broker = PermissionBroker()
        self.permission_leases = PermissionLeaseManager(self.permission_broker)
        self.secret_vault = SecretHandleVault()
        self.idempotency = IdempotencyRegistry()
        self.registry = ToolRegistry()
        self.integrity = IntegrityEngineeringCore()

    def register_adapter(self, name: str, adapter: Callable[..., Any]) -> None:
        if not callable(adapter):
            raise TypeError("adapter must be callable")
        self.adapters[name] = adapter

    def declare_side_effects(self, state: ProjectState, definition: SideEffectDefinition) -> None:
        self.integrity.side_effects.register(state, definition)

    def execute(
        self,
        state: ProjectState,
        *,
        token_id: str,
        tool_name: str,
        permission: str,
        kwargs: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        dry_run: bool = False,
        approved: bool = False,
        evidence_quality: float = .5,
        cost_estimate: float = 0.0,
    ) -> dict[str, Any]:
        tool_row = state.metadata.setdefault(ToolRegistry.KEY, {}).get(tool_name)
        if not tool_row or tool_name not in self.adapters:
            return {"ok": False, "reason": "unknown_tool"}
        lease_row = state.metadata.get(PermissionLeaseManager.KEY, {}).get(token_id)
        if lease_row:
            authorized = self.permission_leases.authorize(state, token_id, tool=tool_name, permission=permission, task_id=(kwargs or {}).get("_task_id"), consume=False)
        else:
            authorized = self.permission_broker.authorize(state, token_id, tool=tool_name, permission=permission, consume=False)
        if not authorized:
            return {"ok": False, "reason": "permission_denied"}

        preflight = self.integrity.preflight(
            state, tool=tool_name, tool_row=tool_row, kwargs=kwargs,
            cost_estimate=cost_estimate, evidence_quality=evidence_quality, approved=approved,
        )
        if dry_run:
            return {"ok": True, **self.integrity.dry_run.run(preflight["preview"], preflight["risk"], preflight["approval"])}
        if preflight["approval"]["decision"] in {"REQUIRE_APPROVAL", "DENY"}:
            return {"ok": False, "reason": "approval_required" if preflight["approval"]["decision"] == "REQUIRE_APPROVAL" else "risk_denied", "preflight": preflight}

        external = bool(preflight["preview"].get("external") or preflight["preview"].get("destructive"))
        if external and not idempotency_key:
            return {"ok": False, "reason": "idempotency_key_required", "preflight": preflight}
        if idempotency_key:
            begin_v2 = self.integrity.exactly_once.begin(
                state, key=idempotency_key, operation=f"tool:{tool_name}:{permission}",
                preview_digest=sha256(repr(preflight["preview"]).encode()).hexdigest(),
            )
            if not begin_v2["execute"]:
                return {"ok": True, "duplicate": True, "record": begin_v2["record"], "preflight": preflight}
            # Preserve the original registry for backward-compatible recovery/audits.
            begin = self.idempotency.begin(state, key=idempotency_key, operation=f"tool:{tool_name}:{permission}")
            if not begin["execute"]:
                return {"ok": True, "duplicate": True, "record": begin["record"], "preflight": preflight}
        try:
            adapter_kwargs = {}
            for key, value in (kwargs or {}).items():
                if key == "_task_id":
                    continue
                if isinstance(value, str) and value.startswith("secret://"):
                    adapter_kwargs[key] = self.secret_vault.resolve_for_tool(state, value, tool=tool_name)
                else:
                    adapter_kwargs[key] = value
            value = self.adapters[tool_name](**adapter_kwargs)
            if idempotency_key:
                self.idempotency.complete(state, idempotency_key, value)
                self.integrity.exactly_once.commit(state, idempotency_key, value)
            if lease_row:
                self.permission_leases.authorize(state, token_id, tool=tool_name, permission=permission, task_id=(kwargs or {}).get("_task_id"), consume=True)
            else:
                self.permission_broker.authorize(state, token_id, tool=tool_name, permission=permission, consume=True)
            return {"ok": True, "duplicate": False, "result": value, "preflight": preflight}
        except Exception as exc:
            if idempotency_key:
                self.idempotency.fail(state, idempotency_key, retryable=True)
                self.integrity.exactly_once.fail(state, idempotency_key, retryable=True)
            return {"ok": False, "reason": "adapter_failed", "error": type(exc).__name__, "preflight": preflight}


@dataclass(slots=True)
class BenchmarkObservation:
    case_id: str
    score: float
    passed: bool
    latency_seconds: float = 0.0
    cost: float = 0.0
    security_failures: int = 0


class BenchmarkHarness:
    """Versioned local benchmark evaluator with baseline/challenger comparison."""

    KEY = "benchmark_registry_v2"

    def record_run(self, state: ProjectState, *, version: str, suite: str, observations: Iterable[BenchmarkObservation]) -> dict[str, Any]:
        rows = list(observations)
        if not rows:
            raise ValueError("benchmark observations required")
        aggregate = {
            "version": version,
            "suite": suite,
            "cases": len(rows),
            "pass_rate": round(sum(int(x.passed) for x in rows) / len(rows), 6),
            "score": round(sum(x.score for x in rows) / len(rows), 6),
            "latency_seconds": round(sum(x.latency_seconds for x in rows), 6),
            "cost": round(sum(x.cost for x in rows), 6),
            "security_failures": sum(x.security_failures for x in rows),
            "digest": sha256("|".join(f"{x.case_id}:{x.score}:{x.passed}" for x in rows).encode()).hexdigest(),
        }
        state.metadata.setdefault(self.KEY, {}).setdefault(suite, {})[version] = aggregate
        return aggregate

    def compare(self, state: ProjectState, *, suite: str, baseline: str, challenger: str, min_gain: float = 0.0) -> dict[str, Any]:
        versions = state.metadata.setdefault(self.KEY, {}).get(suite, {})
        a, b = versions.get(baseline), versions.get(challenger)
        if not a or not b:
            return {"promotable": False, "reason": "missing_benchmark_run"}
        score_gain = float(b["score"]) - float(a["score"])
        promotable = (
            b["pass_rate"] >= a["pass_rate"]
            and b["security_failures"] == 0
            and score_gain > float(min_gain)
        )
        return {
            "promotable": promotable,
            "score_gain": round(score_gain, 6),
            "pass_rate_delta": round(float(b["pass_rate"]) - float(a["pass_rate"]), 6),
            "cost_delta": round(float(b["cost"]) - float(a["cost"]), 6),
            "latency_delta": round(float(b["latency_seconds"]) - float(a["latency_seconds"]), 6),
            "security_failures": int(b["security_failures"]),
            "reason": "safe_out_of_sample_gain" if promotable else "no_safe_measurable_gain",
        }


class WorkflowStrategyLab:
    """A/B evidence for workflow strategies; avoids promotion on tiny samples."""

    KEY = "workflow_strategy_lab_v1"

    def record(self, state: ProjectState, *, strategy: str, score: float, success: bool, cost: float = 0.0, seconds: float = 0.0, holdout: bool = True) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).setdefault(strategy, {"runs": 0, "holdout_runs": 0, "successes": 0, "score_sum": 0.0, "cost_sum": 0.0, "seconds_sum": 0.0})
        row["runs"] += 1
        row["holdout_runs"] += int(bool(holdout))
        row["successes"] += int(bool(success))
        row["score_sum"] += float(score)
        row["cost_sum"] += float(cost)
        row["seconds_sum"] += float(seconds)
        row["avg_score"] = round(row["score_sum"] / row["runs"], 6)
        row["success_rate"] = round(row["successes"] / row["runs"], 6)
        return dict(row)

    def compare(self, state: ProjectState, baseline: str, challenger: str, *, min_holdout_runs: int = 10, min_score_gain: float = .01) -> dict[str, Any]:
        rows = state.metadata.setdefault(self.KEY, {})
        a, b = rows.get(baseline), rows.get(challenger)
        if not a or not b:
            return {"promote": False, "reason": "missing_strategy_data"}
        if min(a.get("holdout_runs", 0), b.get("holdout_runs", 0)) < min_holdout_runs:
            return {"promote": False, "reason": "insufficient_holdout_evidence"}
        gain = float(b.get("avg_score", 0)) - float(a.get("avg_score", 0))
        success_noninferior = float(b.get("success_rate", 0)) >= float(a.get("success_rate", 0))
        promote = gain >= min_score_gain and success_noninferior
        return {"promote": promote, "score_gain": round(gain, 6), "success_noninferior": success_noninferior, "reason": "holdout_gain" if promote else "no_reliable_gain"}
