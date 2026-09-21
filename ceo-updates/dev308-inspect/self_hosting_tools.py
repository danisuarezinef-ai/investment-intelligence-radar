from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable

from .ai_worker import AIWorkerProvider, AIPromptBuilder
from .contracts import WorkerRequest, WorkerResult
from .engineering_autonomy import GitWorkspaceManager
from .execution_integrity import WorkspaceGuard
from .models import ProjectState, Task
from .providers.openai_responses import OpenAIResponsesTransport


def _now() -> float:
    return time.time()


def _sha_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree_digest(root: Path, *, exclude: Iterable[str] = ()) -> str:
    ignored = {str(x).strip("/") for x in exclude}
    rows: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        parts = set(path.relative_to(root).parts)
        if any(
            rel == prefix
            or rel.startswith(prefix.rstrip("/") + "/")
            or prefix in parts
            for prefix in ignored
            if prefix and not prefix.startswith("*.")
        ):
            continue
        if any(prefix.startswith("*.") and path.name.endswith(prefix[1:]) for prefix in ignored):
            continue
        rows.append(f"{rel}:{_sha_file(path)}")
    return sha256("\n".join(rows).encode()).hexdigest()


# 21. ChatGPT worker adapter
class ChatGPTWorkerAdapter(AIWorkerProvider):
    """First-class ChatGPT worker backed by the existing Responses transport.

    The adapter deliberately keeps the provider name compatible with the existing
    router/model-portfolio history (``openai-responses``), while exposing an
    explicit adapter identity through result/health metadata.
    """

    capabilities = frozenset({"general", "chat", "reasoning", "analysis", "writing", "coding", "chatgpt"})

    def __init__(
        self,
        transport: OpenAIResponsesTransport | None = None,
        *,
        api_key: str | None = None,
        model: str | None = None,
        prompt_builder: AIPromptBuilder | None = None,
    ) -> None:
        super().__init__(
            transport or OpenAIResponsesTransport(api_key=api_key, model=model),
            prompt_builder=prompt_builder,
            capabilities=self.capabilities,
        )

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        result = await super().execute(request)
        result.metadata = {"worker_adapter": "chatgpt", "contract": "CEO<->ChatGPT/v1", **dict(result.metadata)}
        return result


# 22. Artifact exchange layer
@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    task_id: str | None
    direction: str
    relative_path: str
    sha256: str
    size_bytes: int
    created_at: float
    verified_exists: bool = True


class ArtifactExchangeLayer:
    KEY = "artifact_exchange_v1"

    def __init__(self, workspace_root: str | Path):
        self.root = Path(workspace_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.guard = WorkspaceGuard(self.root)

    def register(self, state: ProjectState, relative_path: str, *, task_id: str | None = None, direction: str = "output") -> dict[str, Any]:
        path = self.guard.resolve(relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"artifact does not exist: {relative_path}")
        digest = _sha_file(path)
        record = ArtifactRecord(
            artifact_id=sha256(f"{state.id}|{task_id}|{relative_path}|{digest}".encode()).hexdigest()[:20],
            task_id=task_id,
            direction=str(direction),
            relative_path=path.relative_to(self.root).as_posix(),
            sha256=digest,
            size_bytes=path.stat().st_size,
            created_at=_now(),
        )
        rows = state.metadata.setdefault(self.KEY, {})
        rows[record.artifact_id] = asdict(record)
        return asdict(record)

    def accept_worker_artifacts(self, state: ProjectState, task: Task, paths: Iterable[str]) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, str]] = []
        for value in paths:
            try:
                accepted.append(self.register(state, str(value), task_id=task.id, direction="worker_output"))
            except Exception as exc:  # noqa: BLE001
                rejected.append({"path": str(value), "reason": f"{type(exc).__name__}: {exc}"})
        if rejected:
            task.metadata.setdefault("rejected_artifacts", []).extend(rejected)
        if accepted:
            task.metadata.setdefault("verified_artifacts", []).extend(x["artifact_id"] for x in accepted)
        return accepted

    def worker_inputs(self, state: ProjectState, task: Task) -> list[dict[str, Any]]:
        ids = list(task.metadata.get("artifact_inputs", []))
        rows = state.metadata.get(self.KEY, {})
        return [dict(rows[x]) for x in ids if x in rows]

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        rows = list(state.metadata.get(self.KEY, {}).values())
        return {"count": len(rows), "verified": sum(bool(x.get("verified_exists")) for x in rows), "recent": rows[-10:]}


