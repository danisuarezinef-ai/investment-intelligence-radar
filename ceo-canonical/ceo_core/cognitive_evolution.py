from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable
import json
import math
import re

from .models import ProjectState, Task, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


# ---------------------------------------------------------------------------
# 1-4. Dogfooding, self-improvement, immutable baseline and holdout governance
# ---------------------------------------------------------------------------


class ImmutableBaselineRegistry:
    """Freezes benchmark/release baselines and refuses silent replacement."""

    KEY = "immutable_baselines_v1"

    def freeze(self, state: ProjectState, *, name: str, payload: Any, source_ref: str = "") -> dict[str, Any]:
        digest = _digest(payload)
        rows = state.metadata.setdefault(self.KEY, {})
        existing = rows.get(name)
        if existing:
            if existing["digest"] != digest:
                raise RuntimeError(f"baseline '{name}' is immutable")
            return dict(existing)
        row = {"name": name, "digest": digest, "source_ref": source_ref, "frozen_at": _now(), "immutable": True}
        rows[name] = row
        return dict(row)

    def get(self, state: ProjectState, name: str) -> dict[str, Any] | None:
        row = state.metadata.setdefault(self.KEY, {}).get(name)
        return dict(row) if row else None


@dataclass(slots=True)
class BenchmarkCase:
    id: str
    domain: str
    difficulty: float = .5
    tags: list[str] = field(default_factory=list)
    required_steps: int = 1
    hidden: bool = False


class HoldoutBenchmarkRegistry:
    """Keeps development and evaluation cases disjoint by ID and content digest."""

    KEY = "holdout_benchmarks_v1"

    def register(self, state: ProjectState, *, suite: str, cases: Iterable[BenchmarkCase], split: str) -> dict[str, Any]:
        if split not in {"development", "holdout"}:
            raise ValueError("split must be development or holdout")
        root = state.metadata.setdefault(self.KEY, {}).setdefault(suite, {"development": {}, "holdout": {}})
        target = root[split]
        other = root["holdout" if split == "development" else "development"]
        other_digests = {x["digest"] for x in other.values()}
        added = 0
        for case in cases:
            payload = asdict(case)
            digest = _digest(payload)
            if case.id in other or digest in other_digests:
                raise ValueError(f"benchmark leakage detected for case {case.id}")
            target[case.id] = {**payload, "digest": digest, "split": split}
            added += 1
        return {"suite": suite, "split": split, "added": added, "development": len(root["development"]), "holdout": len(root["holdout"])}

    def cases(self, state: ProjectState, suite: str, split: str = "holdout") -> list[dict[str, Any]]:
        return list((state.metadata.setdefault(self.KEY, {}).get(suite, {}) or {}).get(split, {}).values())


class ControlledDogfoodEngine:
    """Records real self-development candidates but cannot merge/promote them."""

    KEY = "controlled_dogfood_v2"

    def begin(self, state: ProjectState, *, description: str, branch: str, baseline: str, scope: Iterable[str]) -> dict[str, Any]:
        if not branch.startswith("ceo/self-"):
            raise ValueError("dogfood branch must be isolated under ceo/self-")
        trial_id = sha256(f"{description}|{branch}|{len(state.metadata.setdefault(self.KEY, {}))}".encode()).hexdigest()[:20]
        row = {
            "id": trial_id, "description": description, "branch": branch, "baseline": baseline,
            "scope": sorted(set(str(x) for x in scope)), "status": "running", "started_at": _now(),
            "auto_merge_allowed": False, "auto_promoted": False,
        }
        state.metadata[self.KEY][trial_id] = row
        return dict(row)

    def finish(self, state: ProjectState, trial_id: str, *, tests_passed: bool, holdout_passed: bool,
               benchmark_delta: float, independent_review: bool, security_regressions: int = 0,
               changed_paths: Iterable[str] = ()) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).get(trial_id)
        if not row:
            raise KeyError("dogfood trial not found")
        eligible = bool(tests_passed and holdout_passed and benchmark_delta > 0 and independent_review and security_regressions == 0)
        row.update({
            "tests_passed": bool(tests_passed), "holdout_passed": bool(holdout_passed),
            "benchmark_delta": float(benchmark_delta), "independent_review": bool(independent_review),
            "security_regressions": int(security_regressions), "changed_paths": sorted(set(changed_paths)),
            "eligible_for_human_promotion": eligible, "status": "eligible" if eligible else "rejected",
            "finished_at": _now(), "auto_promoted": False,
        })
        return dict(row)


