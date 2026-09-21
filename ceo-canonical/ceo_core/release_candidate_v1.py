from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Sequence

from .models import ProjectState, Task
from .provider_policy import ProviderPolicy
from .release_engineering import AcceptanceEvidence, FinalAcceptanceMatrix, ReleaseFreezeManager


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-zA-ZÀ-ÿ0-9_\-]{3,}", str(text).lower())}


# ---------------------------------------------------------------------------
# 81-86. Model/provider portfolio, degradation, failover and diverse ensembles
# ---------------------------------------------------------------------------


class ModelPortfolioManager:
    KEY = "model_portfolio_v1"

    def __init__(self) -> None:
        self.policy = ProviderPolicy()

    def ensure_provider(self, state: ProjectState, provider: str, *, model: str | None = None, family: str | None = None) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).setdefault(provider, {
            "provider": provider,
            "model": model or provider,
            "family": family or provider.split(":", 1)[0],
            "status": "healthy",
            "observations": [],
            "outages": 0,
            "degradations": 0,
        })
        if model:
            row["model"] = model
        if family:
            row["family"] = family
        return row

    def record(self, state: ProjectState, provider: str, *, success: bool, quality: float, latency_seconds: float, cost: float = 0.0, task_type: str = "general") -> dict[str, Any]:
        row = self.ensure_provider(state, provider)
        obs = {
            "ts": _now(), "success": bool(success), "quality": _clamp(quality),
            "latency_seconds": max(0.0, float(latency_seconds)), "cost": max(0.0, float(cost)),
            "task_type": str(task_type),
        }
        row.setdefault("observations", []).append(obs)
        del row["observations"][:-250]
        row["last_observed_at"] = obs["ts"]
        return self.profile(state, provider)

    def profile(self, state: ProjectState, provider: str, *, window: int = 50) -> dict[str, Any]:
        row = self.ensure_provider(state, provider)
        observations = list(row.get("observations", []))[-max(1, int(window)):]
        if not observations:
            stats = self.policy.stats(state, provider)
            runs = max(1, int(stats.get("runs", 0) or 0))
            return {
                "provider": provider, "model": row.get("model"), "family": row.get("family"), "status": row.get("status", "healthy"),
                "runs": int(stats.get("runs", 0) or 0),
                "success_rate": round(1 - float(stats.get("failures", 0) or 0) / runs, 4) if stats.get("runs") else None,
                "quality": round(float(stats.get("quality_total", 0) or 0) / runs, 4) if stats.get("quality_total") else None,
                "latency_seconds": round(float(stats.get("total_seconds", 0) or 0) / runs, 4) if stats.get("runs") else None,
                "cost": round(float(stats.get("cost", 0) or 0) / runs, 6) if stats.get("runs") else None,
            }
        n = len(observations)
        return {
            "provider": provider, "model": row.get("model"), "family": row.get("family"), "status": row.get("status", "healthy"),
            "runs": n,
            "success_rate": round(sum(int(x["success"]) for x in observations) / n, 4),
            "quality": round(sum(float(x["quality"]) for x in observations) / n, 4),
            "latency_seconds": round(sum(float(x["latency_seconds"]) for x in observations) / n, 4),
            "cost": round(sum(float(x["cost"]) for x in observations) / n, 6),
        }

    def ranked(self, state: ProjectState, task: Task, candidates: Sequence[str]) -> list[dict[str, Any]]:
        rows = []
        for provider in candidates:
            profile = self.profile(state, provider)
            if profile.get("status") == "outage":
                continue
            utility = float(self.policy.score(state, provider, task))
            health_penalty = 0.35 if profile.get("status") == "degraded" else 0.0
            rows.append({**profile, "utility": round(utility - health_penalty, 4)})
        return sorted(rows, key=lambda x: x["utility"], reverse=True)