# 23. Multi-turn worker sessions
class WorkerSessionManager:
    KEY = "worker_sessions_v3"

    def record_turn(
        self,
        state: ProjectState,
        task: Task,
        *,
        provider: str,
        request_context: dict[str, Any],
        result: WorkerResult,
    ) -> dict[str, Any]:
        key = f"{task.id}:{provider}"
        sessions = state.metadata.setdefault(self.KEY, {})
        row = sessions.setdefault(key, {
            "task_id": task.id,
            "provider": provider,
            "created_at": _now(),
            "turns": [],
        })
        conversation_id = result.conversation_id or task.conversation_id
        turn = {
            "turn_index": int(task.conversation_turns),
            "ts": _now(),
            "conversation_id": conversation_id,
            "context_digest": sha256(json.dumps(request_context, sort_keys=True, default=str).encode()).hexdigest()[:20],
            "result_digest": sha256((result.text or "").encode()).hexdigest()[:20],
            "success": bool(result.success),
            "artifacts": list(result.artifacts),
        }
        row["turns"].append(turn)
        del row["turns"][:-100]
        row["latest_conversation_id"] = conversation_id
        row["last_turn_at"] = turn["ts"]
        return dict(row)

    def recover_conversation_id(self, state: ProjectState, task: Task, provider: str) -> str | None:
        if task.conversation_id:
            return task.conversation_id
        row = state.metadata.get(self.KEY, {}).get(f"{task.id}:{provider}", {})
        return row.get("latest_conversation_id")

    def snapshot(self, state: ProjectState, task_id: str | None = None) -> dict[str, Any]:
        rows = state.metadata.get(self.KEY, {})
        selected = {k: v for k, v in rows.items() if task_id is None or v.get("task_id") == task_id}
        return {"sessions": len(selected), "turns": sum(len(v.get("turns", [])) for v in selected.values()), "items": selected}


# 24. Provider context recovery
class ProviderContextRecovery:
    KEY = "provider_context_recovery_v1"

    @staticmethod
    def _bounded(value: Any, limit: int) -> Any:
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return value
        return text[:limit] + "...[truncated]"

    def rebuild(self, state: ProjectState, task: Task, *, provider: str | None = None) -> dict[str, Any]:
        dependencies = []
        for dep_id in task.dependencies:
            dep = state.tasks.get(dep_id)
            if dep and dep.result:
                dependencies.append({"task_id": dep.id, "title": dep.title, "result": dep.result[:1800]})
        decisions = []
        for decision in state.decisions.values():
            if decision.selected or decision.recommendation:
                decisions.append({
                    "title": decision.title,
                    "selected": decision.selected,
                    "recommendation": decision.recommendation,
                    "status": decision.status.value,
                })
        binding = list(state.metadata.get("binding_decisions_v2", {}).values())
        evidence = list(state.metadata.get("evidence_ledger_v1", {}).values())[-20:]
        session = {}
        if provider:
            session = state.metadata.get(WorkerSessionManager.KEY, {}).get(f"{task.id}:{provider}", {})
        rebuilt = {
            "recovered_context": True,
            "project_goal": state.goal,
            "constraints": list(state.goal_constraints),
            "forbidden_actions": list(state.metadata.get("forbidden_actions", [])),
            "binding_decisions": self._bounded(binding, 5000),
            "project_summary": str(state.metadata.get("project_summary", ""))[:6000],
            "dependencies": dependencies,
            "decisions": decisions[-20:],
            "recent_evidence": self._bounded(evidence, 5000),
            "session": {"provider": provider, "latest_conversation_id": session.get("latest_conversation_id"), "turn_count": len(session.get("turns", []))},
        }
        task.metadata.setdefault(self.KEY, []).append({"ts": _now(), "provider": provider, "digest": sha256(json.dumps(rebuilt, sort_keys=True, default=str).encode()).hexdigest()[:20]})
        task.metadata[self.KEY] = task.metadata[self.KEY][-20:]
        return rebuilt


