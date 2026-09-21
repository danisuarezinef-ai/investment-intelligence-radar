from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from math import prod
from typing import Any, Iterable
from uuid import uuid4
import json

from .cost import CostEngine
from .cognitive_evolution import CognitiveEvolutionCore
from .graph import TaskGraph
from .models import ProjectState, Task, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(payload: Any) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Project compiler / definition of done
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AcceptanceTestSpec:
    id: str
    criterion: str
    kind: str
    automatable: bool
    evidence_required: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProjectBlueprint:
    objective: str
    success_definition: str
    deliverables: list[str]
    hard_constraints: list[str]
    forbidden_actions: list[str]
    acceptance_tests: list[AcceptanceTestSpec]
    workstreams: list[dict[str, Any]]
    critical_path_task_ids: list[str]
    graph_valid: bool
    blueprint_hash: str


class DefinitionOfDoneCompiler:
    """Turns human completion criteria into explicit acceptance-test contracts.

    This compiler is intentionally conservative. It does not claim a criterion is
    machine-testable unless its wording maps to a known evidence type.
    """

    KEYWORDS = {
        "test": ("test", ["test_report"]),
        "build": ("artifact", ["artifact", "hash"]),
        "install": ("physical", ["field_validation"]),
        "restart": ("physical", ["field_validation"]),
        "security": ("security", ["security_report"]),
        "budget": ("metric", ["cost_snapshot"]),
        "deliver": ("artifact", ["artifact"]),
        "produce": ("artifact", ["artifact"]),
        "no blocking": ("state", ["project_state"]),
        "complete": ("state", ["project_state"]),
    }

    def compile(self, criteria: Iterable[str]) -> list[AcceptanceTestSpec]:
        out: list[AcceptanceTestSpec] = []
        for index, raw in enumerate(criteria, 1):
            criterion = str(raw).strip()
            if not criterion:
                continue
            lowered = criterion.lower()
            kind, evidence, automatable = "review", ["review_record"], False
            for token, (candidate_kind, candidate_evidence) in self.KEYWORDS.items():
                if token in lowered:
                    kind, evidence = candidate_kind, list(candidate_evidence)
                    automatable = candidate_kind not in {"physical", "review"}
                    break
            out.append(
                AcceptanceTestSpec(
                    id=f"accept-{index:03d}",
                    criterion=criterion,
                    kind=kind,
                    automatable=automatable,
                    evidence_required=evidence,
                )
            )
        return out


class ProjectCompiler:
    """Compiles current project state into a deterministic execution blueprint."""

    def __init__(self, graph: TaskGraph | None = None) -> None:
        self.graph = graph or TaskGraph()
        self.dod = DefinitionOfDoneCompiler()

    def compile(self, state: ProjectState, persist: bool = True) -> ProjectBlueprint:
        audit = self.graph.audit(state)
        critical = self.graph.remaining_critical_path(state)
        forbidden = list(state.metadata.get("forbidden_actions", []))
        constitution = state.metadata.get("project_constitution", {}) or {}
        forbidden = list(dict.fromkeys(forbidden + list(constitution.get("prohibited_actions", []) or [])))

        workstreams: list[dict[str, Any]] = []
        roots = [state.tasks[x] for x in state.root_task_ids if x in state.tasks]
        if not roots:
            # A project may exist before task planning. Keep deliverables visible as
            # provisional workstreams without inventing work that was never planned.
            for idx, deliverable in enumerate(state.goal_deliverables, 1):
                workstreams.append({"id": f"deliverable-{idx}", "title": deliverable, "task_ids": [], "status": "unplanned"})
        else:
            for root in roots:
                descendants: list[str] = []
                stack = list(root.children)
                while stack:
                    tid = stack.pop()
                    if tid in descendants or tid not in state.tasks:
                        continue
                    descendants.append(tid)
                    stack.extend(state.tasks[tid].children)
                workstreams.append(
                    {
                        "id": root.id,
                        "title": root.title,
                        "task_ids": descendants,
                        "status": root.status.value,
                        "deliverables": list(root.metadata.get("deliverables", [])),
                    }
                )

        tests = self.dod.compile(state.completion_criteria)
        payload = {
            "objective": state.goal,
            "success_definition": state.goal_success_definition,
            "deliverables": list(state.goal_deliverables),
            "hard_constraints": list(state.goal_constraints),
            "forbidden_actions": forbidden,
            "acceptance_tests": [asdict(x) for x in tests],
            "workstreams": workstreams,
            "critical_path_task_ids": list(critical.get("task_ids", [])),
            "graph_valid": bool(audit.get("valid")),
        }
        blueprint = ProjectBlueprint(**payload, blueprint_hash=_stable_hash(payload))
        if persist:
            state.metadata["project_blueprint"] = {**payload, "blueprint_hash": blueprint.blueprint_hash, "compiled_at": _now()}
        return blueprint


# ---------------------------------------------------------------------------
# Probabilistic planning / candidate strategy simulation
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PlanForecast:
    strategy: str
    success_probability: float
    expected_cost: float
    expected_seconds: float
    deadline_risk: float
    utility: float
    critical_path_probability: float


