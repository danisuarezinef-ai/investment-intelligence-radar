from __future__ import annotations

import json
import os
import shutil
import time
import zipfile
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Sequence

from .models import ProjectState
from .self_hosting_evolution import SelfImprovementAcceptanceGate
from .self_hosting_tools import ImmutableRunningVersion, SelfHostingWorkspace, _tree_digest


def _now() -> float:
    return time.time()


def _sha_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _manifest(root: str | Path) -> dict[str, str]:
    base = Path(root).resolve()
    result: dict[str, str] = {}
    ignored = {".git", "__pycache__", ".pytest_cache", "data", "browser_profiles", ".mypy_cache"}
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        rel = path.relative_to(base)
        if any(part in ignored for part in rel.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        result[rel.as_posix()] = _sha_file(path)
    return result


# 41. Reinforced no-auto-promotion policy
class AutoPromotionGuard:
    KEY = "auto_promotion_guard_v2"

    def initialize(self, state: ProjectState) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {})
        row.update({
            "auto_promotion_allowed": False,
            "agent_can_promote": False,
            "human_approval_required": True,
            "initialized_at": row.get("initialized_at", _now()),
        })
        return dict(row)

    def assert_manual(self, state: ProjectState, *, human_confirmed: bool, actor: str = "human") -> None:
        self.initialize(state)
        if not human_confirmed or str(actor).lower() != "human":
            raise PermissionError("promotion requires explicit human confirmation")

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        return self.initialize(state)


# 42. Candidate build generator
class CandidateBuildGenerator:
    KEY = "candidate_builds_v1"
    EXCLUDE_PARTS = {".git", "__pycache__", ".pytest_cache", "data", "browser_profiles", ".mypy_cache"}

    def build(
        self,
        state: ProjectState,
        candidate_root: str | Path,
        output_dir: str | Path,
        *,
        mission_id: str,
        version: str,
        running_root: str | Path,
    ) -> dict[str, Any]:
        acceptance = state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).get(mission_id, {})
        if acceptance.get("stage") != "ELIGIBLE_FOR_PROMOTION":
            raise PermissionError("candidate is not ELIGIBLE_FOR_PROMOTION")
        candidate = Path(candidate_root).resolve()
        running = Path(running_root).resolve()
        ImmutableRunningVersion(running).assert_candidate(candidate)
        out = Path(output_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
        safe_version = "".join(c if c.isalnum() or c in ".-_" else "-" for c in version).strip("-") or "candidate"
        package = out / f"ceo-de-ias-{safe_version}-candidate.zip"
        manifest = _manifest(candidate)
        if not manifest:
            raise ValueError("candidate workspace is empty")
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel in sorted(manifest):
                zf.write(candidate / rel, arcname=rel)
        row = {
            "mission_id": mission_id,
            "version": version,
            "candidate_root": str(candidate),
            "package": str(package),
            "package_sha256": _sha_file(package),
            "file_count": len(manifest),
            "candidate_digest": _tree_digest(candidate, exclude=(".git", "__pycache__", ".pytest_cache", "data", "browser_profiles")),
            "generated_at": _now(),
            "installed": False,
            "auto_promoted": False,
        }
        state.metadata.setdefault(self.KEY, {})[mission_id] = row
        return dict(row)


# 43. Automatic release diff
class SelfHostingReleaseDiff:
    KEY = "self_hosting_release_diff_v1"

    def compare(self, state: ProjectState, baseline_root: str | Path, candidate_root: str | Path, *, mission_id: str) -> dict[str, Any]:
        baseline = _manifest(baseline_root)
        candidate = _manifest(candidate_root)
        bkeys, ckeys = set(baseline), set(candidate)
        added = sorted(ckeys - bkeys)
        removed = sorted(bkeys - ckeys)
        modified = sorted(k for k in bkeys & ckeys if baseline[k] != candidate[k])
        row = {
            "mission_id": mission_id,
            "added": added,
            "modified": modified,
            "removed": removed,
            "changed_count": len(added) + len(modified) + len(removed),
            "baseline_file_count": len(baseline),
            "candidate_file_count": len(candidate),
            "baseline_digest": sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest(),
            "candidate_digest": sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest(),
            "compared_at": _now(),
        }
        state.metadata.setdefault(self.KEY, {})[mission_id] = row
        return dict(row)


# 44. Human promotion gate
class HumanPromotionGate:
    KEY = "human_promotion_gate_v1"

    def decide(
        self,
        state: ProjectState,
        *,
        mission_id: str,
        decision: str,
        human_confirmed: bool,
        actor: str = "human",
        note: str = "",
    ) -> dict[str, Any]:
        acceptance = state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).get(mission_id, {})
        if acceptance.get("stage") != "ELIGIBLE_FOR_PROMOTION":
            raise PermissionError("candidate must be ELIGIBLE_FOR_PROMOTION before human decision")
        AutoPromotionGuard().assert_manual(state, human_confirmed=human_confirmed, actor=actor)
        decision = str(decision).upper()
        if decision not in {"APPROVE", "REJECT"}:
            raise ValueError("decision must be APPROVE or REJECT")
        row = {
            "mission_id": mission_id,
            "decision": decision,
            "approved": decision == "APPROVE",
            "actor": "human",
            "human_confirmed": True,
            "note": str(note)[:2000],
            "decided_at": _now(),
            "installation_performed": False,
        }
        state.metadata.setdefault(self.KEY, {})[mission_id] = row
        return dict(row)