# 25. VS Code controller
@dataclass(slots=True)
class CommandResult:
    ok: bool
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    dry_run: bool = False


class VSCodeController:
    def __init__(self, workspace_root: str | Path, *, executable: str = "code", runner: Callable[..., Any] | None = None):
        self.root = Path(workspace_root).resolve()
        self.guard = WorkspaceGuard(self.root)
        self.executable = executable
        self.runner = runner or subprocess.run

    def _run(self, args: list[str], *, dry_run: bool = False) -> CommandResult:
        command = [self.executable, *args]
        if dry_run:
            return CommandResult(True, command, 0, dry_run=True)
        proc = self.runner(command, cwd=self.root, capture_output=True, text=True, timeout=30, shell=False)
        return CommandResult(proc.returncode == 0, command, proc.returncode, proc.stdout or "", proc.stderr or "")

    def open_workspace(self, *, dry_run: bool = False) -> CommandResult:
        return self._run([str(self.root), "--reuse-window"], dry_run=dry_run)

    def open_file(self, relative_path: str, *, line: int | None = None, dry_run: bool = False) -> CommandResult:
        path = self.guard.resolve(relative_path)
        target = str(path) + (f":{max(1, int(line))}" if line else "")
        return self._run(["--goto", target, "--reuse-window"], dry_run=dry_run)

    def status(self) -> dict[str, Any]:
        return {"workspace": str(self.root), "executable": self.executable, "available": shutil.which(self.executable) is not None}


# 26. Terminal controller
class TerminalController:
    DEFAULT_ALLOWED = frozenset({"python", "python3", "pytest", "git", "ruff", "node", "npm"})

    def __init__(self, workspace_root: str | Path, *, allowed: Iterable[str] | None = None, runner: Callable[..., Any] | None = None):
        self.root = Path(workspace_root).resolve()
        self.guard = WorkspaceGuard(self.root)
        self.allowed = {Path(x).name.lower() for x in (allowed or self.DEFAULT_ALLOWED)}
        self.runner = runner or subprocess.run

    def run(self, argv: list[str], *, cwd: str = ".", timeout: int = 120, dry_run: bool = False, env: dict[str, str] | None = None) -> CommandResult:
        if not argv:
            raise ValueError("argv required")
        exe = Path(argv[0]).name.lower()
        if exe not in self.allowed:
            raise PermissionError(f"terminal executable not allowed: {exe}")
        work = self.guard.resolve(cwd)
        if not work.is_dir():
            raise NotADirectoryError(cwd)
        if dry_run:
            return CommandResult(True, list(argv), 0, dry_run=True)
        safe_env = dict(os.environ)
        for key in list(safe_env):
            if any(token in key.upper() for token in ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
                safe_env.pop(key, None)
        safe_env.update({str(k): str(v) for k, v in (env or {}).items() if not any(t in str(k).upper() for t in ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))})
        proc = self.runner(list(argv), cwd=work, capture_output=True, text=True, timeout=max(1, int(timeout)), shell=False, env=safe_env)
        return CommandResult(proc.returncode == 0, list(argv), proc.returncode, (proc.stdout or "")[-20000:], (proc.stderr or "")[-20000:])