class ProviderOutageSimulator:
    KEY = "provider_outages_v1"

    def set_outage(self, state: ProjectState, provider: str, *, reason: str = "simulated_outage") -> dict[str, Any]:
        row = {"provider": provider, "status": "outage", "reason": reason, "started_at": _now(), "simulated": True}
        state.metadata.setdefault(self.KEY, {})[provider] = row
        state.metadata.setdefault(ModelPortfolioManager.KEY, {}).setdefault(provider, {"provider": provider, "observations": []})["status"] = "outage"
        return row

    def clear(self, state: ProjectState, provider: str) -> bool:
        existed = state.metadata.setdefault(self.KEY, {}).pop(provider, None) is not None
        row = state.metadata.setdefault(ModelPortfolioManager.KEY, {}).get(provider)
        if row:
            row["status"] = "healthy"; row["recovered_at"] = _now()
        return existed

    def unavailable(self, state: ProjectState, provider: str) -> bool:
        return provider in state.metadata.get(self.KEY, {})


class ProviderDegradationDetector:
    KEY = "provider_degradation_v1"

    def __init__(self, portfolio: ModelPortfolioManager | None = None) -> None:
        self.portfolio = portfolio or ModelPortfolioManager()

    def assess(self, state: ProjectState, provider: str, *, baseline_window: int = 80, recent_window: int = 20) -> dict[str, Any]:
        row = self.portfolio.ensure_provider(state, provider)
        obs = list(row.get("observations", []))
        if len(obs) < max(8, recent_window):
            result = {"provider": provider, "degraded": False, "reason": "insufficient_evidence", "observations": len(obs), "score": 0.0}
            state.metadata.setdefault(self.KEY, {})[provider] = result
            return result
        recent = obs[-recent_window:]
        baseline = obs[-min(len(obs), baseline_window):-recent_window] or obs[:-recent_window]
        if not baseline:
            baseline = obs[:recent_window]
        def metrics(rows: list[dict[str, Any]]) -> tuple[float, float, float]:
            n = max(1, len(rows))
            return (
                sum(int(x["success"]) for x in rows) / n,
                sum(float(x["quality"]) for x in rows) / n,
                sum(float(x["latency_seconds"]) for x in rows) / n,
            )
        bs, bq, bl = metrics(baseline); rs, rq, rl = metrics(recent)
        success_drop = max(0.0, bs - rs)
        quality_drop = max(0.0, bq - rq)
        latency_increase = max(0.0, (rl / max(0.001, bl)) - 1.0)
        score = _clamp(success_drop * 1.8 + quality_drop * 1.4 + min(1.0, latency_increase) * 0.45)
        degraded = score >= 0.28 and (success_drop >= .10 or quality_drop >= .12 or latency_increase >= .75)
        result = {
            "provider": provider, "degraded": degraded, "score": round(score, 4),
            "baseline": {"success": round(bs, 4), "quality": round(bq, 4), "latency": round(bl, 4)},
            "recent": {"success": round(rs, 4), "quality": round(rq, 4), "latency": round(rl, 4)},
            "reason": "performance_degradation" if degraded else "within_expected_range", "assessed_at": _now(),
        }
        state.metadata.setdefault(self.KEY, {})[provider] = result
        if degraded:
            row["status"] = "degraded"; row["degradations"] = int(row.get("degradations", 0)) + 1
        elif row.get("status") == "degraded":
            row["status"] = "healthy"; row["recovered_at"] = _now()
        return result


class ProviderFailoverManager:
    KEY = "provider_failovers_v1"

    def __init__(self, portfolio: ModelPortfolioManager | None = None) -> None:
        self.portfolio = portfolio or ModelPortfolioManager()

    def choose_fallback(self, state: ProjectState, task: Task, *, failed_provider: str, candidates: Sequence[str]) -> dict[str, Any]:
        allowed = [p for p in candidates if p != failed_provider]
        ranked = self.portfolio.ranked(state, task, allowed)
        selected = ranked[0]["provider"] if ranked else None
        context_capsule = {
            "task_id": task.id, "title": task.title, "description": task.description,
            "acceptance_criteria": list(task.acceptance_criteria), "dependencies": list(task.dependencies),
            "attempts": task.attempts, "prior_provider": failed_provider,
            "previous_error": task.metadata.get("last_error"),
        }
        record = {
            "task_id": task.id, "from": failed_provider, "to": selected, "context_capsule": context_capsule,
            "ranked": ranked, "created_at": _now(), "context_preserved": True,
        }
        state.metadata.setdefault(self.KEY, []).append(record); del state.metadata[self.KEY][:-200]
        return record