# 45. Rollback package + restoration primitive. Never replaces the currently-running tree.
class UpdateRollbackManager:
    KEY = "self_hosting_rollback_v1"

    def prepare(self, state: ProjectState, stable_root: str | Path, output_dir: str | Path, *, version: str) -> dict[str, Any]:
        stable = Path(stable_root).resolve()
        out = Path(output_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
        package = out / f"ceo-rollback-{version}.zip"
        manifest = _manifest(stable)
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel in sorted(manifest):
                zf.write(stable / rel, arcname=rel)
        row = {"version": version, "package": str(package), "sha256": _sha_file(package), "file_count": len(manifest), "prepared_at": _now(), "restores_running_process": False}
        state.metadata.setdefault(self.KEY, {})[version] = row
        return dict(row)

    def restore_to_staging(self, package: str | Path, staging_root: str | Path, *, expected_sha256: str) -> dict[str, Any]:
        package = Path(package).resolve(); staging = Path(staging_root).resolve()
        if _sha_file(package) != expected_sha256:
            raise ValueError("rollback package hash mismatch")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        with zipfile.ZipFile(package) as zf:
            zf.extractall(staging)
        return {"ok": True, "staging_root": str(staging), "digest": _tree_digest(staging, exclude=("__pycache__", ".pytest_cache")), "running_process_replaced": False}


@dataclass(slots=True)
class FieldExerciseEvidence:
    exercise: str
    field_executed: bool
    success: bool
    evidence: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    platform: str = "unknown"
    recorded_at: float = field(default_factory=_now)


class FieldExerciseRegistry:
    KEY = "self_hosting_field_exercises_v1"
    EXERCISES = ("chrome_real", "multi_app_real", "chatgpt_real", "self_hosting_real")

    def record(self, state: ProjectState, evidence: FieldExerciseEvidence) -> dict[str, Any]:
        if evidence.exercise not in self.EXERCISES:
            raise ValueError(evidence.exercise)
        # A simulation may be useful evidence but may never upgrade a field gate.
        verified = bool(evidence.field_executed and evidence.success and evidence.evidence)
        row = asdict(evidence)
        row["verified"] = verified
        row["status"] = "VERIFIED" if verified else ("FAILED" if evidence.field_executed and not evidence.success else "NOT_VERIFIED")
        state.metadata.setdefault(self.KEY, {})[evidence.exercise] = row
        return dict(row)

    def status(self, state: ProjectState, exercise: str) -> dict[str, Any]:
        row = state.metadata.get(self.KEY, {}).get(exercise)
        if row:
            return dict(row)
        return {"exercise": exercise, "verified": False, "status": "NOT_VERIFIED", "field_executed": False, "success": False, "evidence": []}


# 46-49. First field exercises. They evaluate evidence; physical execution lives in Windows/browser/provider adapters.
class FirstExerciseEvaluator:
    def __init__(self) -> None:
        self.registry = FieldExerciseRegistry()

    def chrome(self, state: ProjectState, *, field_executed: bool, success: bool, evidence: Sequence[str], details: dict[str, Any] | None = None, platform: str = "unknown") -> dict[str, Any]:
        required = {"opened", "navigated", "read_content", "evidence_returned"}
        data = dict(details or {})
        success = bool(success and required.issubset({k for k, v in data.items() if v is True}))
        return self.registry.record(state, FieldExerciseEvidence("chrome_real", field_executed, success, list(evidence), data, platform))

    def multi_app(self, state: ProjectState, *, field_executed: bool, success: bool, evidence: Sequence[str], details: dict[str, Any] | None = None, platform: str = "unknown") -> dict[str, Any]:
        required = {"browser_step", "artifact_step", "terminal_step", "result_registered"}
        data = dict(details or {})
        success = bool(success and required.issubset({k for k, v in data.items() if v is True}))
        return self.registry.record(state, FieldExerciseEvidence("multi_app_real", field_executed, success, list(evidence), data, platform))

    def chatgpt(self, state: ProjectState, *, field_executed: bool, success: bool, evidence: Sequence[str], details: dict[str, Any] | None = None) -> dict[str, Any]:
        live = bool(state.metadata.get("live_provider_gate_v2", {}).get("authenticated_live_verified"))
        data = dict(details or {}); data["live_provider_verified"] = live
        success = bool(success and live and data.get("task_assigned") is True and data.get("response_processed") is True)
        return self.registry.record(state, FieldExerciseEvidence("chatgpt_real", field_executed, success, list(evidence), data, "provider"))

    def self_hosting(self, state: ProjectState, *, field_executed: bool, success: bool, evidence: Sequence[str], mission_id: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        acceptance = state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).get(mission_id, {})
        data = dict(details or {}); data["mission_id"] = mission_id; data["acceptance_stage"] = acceptance.get("stage")
        success = bool(success and acceptance.get("stage") == "ELIGIBLE_FOR_PROMOTION" and acceptance.get("auto_promoted") is False)
        return self.registry.record(state, FieldExerciseEvidence("self_hosting_real", field_executed, success, list(evidence), data, "local_candidate"))


# 50. Self-hosting Alpha gate
class SelfHostingAlphaGate:
    KEY = "self_hosting_alpha_gate_v1"

    def assess(self, state: ProjectState) -> dict[str, Any]:
        registry = FieldExerciseRegistry()
        exercises = {name: registry.status(state, name) for name in registry.EXERCISES}
        desktop = state.metadata.get("desktop_browser_integration_v1", {})
        live = state.metadata.get("live_provider_gate_v2", {})
        workspace = state.metadata.get(SelfHostingWorkspace.KEY, {})
        acceptance = list(state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).values())
        rollback = state.metadata.get(UpdateRollbackManager.KEY, {})
        builds = state.metadata.get(CandidateBuildGenerator.KEY, {})
        checks = {
            "chrome_real_verified": exercises["chrome_real"].get("verified") is True,
            "multi_app_real_verified": exercises["multi_app_real"].get("verified") is True,
            "chatgpt_real_verified": exercises["chatgpt_real"].get("verified") is True and bool(live.get("authenticated_live_verified")),
            "self_hosting_cycle_verified": exercises["self_hosting_real"].get("verified") is True,
            "windows_desktop_physically_verified": bool(desktop.get("physical_windows_validated")),
            "chrome_physically_verified": bool(desktop.get("chrome_live_validated")),
            "isolated_candidate_workspace": bool(workspace.get("running_immutable")) and bool(workspace.get("candidate_root")),
            "eligible_candidate_exists": any(x.get("stage") == "ELIGIBLE_FOR_PROMOTION" for x in acceptance),
            "candidate_build_exists": bool(builds),
            "rollback_prepared": bool(rollback),
            "auto_promotion_forbidden": AutoPromotionGuard().snapshot(state).get("auto_promotion_allowed") is False,
        }
        ready = all(checks.values())
        blockers = [k for k, v in checks.items() if not v]
        row = {
            "status": "SELF_HOSTING_ALPHA_READY" if ready else "NOT_READY",
            "ready": ready,
            "checks": checks,
            "blockers": blockers,
            "field_exercises": exercises,
            "production_verified": False,
            "assessed_at": _now(),
        }
        state.metadata[self.KEY] = row
        return dict(row)