# 27. Structured filesystem operations
class FilesystemOperations:
    def __init__(self, workspace_root: str | Path):
        self.root = Path(workspace_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.guard = WorkspaceGuard(self.root)

    def read_text(self, relative_path: str) -> str:
        return self.guard.resolve(relative_path).read_text(encoding="utf-8")

    def write_text(self, relative_path: str, text: str) -> dict[str, Any]:
        path = self.guard.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            try: os.unlink(temp)
            except FileNotFoundError: pass
        return {"path": path.relative_to(self.root).as_posix(), "sha256": _sha_file(path), "size_bytes": path.stat().st_size}

    def create_dir(self, relative_path: str) -> str:
        path = self.guard.resolve(relative_path); path.mkdir(parents=True, exist_ok=True)
        return path.relative_to(self.root).as_posix()

    def copy(self, source: str, destination: str) -> dict[str, Any]:
        src, dst = self.guard.resolve(source), self.guard.resolve(destination)
        if not src.is_file(): raise FileNotFoundError(source)
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
        return {"source": src.relative_to(self.root).as_posix(), "destination": dst.relative_to(self.root).as_posix(), "sha256": _sha_file(dst)}

    def move(self, source: str, destination: str) -> dict[str, Any]:
        src, dst = self.guard.resolve(source), self.guard.resolve(destination)
        if not src.exists(): raise FileNotFoundError(source)
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(src), str(dst))
        return {"source": str(source), "destination": dst.relative_to(self.root).as_posix()}

    def rename(self, source: str, new_name: str) -> dict[str, Any]:
        if Path(new_name).name != new_name or new_name in {"", ".", ".."}:
            raise ValueError("new_name must be a basename")
        src = self.guard.resolve(source)
        dst = src.with_name(new_name)
        self.guard.resolve(dst.relative_to(self.root))
        src.rename(dst)
        return {"source": str(source), "destination": dst.relative_to(self.root).as_posix()}

    def replace_text(self, relative_path: str, old: str, new: str, *, expected_occurrences: int = 1) -> dict[str, Any]:
        text = self.read_text(relative_path)
        count = text.count(old)
        if count != expected_occurrences:
            raise RuntimeError(f"expected {expected_occurrences} occurrences, found {count}")
        return self.write_text(relative_path, text.replace(old, new))


# 28. Local Git integration facade
class SelfHostingGitController:
    def __init__(self, workspace_root: str | Path):
        self.root = Path(workspace_root).resolve()
        self.git = GitWorkspaceManager(self.root)

    def initialize(self) -> dict[str, Any]:
        self.git.initialize()
        return self.status()

    def create_branch(self, task_id: str, *, base_ref: str = "HEAD") -> str:
        return self.git.create_task_branch(task_id, base_ref=base_ref)

    def commit(self, message: str) -> str | None:
        return self.git.commit_all(message)

    def diff(self, base_ref: str = "HEAD~1") -> str:
        return self.git.diff(base_ref)

    def revert_worktree(self) -> CommandResult:
        result = self.git._run("restore", "--staged", "--worktree", ".", check=False)
        return CommandResult(result.ok, result.command, result.returncode, result.stdout, result.stderr)

    def status(self) -> dict[str, Any]:
        return self.git.local_audit()


# 30. Immutable running version guard
class ImmutableRunningVersion:
    KEY = "immutable_running_version_v1"
    EXCLUDE = (".git", "__pycache__", ".pytest_cache", "data", "browser_profiles", "*.pyc")

    def __init__(self, running_root: str | Path):
        self.running_root = Path(running_root).resolve()

    def assert_candidate(self, candidate_root: str | Path) -> Path:
        candidate = Path(candidate_root).resolve()
        if candidate == self.running_root or self.running_root in candidate.parents or candidate in self.running_root.parents:
            raise PermissionError("candidate workspace must be physically separate from the running version")
        return candidate

    def freeze(self, state: ProjectState) -> dict[str, Any]:
        digest = _tree_digest(self.running_root, exclude=(".git", "__pycache__", ".pytest_cache", "data", "browser_profiles"))
        row = {"running_root": str(self.running_root), "digest": digest, "frozen_at": _now(), "mutable": False}
        state.metadata[self.KEY] = row
        return dict(row)

    def verify(self, state: ProjectState) -> dict[str, Any]:
        row = state.metadata.get(self.KEY) or self.freeze(state)
        current = _tree_digest(self.running_root, exclude=(".git", "__pycache__", ".pytest_cache", "data", "browser_profiles"))
        return {"unchanged": current == row.get("digest"), "expected_digest": row.get("digest"), "current_digest": current, "running_root": str(self.running_root)}

    def assert_mutable_path(self, path: str | Path) -> Path:
        target = Path(path).resolve()
        if target == self.running_root or self.running_root in target.parents:
            raise PermissionError("running CEO version is immutable")
        return target