class SelfImprovementPipeline:
    """Governed detect -> propose -> build -> evaluate -> review pipeline.

    Promotion is intentionally outside this class; it can only make a candidate eligible.
    """

    KEY = "self_improvement_pipeline_v1"
    STAGES = ("detected", "proposed", "built", "evaluated", "reviewed", "eligible", "rejected")

    def detect(self, state: ProjectState, *, weakness: str, evidence_refs: Iterable[str], expected_gain: float) -> dict[str, Any]:
        iid = sha256(f"{weakness}|{len(state.metadata.setdefault(self.KEY, {}))}".encode()).hexdigest()[:20]
        row = {"id": iid, "weakness": weakness, "evidence_refs": list(evidence_refs), "expected_gain": float(expected_gain), "stage": "detected", "created_at": _now(), "auto_promoted": False}
        state.metadata[self.KEY][iid] = row
        return dict(row)

    def propose(self, state: ProjectState, improvement_id: str, *, hypothesis: str, branch: str) -> dict[str, Any]:
        row = self._row(state, improvement_id)
        self._require_stage(row, {"detected"})
        row.update({"hypothesis": hypothesis, "branch": branch, "stage": "proposed"})
        return dict(row)

    def built(self, state: ProjectState, improvement_id: str, *, commit_ref: str, changed_paths: Iterable[str]) -> dict[str, Any]:
        row = self._row(state, improvement_id); self._require_stage(row, {"proposed"})
        row.update({"commit_ref": commit_ref, "changed_paths": sorted(set(changed_paths)), "stage": "built"})
        return dict(row)

    def evaluate(self, state: ProjectState, improvement_id: str, *, development_score: float, holdout_score: float,
                 baseline_holdout_score: float, tests_passed: bool, security_regressions: int = 0) -> dict[str, Any]:
        row = self._row(state, improvement_id); self._require_stage(row, {"built"})
        gain = float(holdout_score) - float(baseline_holdout_score)
        row.update({"development_score": float(development_score), "holdout_score": float(holdout_score),
                    "baseline_holdout_score": float(baseline_holdout_score), "holdout_gain": gain,
                    "tests_passed": bool(tests_passed), "security_regressions": int(security_regressions), "stage": "evaluated"})
        return dict(row)

    def review(self, state: ProjectState, improvement_id: str, *, independent_review: bool, min_holdout_gain: float = .0) -> dict[str, Any]:
        row = self._row(state, improvement_id); self._require_stage(row, {"evaluated"})
        eligible = bool(independent_review and row.get("tests_passed") and row.get("security_regressions", 0) == 0 and float(row.get("holdout_gain", 0)) > min_holdout_gain)
        row.update({"independent_review": bool(independent_review), "stage": "eligible" if eligible else "rejected", "eligible_for_human_promotion": eligible, "auto_promoted": False, "reviewed_at": _now()})
        return dict(row)

    def _row(self, state: ProjectState, improvement_id: str) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).get(improvement_id)
        if not row: raise KeyError("improvement not found")
        return row

    @staticmethod
    def _require_stage(row: dict[str, Any], stages: set[str]) -> None:
        if row.get("stage") not in stages:
            raise RuntimeError(f"invalid self-improvement transition from {row.get('stage')}")


# ---------------------------------------------------------------------------
# 5-8. Benchmark families
# ---------------------------------------------------------------------------


