from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Any, Iterable

from .models import ProjectState, TaskStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat()


def _deadline_pressure(value: str | None, now: datetime) -> float:
    if not value:
        return 0.0
    try:
        raw = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hours = (dt.astimezone(timezone.utc) - now).total_seconds() / 3600.0
    except Exception:
        return 0.0
    if hours <= 0:
        return 1.0
    if hours >= 7 * 24:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (hours / (7 * 24))))


@dataclass(slots=True)
class PortfolioProjectDecision:
    project_id: str
    score: float
    slots: int
    rank: int
    runnable: bool
    reason: str
    urgency: int
    progress: float
    attention: int
    open_tasks: int
    deadline_pressure: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PortfolioSupervisor:
    """Cross-project resource planner.

    The planner is deliberately advisory at the project boundary: it decides which
    projects deserve capacity and records the plan, but it never unpauses a project,
    bypasses a human gate, spends money, or publishes anything. Existing per-project
    schedulers remain responsible for task dispatch and all side-effect gates.
    """

    KEY = "portfolio_supervisor_v1"

    @staticmethod
    def _project_features(state: ProjectState, now: datetime) -> tuple[bool, str, dict[str, float | int]]:
        terminal = {
            TaskStatus.COMPLETE,
            TaskStatus.PARTIAL_COMPLETE,
            TaskStatus.COMPLETE_WITH_UNCERTAINTY,
            TaskStatus.SUPERSEDED,
            TaskStatus.FAILED,
        }
        leaves = [t for t in state.leaf_tasks if t.status != TaskStatus.SUPERSEDED]
        open_tasks = [t for t in leaves if t.status not in terminal]
        attention = [t for t in open_tasks if t.status in {TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.NEEDS_REVIEW}]
        executable = [t for t in open_tasks if t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.WAITING, TaskStatus.RUNNING}]
        if state.archived:
            runnable, reason = False, "archived"
        elif state.completed_at is not None:
            runnable, reason = False, "complete"
        elif state.paused:
            runnable, reason = False, "operator_paused"
        elif open_tasks and not executable and attention:
            runnable, reason = False, "human_or_dependency_gate"
        else:
            runnable, reason = True, "runnable"
        return runnable, reason, {
            "open_tasks": len(open_tasks),
            "attention": len(attention),
            "deadline_pressure": _deadline_pressure(state.deadline, now),
        }

    def score(self, state: ProjectState, *, now: datetime | None = None) -> float:
        now = now or _now()
        runnable, _, f = self._project_features(state, now)
        if not runnable:
            return -1.0
        urgency = max(1, min(100, int(state.urgency))) / 100.0
        progress_deficit = max(0.0, min(1.0, 1.0 - float(state.progress) / 100.0))
        open_pressure = min(1.0, int(f["open_tasks"]) / 25.0)
        attention_penalty = min(0.35, int(f["attention"]) * 0.03)
        deadline = float(f["deadline_pressure"])
        # Value-biased but conservative: urgency/deadline lead, large unfinished
        # projects get modest pressure, and attention debt prevents monopolisation.
        value = (0.34 * urgency) + (0.26 * deadline) + (0.22 * progress_deficit) + (0.18 * open_pressure) - attention_penalty
        return round(max(0.0, value), 6)

    def plan(self, states: Iterable[ProjectState], *, total_slots: int, max_share: float = 0.60) -> dict[str, Any]:
        rows = list(states)
        now = _now()
        total_slots = max(0, int(total_slots))
        max_share = max(0.10, min(1.0, float(max_share)))
        decisions: list[PortfolioProjectDecision] = []
        prelim: list[tuple[ProjectState, float, bool, str, dict[str, float | int]]] = []
        for state in rows:
            runnable, reason, features = self._project_features(state, now)
            score = self.score(state, now=now)
            prelim.append((state, score, runnable, reason, features))
        ranked = sorted(prelim, key=lambda x: (-x[1], -int(x[0].urgency), x[0].created_at))
        allocations: dict[str, int] = {s.id: 0 for s, *_ in ranked}
        runnable_rows = [row for row in ranked if row[2]]

        # Fair first pass: one slot per runnable project while capacity exists.
        remaining = total_slots
        for state, *_ in runnable_rows:
            if remaining <= 0:
                break
            allocations[state.id] += 1
            remaining -= 1

        # Weighted fill with a hard per-project share while alternatives exist.
        cap = max(1, int(ceil(total_slots * max_share))) if total_slots else 0
        while remaining > 0 and runnable_rows:
            eligible = [row for row in runnable_rows if allocations[row[0].id] < cap]
            if not eligible:
                eligible = runnable_rows
            # Diminishing-return score prevents the top project from swallowing all
            # remaining slots even when it leads the portfolio.
            chosen = max(eligible, key=lambda row: row[1] / (1.0 + allocations[row[0].id] * 0.75))
            allocations[chosen[0].id] += 1
            remaining -= 1

        for rank, (state, score, runnable, reason, features) in enumerate(ranked, start=1):
            decision = PortfolioProjectDecision(
                project_id=state.id,
                score=score,
                slots=allocations[state.id],
                rank=rank,
                runnable=runnable,
                reason=reason,
                urgency=int(state.urgency),
                progress=float(state.progress),
                attention=int(features["attention"]),
                open_tasks=int(features["open_tasks"]),
                deadline_pressure=float(features["deadline_pressure"]),
            )
            state.metadata[self.KEY] = {
                **decision.to_dict(),
                "generated_at": now.isoformat(),
                "total_slots": total_slots,
                "max_share": max_share,
                "advisory_only": True,
                "auto_unpause": False,
            }
            decisions.append(decision)

        return {
            "generated_at": now.isoformat(),
            "total_slots": total_slots,
            "max_share": max_share,
            "projects": [d.to_dict() for d in decisions],
            "automatic_project_unpause": False,
            "automatic_side_effects": False,
        }

    def next_runnable(self, states: Iterable[ProjectState]) -> str | None:
        plan = self.plan(states, total_slots=1, max_share=1.0)
        for row in plan["projects"]:
            if row["runnable"] and row["slots"] > 0:
                return str(row["project_id"])
        return None