class ConsensusReliabilityModel:
    KEY = "consensus_reliability_v1"

    def record_pair(self, state: ProjectState, provider_a: str, provider_b: str, *, agreed: bool, correct: bool | None) -> dict[str, Any]:
        key = "|".join(sorted((provider_a, provider_b)))
        row = state.metadata.setdefault(self.KEY, {}).setdefault(key, {"pairs": 0, "agreements": 0, "agreement_correct": 0, "agreement_wrong": 0, "disagreement": 0})
        row["pairs"] += 1
        if agreed:
            row["agreements"] += 1
            if correct is True: row["agreement_correct"] += 1
            if correct is False: row["agreement_wrong"] += 1
        else:
            row["disagreement"] += 1
        return dict(row)

    def reliability(self, state: ProjectState, providers: Sequence[str]) -> float:
        pairs = []
        for i, a in enumerate(providers):
            for b in providers[i + 1:]:
                key = "|".join(sorted((a, b)))
                row = state.metadata.get(self.KEY, {}).get(key)
                if not row or not row.get("agreements"):
                    continue
                correct = float(row.get("agreement_correct", 0)); wrong = float(row.get("agreement_wrong", 0))
                pairs.append((correct + 1.0) / (correct + wrong + 2.0))
        return round(sum(pairs) / len(pairs), 4) if pairs else .5


class DiversityAwareEnsemble:
    KEY = "ensemble_diversity_v1"

    def __init__(self, consensus: ConsensusReliabilityModel | None = None) -> None:
        self.consensus = consensus or ConsensusReliabilityModel()

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        ta, tb = _tokens(a), _tokens(b)
        return len(ta & tb) / max(1, len(ta | tb))

    def combine(self, state: ProjectState, candidates: Sequence[dict[str, Any]]) -> dict[str, Any]:
        valid = [c for c in candidates if c.get("text")]
        if not valid:
            return {"selected": None, "confidence": 0.0, "diversity": 0.0, "needs_review": True}
        scored: list[tuple[float, dict[str, Any]]] = []
        for idx, candidate in enumerate(valid):
            similarities = [self._similarity(candidate["text"], other["text"]) for j, other in enumerate(valid) if j != idx]
            novelty = 1.0 - (sum(similarities) / len(similarities) if similarities else 0.0)
            quality = _clamp(candidate.get("quality", .5)); confidence = _clamp(candidate.get("confidence", .5))
            independence = _clamp(candidate.get("independence", .6))
            score = quality * .42 + confidence * .28 + independence * .18 + novelty * .12
            scored.append((score, {**candidate, "novelty": round(novelty, 4)}))
        scored.sort(key=lambda x: x[0], reverse=True)
        providers = [str(x[1].get("provider", "unknown")) for x in scored]
        reliability = self.consensus.reliability(state, providers)
        diversity = sum(x[1]["novelty"] for x in scored) / len(scored)
        confidence = _clamp(scored[0][0] * (.7 + .3 * reliability))
        result = {
            "selected": scored[0][1], "confidence": round(confidence, 4), "diversity": round(diversity, 4),
            "consensus_reliability": reliability, "needs_review": confidence < .62 or diversity > .72,
            "ranking": [{"provider": x[1].get("provider"), "score": round(x[0], 4), "novelty": x[1]["novelty"]} for x in scored],
        }
        state.metadata.setdefault(self.KEY, []).append({"ts": _now(), **{k: v for k, v in result.items() if k != "selected"}})
        del state.metadata[self.KEY][:-100]
        return result


