from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import random
from typing import Any, Callable, Iterable

from .models import ProjectState, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class FaultScenario:
    scenario_id: str
    family: str
    description: str
    severity: int = 1
    safe_to_retry: bool = True


@dataclass(frozen=True, slots=True)
class StressOutcome:
    scenario_id: str
    passed: bool
    invariant: str
    detail: str = ""


class StressLab:
    """Deterministic fault-injection model for CEO's operational invariants.

    The lab never performs external side effects. It mutates only caller-provided
    in-memory state (normally a synthetic ProjectState) and records a bounded summary.
    Physical Windows, GUI and authenticated-provider claims remain separate gates.
    """

    DEFAULT_SCENARIOS = (
        FaultScenario("provider-timeout", "provider", "provider exceeds deadline"),
        FaultScenario("provider-empty", "provider", "provider returns empty output"),
        FaultScenario("worker-orphan", "worker", "persisted RUNNING work has no live worker"),
        FaultScenario("store-corruption", "persistence", "primary checkpoint becomes unreadable"),
        FaultScenario("browser-closed", "application", "browser disappears mid-flow"),
        FaultScenario("download-partial", "application", "download stops before expected length"),
        FaultScenario("remote-token-tamper", "security", "remote token signature is modified", safe_to_retry=False),
        FaultScenario("ledger-tamper", "security", "evidence hash chain is modified", safe_to_retry=False),
        FaultScenario("hard-dependency-missing", "planning", "hard prerequisite is absent", safe_to_retry=False),
        FaultScenario("soft-dependency-missing", "planning", "best-effort prerequisite is absent"),
        FaultScenario("update-stage-tamper", "update", "staged critical file changes", safe_to_retry=False),
        FaultScenario("restart-mid-dispatch", "runtime", "process exits after durable dispatch intent"),
    )

    def __init__(self, *, seed: int = 4655, history_limit: int = 200) -> None:
        self.seed = int(seed)
        self.history_limit = max(10, int(history_limit))

    def scenario_matrix(self, repetitions: int = 1) -> list[FaultScenario]:
        repetitions = max(1, int(repetitions))
        rows: list[FaultScenario] = []
        for i in range(repetitions):
            for scenario in self.DEFAULT_SCENARIOS:
                rows.append(FaultScenario(
                    scenario_id=f"{scenario.scenario_id}-{i+1}",
                    family=scenario.family,
                    description=scenario.description,
                    severity=scenario.severity,
                    safe_to_retry=scenario.safe_to_retry,
                ))
        return rows

    def synthetic_order(self, scenarios: Iterable[FaultScenario]) -> list[FaultScenario]:
        rows = list(scenarios)
        random.Random(self.seed).shuffle(rows)
        return rows

    @staticmethod
    def invariant_snapshot(state: ProjectState) -> dict[str, Any]:
        dangerous_running = [
            t.id for t in state.leaf_tasks
            if t.status == TaskStatus.RUNNING and any(bool(t.metadata.get(k)) for k in (
                "destructive", "irreversible", "spending", "publication", "external_side_effect"
            ))
        ]
        return {
            "paused": bool(state.paused),
            "dangerous_running": dangerous_running,
            "automatic_spending": bool(state.metadata.get("automatic_spending", False)),
            "automatic_publication": bool(state.metadata.get("automatic_publication", False)),
            "stable_auto_promotion": bool(state.metadata.get("automatic_candidate_promotion", False)),
        }

    @staticmethod
    def assert_safety_invariants(snapshot: dict[str, Any]) -> list[str]:
        failures = []
        if snapshot.get("automatic_spending"):
            failures.append("automatic_spending_enabled")
        if snapshot.get("automatic_publication"):
            failures.append("automatic_publication_enabled")
        if snapshot.get("stable_auto_promotion"):
            failures.append("automatic_candidate_promotion_enabled")
        return failures

    def run_model(
        self,
        state: ProjectState,
        executor: Callable[[ProjectState, FaultScenario], StressOutcome],
        *,
        repetitions: int = 1,
    ) -> dict[str, Any]:
        outcomes: list[StressOutcome] = []
        for scenario in self.synthetic_order(self.scenario_matrix(repetitions)):
            try:
                outcome = executor(state, scenario)
            except Exception as exc:  # the lab converts harness crashes into explicit failures
                outcome = StressOutcome(scenario.scenario_id, False, "executor_did_not_crash", f"{type(exc).__name__}: {exc}")
            outcomes.append(outcome)
        safety_failures = self.assert_safety_invariants(self.invariant_snapshot(state))
        passed = sum(1 for x in outcomes if x.passed)
        report = {
            "generated_at": _now(),
            "seed": self.seed,
            "cases": len(outcomes),
            "passed": passed,
            "failed": len(outcomes) - passed,
            "safety_failures": safety_failures,
            "all_pass": passed == len(outcomes) and not safety_failures,
            "digest": sha256("|".join(f"{x.scenario_id}:{int(x.passed)}:{x.invariant}" for x in outcomes).encode()).hexdigest(),
            "failures": [asdict(x) for x in outcomes if not x.passed][:50],
        }
        history = state.metadata.setdefault("stress_lab_history", [])
        history.append(report)
        del history[:-self.history_limit]
        state.metadata["stress_lab_latest"] = report
        return report