class ProbabilisticPlanningEngine:
    STRATEGIES = {
        "quality": {"success": 1.08, "cost": 1.35, "time": 1.25, "verification": 1.45},
        "balanced": {"success": 1.00, "cost": 1.00, "time": 1.00, "verification": 1.00},
        "speed": {"success": .94, "cost": 1.12, "time": .68, "verification": .72},
        "cost_min": {"success": .90, "cost": .64, "time": 1.18, "verification": .78},
    }

    def __init__(self, graph: TaskGraph | None = None, cost: CostEngine | None = None) -> None:
        self.graph = graph or TaskGraph()
        self.cost = cost or CostEngine()

    @staticmethod
    def task_probability(task: Task) -> float:
        if task.status in {TaskStatus.COMPLETE, TaskStatus.SUPERSEDED}:
            return 1.0
        if task.status == TaskStatus.FAILED:
            return .05
        confidence = .58 if task.confidence is None else float(task.confidence)
        quality = .62 if task.quality_score is None else float(task.quality_score)
        attempt_penalty = max(.65, 1.0 - .08 * max(0, task.attempts - 1))
        blocked_penalty = .82 if task.status in {TaskStatus.BLOCKED, TaskStatus.NEEDS_REVIEW} else 1.0
        return max(.05, min(.995, (.58 * confidence + .42 * quality) * attempt_penalty * blocked_penalty))

    def _deadline_risk(self, state: ProjectState, seconds: float) -> float:
        if not state.deadline:
            return 0.0
        try:
            deadline = datetime.fromisoformat(state.deadline.replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        except ValueError:
            return 0.0
        if remaining <= 0:
            return 1.0
        ratio = seconds / remaining
        return round(max(0.0, min(1.0, ratio)), 4)

    def forecast(self, state: ProjectState, strategy: str = "balanced") -> PlanForecast:
        if strategy not in self.STRATEGIES:
            raise ValueError(f"unknown strategy: {strategy}")
        cfg = self.STRATEGIES[strategy]
        pending = [t for t in state.leaf_tasks if t.status not in {TaskStatus.COMPLETE, TaskStatus.SUPERSEDED}]
        base_probs = [self.task_probability(t) for t in pending]
        if base_probs:
            # Geometric mean is stable for large projects and penalizes repeated weak links.
            base_success = prod(base_probs) ** (1 / len(base_probs))
        else:
            base_success = 1.0
        success = max(.0, min(.999, base_success * cfg["success"]))
        expected_cost = round(sum(float(t.cost_estimate or 0) for t in pending) * cfg["cost"], 6)
        base_seconds = sum(float(t.actual_seconds or t.estimated_seconds or 0) for t in pending)
        critical_seconds = float(self.graph.remaining_critical_path(state).get("seconds", 0.0))
        expected_seconds = round(max(critical_seconds, base_seconds) * cfg["time"], 3)
        deadline_risk = self._deadline_risk(state, expected_seconds)
        cp_ids = self.graph.remaining_critical_path(state).get("task_ids", [])
        cp_probs = [self.task_probability(state.tasks[tid]) for tid in cp_ids if tid in state.tasks]
        cp_probability = prod(cp_probs) if cp_probs else 1.0
        if state.budget_limit and state.budget_limit > 0:
            cost_penalty = min(1.0, expected_cost / max(.000001, float(state.budget_limit)))
        else:
            cost_penalty = min(1.0, expected_cost / max(1.0, expected_cost + 1.0))
        utility = success * .62 + (1 - deadline_risk) * .23 + (1 - cost_penalty) * .15
        return PlanForecast(
            strategy=strategy,
            success_probability=round(success, 4),
            expected_cost=expected_cost,
            expected_seconds=expected_seconds,
            deadline_risk=deadline_risk,
            utility=round(utility, 4),
            critical_path_probability=round(max(0.0, min(1.0, cp_probability)), 4),
        )

    def compare(self, state: ProjectState) -> list[PlanForecast]:
        return sorted((self.forecast(state, name) for name in self.STRATEGIES), key=lambda x: x.utility, reverse=True)

    def recommend(self, state: ProjectState) -> PlanForecast:
        forecasts = self.compare(state)
        selected = forecasts[0]
        state.metadata["probabilistic_plan"] = {
            "recommended": selected.strategy,
            "forecasts": [asdict(x) for x in forecasts],
            "computed_at": _now(),
        }
        return selected


# ---------------------------------------------------------------------------
# Risk / policy engine
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ActionDescriptor:
    action: str
    external_effect: bool = False
    irreversible: bool = False
    destructive: bool = False
    touches_credentials: bool = False
    money_amount: float = 0.0
    data_scope: str = "project"
    permissions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ActionPolicyDecision:
    risk: str
    allowed: bool
    requires_human: bool
    reversible: bool
    reasons: list[str]
    required_permissions: list[str]


class PolicyEngine:
    """Central immutable policy decision point for tool/external actions."""

    LEVELS = ("low", "medium", "high", "critical")

    def evaluate(self, state: ProjectState, action: ActionDescriptor) -> ActionPolicyDecision:
        reasons: list[str] = []
        score = 0
        text = action.action.lower()
        forbidden = list(state.metadata.get("forbidden_actions", []))
        constitution = state.metadata.get("project_constitution", {}) or {}
        forbidden.extend(constitution.get("prohibited_actions", []) or [])
        if any(str(rule).lower() in text for rule in forbidden):
            reasons.append("forbidden_by_project_policy")
            return ActionPolicyDecision("critical", False, True, not action.irreversible, reasons, list(action.permissions))
        if action.external_effect:
            score += 1; reasons.append("external_effect")
        if action.destructive:
            score += 2; reasons.append("destructive")
        if action.irreversible:
            score += 3; reasons.append("irreversible")
        if action.touches_credentials:
            score += 2; reasons.append("credentials")
        if action.money_amount > 0:
            score += 1; reasons.append("spend")
        if action.money_amount >= float(state.metadata.get("human_approval_spend_threshold", 25.0)):
            score += 2; reasons.append("spend_above_approval_threshold")
        if action.data_scope in {"account", "system", "external_org"}:
            score += 1; reasons.append(f"scope:{action.data_scope}")
        risk = "low" if score <= 1 else "medium" if score <= 3 else "high" if score <= 5 else "critical"
        autonomy = str(state.metadata.get("autonomy_level", "balanced")).lower()
        auto_limit = {"supervised": "low", "balanced": "medium", "high": "medium", "maximum": "high"}.get(autonomy, "medium")
        requires_human = action.irreversible or self.LEVELS.index(risk) > self.LEVELS.index(auto_limit)
        allowed = not requires_human
        # Critical/destructive actions never get auto-approved merely by autonomy level.
        if risk == "critical" or action.destructive and action.irreversible:
            allowed = False; requires_human = True
        return ActionPolicyDecision(risk, allowed, requires_human, not action.irreversible, reasons, list(dict.fromkeys(action.permissions)))


# ---------------------------------------------------------------------------
# Evidence ledger / truth boundary / anti-hallucination operational claims
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvidenceRecord:
    id: str
    task_id: str | None
    claim_id: str | None
    source_kind: str
    source_ref: str
    direct: bool
    independent_group: str
    strength: float
    outcome: str
    digest: str
    observed_at: str


class EvidenceLedger:
    KEY = "evidence_ledger_v2"

    def records(self, state: ProjectState) -> list[dict[str, Any]]:
        return state.metadata.setdefault(self.KEY, [])

    def add(
        self,
        state: ProjectState,
        *,
        source_kind: str,
        source_ref: str,
        task_id: str | None = None,
        claim_id: str | None = None,
        direct: bool = True,
        independent_group: str | None = None,
        strength: float = 1.0,
        outcome: str = "supports",
        payload: Any = None,
    ) -> EvidenceRecord:
        if outcome not in {"supports", "contradicts", "neutral"}:
            raise ValueError("outcome must be supports|contradicts|neutral")
        digest = _stable_hash(payload if payload is not None else {"source_kind": source_kind, "source_ref": source_ref, "task_id": task_id, "claim_id": claim_id, "outcome": outcome})
        record_id = sha256(f"{source_kind}|{source_ref}|{task_id}|{claim_id}|{digest}".encode()).hexdigest()[:24]
        existing = next((r for r in self.records(state) if r.get("id") == record_id), None)
        if existing:
            return EvidenceRecord(**existing)
        record = EvidenceRecord(
            id=record_id,
            task_id=task_id,
            claim_id=claim_id,
            source_kind=str(source_kind),
            source_ref=str(source_ref),
            direct=bool(direct),
            independent_group=str(independent_group or source_ref),
            strength=round(max(0.0, min(1.0, float(strength))), 4),
            outcome=outcome,
            digest=digest,
            observed_at=_now(),
        )
        rows = self.records(state)
        rows.append(asdict(record))
        if len(rows) > 5000:
            del rows[:-5000]
        return record

    def for_claim(self, state: ProjectState, claim_id: str) -> list[EvidenceRecord]:
        return [EvidenceRecord(**r) for r in self.records(state) if r.get("claim_id") == claim_id]

    def for_task(self, state: ProjectState, task_id: str) -> list[EvidenceRecord]:
        return [EvidenceRecord(**r) for r in self.records(state) if r.get("task_id") == task_id]


class TruthBoundary:
    STATUSES = ("KNOWN", "OBSERVED", "INFERRED", "ASSUMED", "NOT_VERIFIED", "FAILED")

    def __init__(self, ledger: EvidenceLedger | None = None) -> None:
        self.ledger = ledger or EvidenceLedger()

    def classify(self, state: ProjectState, claim_id: str, *, assumed: bool = False) -> dict[str, Any]:
        records = self.ledger.for_claim(state, claim_id)
        support = [r for r in records if r.outcome == "supports"]
        contradictions = [r for r in records if r.outcome == "contradicts"]
        independent_direct = {r.independent_group for r in support if r.direct and r.strength >= .6}
        if contradictions and sum(r.strength for r in contradictions) >= max(.6, sum(r.strength for r in support)):
            status = "FAILED"
        elif len(independent_direct) >= 2:
            status = "KNOWN"
        elif any(r.direct for r in support):
            status = "OBSERVED"
        elif support:
            status = "INFERRED"
        elif assumed:
            status = "ASSUMED"
        else:
            status = "NOT_VERIFIED"
        return {
            "claim_id": claim_id,
            "status": status,
            "supporting_records": len(support),
            "contradicting_records": len(contradictions),
            "independent_direct_groups": len(independent_direct),
        }

    def operational_claim(self, state: ProjectState, task_id: str, verb: str) -> dict[str, Any]:
        """Gate claims such as 'created', 'tested', 'deployed', 'verified'."""
        required = {
            "created": {"artifact", "file", "tool_result"},
            "tested": {"test_report", "tool_result"},
            "deployed": {"deployment", "field_validation", "tool_result"},
            "verified": {"verification", "test_report", "field_validation", "tool_result"},
        }.get(verb.lower(), {"tool_result", "artifact", "verification"})
        records = self.ledger.for_task(state, task_id)
        matching = [r for r in records if r.source_kind in required and r.outcome == "supports"]
        return {
            "task_id": task_id,
            "verb": verb,
            "allowed": bool(matching),
            "required_evidence_kinds": sorted(required),
            "evidence_ids": [r.id for r in matching],
        }


# ---------------------------------------------------------------------------
# Verification graph
# ---------------------------------------------------------------------------


class VerificationGraph:
    """Builds acceptance state from independent/adversarial verification tasks."""

    TERMINAL = {TaskStatus.COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.PARTIAL_COMPLETE}

    def target_summary(self, state: ProjectState, target_id: str) -> dict[str, Any]:
        target = state.tasks.get(target_id)
        if not target:
            return {"target_id": target_id, "status": "missing", "accepted": False, "checks": []}
        checks = [t for t in state.tasks.values() if str(t.metadata.get("verifies") or "") == target_id]
        rows = []
        for task in checks:
            verdict = str(task.metadata.get("verification_verdict") or task.metadata.get("verdict") or "").lower()
            if not verdict and task.status in self.TERMINAL:
                if task.metadata.get("verified"):
                    verdict = "pass"
                elif task.status == TaskStatus.COMPLETE_WITH_UNCERTAINTY:
                    verdict = "uncertain"
            rows.append({
                "task_id": task.id,
                "layer": task.metadata.get("verification_layer", "adversarial" if task.metadata.get("adversarial") else "independent"),
                "status": task.status.value,
                "verdict": verdict or "pending",
                "provider": task.provider_name,
            })
        required = int(target.metadata.get("required_verification_checks", 0) or 0)
        if required == 0:
            required = len(checks)
        fails = [r for r in rows if r["verdict"] == "fail"]
        passes = [r for r in rows if r["verdict"] == "pass"]
        uncertain = [r for r in rows if r["verdict"] == "uncertain"]
        pending = [r for r in rows if r["verdict"] in {"", "pending"}]
        source_groups = {state.tasks[r["task_id"]].provider_name or r["task_id"] for r in passes if r["task_id"] in state.tasks}
        if fails:
            status = "failed"
        elif pending:
            status = "pending"
        elif uncertain:
            status = "uncertain"
        elif required and len(passes) >= required:
            status = "passed"
        elif required == 0:
            status = "not_required"
        else:
            status = "insufficient"
        accepted = status in {"passed", "not_required"} and target.status in self.TERMINAL
        return {
            "target_id": target_id,
            "status": status,
            "accepted": accepted,
            "required_checks": required,
            "passed_checks": len(passes),
            "independent_groups": len(source_groups),
            "checks": rows,
        }

    def project_summary(self, state: ProjectState) -> dict[str, Any]:
        targets = [t for t in state.tasks.values() if not t.metadata.get("verification_task")]
        summaries = [self.target_summary(state, t.id) for t in targets if any(str(x.metadata.get("verifies") or "") == t.id for x in state.tasks.values())]
        return {
            "targets": len(summaries),
            "passed": sum(x["status"] == "passed" for x in summaries),
            "failed": sum(x["status"] == "failed" for x in summaries),
            "uncertain": sum(x["status"] == "uncertain" for x in summaries),
            "pending": sum(x["status"] in {"pending", "insufficient"} for x in summaries),
            "items": summaries[:100],
        }


# ---------------------------------------------------------------------------
# Universal tool registry / least privilege
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ToolDefinition:
    name: str
    capabilities: list[str]
    permissions: list[str]
    external_effects: bool = False
    destructive: bool = False
    cost_class: str = "low"
    reliability: float = .5


class ToolRegistry:
    KEY = "tool_registry_v1"

    def register(self, state: ProjectState, tool: ToolDefinition) -> None:
        rows = state.metadata.setdefault(self.KEY, {})
        rows[tool.name] = asdict(tool)

    def list(self, state: ProjectState) -> list[ToolDefinition]:
        return [ToolDefinition(**row) for row in state.metadata.setdefault(self.KEY, {}).values()]

    def discover(self, state: ProjectState, required_capabilities: Iterable[str]) -> list[dict[str, Any]]:
        required = {str(x).lower() for x in required_capabilities}
        ranked: list[dict[str, Any]] = []
        for tool in self.list(state):
            caps = {x.lower() for x in tool.capabilities}
            coverage = len(required & caps) / max(1, len(required))
            if required and coverage == 0:
                continue
            score = coverage * .7 + max(0.0, min(1.0, tool.reliability)) * .3
            ranked.append({"tool": tool.name, "coverage": round(coverage, 4), "score": round(score, 4), "external_effects": tool.external_effects, "destructive": tool.destructive})
        return sorted(ranked, key=lambda x: x["score"], reverse=True)

    def least_privilege_grant(self, state: ProjectState, tool_name: str, requested: Iterable[str]) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).get(tool_name)
        if not row:
            return {"tool": tool_name, "granted": [], "denied": list(requested), "known": False}
        allowed = set(row.get("permissions", []))
        requested_set = set(str(x) for x in requested)
        return {
            "tool": tool_name,
            "granted": sorted(requested_set & allowed),
            "denied": sorted(requested_set - allowed),
            "known": True,
        }