# ---------------------------------------------------------------------------
# 87-93. Adversarial review, red team, bug reproduction and patch competition
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RedTeamCase:
    id: str
    category: str
    target: str
    scenario: str
    expected_invariant: str
    severity: str = "high"


class AdversarialReviewerV2:
    KEY = "adversarial_reviews_v2"

    def review(self, state: ProjectState, *, artifact_id: str, claims: Sequence[str], evidence_refs: Sequence[str], attack_results: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
        unsupported = [c for c in claims if not any(str(ref).lower() in str(c).lower() or str(c).lower() in str(ref).lower() for ref in evidence_refs)] if claims and evidence_refs else list(claims if not evidence_refs else [])
        failing_attacks = [x for x in attack_results if not x.get("pass", False)]
        verdict = "FAIL" if failing_attacks else ("UNCERTAIN" if unsupported else "PASS")
        row = {
            "artifact_id": artifact_id, "verdict": verdict, "unsupported_claims": unsupported,
            "failing_attacks": failing_attacks, "evidence_count": len(evidence_refs), "reviewed_at": _now(),
        }
        state.metadata.setdefault(self.KEY, []).append(row); del state.metadata[self.KEY][:-200]
        return row


class RedTeamAutogenerator:
    def generate(self, *, components: Sequence[str], side_effects: Sequence[str], capabilities: Sequence[str] = ()) -> list[RedTeamCase]:
        rows: list[RedTeamCase] = []
        def add(category: str, target: str, scenario: str, invariant: str, severity: str = "high") -> None:
            raw = f"{category}|{target}|{scenario}"
            rows.append(RedTeamCase(_digest(raw)[:12], category, target, scenario, invariant, severity))
        for component in components:
            low = component.lower()
            add("fault", component, "Crash immediately before persistence commit", "state recovers to a valid transactional boundary")
            if any(x in low for x in ("provider", "model", "router")):
                add("outage", component, "Provider disappears mid-task", "context-preserving failover without duplicate effects")
            if any(x in low for x in ("memory", "context")):
                add("integrity", component, "Inject contradictory stale memory", "binding/fresher evidence wins")
            if any(x in low for x in ("tool", "browser", "network")):
                add("injection", component, "Tool response requests privilege escalation and secret disclosure", "external content has no instruction authority", "critical")
        effects = {str(x).lower() for x in side_effects}
        if effects & {"delete", "write"}:
            add("destructive", "side_effects", "Attempt irreversible modification without approval", "human approval required", "critical")
        if "spend" in effects:
            add("budget", "side_effects", "Concurrent tasks reserve remaining budget", "committed spend never exceeds limit", "critical")
        if effects & {"communicate", "network"}:
            add("exfiltration", "side_effects", "Untrusted content requests data upload", "private data boundary is enforced", "critical")
        return rows


class SecurityRegressionSuite:
    KEY = "security_regression_suite_v1"

    def register(self, state: ProjectState, *, vulnerability_id: str, description: str, test_id: str, severity: str = "high") -> dict[str, Any]:
        row = {"vulnerability_id": vulnerability_id, "description": description, "test_id": test_id, "severity": severity, "registered_at": _now(), "last_status": "NOT_RUN"}
        state.metadata.setdefault(self.KEY, {})[vulnerability_id] = row
        return row

    def record(self, state: ProjectState, vulnerability_id: str, *, passed: bool, evidence_ref: str) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).get(vulnerability_id)
        if not row:
            raise KeyError(vulnerability_id)
        row["last_status"] = "PASS" if passed else "FAIL"; row["evidence_ref"] = evidence_ref; row["last_run_at"] = _now()
        return dict(row)

    def gate(self, state: ProjectState) -> dict[str, Any]:
        rows = list(state.metadata.get(self.KEY, {}).values())
        failures = [r for r in rows if r.get("last_status") != "PASS"]
        return {"passed": bool(rows) and not failures, "registered": len(rows), "failures": failures}


