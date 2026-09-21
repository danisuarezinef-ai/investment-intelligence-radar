from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ActionRequest:
    action: str
    external_effect: bool = False
    irreversible: bool = False
    cost: float = 0.0


class SafetyBoundary:
    """Core guardrail for external, irreversible, costly and explicitly forbidden actions."""

    def allowed(self, req: ActionRequest, policy: dict | None = None) -> bool:
        policy = policy or {}
        action = req.action.lower().strip()
        for forbidden in policy.get("forbidden_actions", []) or []:
            token = str(forbidden).lower().strip()
            if token and token in action:
                return False
        if req.irreversible and not policy.get("allow_irreversible", False):
            return False
        if req.external_effect and not policy.get("allow_external_actions", False):
            return False
        max_cost = policy.get("max_action_cost")
        if max_cost is not None and req.cost > float(max_cost):
            return False
        return True
