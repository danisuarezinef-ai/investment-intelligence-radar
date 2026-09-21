from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Callable, Iterable

from .execution_integrity import ChaosPlanner
from .models import ProjectState


@dataclass(slots=True)
class CalibrationObservation:
    predicted: float
    outcome: float
    context: str = "general"


class ConfidenceCalibrationEngine:
    """Tracks whether declared confidence matches observed success."""

    KEY = "confidence_calibration_v1"

    def record(self, state: ProjectState, *, predicted: float, success: bool, context: str = "general") -> dict[str, Any]:
        p = max(0.0, min(1.0, float(predicted)))
        row = {"predicted": p, "outcome": 1.0 if success else 0.0, "context": context}
        state.metadata.setdefault(self.KEY, []).append(row)
        return row

    def report(self, state: ProjectState, *, context: str | None = None, bins: int = 10) -> dict[str, Any]:
        rows = state.metadata.setdefault(self.KEY, [])
        if context is not None:
            rows = [x for x in rows if x.get("context") == context]
        if not rows:
            return {"samples": 0, "brier": None, "expected_calibration_error": None, "bias": None, "bins": []}
        brier = sum((float(x["predicted"]) - float(x["outcome"])) ** 2 for x in rows) / len(rows)
        bias = sum(float(x["predicted"]) - float(x["outcome"]) for x in rows) / len(rows)
        bucket_rows = []
        ece = 0.0
        for idx in range(max(1, bins)):
            lo, hi = idx / bins, (idx + 1) / bins
            selected = [x for x in rows if lo <= float(x["predicted"]) <= hi and (idx == bins - 1 or float(x["predicted"]) < hi)]
            if not selected:
                continue
            mean_p = sum(float(x["predicted"]) for x in selected) / len(selected)
            mean_y = sum(float(x["outcome"]) for x in selected) / len(selected)
            gap = abs(mean_p - mean_y)
            ece += (len(selected) / len(rows)) * gap
            bucket_rows.append({"lo": lo, "hi": hi, "n": len(selected), "predicted": round(mean_p, 6), "observed": round(mean_y, 6), "gap": round(gap, 6)})
        return {"samples": len(rows), "brier": round(brier, 6), "expected_calibration_error": round(ece, 6), "bias": round(bias, 6), "bins": bucket_rows}

    def calibrated(self, state: ProjectState, predicted: float, *, context: str = "general", min_samples: int = 20) -> float:
        report = self.report(state, context=context)
        p = max(0.0, min(1.0, float(predicted)))
        if report["samples"] < min_samples:
            return p
        # Bias correction is intentionally bounded to avoid unstable early swings.
        adjustment = max(-.2, min(.2, float(report["bias"] or 0.0)))
        return round(max(0.0, min(1.0, p - adjustment)), 6)


@dataclass(slots=True)
class SOPVersion:
    id: str
    task_type: str
    version: int
    steps: list[str]
    verified_runs: int
    failed_runs: int
    status: str
    source_digest: str


class AutomatedSOPBuilder:
    """Promotes repeated verified procedures into reusable SOPs."""

    KEY = "sop_library_v1"

    @staticmethod
    def _digest(task_type: str, steps: Iterable[str]) -> str:
        return sha256((task_type + "|" + "|".join(str(x).strip() for x in steps)).encode()).hexdigest()

    def observe(self, state: ProjectState, *, task_type: str, steps: Iterable[str], verified_success: bool, min_verified_runs: int = 3) -> dict[str, Any]:
        clean_steps = [str(x).strip() for x in steps if str(x).strip()]
        if not clean_steps:
            raise ValueError("SOP steps required")
        digest = self._digest(task_type, clean_steps)
        library = state.metadata.setdefault(self.KEY, {})
        family = library.setdefault(task_type, {})
        row = family.setdefault(digest, {"task_type": task_type, "steps": clean_steps, "verified_runs": 0, "failed_runs": 0, "status": "experimental", "version": 1, "source_digest": digest})
        if verified_success:
            row["verified_runs"] += 1
        else:
            row["failed_runs"] += 1
        if row["failed_runs"] > 0:
            row["status"] = "needs_review"
        elif row["verified_runs"] >= min_verified_runs:
            # Demote competing preferred SOPs only when this candidate has more evidence.
            current_preferred = [x for x in family.values() if x.get("status") == "preferred" and x.get("source_digest") != digest]
            if not current_preferred or all(row["verified_runs"] > x.get("verified_runs", 0) for x in current_preferred):
                for x in current_preferred:
                    x["status"] = "verified"
                row["status"] = "preferred"
            else:
                row["status"] = "verified"
        return dict(row)

    def preferred(self, state: ProjectState, task_type: str) -> dict[str, Any] | None:
        family = state.metadata.setdefault(self.KEY, {}).get(task_type, {})
        candidates = [dict(x) for x in family.values() if x.get("status") == "preferred"]
        return max(candidates, key=lambda x: x.get("verified_runs", 0), default=None)

    def propose_revision(self, state: ProjectState, *, task_type: str, base_digest: str, new_steps: Iterable[str]) -> dict[str, Any]:
        family = state.metadata.setdefault(self.KEY, {}).setdefault(task_type, {})
        base = family.get(base_digest)
        if not base:
            raise KeyError("base SOP not found")
        steps = [str(x).strip() for x in new_steps if str(x).strip()]
        digest = self._digest(task_type, steps)
        row = family.setdefault(digest, {"task_type": task_type, "steps": steps, "verified_runs": 0, "failed_runs": 0, "status": "experimental", "version": int(base.get("version", 1)) + 1, "source_digest": digest, "parent_digest": base_digest})
        return dict(row)


class ChaosRecoveryHarness:
    """Deterministic chaos experiments with explicit expected recovery evidence."""

    KEY = "chaos_recovery_trials_v1"

    def run(
        self,
        state: ProjectState,
        task_ids: Iterable[str],
        *,
        injector: Callable[[str, str], Any],
        recovery: Callable[[str, str], str],
        seed: int = 1,
        rate: float = .1,
    ) -> dict[str, Any]:
        planner = ChaosPlanner()
        faults = planner.plan(list(task_ids), seed=seed, rate=rate)
        trials = []
        for fault in faults:
            injected = False
            error = None
            try:
                injector(fault.task_id, fault.kind)
                injected = True
            except Exception as exc:
                injected = True
                error = type(exc).__name__
            expected = planner.expected_recovery(fault.kind)
            actual = recovery(fault.task_id, fault.kind)
            trials.append({"task_id": fault.task_id, "fault": fault.kind, "injected": injected, "injection_error": error, "expected_recovery": expected, "actual_recovery": actual, "pass": actual == expected})
        summary = {"seed": seed, "planned_faults": len(faults), "passed": sum(int(x["pass"]) for x in trials), "failed": sum(int(not x["pass"]) for x in trials), "pass": all(x["pass"] for x in trials), "trials": trials}
        state.metadata.setdefault(self.KEY, []).append(summary)
        return summary