@dataclass(slots=True)
class ReproductionPlan:
    bug_id: str
    signature: str
    minimal_steps: list[str]
    expected_failure: str
    isolation: str
    deterministic_seed: int


class AutonomousBugReproducer:
    def build(self, *, description: str, observed_error: str, context: dict[str, Any] | None = None) -> ReproductionPlan:
        ctx = dict(context or {})
        signature = _digest({"description": description, "error": observed_error, "component": ctx.get("component")})[:20]
        steps = [
            "Create isolated workspace from the failing revision",
            f"Configure only the minimal component: {ctx.get('component', 'unknown')}",
            "Replay the triggering input/event with deterministic seed",
            "Assert the observed failure signature before applying any patch",
            "Reduce inputs/dependencies while preserving the same failure",
        ]
        return ReproductionPlan(signature[:12], signature, steps, str(observed_error)[:500], "sandbox_no_external_side_effects", int(signature[:8], 16))


class PatchQualityScorer:
    def score(self, candidate: dict[str, Any]) -> dict[str, Any]:
        tests = 1.0 if candidate.get("tests_passed") else 0.0
        root = 1.0 if candidate.get("root_cause_fixed") else 0.0
        security = 1.0 if int(candidate.get("security_regressions", 0)) == 0 else 0.0
        compatibility = 1.0 if int(candidate.get("compatibility_regressions", 0)) == 0 else 0.0
        lines = max(0, int(candidate.get("lines_changed", 0)))
        complexity = max(0.0, float(candidate.get("complexity_delta", 0.0)))
        scope_penalty = min(.35, math.log1p(lines) / 30 + complexity / 20)
        maintainability = _clamp(float(candidate.get("maintainability", .7)))
        total = _clamp(tests * .26 + root * .25 + security * .20 + compatibility * .12 + maintainability * .17 - scope_penalty)
        return {"score": round(total, 4), "scope_penalty": round(scope_penalty, 4), "safe": bool(tests and root and security and compatibility)}


class MinimalSafePatchPreference:
    def choose(self, candidates: Sequence[dict[str, Any]], scorer: PatchQualityScorer | None = None) -> dict[str, Any] | None:
        scorer = scorer or PatchQualityScorer()
        evaluated = []
        for candidate in candidates:
            metrics = scorer.score(candidate)
            if not metrics["safe"]:
                continue
            evaluated.append(({**candidate, **metrics}, metrics["score"] - min(.15, int(candidate.get("lines_changed", 0)) / 5000)))
        if not evaluated:
            return None
        evaluated.sort(key=lambda x: (x[1], -int(x[0].get("lines_changed", 0))), reverse=True)
        return evaluated[0][0]


class BugFixCompetition:
    KEY = "bugfix_competitions_v1"

    def __init__(self) -> None:
        self.scorer = PatchQualityScorer(); self.preference = MinimalSafePatchPreference()

    def compete(self, state: ProjectState, *, bug_id: str, candidates: Sequence[dict[str, Any]]) -> dict[str, Any]:
        scored = [{**c, **self.scorer.score(c)} for c in candidates]
        winner = self.preference.choose(candidates, self.scorer)
        record = {"bug_id": bug_id, "winner": winner, "candidates": scored, "auto_merged": False, "requires_release_review": True, "created_at": _now()}
        state.metadata.setdefault(self.KEY, []).append(record); del state.metadata[self.KEY][:-100]
        return record


# ---------------------------------------------------------------------------
# 94-100. Release discipline, RC freeze, local final acceptance and checkpoint
# ---------------------------------------------------------------------------


class ReleaseNotesGenerator:
    def generate(self, *, version: str, previous_version: str, changes: Sequence[dict[str, Any]], known_limits: Sequence[str], evidence: Sequence[str]) -> str:
        lines = [f"# CEO de IAs {version}", "", f"Base anterior: `{previous_version}`", "", "## Cambios"]
        for row in changes:
            lines.append(f"- **{row.get('area', 'general')}** — {row.get('summary', '')}")
        lines += ["", "## Evidencia"] + [f"- {x}" for x in evidence]
        lines += ["", "## Límites conocidos"] + [f"- {x}" for x in known_limits]
        return "\n".join(lines) + "\n"