# ---------------------------------------------------------------------------
# Specialists / capability registry / ensemble disagreement
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SpecialistProfile:
    id: str
    role: str
    capabilities: list[str]
    permissions: list[str]
    temporary: bool = False
    reliability: float = .5
    runs: int = 0
    successes: int = 0


class AgentCapabilityRegistry:
    KEY = "agent_capability_registry_v1"
    DEFAULTS = {
        "planner": ["planning", "decomposition", "estimation"],
        "researcher": ["research", "sources", "analysis"],
        "coder": ["coding", "testing", "debugging"],
        "analyst": ["analysis", "data", "forecasting"],
        "critic": ["critique", "risk", "assumptions"],
        "verifier": ["verification", "sources", "testing"],
        "security_auditor": ["security", "threat_model", "audit"],
        "release_manager": ["release", "gates", "rollback"],
    }

    def ensure_defaults(self, state: ProjectState) -> None:
        rows = state.metadata.setdefault(self.KEY, {})
        for role, caps in self.DEFAULTS.items():
            rows.setdefault(role, asdict(SpecialistProfile(role, role, caps, [], False, .65)))

    def create_dynamic(self, state: ProjectState, role: str, capabilities: Iterable[str], permissions: Iterable[str] = ()) -> SpecialistProfile:
        self.ensure_defaults(state)
        sid = f"dynamic-{sha256((role+'|'+','.join(sorted(capabilities))).encode()).hexdigest()[:12]}"
        profile = SpecialistProfile(sid, role, sorted(set(capabilities)), sorted(set(permissions)), True, .5)
        state.metadata[self.KEY][sid] = asdict(profile)
        return profile

    def rank(self, state: ProjectState, required: Iterable[str]) -> list[dict[str, Any]]:
        self.ensure_defaults(state)
        required_set = {str(x).lower() for x in required}
        out = []
        for row in state.metadata[self.KEY].values():
            caps = {str(x).lower() for x in row.get("capabilities", [])}
            coverage = len(required_set & caps) / max(1, len(required_set))
            if required_set and not coverage:
                continue
            runs = int(row.get("runs", 0) or 0); successes = int(row.get("successes", 0) or 0)
            empirical = successes / runs if runs else float(row.get("reliability", .5))
            score = .72 * coverage + .28 * empirical
            out.append({"id": row.get("id"), "role": row.get("role"), "coverage": round(coverage, 4), "reliability": round(empirical, 4), "score": round(score, 4)})
        return sorted(out, key=lambda x: x["score"], reverse=True)

    def record_outcome(self, state: ProjectState, specialist_id: str, success: bool) -> None:
        self.ensure_defaults(state)
        row = state.metadata[self.KEY].get(specialist_id)
        if not row:
            return
        row["runs"] = int(row.get("runs", 0)) + 1
        row["successes"] = int(row.get("successes", 0)) + int(bool(success))
        row["reliability"] = round(row["successes"] / max(1, row["runs"]), 4)


