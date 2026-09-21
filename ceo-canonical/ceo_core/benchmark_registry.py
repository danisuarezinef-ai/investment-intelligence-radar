from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class BenchmarkSample:
    suite: str
    version: str
    metric: str
    value: float
    higher_is_better: bool = True
    holdout: bool = True


class BenchmarkRegistry:
    KEY = "benchmark_registry_v2"

    def record(self, state: ProjectState, samples: Iterable[BenchmarkSample]) -> int:
        rows = state.metadata.setdefault(self.KEY, {}).setdefault("samples", [])
        added = 0
        for sample in samples:
            rows.append({**asdict(sample), "recorded_at": _now()})
            added += 1
        del rows[:-20000]
        return added

    def compare(
        self,
        state: ProjectState,
        *,
        suite: str,
        baseline: str,
        challenger: str,
        max_regression_fraction: float = 0.02,
        require_holdout: bool = True,
    ) -> dict[str, Any]:
        rows = (state.metadata.get(self.KEY) or {}).get("samples", []) or []
        relevant = [r for r in rows if r.get("suite") == suite and (not require_holdout or r.get("holdout") is True)]
        metrics = sorted({str(r.get("metric")) for r in relevant})
        results = []
        all_pass = bool(metrics)
        for metric in metrics:
            b = [float(r["value"]) for r in relevant if r.get("version") == baseline and r.get("metric") == metric]
            c = [float(r["value"]) for r in relevant if r.get("version") == challenger and r.get("metric") == metric]
            if not b or not c:
                results.append({"metric": metric, "passed": False, "reason": "missing_baseline_or_challenger"})
                all_pass = False
                continue
            direction = bool(next(r.get("higher_is_better", True) for r in relevant if r.get("metric") == metric))
            bmed, cmed = median(b), median(c)
            denom = max(abs(bmed), 1e-12)
            signed_gain = (cmed - bmed) / denom * (1 if direction else -1)
            passed = signed_gain >= -abs(float(max_regression_fraction))
            all_pass &= passed
            results.append({"metric": metric, "baseline_median": bmed, "challenger_median": cmed, "signed_gain_fraction": round(signed_gain, 6), "passed": passed, "samples": {"baseline": len(b), "challenger": len(c)}})
        report = {"suite": suite, "baseline": baseline, "challenger": challenger, "require_holdout": require_holdout, "passed": all_pass, "metrics": results, "generated_at": _now()}
        state.metadata.setdefault(self.KEY, {})["last_comparison"] = report
        return report