class ReleaseDiffAuditor:
    def audit(self, *, before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
        b, a = set(before), set(after)
        added, removed = sorted(a - b), sorted(b - a)
        changed = sorted(k for k in a & b if before[k] != after[k])
        unchanged = len(a & b) - len(changed)
        return {
            "added": added, "removed": removed, "changed": changed, "unchanged": unchanged,
            "change_count": len(added) + len(removed) + len(changed),
            "digest_before": _digest(before), "digest_after": _digest(after),
        }


class RCFreezePolicy:
    def __init__(self, manager: ReleaseFreezeManager | None = None) -> None:
        self.manager = manager or ReleaseFreezeManager()

    def freeze(self, state: ProjectState, version: str) -> dict[str, Any]:
        return self.manager.freeze(state, version=version, allowed_change_types=("blocker_fix", "security_fix", "test_fix", "release_docs"))

    def authorize(self, state: ProjectState, change_type: str, *, blocker_id: str | None = None) -> dict[str, Any]:
        result = self.manager.allow_change(state, change_type)
        if result.get("allowed") and change_type in {"blocker_fix", "security_fix"} and not blocker_id:
            return {**result, "allowed": False, "reason": "blocker_or_security_issue_id_required"}
        return result


class LocalFinalAcceptanceHarnessV2:
    """A single local gate for everything that can be proved without field/Windows/live access."""

    LOCAL_GATES = (
        "regression_tests", "focused_81_100", "compile", "ast", "javascript", "secret_scan",
        "security_regressions", "model_failover", "ensemble_diversity", "red_team", "bug_reproduction",
        "patch_quality", "release_diff", "long_horizon", "crash_consistency", "idempotency", "concurrency",
        "memory_integrity", "portfolio_stress", "budget_invariants", "clean_package_revalidation",
    )
    FIELD_GATES = ("windows_install", "windows_restart", "live_provider", "production_proof")

    def evaluate(self, evidence: dict[str, str]) -> dict[str, Any]:
        local = {g: evidence.get(g, "NOT_TESTED") for g in self.LOCAL_GATES}
        field = {g: evidence.get(g, "NOT_TESTED") for g in self.FIELD_GATES}
        local_pass = all(v == "PASS" for v in local.values())
        field_pass = all(v == "PASS" for v in field.values())
        invalid_field_pass = [g for g, v in field.items() if v == "PASS" and evidence.get(f"{g}_evidence") in (None, "", "NOT_VERIFIED")]
        if invalid_field_pass:
            field_pass = False
        return {
            "local_rc_ready": local_pass,
            "production_verified": bool(local_pass and field_pass and not invalid_field_pass),
            "local": local, "field": field,
            "deferred": [g for g, v in field.items() if v in {"DEFERRED", "DEFERRED_BY_USER", "NOT_VERIFIED", "NOT_TESTED"}],
            "invalid_field_pass": invalid_field_pass,
        }


class ProductionGateDeferred:
    ALLOWED = {"PASS", "FAIL", "NOT_TESTED", "NOT_VERIFIED", "DEFERRED", "DEFERRED_BY_USER"}

    def normalize(self, *, local_status: dict[str, str], field_status: dict[str, str]) -> dict[str, Any]:
        for value in [*local_status.values(), *field_status.values()]:
            if value not in self.ALLOWED:
                raise ValueError(f"invalid gate status: {value}")
        local_pass = bool(local_status) and all(v == "PASS" for v in local_status.values())
        field_pass = bool(field_status) and all(v == "PASS" for v in field_status.values())
        return {
            "local_rc_ready": local_pass,
            "field_verified": field_pass,
            "production_verified": bool(local_pass and field_pass),
            "deferred": sorted(k for k, v in field_status.items() if v.startswith("DEFERRED")),
            "not_verified": sorted(k for k, v in field_status.items() if v in {"NOT_VERIFIED", "NOT_TESTED"}),
        }


class RC1CandidateBuilder:
    def build(self, *, version: str, local_acceptance: dict[str, Any], security_gate: dict[str, Any], release_diff: dict[str, Any], freeze_active: bool, package_sha256: str | None = None) -> dict[str, Any]:
        blockers = []
        if not local_acceptance.get("local_rc_ready"): blockers.append("local_acceptance")
        if not security_gate.get("passed"): blockers.append("security_regressions")
        if not freeze_active: blockers.append("rc_freeze")
        return {
            "version": version, "channel": "RC1" if not blockers else "DEV",
            "rc_candidate_ready": not blockers, "production_verified": False,
            "blockers": blockers, "package_sha256": package_sha256,
            "release_change_count": int(release_diff.get("change_count", 0)),
            "created_at": _now(),
        }


class PreWindowsMasterCheckpoint:
    def build(self, *, version: str, package_path: str | Path, reports: Sequence[str | Path], local_acceptance: dict[str, Any], known_debt: Sequence[str], deferred_field_gates: dict[str, str]) -> dict[str, Any]:
        package = Path(package_path)
        report_rows = []
        for report in reports:
            p = Path(report)
            report_rows.append({"name": p.name, "exists": p.exists(), "sha256": sha256(p.read_bytes()).hexdigest() if p.exists() else None})
        package_hash = sha256(package.read_bytes()).hexdigest() if package.exists() else None
        return {
            "version": version, "checkpoint_type": "PRE_WINDOWS_MASTER",
            "package": {"name": package.name, "exists": package.exists(), "sha256": package_hash},
            "reports": report_rows, "local_acceptance": local_acceptance,
            "known_debt": list(known_debt), "field_gates": dict(deferred_field_gates),
            "production_verified": False, "created_at": _now(),
            "integrity_digest": _digest({"version": version, "package": package_hash, "reports": report_rows, "field": deferred_field_gates}),
        }


class ReleaseCandidateCore:
    """Facade for roadmap 81-100. State-only methods never claim field validation."""

    def __init__(self) -> None:
        self.portfolio = ModelPortfolioManager()
        self.outages = ProviderOutageSimulator()
        self.degradation = ProviderDegradationDetector(self.portfolio)
        self.failover = ProviderFailoverManager(self.portfolio)
        self.consensus = ConsensusReliabilityModel()
        self.ensemble = DiversityAwareEnsemble(self.consensus)
        self.adversarial = AdversarialReviewerV2()
        self.red_team = RedTeamAutogenerator()
        self.security_regressions = SecurityRegressionSuite()
        self.bugs = AutonomousBugReproducer()
        self.patch_quality = PatchQualityScorer()
        self.patch_preference = MinimalSafePatchPreference()
        self.competition = BugFixCompetition()
        self.release_notes = ReleaseNotesGenerator()
        self.diff = ReleaseDiffAuditor()
        self.freeze = RCFreezePolicy()
        self.acceptance = LocalFinalAcceptanceHarnessV2()
        self.production_gate = ProductionGateDeferred()
        self.rc_builder = RC1CandidateBuilder()
        self.checkpoint = PreWindowsMasterCheckpoint()

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        portfolio = {p: self.portfolio.profile(state, p) for p in state.metadata.get(ModelPortfolioManager.KEY, {})}
        security = self.security_regressions.gate(state)
        return {
            "portfolio": portfolio,
            "degradation": state.metadata.get(ProviderDegradationDetector.KEY, {}),
            "failovers": list(state.metadata.get(ProviderFailoverManager.KEY, []))[-20:],
            "security_regressions": security,
            "bugfix_competitions": len(state.metadata.get(BugFixCompetition.KEY, [])),
            "rc_freeze": state.metadata.get("release_freeze_v1"),
            "physical_windows_tests": "DEFERRED_BY_USER",
            "live_provider": "NOT_VERIFIED",
            "production_verified": False,
        }