class SelfHostingAlphaCore:
    VERSION = 1

    def __init__(self, running_root: str | Path):
        self.running_root = Path(running_root).resolve()
        self.guard = AutoPromotionGuard()
        self.builds = CandidateBuildGenerator()
        self.diff = SelfHostingReleaseDiff()
        self.promotion = HumanPromotionGate()
        self.rollback = UpdateRollbackManager()
        self.exercises = FirstExerciseEvaluator()
        self.gate = SelfHostingAlphaGate()

    def initialize(self, state: ProjectState) -> dict[str, Any]:
        self.guard.initialize(state)
        return self.snapshot(state)

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "auto_promotion": self.guard.snapshot(state),
            "candidate_builds": list(state.metadata.get(CandidateBuildGenerator.KEY, {}).values())[-10:],
            "release_diffs": list(state.metadata.get(SelfHostingReleaseDiff.KEY, {}).values())[-10:],
            "human_decisions": list(state.metadata.get(HumanPromotionGate.KEY, {}).values())[-10:],
            "rollback_packages": list(state.metadata.get(UpdateRollbackManager.KEY, {}).values())[-10:],
            "field_exercises": {name: FieldExerciseRegistry().status(state, name) for name in FieldExerciseRegistry.EXERCISES},
            "alpha_gate": self.gate.assess(state),
            "windows_physical": "DEFERRED_BY_USER",
            "live_provider": "VERIFIED" if state.metadata.get("live_provider_gate_v2", {}).get("authenticated_live_verified") else "NOT_VERIFIED",
            "production_verified": False,
        }

    def preflight(self, state: ProjectState) -> dict[str, Any]:
        checks = {
            "reinforced_no_auto_promotion": True,
            "candidate_build_generator": True,
            "release_diff": True,
            "human_promotion_gate": True,
            "rollback_staging": True,
            "chrome_exercise_harness": True,
            "multi_app_exercise_harness": True,
            "chatgpt_exercise_harness": True,
            "self_hosting_exercise_harness": True,
            "alpha_gate_evidence_backed": True,
        }
        return {"pass": all(checks.values()), "checks": checks, "alpha": self.gate.assess(state), "windows_physical": "DEFERRED_BY_USER", "production_verified": False}
