from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from .execution_integrity import WorkspaceGuard
from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


@dataclass(slots=True)
class WorkspaceManifest:
    project_id: str
    goal_hash: str
    created_at: str
    schema_version: int = 1
    directories: list[str] = field(default_factory=list)


class ProjectWorkspaceManager:
    """Creates a predictable, contained, per-project filesystem workspace."""

    DIRECTORIES = (
        "src", "docs", "artifacts", "tests", "logs", "checkpoints", "memory", "reports", "tmp"
    )

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.guard = WorkspaceGuard(self.root)

    def create(self, state: ProjectState) -> WorkspaceManifest:
        for name in self.DIRECTORIES:
            self.guard.resolve(name).mkdir(parents=True, exist_ok=True)
        manifest = WorkspaceManifest(
            project_id=state.id,
            goal_hash=sha256(state.goal.encode()).hexdigest(),
            created_at=_now(),
            directories=list(self.DIRECTORIES),
        )
        _atomic_json(self.guard.resolve("workspace.json"), asdict(manifest))
        state.metadata["workspace_v2"] = {**asdict(manifest), "root": str(self.root)}
        return manifest

    def validate(self, state: ProjectState) -> dict[str, Any]:
        manifest_path = self.guard.resolve("workspace.json")
        if not manifest_path.exists():
            return {"valid": False, "reason": "missing_manifest"}
        try:
            row = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {"valid": False, "reason": "invalid_manifest"}
        expected = sha256(state.goal.encode()).hexdigest()
        missing = [d for d in self.DIRECTORIES if not self.guard.resolve(d).is_dir()]
        valid = row.get("project_id") == state.id and row.get("goal_hash") == expected and not missing
        return {"valid": valid, "goal_matches": row.get("goal_hash") == expected, "missing_directories": missing}

    def write_text(self, relative_path: str, text: str) -> Path:
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
        return path


@dataclass(slots=True)
class ReleaseFreeze:
    version: str
    frozen_at: str
    allowed_change_types: list[str]
    reason: str
    active: bool = True


class ReleaseFreezeManager:
    """Feature freeze guard for RC stabilization cycles."""

    KEY = "release_freeze_v1"
    DEFAULT_ALLOWED = ("bugfix", "security", "test", "docs", "performance", "release")

    def freeze(self, state: ProjectState, version: str, *, reason: str = "release candidate stabilization", allowed_change_types: Iterable[str] | None = None) -> ReleaseFreeze:
        freeze = ReleaseFreeze(version, _now(), sorted(set(allowed_change_types or self.DEFAULT_ALLOWED)), reason, True)
        state.metadata[self.KEY] = asdict(freeze)
        return freeze

    def unfreeze(self, state: ProjectState, *, authorized: bool, reason: str) -> bool:
        row = state.metadata.get(self.KEY)
        if not row or not authorized:
            return False
        row["active"] = False; row["unfrozen_at"] = _now(); row["unfreeze_reason"] = reason
        return True

    def allow_change(self, state: ProjectState, change_type: str) -> dict[str, Any]:
        row = state.metadata.get(self.KEY) or {}
        if not row.get("active"):
            return {"allowed": True, "reason": "no_active_freeze"}
        allowed = change_type in set(row.get("allowed_change_types", []))
        return {"allowed": allowed, "reason": "allowed_during_freeze" if allowed else "feature_freeze", "version": row.get("version")}


@dataclass(slots=True)
class AcceptanceEvidence:
    gate: str
    status: str
    evidence_ref: str | None = None
    note: str = ""


class FinalAcceptanceMatrix:
    """Separates locally provable gates from external/field proof without upgrading either."""

    LOCAL_GATES = (
        "regression_tests", "compile", "static_analysis", "security_scan", "long_horizon",
        "crash_consistency", "idempotency", "concurrency", "chaos_recovery", "memory_preservation",
    )
    FIELD_GATES = ("windows_install", "windows_restart", "live_provider", "production_proof")

    def evaluate(self, evidence: Iterable[AcceptanceEvidence]) -> dict[str, Any]:
        rows = {e.gate: asdict(e) for e in evidence}
        local = {g: rows.get(g, {"gate": g, "status": "NOT_TESTED"}) for g in self.LOCAL_GATES}
        field = {g: rows.get(g, {"gate": g, "status": "NOT_TESTED"}) for g in self.FIELD_GATES}
        local_pass = all(x["status"] == "PASS" for x in local.values())
        field_pass = all(x["status"] == "PASS" for x in field.values())
        return {
            "local_acceptance_pass": local_pass,
            "field_acceptance_pass": field_pass,
            "production_verified": bool(local_pass and field_pass),
            "local": local,
            "field": field,
            "deferred": [g for g, x in field.items() if x["status"] != "PASS"],
        }


class DogfoodGate:
    """Records self-development trials but never auto-promotes them."""

    KEY = "dogfood_trials_v1"

    def record(self, state: ProjectState, *, description: str, branch: str, tests_passed: bool, benchmark_delta: float, independent_review: bool, security_regressions: int = 0) -> dict[str, Any]:
        trial = {
            "id": sha256(f"{description}|{branch}|{len(state.metadata.setdefault(self.KEY, []))}".encode()).hexdigest()[:16],
            "description": description,
            "branch": branch,
            "tests_passed": bool(tests_passed),
            "benchmark_delta": float(benchmark_delta),
            "independent_review": bool(independent_review),
            "security_regressions": int(security_regressions),
            "eligible_for_human_promotion": bool(tests_passed and benchmark_delta > 0 and independent_review and security_regressions == 0),
            "auto_promoted": False,
            "recorded_at": _now(),
        }
        state.metadata[self.KEY].append(trial)
        return trial
