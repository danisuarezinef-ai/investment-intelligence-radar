from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable

from .models import ProjectState, TaskStatus
from .production_intelligence import MissionControl


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Human escalation packets and autonomous operating modes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DecisionOption:
    id: str
    label: str
    upside: str
    downside: str
    reversible: bool = True


@dataclass(slots=True)
class EscalationPacket:
    id: str
    situation: str
    why_human_needed: str
    options: list[DecisionOption]
    recommendation: str | None
    recommendation_reason: str
    consequence_of_no_decision: str
    severity: str
    created_at: str


class HumanEscalationV2:
    KEY = "human_escalations_v2"

    def build(
        self,
        state: ProjectState,
        *,
        situation: str,
        why_human_needed: str,
        options: Iterable[DecisionOption],
        recommendation: str | None,
        recommendation_reason: str,
        consequence_of_no_decision: str,
        severity: str = "medium",
    ) -> EscalationPacket:
        opts = list(options)
        payload = f"{state.id}|{situation}|{','.join(x.id for x in opts)}|{recommendation}"
        packet = EscalationPacket(
            id=sha256(payload.encode()).hexdigest()[:24],
            situation=situation,
            why_human_needed=why_human_needed,
            options=opts,
            recommendation=recommendation,
            recommendation_reason=recommendation_reason,
            consequence_of_no_decision=consequence_of_no_decision,
            severity=severity,
            created_at=_now(),
        )
        state.metadata.setdefault(self.KEY, {})[packet.id] = {
            **asdict(packet),
            "options": [asdict(x) for x in opts],
            "status": "open",
        }
        state.human_interventions_required += 1
        return packet

    def resolve(self, state: ProjectState, packet_id: str, selected: str) -> bool:
        row = state.metadata.setdefault(self.KEY, {}).get(packet_id)
        if not row:
            return False
        valid = {x.get("id") for x in row.get("options", [])}
        if selected not in valid:
            return False
        row["selected"] = selected; row["status"] = "resolved"; row["resolved_at"] = _now(); return True


class OperatingModeEngine:
    KEY = "operating_mode_v1"
    MODES = {
        "normal": {"external_actions": True, "execution": True, "modification": True, "auto_recovery": True, "max_risk": "medium"},
        "while_away": {"external_actions": True, "execution": True, "modification": True, "auto_recovery": True, "max_risk": "medium"},
        "finish_it": {"external_actions": True, "execution": True, "modification": True, "auto_recovery": True, "max_risk": "high"},
        "plan_only": {"external_actions": False, "execution": False, "modification": False, "auto_recovery": False, "max_risk": "low"},
        "auditor": {"external_actions": False, "execution": True, "modification": False, "auto_recovery": False, "max_risk": "low"},
    }

    def set(self, state: ProjectState, mode: str, *, allowed_actions: Iterable[str] = (), stop_conditions: Iterable[str] = ()) -> dict[str, Any]:
        if mode not in self.MODES:
            raise ValueError(f"unknown operating mode: {mode}")
        row = {
            "mode": mode,
            **self.MODES[mode],
            "allowed_actions": sorted(set(allowed_actions)),
            "stop_conditions": list(stop_conditions),
            "set_at": _now(),
        }
        state.metadata[self.KEY] = row
        state.absence_mode = mode == "while_away"
        return row

    def can(self, state: ProjectState, capability: str) -> bool:
        row = state.metadata.get(self.KEY) or {"mode": "normal", **self.MODES["normal"]}
        mapping = {
            "execute": "execution",
            "modify": "modification",
            "external": "external_actions",
            "recover": "auto_recovery",
        }
        key = mapping.get(capability, capability)
        return bool(row.get(key, False))


# ---------------------------------------------------------------------------
# Subprojects / portfolio / global resource scheduler
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SubprojectSpec:
    id: str
    parent_project_id: str
    title: str
    objective: str
    budget_cap: float | None
    resource_weight: float
    status: str
    created_at: str


class RecursiveProjectManager:
    KEY = "subprojects_v1"

    def create(self, state: ProjectState, *, title: str, objective: str, budget_cap: float | None = None, resource_weight: float = 1.0) -> SubprojectSpec:
        sid = sha256(f"{state.id}|{title}|{objective}".encode()).hexdigest()[:24]
        spec = SubprojectSpec(sid, state.id, title, objective, budget_cap, max(.1, float(resource_weight)), "planned", _now())
        state.metadata.setdefault(self.KEY, {})[sid] = asdict(spec)
        return spec

    def update_status(self, state: ProjectState, subproject_id: str, status: str) -> bool:
        row = state.metadata.setdefault(self.KEY, {}).get(subproject_id)
        if not row:
            return False
        row["status"] = status; row["updated_at"] = _now(); return True


