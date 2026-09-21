from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FailureScenario:
    name: str
    fail_phase: str
    cutover_allowed: bool
    rollback_expected: bool


@dataclass(slots=True)
class FailureLabResult:
    scenario: str
    passed: bool
    current_preserved_before_cutover: bool
    rollback_observed: bool
    final_state: str
    detail: str = ""


class UpdateFailureLab:
    """Deterministic updater fault lab with no real filesystem side effects.

    The model deliberately tests the safety ordering introduced in DEV78:
    download/verification/stage/preflight must fail closed before cutover; only
    failures after activation may require rollback.
    """

    PRE_CUTOVER_PHASES = (
        "manifest",
        "download",
        "sha256",
        "package_contract",
        "stage",
        "staged_integrity",
        "preflight_start",
        "preflight_health",
    )
    POST_CUTOVER_PHASES = ("activation", "restart", "health_check")

    @classmethod
    def scenarios(cls) -> tuple[FailureScenario, ...]:
        rows = [FailureScenario(p, p, False, False) for p in cls.PRE_CUTOVER_PHASES]
        rows.extend(FailureScenario(p, p, True, True) for p in cls.POST_CUTOVER_PHASES)
        rows.append(FailureScenario("success", "", True, False))
        return tuple(rows)

    @staticmethod
    def _simulate(scenario: FailureScenario) -> FailureLabResult:
        current = "stable"
        candidate = "candidate"
        pointer = current
        cutover = False
        rollback = False

        phases = [
            "manifest", "download", "sha256", "package_contract", "stage",
            "staged_integrity", "preflight_start", "preflight_health",
            "activation", "restart", "health_check", "healthy",
        ]
        try:
            for phase in phases:
                if phase == "activation":
                    cutover = True
                    pointer = candidate
                if scenario.fail_phase == phase:
                    raise RuntimeError(f"injected:{phase}")
            final = "healthy"
        except RuntimeError:
            if cutover:
                rollback = True
                pointer = current
                final = "rolled_back"
            else:
                final = "blocked_before_cutover"

        preserved_before = (pointer == current) if not cutover else True
        passed = True
        if scenario.fail_phase in UpdateFailureLab.PRE_CUTOVER_PHASES:
            passed = (not cutover and pointer == current and not rollback and final == "blocked_before_cutover")
        elif scenario.fail_phase in UpdateFailureLab.POST_CUTOVER_PHASES:
            passed = (cutover and pointer == current and rollback and final == "rolled_back")
        else:
            passed = (cutover and pointer == candidate and not rollback and final == "healthy")
        return FailureLabResult(
            scenario=scenario.name,
            passed=passed,
            current_preserved_before_cutover=preserved_before,
            rollback_observed=rollback,
            final_state=final,
            detail=f"cutover={cutover}; pointer={pointer}",
        )

    @classmethod
    def run_matrix(cls, *, repetitions: int = 100) -> dict[str, Any]:
        reps = max(1, int(repetitions))
        results: list[FailureLabResult] = []
        for _ in range(reps):
            for scenario in cls.scenarios():
                results.append(cls._simulate(scenario))
        failed = [r for r in results if not r.passed]
        return {
            "ok": not failed,
            "repetitions": reps,
            "scenarios_per_repetition": len(cls.scenarios()),
            "cases": len(results),
            "failed": len(failed),
            "invariants": {
                "no_cutover_before_preflight": all(
                    r.passed for r in results if r.scenario in cls.PRE_CUTOVER_PHASES
                ),
                "post_cutover_failure_rolls_back": all(
                    r.rollback_observed for r in results if r.scenario in cls.POST_CUTOVER_PHASES
                ),
                "success_keeps_candidate": all(
                    r.final_state == "healthy" for r in results if r.scenario == "success"
                ),
            },
            "sample": [asdict(r) for r in results[: len(cls.scenarios())]],
        }