class EnsembleDecisionEngine:
    def combine(self, tasks: Iterable[Task]) -> dict[str, Any]:
        rows = [t for t in tasks if t.result]
        if not rows:
            return {"selected_task_id": None, "confidence": 0.0, "disagreement": 0.0, "candidates": []}
        scored = []
        for t in rows:
            confidence = float(t.confidence if t.confidence is not None else .5)
            quality = float(t.quality_score if t.quality_score is not None else .5)
            independence = 1.0 if t.metadata.get("independent_source_groups") else .75
            score = confidence * .45 + quality * .40 + independence * .15
            scored.append((score, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        # Result-text disagreement uses token overlap, intentionally lightweight and deterministic.
        token_sets = [{w.lower().strip('.,:;!?()[]{}') for w in (t.result or '').split() if len(w) > 2} for _, t in scored]
        overlaps = []
        for i, a in enumerate(token_sets):
            for b in token_sets[i+1:]:
                overlaps.append(len(a & b) / max(1, len(a | b)))
        disagreement = 1.0 - (sum(overlaps) / len(overlaps) if overlaps else 1.0)
        return {
            "selected_task_id": scored[0][1].id,
            "confidence": round(scored[0][0] * (1 - .35 * disagreement), 4),
            "disagreement": round(disagreement, 4),
            "needs_resolution": disagreement >= .55 and len(scored) >= 2,
            "candidates": [{"task_id": t.id, "score": round(s, 4), "provider": t.provider_name} for s, t in scored],
        }

    def resolution_task(self, candidates: Iterable[Task]) -> Task | None:
        rows = [t for t in candidates if t.result]
        combined = self.combine(rows)
        if not combined.get("needs_resolution"):
            return None
        return Task(
            title="Resolve specialist disagreement",
            description="Identify the exact propositions on which candidate outputs disagree. Seek independent evidence that can discriminate between them; do not choose by majority vote alone.",
            priority=90,
            dependencies=[t.id for t in rows],
            required_capabilities=["verification", "research", "critique"],
            acceptance_criteria=["Disagreement propositions isolated", "Independent discriminating evidence gathered", "Resolution verdict documented"],
            metadata={"disagreement_resolution": True, "candidate_task_ids": [t.id for t in rows], "required_verification_checks": 2},
        )


# ---------------------------------------------------------------------------
# Rollback / failure memory / recovery planner v2
# ---------------------------------------------------------------------------


class RollbackCoordinator:
    KEY = "operation_journal_v1"

    def begin(self, state: ProjectState, store: Any, *, action: str, reversible: bool = True, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        operation_id = uuid4().hex
        snapshot_seq = store.snapshot_full(state) if reversible and hasattr(store, "snapshot_full") else None
        record = {
            "operation_id": operation_id,
            "action": action,
            "reversible": bool(reversible),
            "snapshot_seq": snapshot_seq,
            "state_hash_before": _stable_hash(state.model_dump(mode="json")),
            "status": "started",
            "started_at": _now(),
            "metadata": dict(metadata or {}),
        }
        state.metadata.setdefault(self.KEY, []).append(record)
        return record

    def commit(self, state: ProjectState, operation_id: str) -> dict[str, Any] | None:
        for row in reversed(state.metadata.setdefault(self.KEY, [])):
            if row.get("operation_id") == operation_id:
                row["status"] = "committed"; row["committed_at"] = _now(); row["state_hash_after"] = _stable_hash(state.model_dump(mode="json"))
                return row
        return None

    def rollback(self, state: ProjectState, store: Any, operation_id: str) -> ProjectState | None:
        row = next((x for x in reversed(state.metadata.setdefault(self.KEY, [])) if x.get("operation_id") == operation_id), None)
        if not row or not row.get("reversible") or row.get("snapshot_seq") is None:
            return None
        restored = store.restore_full_snapshot(int(row["snapshot_seq"]))
        if restored is None:
            row["status"] = "rollback_failed"; row["rollback_at"] = _now(); return None
        restored.metadata.setdefault(self.KEY, []).append({**row, "status": "rolled_back", "rollback_at": _now()})
        if hasattr(store, "save"):
            store.save(restored)
        return restored


class FailureMemory:
    KEY = "failure_memory_v1"

    @staticmethod
    def signature(error: str, stage: str = "", provider: str = "") -> str:
        normalized = " ".join(str(error).lower().split())[:600]
        return sha256(f"{stage}|{provider}|{normalized}".encode()).hexdigest()[:20]

    def record(self, state: ProjectState, task: Task, *, error: str, recovery_action: str | None = None, recovered: bool | None = None) -> dict[str, Any]:
        sig = self.signature(error, str(task.metadata.get("provider_stage", "")), str(task.provider_name or ""))
        rows = state.metadata.setdefault(self.KEY, {})
        row = rows.setdefault(sig, {"signature": sig, "examples": [], "recoveries": {}, "occurrences": 0})
        row["occurrences"] += 1
        row["last_seen"] = _now()
        row["examples"].append({"task_id": task.id, "error": str(error)[:800], "provider": task.provider_name, "stage": task.metadata.get("provider_stage")})
        del row["examples"][:-10]
        if recovery_action:
            rr = row["recoveries"].setdefault(recovery_action, {"attempts": 0, "successes": 0})
            rr["attempts"] += 1
            rr["successes"] += int(bool(recovered))
        return row

    def best_recovery(self, state: ProjectState, signature: str) -> str | None:
        row = state.metadata.setdefault(self.KEY, {}).get(signature)
        if not row:
            return None
        ranked = []
        for action, stats in row.get("recoveries", {}).items():
            attempts = int(stats.get("attempts", 0)); successes = int(stats.get("successes", 0))
            if attempts:
                ranked.append((successes / attempts, attempts, action))
        return sorted(ranked, reverse=True)[0][2] if ranked else None


@dataclass(slots=True)
class RecoveryPlan:
    action: str
    confidence: float
    reason: str
    alternatives: list[str]


class RecoveryPlannerV2:
    def __init__(self, memory: FailureMemory | None = None, policy: PolicyEngine | None = None) -> None:
        self.memory = memory or FailureMemory(); self.policy = policy or PolicyEngine()

    def plan(self, state: ProjectState, task: Task, error: str) -> RecoveryPlan:
        sig = self.memory.signature(error, str(task.metadata.get("provider_stage", "")), str(task.provider_name or ""))
        learned = self.memory.best_recovery(state, sig)
        alternatives = ["retry", "fallback_provider", "split_task", "rollback", "escalate"]
        if learned in alternatives:
            return RecoveryPlan(learned, .82, "previously successful recovery for matching failure signature", [x for x in alternatives if x != learned])
        text = error.lower()
        if "timeout" in text or "rate" in text or "429" in text:
            action, confidence, reason = "fallback_provider", .76, "transient/provider-specific failure"
        elif "context" in text or "too large" in text or "token" in text:
            action, confidence, reason = "split_task", .79, "work unit exceeds execution envelope"
        elif task.attempts < max(1, task.max_attempts - 1):
            action, confidence, reason = "retry", .62, "retry budget remains"
        elif task.metadata.get("operation_id"):
            action, confidence, reason = "rollback", .68, "reversible operation has rollback record"
        else:
            action, confidence, reason = "escalate", .7, "automatic recovery options exhausted"
        return RecoveryPlan(action, confidence, reason, [x for x in alternatives if x != action])


# ---------------------------------------------------------------------------
# Cost / budget / deadline intelligence
# ---------------------------------------------------------------------------


class CostIntelligenceEngine:
    def __init__(self, cost: CostEngine | None = None, planner: ProbabilisticPlanningEngine | None = None) -> None:
        self.cost = cost or CostEngine(); self.planner = planner or ProbabilisticPlanningEngine(cost=self.cost)

    def allocate_budget(self, state: ProjectState) -> dict[str, Any]:
        limit = state.budget_limit
        if limit is None:
            return {"limit": None, "allocations": {}, "reserve": None}
        pressure = self.cost.budget_pressure(state)
        verification = max(.10, min(.30, state.verification_percent / 100 * .25))
        contingency = .15 if pressure < .7 else .08
        research = .18
        planning = .08
        execution = max(.25, 1.0 - verification - contingency - research - planning)
        shares = {"planning": planning, "research": research, "execution": execution, "verification": verification, "contingency": contingency}
        # Normalize exactly to one after dynamic adjustments.
        total = sum(shares.values())
        shares = {k: v / total for k, v in shares.items()}
        allocation = {k: round(float(limit) * v, 6) for k, v in shares.items()}
        result = {"limit": float(limit), "spent": self.cost.spent(state), "committed": self.cost.committed(state), "allocations": allocation, "reserve": allocation["contingency"]}
        state.metadata["budget_autopilot"] = {**result, "computed_at": _now()}
        return result

    def deadline_policy(self, state: ProjectState) -> dict[str, Any]:
        forecast = self.planner.recommend(state)
        risk = forecast.deadline_risk
        if risk >= .9:
            mode = "emergency"; verification_floor = 35; exploration_cap = 5
        elif risk >= .65:
            mode = "deadline"; verification_floor = 45; exploration_cap = 15
        elif risk >= .35:
            mode = "accelerated"; verification_floor = 50; exploration_cap = 25
        else:
            mode = "normal"; verification_floor = state.verification_percent; exploration_cap = state.exploration_percent
        result = {
            "mode": mode,
            "deadline_risk": risk,
            "recommended_strategy": forecast.strategy,
            "verification_floor": verification_floor,
            "exploration_cap": exploration_cap,
            "expected_seconds": forecast.expected_seconds,
        }
        state.metadata["deadline_intelligence"] = {**result, "computed_at": _now()}
        return result

    def roi_snapshot(self, state: ProjectState) -> dict[str, Any]:
        completed = [t for t in state.leaf_tasks if t.status in {TaskStatus.COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.PARTIAL_COMPLETE}]
        value = sum(float(t.quality_score if t.quality_score is not None else .5) * max(.1, float(t.metadata.get("importance", t.priority / 100))) for t in completed)
        spent = self.cost.spent(state)
        seconds = sum(float(t.actual_seconds or 0) for t in completed)
        return {
            "completed_value": round(value, 4),
            "spent": spent,
            "seconds": round(seconds, 3),
            "value_per_currency": None if spent <= 0 else round(value / spent, 4),
            "value_per_minute": None if seconds <= 0 else round(value / (seconds / 60), 4),
        }


# ---------------------------------------------------------------------------
# Mission control / health / forecast
# ---------------------------------------------------------------------------


class MissionControl:
    def __init__(self) -> None:
        self.graph = TaskGraph()
        self.compiler = ProjectCompiler(self.graph)
        self.planning = ProbabilisticPlanningEngine(self.graph)
        self.policy = PolicyEngine()
        self.ledger = EvidenceLedger()
        self.truth = TruthBoundary(self.ledger)
        self.verification = VerificationGraph()
        self.tools = ToolRegistry()
        self.agents = AgentCapabilityRegistry()
        self.cost = CostIntelligenceEngine(planner=self.planning)
        self.cognitive = CognitiveEvolutionCore()

    def health(self, state: ProjectState) -> dict[str, Any]:
        audit = self.graph.audit(state)
        failures = sum(t.status == TaskStatus.FAILED for t in state.leaf_tasks)
        review = sum(t.status == TaskStatus.NEEDS_REVIEW for t in state.leaf_tasks)
        blocked = sum(t.status == TaskStatus.BLOCKED for t in state.leaf_tasks)
        verification = self.verification.project_summary(state)
        budget_pressure = CostEngine().budget_pressure(state)
        plan = self.planning.forecast(state, "balanced")
        penalty = min(1.0, failures * .08 + review * .04 + blocked * .015 + verification["failed"] * .10 + budget_pressure * .16 + plan.deadline_risk * .18 + (0 if audit["valid"] else .35))
        score = round(max(0.0, 1.0 - penalty), 4)
        return {
            "score": score,
            "label": "healthy" if score >= .8 else "watch" if score >= .6 else "at_risk" if score >= .35 else "critical",
            "graph_valid": bool(audit["valid"]),
            "failed_tasks": failures,
            "needs_review": review,
            "blocked_tasks": blocked,
            "verification_failures": verification["failed"],
            "budget_pressure": round(budget_pressure, 4),
            "deadline_risk": plan.deadline_risk,
        }

    def snapshot(self, state: ProjectState, *, persist: bool = False) -> dict[str, Any]:
        blueprint = self.compiler.compile(state, persist=persist)
        forecasts = self.planning.compare(state)
        recommended = forecasts[0] if forecasts else self.planning.forecast(state)
        verification = self.verification.project_summary(state)
        self.agents.ensure_defaults(state)
        budget = self.cost.allocate_budget(state) if persist else state.metadata.get("budget_autopilot", {})
        deadline = self.cost.deadline_policy(state) if persist else state.metadata.get("deadline_intelligence", {})
        evidence = self.ledger.records(state)
        truth_counts = {key: 0 for key in TruthBoundary.STATUSES}
        claims = state.metadata.get("claims", {}) or {}
        for claim_id, claim in claims.items():
            assumed = bool(claim.get("assumed")) if isinstance(claim, dict) else False
            truth_counts[self.truth.classify(state, str(claim_id), assumed=assumed)["status"]] += 1
        result = {
            "blueprint": asdict(blueprint),
            "health": self.health(state),
            "recommended_strategy": asdict(recommended),
            "strategy_forecasts": [asdict(x) for x in forecasts],
            "verification": verification,
            "evidence": {"records": len(evidence), "truth_counts": truth_counts},
            "budget_autopilot": budget,
            "deadline_intelligence": deadline,
            "roi": self.cost.roi_snapshot(state),
            "specialists": len(state.metadata.get(AgentCapabilityRegistry.KEY, {})),
            "tools": len(state.metadata.get(ToolRegistry.KEY, {})),
            "critical_path": self.graph.remaining_critical_path(state),
            "cognitive_evolution": {
                "dogfood_trials": len(state.metadata.get("controlled_dogfood_v2", {})),
                "self_improvement_candidates": len(state.metadata.get("self_improvement_pipeline_v1", {})),
                "frozen_baselines": len(state.metadata.get("immutable_baselines_v1", {})),
                "holdout_suites": len(state.metadata.get("holdout_benchmarks_v1", {})),
                "strategy_families": len(state.metadata.get("cognitive_strategy_lab_v2", {})),
                "calibration_contexts": len(state.metadata.get("confidence_calibration_v2", {})),
                "dead_end": state.metadata.get("cognitive_dead_end", {}),
            },
        }
        if persist:
            state.metadata["mission_control"] = {**result, "updated_at": _now()}
        return result


class ProductionIntelligenceCore:
    """Facade used by the app/scheduler to expose the integrated production brain."""

    def __init__(self) -> None:
        self.mission_control = MissionControl()
        self.compiler = self.mission_control.compiler
        self.planner = self.mission_control.planning
        self.policy = self.mission_control.policy
        self.evidence = self.mission_control.ledger
        self.truth = self.mission_control.truth
        self.verification = self.mission_control.verification
        self.tools = self.mission_control.tools
        self.agents = self.mission_control.agents
        self.cost = self.mission_control.cost
        self.rollback = RollbackCoordinator()
        self.failure_memory = FailureMemory()
        self.recovery = RecoveryPlannerV2(self.failure_memory, self.policy)
        self.ensemble = EnsembleDecisionEngine()

    def initialize_project(self, state: ProjectState) -> dict[str, Any]:
        self.agents.ensure_defaults(state)
        self.compiler.compile(state, persist=True)
        self.planner.recommend(state)
        if state.budget_limit is not None:
            self.cost.allocate_budget(state)
        self.cost.deadline_policy(state)
        return self.mission_control.snapshot(state, persist=True)
