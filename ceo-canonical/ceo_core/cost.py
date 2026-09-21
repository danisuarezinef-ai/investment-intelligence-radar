from __future__ import annotations

from .models import ProjectState


class CostEngine:
    """Tracks actual API spend and in-flight reservations.

    Reservations are intentionally separate from actual spend: they prevent two
    concurrent tasks from both consuming the same remaining budget without
    fabricating a charge before a provider returns usage data.
    """

    RESERVATIONS_KEY = "cost_reservations"

    def projected_cost(self, state: ProjectState) -> float:
        return round(
            sum(
                float(t.cost_estimate or 0)
                for t in state.leaf_tasks
                if t.status.value not in {"complete", "superseded"}
            ),
            4,
        )

    def spent(self, state: ProjectState) -> float:
        return round(float(state.metadata.get("cost_spent", 0.0)), 6)

    def reservations(self, state: ProjectState) -> dict[str, float]:
        raw = state.metadata.setdefault(self.RESERVATIONS_KEY, {})
        # Normalize old/malformed values defensively without letting them become
        # negative credits against the budget.
        normalized = {str(k): max(0.0, float(v or 0.0)) for k, v in dict(raw).items()}
        if raw != normalized:
            state.metadata[self.RESERVATIONS_KEY] = normalized
        return state.metadata[self.RESERVATIONS_KEY]

    def reserved(self, state: ProjectState) -> float:
        return round(sum(self.reservations(state).values()), 6)

    def committed(self, state: ProjectState) -> float:
        return round(self.spent(state) + self.reserved(state), 6)

    def remaining_budget(self, state: ProjectState, *, include_reserved: bool = True) -> float | None:
        if state.budget_limit is None:
            return None
        used = self.committed(state) if include_reserved else self.spent(state)
        return round(max(0.0, float(state.budget_limit) - used), 6)

    def budget_pressure(self, state: ProjectState, *, include_reserved: bool = True) -> float:
        if state.budget_limit is None or float(state.budget_limit) <= 0:
            return 0.0
        used = self.committed(state) if include_reserved else self.spent(state)
        return max(0.0, min(1.0, used / float(state.budget_limit)))

    def can_spend(self, state: ProjectState, amount: float) -> bool:
        amount = max(0.0, float(amount or 0.0))
        return state.budget_limit is None or self.committed(state) + amount <= float(state.budget_limit) + 1e-12

    def reserve(self, state: ProjectState, reservation_id: str, amount: float) -> bool:
        amount = max(0.0, float(amount or 0.0))
        reservations = self.reservations(state)
        previous = float(reservations.get(str(reservation_id), 0.0))
        # Re-reserving the same task replaces its old reservation rather than
        # double-counting a retry.
        available_committed = self.committed(state) - previous
        if state.budget_limit is not None and available_committed + amount > float(state.budget_limit) + 1e-12:
            return False
        if amount > 0:
            reservations[str(reservation_id)] = round(amount, 6)
        else:
            reservations.pop(str(reservation_id), None)
        return True

    def release(self, state: ProjectState, reservation_id: str) -> float:
        amount = float(self.reservations(state).pop(str(reservation_id), 0.0) or 0.0)
        return round(max(0.0, amount), 6)

    def settle(self, state: ProjectState, reservation_id: str, actual_amount: float) -> dict:
        reserved = self.release(state, reservation_id)
        actual = max(0.0, float(actual_amount or 0.0))
        if actual:
            self.record(state, actual)
        overshoot = bool(
            state.budget_limit is not None
            and self.spent(state) > float(state.budget_limit) + 1e-12
        )
        row = {
            "reservation_id": str(reservation_id),
            "reserved": round(reserved, 6),
            "actual": round(actual, 6),
            "overshoot": overshoot,
        }
        history = state.metadata.setdefault("cost_settlements", [])
        history.append(row)
        del history[:-200]
        if overshoot:
            state.metadata["budget_overshoot_detected"] = row
        return row

    def clear_reservations(self, state: ProjectState, *, reason: str = "restart") -> dict:
        reservations = dict(self.reservations(state))
        if reservations:
            state.metadata[self.RESERVATIONS_KEY] = {}
            history = state.metadata.setdefault("released_stale_cost_reservations", [])
            history.append({"reason": reason, "reservations": reservations})
            del history[:-50]
        return reservations

    def record(self, state: ProjectState, amount: float) -> None:
        state.metadata["cost_spent"] = round(self.spent(state) + max(0.0, float(amount or 0.0)), 6)

    def snapshot(self, state: ProjectState) -> dict:
        return {
            "spent": self.spent(state),
            "reserved": self.reserved(state),
            "committed": self.committed(state),
            "projected": self.projected_cost(state),
            "limit": state.budget_limit,
            "remaining": self.remaining_budget(state),
            "pressure": round(self.budget_pressure(state), 4),
            "priority_mode": state.priority_mode,
        }
