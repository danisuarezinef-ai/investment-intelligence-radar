from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from .models import ProjectState, Task


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class DelegationDecision:
    allowed: bool
    reason: str
    contract_id: str | None
    required_capabilities: list[str]
    allowed_capabilities: list[str]
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DelegationContractsV2:
    """Least-privilege delegation contracts for child/remote worker tasks.

    Contracts constrain delegated work; they never grant an authority that the normal
    CapabilityPolicyV2 would otherwise reject. Tasks without a delegation contract
    retain existing scheduler semantics.
    """

    KEY = "delegation_contracts_v2"
    TASK_KEY = "delegation_contract_v2"

    @staticmethod
    def _digest(body: dict[str, Any]) -> str:
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return sha256(raw).hexdigest()

    def issue(
        self,
        state: ProjectState,
        parent: Task,
        child: Task,
        *,
        allowed_capabilities: list[str] | None = None,
        allowed_tools: list[str] | None = None,
        ttl_seconds: int = 3600,
        max_cost: float = 0.0,
    ) -> dict[str, Any]:
        requested = sorted({str(x).strip().lower() for x in child.required_capabilities if str(x).strip()})
        parent_caps = {str(x).strip().lower() for x in parent.required_capabilities if str(x).strip()}
        requested_scope = set(str(x).strip().lower() for x in (allowed_capabilities or requested) if str(x).strip())
        # A parent with an explicit scope cannot delegate capabilities it does not own.
        if parent_caps and not requested_scope.issubset(parent_caps):
            raise ValueError("delegation scope exceeds parent capabilities")
        expires = _now() + timedelta(seconds=max(30, int(ttl_seconds)))
        body = {
            "contract_id": uuid4().hex,
            "project_id": state.id,
            "parent_task_id": parent.id,
            "child_task_id": child.id,
            "allowed_capabilities": sorted(requested_scope),
            "allowed_tools": sorted({str(x) for x in (allowed_tools or [])}),
            "max_cost": max(0.0, float(max_cost)),
            "issued_at": _now().isoformat(),
            "expires_at": expires.isoformat(),
            "may_subdelegate": False,
        }
        body["digest"] = self._digest(body)
        child.metadata[self.TASK_KEY] = body
        root = state.metadata.setdefault(self.KEY, {"issued": 0, "events": []})
        root["issued"] = int(root.get("issued", 0) or 0) + 1
        root.setdefault("events", []).append({"event": "issued", "contract_id": body["contract_id"], "child_task_id": child.id, "ts": body["issued_at"]})
        del root["events"][:-1000]
        return body

    def assess(self, state: ProjectState, task: Task, *, now: datetime | None = None) -> DelegationDecision:
        now = now or _now()
        contract = task.metadata.get(self.TASK_KEY)
        required = sorted({str(x).strip().lower() for x in task.required_capabilities if str(x).strip()})
        if not contract:
            decision = DelegationDecision(True, "not_delegated", None, required, [], now.isoformat())
            return decision
        contract = dict(contract)
        digest = str(contract.pop("digest", ""))
        if digest != self._digest(contract):
            return self._record(state, task, DelegationDecision(False, "contract_tampered", str(contract.get("contract_id") or "") or None, required, list(contract.get("allowed_capabilities", [])), now.isoformat()))
        if str(contract.get("project_id")) != state.id or str(contract.get("child_task_id")) != task.id:
            return self._record(state, task, DelegationDecision(False, "contract_binding_mismatch", str(contract.get("contract_id") or "") or None, required, list(contract.get("allowed_capabilities", [])), now.isoformat()))
        try:
            expires = datetime.fromisoformat(str(contract.get("expires_at")).replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires.astimezone(timezone.utc) < now:
                return self._record(state, task, DelegationDecision(False, "contract_expired", str(contract.get("contract_id") or "") or None, required, list(contract.get("allowed_capabilities", [])), now.isoformat()))
        except Exception:
            return self._record(state, task, DelegationDecision(False, "contract_expiry_invalid", str(contract.get("contract_id") or "") or None, required, list(contract.get("allowed_capabilities", [])), now.isoformat()))
        allowed = sorted({str(x).strip().lower() for x in contract.get("allowed_capabilities", []) if str(x).strip()})
        if not set(required).issubset(set(allowed)):
            return self._record(state, task, DelegationDecision(False, "capability_scope_escalation", str(contract.get("contract_id") or "") or None, required, allowed, now.isoformat()))
        max_cost = max(0.0, float(contract.get("max_cost", 0.0) or 0.0))
        if max_cost and float(task.cost_estimate or 0.0) > max_cost + 1e-12:
            return self._record(state, task, DelegationDecision(False, "delegated_cost_exceeded", str(contract.get("contract_id") or "") or None, required, allowed, now.isoformat()))
        return self._record(state, task, DelegationDecision(True, "within_delegated_scope", str(contract.get("contract_id") or "") or None, required, allowed, now.isoformat()))

    def _record(self, state: ProjectState, task: Task, decision: DelegationDecision) -> DelegationDecision:
        task.metadata["delegation_decision_v2"] = decision.to_dict()
        root = state.metadata.setdefault(self.KEY, {"issued": 0, "events": []})
        root.setdefault("events", []).append({"event": "assessed", "task_id": task.id, **decision.to_dict()})
        del root["events"][:-1000]
        root["blocked"] = int(root.get("blocked", 0) or 0) + (0 if decision.allowed else 1)
        return decision