class BenchmarkPortfolio:
    DOMAINS = ("coding", "research", "planning", "analysis", "documentation", "debugging", "decision", "project_management")
    ADVERSARIAL_TAGS = ("contradiction", "prompt_injection", "false_source", "hidden_requirement")

    def default_multidomain(self) -> list[BenchmarkCase]:
        return [BenchmarkCase(f"domain-{d}", d, .6, ["multidomain"], required_steps=8, hidden=True) for d in self.DOMAINS]

    def long_reasoning(self, count: int = 4, steps: int = 120) -> list[BenchmarkCase]:
        return [BenchmarkCase(f"long-{i+1}", "planning", .9, ["long_horizon", "dependency_retention"], required_steps=steps + i * 20, hidden=True) for i in range(max(1, count))]

    def incomplete_projects(self) -> list[BenchmarkCase]:
        tags = ["missing_files", "partial_docs", "ambiguous_requirements", "broken_dependency"]
        return [BenchmarkCase(f"incomplete-{tag}", "project_management", .8, ["incomplete_project", tag], required_steps=25, hidden=True) for tag in tags]

    def adversarial(self) -> list[BenchmarkCase]:
        return [BenchmarkCase(f"adversarial-{tag}", "decision", .95, ["adversarial", tag], required_steps=20, hidden=True) for tag in self.ADVERSARIAL_TAGS]

    def summarize(self, observations: Iterable[dict[str, Any]], *, require_all_domains: bool = False) -> dict[str, Any]:
        rows = list(observations)
        if not rows: return {"cases": 0, "pass": False, "score": 0.0, "domains": {}}
        domains: dict[str, list[dict[str, Any]]] = {}
        for row in rows: domains.setdefault(str(row.get("domain", "unknown")), []).append(row)
        domain_scores = {d: round(sum(float(x.get("score", 0)) for x in rs) / len(rs), 6) for d, rs in domains.items()}
        pass_rate = sum(bool(x.get("passed")) for x in rows) / len(rows)
        all_domains = set(self.DOMAINS).issubset(domains) if require_all_domains else True
        return {"cases": len(rows), "pass_rate": round(pass_rate, 6), "score": round(sum(float(x.get("score", 0)) for x in rows) / len(rows), 6), "domains": domain_scores, "pass": bool(pass_rate == 1.0 and all_domains)}


# ---------------------------------------------------------------------------
# 9-13. Cognitive strategy, adaptive depth and calibration v2
# ---------------------------------------------------------------------------


class CognitiveStrategyLabV2:
    KEY = "cognitive_strategy_lab_v2"
    STRATEGIES = ("planner", "planner_critic", "planner_verifier", "debate", "ensemble", "tree_search")

    def record(self, state: ProjectState, *, strategy: str, domain: str, difficulty: float, score: float, success: bool,
               cost: float = 0.0, seconds: float = 0.0, holdout: bool = True) -> dict[str, Any]:
        if strategy not in self.STRATEGIES: raise ValueError("unknown cognitive strategy")
        key = f"{strategy}|{domain}"
        row = state.metadata.setdefault(self.KEY, {}).setdefault(key, {"strategy": strategy, "domain": domain, "runs": 0, "holdout_runs": 0, "successes": 0, "score_sum": 0.0, "cost_sum": 0.0, "seconds_sum": 0.0, "difficulty_sum": 0.0})
        row["runs"] += 1; row["holdout_runs"] += int(holdout); row["successes"] += int(success)
        row["score_sum"] += float(score); row["cost_sum"] += float(cost); row["seconds_sum"] += float(seconds); row["difficulty_sum"] += float(difficulty)
        n = row["runs"]; row["success_rate"] = round(row["successes"] / n, 6); row["avg_score"] = round(row["score_sum"] / n, 6); row["avg_cost"] = round(row["cost_sum"] / n, 6); row["avg_seconds"] = round(row["seconds_sum"] / n, 6)
        return dict(row)

    def utility(self, row: dict[str, Any]) -> float:
        return round(float(row.get("avg_score", 0)) * .55 + float(row.get("success_rate", 0)) * .35 - min(.15, float(row.get("avg_cost", 0)) * .03) - min(.1, float(row.get("avg_seconds", 0)) / 10000), 6)

    def best(self, state: ProjectState, *, domain: str, min_holdout: int = 5) -> dict[str, Any] | None:
        rows = [dict(x) for x in state.metadata.setdefault(self.KEY, {}).values() if x.get("domain") == domain and int(x.get("holdout_runs", 0)) >= min_holdout]
        if not rows: return None
        return max(rows, key=self.utility)