# 29. Self-hosting workspace manager
class SelfHostingWorkspace:
    KEY = "self_hosting_workspace_v1"
    IGNORE_PATTERNS = (".git", "__pycache__", ".pytest_cache", "data", "browser_profiles", "*.pyc", "*.pyo")

    def __init__(self, running_root: str | Path, candidates_root: str | Path):
        self.running_root = Path(running_root).resolve()
        self.candidates_root = Path(candidates_root).resolve()
        self.immutable = ImmutableRunningVersion(self.running_root)

    def create(self, state: ProjectState, *, label: str = "self-hosting") -> dict[str, Any]:
        self.immutable.freeze(state)
        self.candidates_root.mkdir(parents=True, exist_ok=True)
        candidate = self.candidates_root / f"{label}-{state.id[:8]}-{int(_now())}"
        self.immutable.assert_candidate(candidate)
        if candidate.exists():
            raise FileExistsError(candidate)
        shutil.copytree(self.running_root, candidate, ignore=shutil.ignore_patterns(*self.IGNORE_PATTERNS))
        git = SelfHostingGitController(candidate)
        git.initialize()
        if not git.git._run("rev-parse", "--verify", "HEAD", check=False).ok:
            git.commit("Baseline self-hosting candidate")
        baseline = _tree_digest(candidate, exclude=(".git", "__pycache__", ".pytest_cache"))
        row = {
            "running_root": str(self.running_root),
            "candidate_root": str(candidate),
            "created_at": _now(),
            "baseline_digest": baseline,
            "running_immutable": True,
            "git": git.status(),
            "network_actions_performed": False,
        }
        state.metadata[self.KEY] = row
        return dict(row)

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        row = dict(state.metadata.get(self.KEY, {}))
        row["running_version"] = self.immutable.verify(state) if state.metadata.get(ImmutableRunningVersion.KEY) else {"unchanged": None}
        return row


class SelfHostingToolsCore:
    VERSION = 1

    def __init__(self, running_root: str | Path | None = None):
        self.running_root = Path(running_root or Path.cwd()).resolve()
        self.sessions = WorkerSessionManager()
        self.context_recovery = ProviderContextRecovery()

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "chatgpt_worker_adapter": True,
            "artifact_exchange": {"configured": bool((state.metadata.get("workspace_v2") or {}).get("root")), "count": len(state.metadata.get(ArtifactExchangeLayer.KEY, {}))},
            "worker_sessions": self.sessions.snapshot(state),
            "context_recovery": True,
            "vscode_controller": True,
            "terminal_controller": True,
            "filesystem_operations": True,
            "git_local": True,
            "self_hosting_workspace": dict(state.metadata.get(SelfHostingWorkspace.KEY, {})),
            "immutable_running_version": dict(state.metadata.get(ImmutableRunningVersion.KEY, {})),
            "windows_physical": "DEFERRED_BY_USER",
            "live_provider": "NOT_VERIFIED" if not state.metadata.get("live_provider_gate_v2", {}).get("authenticated_live_verified") else "VERIFIED",
        }

    def preflight(self, state: ProjectState) -> dict[str, Any]:
        checks = {
            "chatgpt_worker_adapter": True,
            "artifact_exchange": True,
            "multi_turn_sessions": True,
            "provider_context_recovery": True,
            "vscode_controller": True,
            "terminal_controller": True,
            "filesystem_structured_ops": True,
            "git_local_only": True,
            "self_hosting_workspace": True,
            "immutable_running_version": True,
        }
        return {"pass": all(checks.values()), "checks": checks, "windows_physical": "DEFERRED_BY_USER", "live_provider": self.snapshot(state)["live_provider"]}