@dataclass(slots=True)
class PortfolioEntry:
    project_id: str
    name: str
    urgency: int
    progress: float
    health: float
    deadline_risk: float
    importance: float = .5
    paused: bool = False


class PortfolioScheduler:
    """Allocates finite global workers fairly across multiple projects."""

    def rank(self, entries: Iterable[PortfolioEntry]) -> list[dict[str, Any]]:
        out = []
        for e in entries:
            if e.paused:
                score = 0.0
            else:
                remaining = max(0.0, 1.0 - e.progress / 100)
                score = (e.urgency / 100) * .28 + e.importance * .28 + (1 - e.health) * .18 + e.deadline_risk * .18 + remaining * .08
            out.append({**asdict(e), "priority_score": round(score, 4)})
        return sorted(out, key=lambda x: x["priority_score"], reverse=True)

    def allocate(self, entries: Iterable[PortfolioEntry], total_workers: int) -> dict[str, int]:
        total_workers = max(0, int(total_workers)); ranked = self.rank(entries)
        active = [x for x in ranked if not x["paused"] and x["priority_score"] > 0]
        if not active or total_workers == 0:
            return {x["project_id"]: 0 for x in ranked}
        alloc = {x["project_id"]: 0 for x in ranked}
        # Fairness floor: one worker per active project when possible.
        for row in active[:total_workers]:
            alloc[row["project_id"]] += 1
        remaining = total_workers - min(total_workers, len(active))
        if remaining <= 0:
            return alloc
        score_sum = sum(x["priority_score"] for x in active) or 1.0
        fractions = []
        assigned = 0
        for row in active:
            exact = remaining * row["priority_score"] / score_sum
            whole = int(exact); alloc[row["project_id"]] += whole; assigned += whole
            fractions.append((exact - whole, row["project_id"]))
        for _, pid in sorted(fractions, reverse=True)[: remaining - assigned]:
            alloc[pid] += 1
        return alloc


class CrossProjectLearning:
    """Exports only non-sensitive aggregate learning, never raw project content."""

    SAFE_KEYS = {"task_type", "strategy", "runs", "successes", "success_rate", "avg_quality", "avg_cost", "avg_seconds", "utility"}

    def export_safe(self, state: ProjectState) -> dict[str, Any]:
        outcomes = []
        for row in (state.metadata.get("outcome_learning_v1", {}) or {}).values():
            outcomes.append({k: row.get(k) for k in self.SAFE_KEYS if k in row})
        preferred_skills = [name for name, row in (state.metadata.get("skills_library_v1", {}) or {}).items() if row.get("stage") == "preferred"]
        return {
            "schema": 1,
            "project_type": state.metadata.get("project_type", "general"),
            "outcomes": outcomes,
            "preferred_skill_names": preferred_skills,
            "contains_raw_results": False,
            "contains_secrets": False,
        }

    def import_safe(self, state: ProjectState, payload: dict[str, Any]) -> int:
        if payload.get("contains_raw_results") or payload.get("contains_secrets"):
            raise ValueError("unsafe cross-project payload")
        count = 0
        target = state.metadata.setdefault("cross_project_learning_v1", [])
        for row in payload.get("outcomes", []):
            clean = {k: row.get(k) for k in self.SAFE_KEYS if k in row}
            target.append(clean); count += 1
        del target[:-500]
        return count


# ---------------------------------------------------------------------------
# Smart notifications / autonomy confidence
# ---------------------------------------------------------------------------


class SmartNotificationPolicy:
    IMPORTANT = {"project_complete", "critical_failure", "human_decision", "budget_risk", "deadline_risk", "security_block", "milestone"}

    def should_notify(self, event: str, severity: str = "info", *, repeated_count: int = 1) -> bool:
        if event in self.IMPORTANT:
            return True
        if severity in {"error", "critical"}:
            return True
        if repeated_count >= 5 and event in {"retry", "provider_failure", "blocked"}:
            return True
        return False


class AutonomyConfidenceEngine:
    def __init__(self) -> None:
        self.mc = MissionControl()

    def score(self, state: ProjectState) -> dict[str, Any]:
        health = self.mc.health(state)
        open_critical = sum(
            1 for d in state.decisions.values()
            if d.status.value == "open" and str(d.metadata.get("severity", "")).lower() in {"high", "critical"}
        )
        failed = health["failed_tasks"]
        security_blocks = len(state.metadata.get("security_blocks", []))
        base = health["score"]
        penalty = min(.9, open_critical * .15 + failed * .04 + security_blocks * .08)
        score = round(max(0.0, min(1.0, base - penalty)), 4)
        return {
            "score": score,
            "level": "high" if score >= .8 else "medium" if score >= .55 else "low",
            "can_continue_unattended": score >= .65 and open_critical == 0,
            "factors": {"health": health["score"], "open_critical_decisions": open_critical, "failed_tasks": failed, "security_blocks": security_blocks},
        }