class CognitiveStrategySelector:
    def __init__(self, lab: CognitiveStrategyLabV2 | None = None) -> None:
        self.lab = lab or CognitiveStrategyLabV2()

    def select(self, state: ProjectState, task: Task, *, risk: float | None = None, uncertainty: float | None = None) -> dict[str, Any]:
        domain = self._domain(task); risk = _clip(task.metadata.get("risk_score", .35) if risk is None else risk); uncertainty = _clip(task.metadata.get("uncertainty", .35) if uncertainty is None else uncertainty)
        difficulty = _clip(task.metadata.get("difficulty", max(.2, min(1.0, task.depth * .08 + len(task.dependencies) * .05 + .35))))
        learned = self.lab.best(state, domain=domain)
        if learned:
            strategy = str(learned["strategy"]); reason = "learned_holdout_utility"
        elif risk >= .85 or (difficulty >= .85 and uncertainty >= .65): strategy, reason = "ensemble", "high_risk_or_high_uncertainty"
        elif difficulty >= .8: strategy, reason = "tree_search", "high_complexity"
        elif uncertainty >= .65: strategy, reason = "planner_verifier", "uncertainty_requires_verification"
        elif risk >= .6: strategy, reason = "planner_critic", "elevated_risk"
        else: strategy, reason = "planner", "routine_task"
        row = {"strategy": strategy, "domain": domain, "difficulty": difficulty, "risk": risk, "uncertainty": uncertainty, "reason": reason}
        task.metadata["cognitive_strategy"] = row
        return row

    @staticmethod
    def _domain(task: Task) -> str:
        caps = " ".join(task.required_capabilities or []).lower(); title = f"{task.title} {task.description}".lower()
        text = f"{caps} {title}"
        mapping = [("code", "coding"), ("debug", "debugging"), ("research", "research"), ("document", "documentation"), ("plan", "planning"), ("decision", "decision"), ("project", "project_management")]
        for token, domain in mapping:
            if token in text: return domain
        return "analysis"


class EarlyAbortEngine:
    KEY = "early_abort_v1"

    def evaluate(self, state: ProjectState, task: Task, *, spent_fraction: float, progress_gain: float, failure_count: int,
                 expected_success: float, min_observations: int = 2) -> dict[str, Any]:
        observations = int(task.metadata.get("strategy_observations", 0))
        abort = bool(observations >= min_observations and ((spent_fraction >= .6 and progress_gain <= .05) or failure_count >= 3 or expected_success < .15))
        reason = "continue"
        if abort:
            if failure_count >= 3: reason = "repeated_failures"
            elif expected_success < .15: reason = "low_expected_success"
            else: reason = "poor_marginal_progress"
        row = {"abort": abort, "reason": reason, "spent_fraction": _clip(spent_fraction), "progress_gain": float(progress_gain), "failure_count": int(failure_count), "expected_success": _clip(expected_success)}
        task.metadata[self.KEY] = row
        return row


class AdaptiveDepthEngine:
    LEVELS = {"shallow": 1, "standard": 2, "deep": 3, "max": 4}

    def choose(self, task: Task, *, risk: float, uncertainty: float, novelty: float = .5, budget_pressure: float = 0.0, deadline_pressure: float = 0.0) -> dict[str, Any]:
        need = _clip(.36 * risk + .36 * uncertainty + .28 * novelty)
        pressure = _clip(max(budget_pressure, deadline_pressure))
        effective = max(0.0, need - pressure * .28)
        if effective >= .78: level = "max"
        elif effective >= .58: level = "deep"
        elif effective >= .32: level = "standard"
        else: level = "shallow"
        row = {"level": level, "depth": self.LEVELS[level], "need": round(need, 4), "resource_pressure": round(pressure, 4), "effective_need": round(effective, 4)}
        task.metadata["adaptive_depth"] = row
        return row


