from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
from typing import Callable, Any

from .models import ProjectState


@dataclass(slots=True)
class ImprovementCandidate:
    id: str
    description: str
    baseline_score: float
    challenger_score: float
    tests_passed: bool
    benchmark_improved: bool
    promoted: bool = False


class SelfEvaluationEngine:
    """Turns completed-project telemetry into bounded improvement hypotheses."""
    def evaluate(self, state: ProjectState) -> dict[str, Any]:
        provider_stats = state.metadata.get("provider_stats", {})
        failures = sum(int(x.get("failures", 0)) for x in provider_stats.values())
        runs = sum(int(x.get("runs", 0)) for x in provider_stats.values())
        retries = sum(max(0, t.attempts - 1) for t in state.leaf_tasks)
        low_quality = sum((t.quality_score or 1) < .6 for t in state.completed_leaf_tasks)
        recommendations = []
        if retries > max(3, len(state.leaf_tasks) * .1): recommendations.append("increase_task_fragmentation_or_provider_fallback")
        if low_quality: recommendations.append("increase_verification_for_low_quality_task_types")
        if failures / max(1, runs) > .12: recommendations.append("reduce_concurrency_or_demote_unstable_provider")
        result = {"runs": runs, "failures": failures, "retries": retries, "low_quality": low_quality, "recommendations": recommendations}
        state.metadata["self_evaluation"] = result
        return result


class SelfImprovementSandbox:
    """Evaluates proposed changes out-of-band; Stable is never replaced automatically."""
    def evaluate_candidate(self, description: str, *, baseline_score: float, challenger_score: float, tests_passed: bool, benchmark_tolerance: float = 0.01) -> ImprovementCandidate:
        cid = sha256(description.encode()).hexdigest()[:12]
        improved = challenger_score > baseline_score * (1 + benchmark_tolerance)
        return ImprovementCandidate(cid, description, baseline_score, challenger_score, tests_passed, improved, False)

    def recommend_promotion(self, candidate: ImprovementCandidate) -> bool:
        return bool(candidate.tests_passed and candidate.benchmark_improved)

class LocalImprovementSandbox:
    """Copies Stable to a temporary challenger workspace and evaluates it there.

    It never mutates Stable. A caller may provide a patch callback for generated code,
    then the sandbox runs deterministic validation commands and compares a numeric score.
    """
    def run(self, source_root: str | Path, *, description: str, patch: Callable[[Path], None] | None = None, test_command: list[str] | None = None, score_fn: Callable[[Path], float] | None = None) -> ImprovementCandidate:
        import shutil, subprocess, tempfile
        source = Path(source_root)
        baseline_score = float(score_fn(source)) if score_fn else 1.0
        with tempfile.TemporaryDirectory(prefix="ceo-challenger-") as td:
            challenger = Path(td) / "challenger"
            shutil.copytree(source, challenger, ignore=shutil.ignore_patterns("data", "__pycache__", ".pytest_cache", "browser_profiles"))
            if patch: patch(challenger)
            command = test_command or ["python", "-m", "pytest", "-q"]
            proc = subprocess.run(command, cwd=challenger, capture_output=True, text=True, timeout=180)
            tests_passed = proc.returncode == 0
            challenger_score = float(score_fn(challenger)) if score_fn and tests_passed else 0.0
            return SelfImprovementSandbox().evaluate_candidate(description, baseline_score=baseline_score, challenger_score=challenger_score, tests_passed=tests_passed, benchmark_tolerance=0.0)
