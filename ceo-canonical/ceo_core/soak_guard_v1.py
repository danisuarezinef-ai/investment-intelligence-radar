from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .decision_trace_v3 import DecisionTraceV3
from .models import ProjectState, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SoakVerdict:
    passed: bool
    cycles: int
    invariant_failures: list[str]
    trace_valid: bool
    digest: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SoakGuardV1:
    """Logical soak/invariant monitor for long-running local qualification.

    Passing this guard is intentionally not a substitute for the physical Windows
    campaign. It only proves that repeated local state transitions preserved selected
    safety and integrity invariants.
    """

    KEY = "soak_guard_v1"

    def inspect(self, state: ProjectState, *, cycles: int) -> SoakVerdict:
        failures: list[str] = []
        forbidden_flags = {
            "automatic_spending": True,
            "automatic_publication": True,
            "automatic_candidate_promotion": True,
            "automatic_installation": True,
        }
        for key, unsafe in forbidden_flags.items():
            if state.metadata.get(key) is unsafe:
                failures.append(f"unsafe_flag:{key}")
        # No task should be RUNNING without a dispatch token once the durable dispatch
        # protocol is active. Historical fixtures can opt out explicitly.
        for task in state.leaf_tasks:
            if task.status == TaskStatus.RUNNING and not task.metadata.get("dispatch_token") and not task.metadata.get("legacy_running_fixture"):
                failures.append(f"running_without_dispatch_token:{task.id}")
                if len(failures) >= 50:
                    break
        trace = DecisionTraceV3().verify(state)
        if not trace.get("valid", True):
            failures.append("decision_trace_invalid")
        digest_src = {
            "project_id": state.id,
            "cycles": int(cycles),
            "task_statuses": sorted((t.id, t.status.value, int(t.attempts)) for t in state.leaf_tasks),
            "failures": sorted(failures),
            "trace": trace,
        }
        digest = sha256(json.dumps(digest_src, sort_keys=True, default=str).encode()).hexdigest()
        verdict = SoakVerdict(not failures, int(cycles), failures, bool(trace.get("valid", True)), digest, _now())
        state.metadata[self.KEY] = verdict.to_dict()
        return verdict


class ReleaseFreezeV1:
    """Exact-file freeze receipt used after local qualification."""

    KEY = "release_freeze_v1"

    @staticmethod
    def create(root: str | Path, *, version: str, required_paths: list[str]) -> dict[str, Any]:
        base = Path(root)
        files: dict[str, str] = {}
        missing: list[str] = []
        for rel in sorted(set(required_paths)):
            path = base / rel
            if not path.is_file():
                missing.append(rel)
                continue
            files[rel] = sha256(path.read_bytes()).hexdigest()
        canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        return {
            "version": version,
            "created_at": _now(),
            "required_file_hashes": files,
            "missing": missing,
            "freeze_digest": sha256(canonical).hexdigest(),
            "automatic_publication": False,
            "automatic_installation": False,
            "production_verified": False,
        }

    @staticmethod
    def verify(root: str | Path, receipt: dict[str, Any]) -> dict[str, Any]:
        base = Path(root)
        mismatches: list[str] = []
        for rel, expected in dict(receipt.get("required_file_hashes", {})).items():
            path = base / rel
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
                mismatches.append(rel)
        return {"valid": not mismatches and not receipt.get("missing"), "mismatches": mismatches, "checked_at": _now()}