class ConfidenceCalibrationV2:
    KEY = "confidence_calibration_v2"

    @staticmethod
    def _key(*, task_type: str, agent: str, model: str, tool: str) -> str:
        return "|".join(x or "unknown" for x in (task_type, agent, model, tool))

    def record(self, state: ProjectState, *, predicted: float, success: bool, task_type: str = "general", agent: str = "unknown", model: str = "unknown", tool: str = "none") -> dict[str, Any]:
        key = self._key(task_type=task_type, agent=agent, model=model, tool=tool)
        bucket = state.metadata.setdefault(self.KEY, {}).setdefault(key, {"n": 0, "predicted_sum": 0.0, "outcome_sum": 0.0, "brier_sum": 0.0})
        p = _clip(predicted); y = 1.0 if success else 0.0
        bucket["n"] += 1; bucket["predicted_sum"] += p; bucket["outcome_sum"] += y; bucket["brier_sum"] += (p - y) ** 2
        n = bucket["n"]; bucket["mean_predicted"] = round(bucket["predicted_sum"] / n, 6); bucket["observed_success"] = round(bucket["outcome_sum"] / n, 6); bucket["bias"] = round(bucket["mean_predicted"] - bucket["observed_success"], 6); bucket["brier"] = round(bucket["brier_sum"] / n, 6)
        return dict(bucket)

    def calibrated(self, state: ProjectState, predicted: float, *, task_type: str = "general", agent: str = "unknown", model: str = "unknown", tool: str = "none", min_samples: int = 12) -> float:
        row = state.metadata.setdefault(self.KEY, {}).get(self._key(task_type=task_type, agent=agent, model=model, tool=tool))
        p = _clip(predicted)
        if not row or int(row.get("n", 0)) < min_samples: return p
        correction = max(-.25, min(.25, float(row.get("bias", 0))))
        return round(_clip(p - correction), 6)


# ---------------------------------------------------------------------------
# 14-18. Failure taxonomy, root cause, recovery ranking and dead-end guards
# ---------------------------------------------------------------------------


class FailureTaxonomyEngine:
    CATEGORIES = ("planning", "tool", "provider", "context", "logic", "permissions", "budget", "dependency", "data", "verification", "unknown")
    RULES = [
        ("budget", re.compile(r"budget|cost limit|insufficient funds", re.I)),
        ("permissions", re.compile(r"permission|forbidden|unauthori[sz]ed|access denied", re.I)),
        ("provider", re.compile(r"429|rate.?limit|provider|timeout|http 5\d\d|service unavailable", re.I)),
        ("context", re.compile(r"context|token limit|too long|overflow", re.I)),
        ("dependency", re.compile(r"dependency|missing module|importerror|modulenotfound|blocked by", re.I)),
        ("data", re.compile(r"invalid data|schema|parse|json|corrupt|missing field", re.I)),
        ("verification", re.compile(r"verification|test failed|assertion|acceptance", re.I)),
        ("planning", re.compile(r"plan|dead end|no executable task|circular", re.I)),
        ("tool", re.compile(r"tool|executable|command|subprocess|browser", re.I)),
        ("logic", re.compile(r"logic|wrong result|incorrect|invariant", re.I)),
    ]

    def classify(self, error: str, *, task: Task | None = None) -> dict[str, Any]:
        text = str(error or "")
        for category, pattern in self.RULES:
            if pattern.search(text):
                return {"category": category, "confidence": .82, "error": text[:1000]}
        if task and task.status == TaskStatus.BLOCKED: return {"category": "dependency", "confidence": .62, "error": text[:1000]}
        return {"category": "unknown", "confidence": .25, "error": text[:1000]}


class RootCauseEngine:
    KEY = "root_cause_history_v1"

    def analyze(self, state: ProjectState, task: Task, error: str, *, recent_events: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
        taxonomy = FailureTaxonomyEngine().classify(error, task=task)
        events = list(recent_events)
        same_provider = sum(1 for x in events if x.get("provider") == task.provider_name and x.get("kind") == "provider_failure")
        hypotheses = [{"cause": taxonomy["category"], "confidence": taxonomy["confidence"], "evidence": "error_pattern"}]
        if same_provider >= 2:
            hypotheses.insert(0, {"cause": "provider", "confidence": min(.95, .7 + .05 * same_provider), "evidence": f"{same_provider}_recent_provider_failures"})
        if task.dependencies and task.status == TaskStatus.BLOCKED:
            hypotheses.insert(0, {"cause": "dependency", "confidence": .9, "evidence": "blocked_with_dependencies"})
        best = max(hypotheses, key=lambda x: x["confidence"])
        row = {"task_id": task.id, "root_cause": best["cause"], "confidence": round(float(best["confidence"]), 4), "hypotheses": hypotheses, "analyzed_at": _now()}
        hist = state.metadata.setdefault(self.KEY, []); hist.append(row); del hist[:-500]
        return row


class RecoveryStrategyRanker:
    KEY = "recovery_strategy_ranker_v1"

    def record(self, state: ProjectState, *, failure_type: str, action: str, success: bool, cost: float = 0.0, seconds: float = 0.0) -> dict[str, Any]:
        key = f"{failure_type}|{action}"; row = state.metadata.setdefault(self.KEY, {}).setdefault(key, {"failure_type": failure_type, "action": action, "attempts": 0, "successes": 0, "cost": 0.0, "seconds": 0.0})
        row["attempts"] += 1; row["successes"] += int(success); row["cost"] += float(cost); row["seconds"] += float(seconds)
        # Beta(1,1) posterior mean avoids overconfidence on tiny samples.
        row["success_posterior"] = round((row["successes"] + 1) / (row["attempts"] + 2), 6)
        row["avg_cost"] = round(row["cost"] / row["attempts"], 6); row["avg_seconds"] = round(row["seconds"] / row["attempts"], 6)
        return dict(row)

    def rank(self, state: ProjectState, failure_type: str, candidates: Iterable[str]) -> list[dict[str, Any]]:
        out = []
        for action in candidates:
            row = state.metadata.setdefault(self.KEY, {}).get(f"{failure_type}|{action}", {})
            p = float(row.get("success_posterior", .5)); avg_cost = float(row.get("avg_cost", 0)); avg_seconds = float(row.get("avg_seconds", 0))
            utility = p - min(.2, avg_cost * .04) - min(.15, avg_seconds / 5000)
            out.append({"action": action, "success_probability": round(p, 6), "utility": round(utility, 6), "attempts": int(row.get("attempts", 0))})
        return sorted(out, key=lambda x: (x["utility"], x["attempts"]), reverse=True)


class RepeatedFailureGuard:
    KEY = "repeated_failure_guard_v1"

    def record(self, task: Task, *, action: str, error: str, progress_gain: float = 0.0, max_repeats: int = 2) -> dict[str, Any]:
        fingerprint = sha256(f"{action}|{FailureTaxonomyEngine().classify(error)['category']}|{str(error)[:200]}".encode()).hexdigest()[:20]
        root = task.metadata.setdefault(self.KEY, {}); row = root.setdefault(fingerprint, {"attempts": 0, "no_progress": 0, "action": action})
        row["attempts"] += 1; row["no_progress"] += int(progress_gain <= 0.001); row["last_error"] = str(error)[:500]
        blocked = row["attempts"] > max_repeats and row["no_progress"] >= max_repeats
        return {"fingerprint": fingerprint, "blocked": blocked, **row}


class DeadEndDetector:
    KEY = "dead_end_detector_v1"

    def evaluate(self, state: ProjectState, *, progress_samples: Iterable[float], cost_samples: Iterable[float], evidence_samples: Iterable[int], min_samples: int = 4) -> dict[str, Any]:
        p, c, e = list(progress_samples), list(cost_samples), list(evidence_samples); n = min(len(p), len(c), len(e))
        if n < min_samples:
            return {"dead_end": False, "reason": "insufficient_history", "samples": n}
        p, c, e = p[-n:], c[-n:], e[-n:]
        progress_gain = p[-1] - p[0]; cost_gain = c[-1] - c[0]; evidence_gain = e[-1] - e[0]
        dead = bool(cost_gain > 0 and progress_gain <= .01 and evidence_gain <= 0)
        row = {"dead_end": dead, "reason": "resource_consumption_without_verified_progress" if dead else "progress_observed", "samples": n, "progress_gain": round(progress_gain, 6), "cost_gain": round(cost_gain, 6), "evidence_gain": evidence_gain, "evaluated_at": _now()}
        hist = state.metadata.setdefault(self.KEY, []); hist.append(row); del hist[:-100]
        return row


# ---------------------------------------------------------------------------
# 19-20. Marginal value and formal stopping rule
# ---------------------------------------------------------------------------


class MarginalValueEngine:
    def evaluate(self, *, expected_quality_gain: float, expected_evidence_gain: float, expected_success_gain: float,
                 expected_cost: float, expected_seconds: float, cost_weight: float = .12, time_weight: float = .08) -> dict[str, Any]:
        benefit = _clip(expected_quality_gain) * .45 + _clip(expected_evidence_gain) * .3 + _clip(expected_success_gain) * .25
        penalty = min(.6, max(0.0, float(expected_cost)) * cost_weight) + min(.4, max(0.0, float(expected_seconds)) / 3600 * time_weight)
        value = benefit - penalty
        return {"benefit": round(benefit, 6), "penalty": round(penalty, 6), "marginal_value": round(value, 6), "worth_continuing": value > .02}


class StoppingRuleEngine:
    """Stops only when acceptance/quality are sufficient and more work has low value."""

    def decide(self, *, quality: float, quality_target: float, acceptance_coverage: float, uncertainty: float,
               blockers: Iterable[str], marginal_value: float, hard_cap_reached: bool = False) -> dict[str, Any]:
        blockers = list(blockers)
        if blockers:
            return {"stop": False, "reason": "blocking_requirements", "blockers": blockers}
        if hard_cap_reached:
            return {"stop": True, "reason": "hard_resource_cap", "complete": False, "blockers": []}
        sufficient = quality >= quality_target and acceptance_coverage >= 1.0 and uncertainty <= .2
        if sufficient and marginal_value <= .02:
            return {"stop": True, "reason": "quality_sufficient_low_marginal_value", "complete": True, "blockers": []}
        return {"stop": False, "reason": "additional_work_has_value" if marginal_value > .02 else "quality_or_certainty_insufficient", "complete": False, "blockers": []}


class CognitiveEvolutionCore:
    """Facade covering roadmap items 1-20 without performing external/Windows actions."""

    def __init__(self) -> None:
        self.baselines = ImmutableBaselineRegistry(); self.holdout = HoldoutBenchmarkRegistry(); self.dogfood = ControlledDogfoodEngine(); self.self_improvement = SelfImprovementPipeline(); self.benchmarks = BenchmarkPortfolio(); self.lab = CognitiveStrategyLabV2(); self.selector = CognitiveStrategySelector(self.lab); self.early_abort = EarlyAbortEngine(); self.depth = AdaptiveDepthEngine(); self.calibration = ConfidenceCalibrationV2(); self.failures = FailureTaxonomyEngine(); self.root_cause = RootCauseEngine(); self.recovery_ranker = RecoveryStrategyRanker(); self.repeat_guard = RepeatedFailureGuard(); self.dead_end = DeadEndDetector(); self.marginal_value = MarginalValueEngine(); self.stopping = StoppingRuleEngine()

    def task_plan(self, state: ProjectState, task: Task, *, budget_pressure: float = 0.0, deadline_pressure: float = 0.0) -> dict[str, Any]:
        strategy = self.selector.select(state, task)
        depth = self.depth.choose(task, risk=strategy["risk"], uncertainty=strategy["uncertainty"], novelty=float(task.metadata.get("novelty", .5)), budget_pressure=budget_pressure, deadline_pressure=deadline_pressure)
        return {"strategy": strategy, "depth": depth}
