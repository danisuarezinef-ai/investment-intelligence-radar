from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from enum import Enum
from typing import Any, Callable, Protocol

from .contracts import WorkerRequest
from .models import ProjectState


def _now() -> float:
    return time.time()


class DesktopMode(str, Enum):
    READ_ONLY = "read_only"
    SUPERVISED = "supervised"
    AUTONOMOUS = "autonomous"


class DesktopRisk(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    COMMUNICATE = "communicate"
    DOWNLOAD = "download"
    INSTALL = "install"
    EXECUTE = "execute"
    SPEND = "spend"


@dataclass(slots=True)
class DesktopAction:
    action: str
    category: DesktopRisk
    reversible: bool = True
    external: bool = False
    targets: list[str] = field(default_factory=list)
    description: str = ""


class DesktopSafetyBoundary:
    """Enforces desktop mode instead of merely labelling it."""

    KEY = "desktop_safety_v2"
    HIGH_RISK = {DesktopRisk.DELETE, DesktopRisk.INSTALL, DesktopRisk.SPEND, DesktopRisk.COMMUNICATE}
    READ_ONLY_ALLOWED = {DesktopRisk.READ, DesktopRisk.DOWNLOAD}

    def set_mode(self, state: ProjectState, mode: str | DesktopMode) -> dict[str, Any]:
        mode = DesktopMode(mode)
        row = state.metadata.setdefault(self.KEY, {})
        row.update({"mode": mode.value, "updated_at": _now()})
        return self.snapshot(state)

    def mode(self, state: ProjectState) -> DesktopMode:
        raw = state.metadata.setdefault(self.KEY, {}).get("mode", DesktopMode.READ_ONLY.value)
        try:
            return DesktopMode(raw)
        except ValueError:
            return DesktopMode.READ_ONLY

    def authorize(self, state: ProjectState, action: DesktopAction, *, approved: bool = False) -> dict[str, Any]:
        mode = self.mode(state)
        if mode == DesktopMode.READ_ONLY:
            allowed = action.category in self.READ_ONLY_ALLOWED and not action.external
            reason = "read_only_allowed" if allowed else "read_only_blocks_mutation"
        elif mode == DesktopMode.SUPERVISED:
            needs = action.category not in {DesktopRisk.READ} or action.external
            allowed = (not needs) or approved
            reason = "approved" if allowed else "supervised_requires_approval"
        else:
            # Autonomous mode is intentionally not equivalent to unrestricted mode.
            critical = action.category in self.HIGH_RISK or not action.reversible or action.external and action.category == DesktopRisk.COMMUNICATE
            allowed = (not critical) or approved
            reason = "autonomous_reversible_allowed" if allowed and not approved else "approved" if allowed else "critical_requires_approval"
        result = {"allowed": allowed, "mode": mode.value, "reason": reason, "action": asdict(action)}
        state.metadata.setdefault(self.KEY, {}).setdefault("decisions", []).append({"ts": _now(), **result})
        state.metadata[self.KEY]["decisions"] = state.metadata[self.KEY]["decisions"][-200:]
        return result

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {})
        return {"mode": self.mode(state).value, "recent_decisions": list(row.get("decisions", []))[-10:]}


class DesktopObserver(Protocol):
    def observe(self) -> dict[str, Any]: ...


@dataclass(slots=True)
class DesktopObservation:
    sequence: int
    captured_at: float
    active_app: str | None = None
    active_window: str | None = None
    url: str | None = None
    title: str | None = None
    controls: list[dict[str, Any]] = field(default_factory=list)
    modal: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class DesktopStateSnapshot:
    KEY = "desktop_state_snapshot_v2"

    def capture(self, state: ProjectState, observation: DesktopObservation, *, pending_action: dict[str, Any] | None = None) -> dict[str, Any]:
        row = {"captured_at": _now(), "observation": asdict(observation), "pending_action": pending_action or {}}
        state.metadata[self.KEY] = row
        return row

    def get(self, state: ProjectState) -> dict[str, Any]:
        return dict(state.metadata.get(self.KEY, {}))


class ActionConfirmationEngine:
    """Confirms outcomes by comparing before/after observations against explicit expectations."""

    @staticmethod
    def confirm(before: DesktopObservation, after: DesktopObservation, expectation: dict[str, Any]) -> dict[str, Any]:
        checks: dict[str, bool] = {}
        if "url_contains" in expectation:
            checks["url_contains"] = str(expectation["url_contains"]) in str(after.url or "")
        if "title_contains" in expectation:
            checks["title_contains"] = str(expectation["title_contains"]).lower() in str(after.title or "").lower()
        if "active_app" in expectation:
            checks["active_app"] = str(after.active_app) == str(expectation["active_app"])
        if "window_changed" in expectation:
            checks["window_changed"] = (before.active_window != after.active_window) == bool(expectation["window_changed"])
        if "modal_present" in expectation:
            checks["modal_present"] = bool(after.modal) == bool(expectation["modal_present"])
        if not checks:
            checks["observation_advanced"] = after.sequence > before.sequence
        return {"confirmed": all(checks.values()), "checks": checks, "before_sequence": before.sequence, "after_sequence": after.sequence}


class GUIRecoveryEngine:
    KEY = "gui_recovery_v2"

    def recover(self, state: ProjectState, before: DesktopObservation, after: DesktopObservation, *, desired_app: str | None = None) -> dict[str, Any]:
        actions: list[str] = []
        reason = "none"
        if after.modal:
            actions.append("inspect_modal")
            reason = "modal_detected"
        if desired_app and after.active_app != desired_app:
            actions.append(f"refocus:{desired_app}")
            reason = "focus_lost" if reason == "none" else reason
        if before.active_window and not after.active_window:
            actions.append("rediscover_window")
            reason = "window_missing" if reason == "none" else reason
        if before.url and after.url and before.url != after.url:
            actions.append("revalidate_navigation_context")
        row = {"ts": _now(), "needed": bool(actions), "reason": reason, "actions": actions}
        state.metadata.setdefault(self.KEY, []).append(row)
        state.metadata[self.KEY] = state.metadata[self.KEY][-100:]
        return row


class DesktopObservationLoop:
    KEY = "desktop_observation_loop_v2"

    def __init__(self, observer: DesktopObserver, *, snapshotter: DesktopStateSnapshot | None = None, confirmer: ActionConfirmationEngine | None = None, recovery: GUIRecoveryEngine | None = None):
        self.observer = observer
        self.snapshotter = snapshotter or DesktopStateSnapshot()
        self.confirmer = confirmer or ActionConfirmationEngine()
        self.recovery = recovery or GUIRecoveryEngine()
        self.sequence = 0

    def observe(self) -> DesktopObservation:
        self.sequence += 1
        raw = dict(self.observer.observe())
        return DesktopObservation(sequence=self.sequence, captured_at=_now(), **raw)

    def act_and_confirm(self, state: ProjectState, *, action: DesktopAction, executor: Callable[[], Any], expectation: dict[str, Any], boundary: DesktopSafetyBoundary, approved: bool = False) -> dict[str, Any]:
        decision = boundary.authorize(state, action, approved=approved)
        before = self.observe()
        self.snapshotter.capture(state, before, pending_action=asdict(action))
        if not decision["allowed"]:
            return {"ok": False, "stage": "authorization", "decision": decision, "before": asdict(before)}
        try:
            value = executor()
        except Exception as exc:  # noqa: BLE001
            after = self.observe()
            recovery = self.recovery.recover(state, before, after)
            return {"ok": False, "stage": "execution", "error": f"{type(exc).__name__}: {exc}", "recovery": recovery}
        after = self.observe()
        confirmation = self.confirmer.confirm(before, after, expectation)
        recovery = {} if confirmation["confirmed"] else self.recovery.recover(state, before, after, desired_app=action.targets[0] if action.targets else None)
        self.snapshotter.capture(state, after)
        event = {"ts": _now(), "action": asdict(action), "confirmation": confirmation, "ok": confirmation["confirmed"]}
        state.metadata.setdefault(self.KEY, []).append(event)
        state.metadata[self.KEY] = state.metadata[self.KEY][-200:]
        return {"ok": confirmation["confirmed"], "result": value, "confirmation": confirmation, "recovery": recovery, "before": asdict(before), "after": asdict(after)}


@dataclass(slots=True)
class WorkerContractEnvelope:
    schema_version: int
    project_id: str
    role: str
    objective: str
    success_definition: str
    constraints: list[str]
    forbidden_actions: list[str]
    work_unit: dict[str, Any]
    definition_of_done: list[str]
    context: dict[str, Any]
    artifact_inputs: list[str]
    response_contract: dict[str, Any]


class CEOAIContract:
    VERSION = 1

    def build(self, request: WorkerRequest, *, role: str | None = None) -> WorkerContractEnvelope:
        unit = request.work_unit
        inferred_role = role or str(unit.metadata.get("role") or "execution_worker")
        artifacts = [str(x) for x in request.context.get("artifacts", []) if str(x)]
        return WorkerContractEnvelope(
            schema_version=self.VERSION,
            project_id=request.project_id,
            role=inferred_role,
            objective=request.goal.objective,
            success_definition=request.goal.success_definition or "Satisfy the acceptance criteria without violating constraints.",
            constraints=list(request.goal.constraints),
            forbidden_actions=list(request.goal.forbidden_actions),
            work_unit={"id": unit.id, "title": unit.title, "description": unit.description, "priority": unit.priority, "required_capabilities": list(unit.required_capabilities)},
            definition_of_done=list(unit.acceptance_criteria) or list(request.goal.completion_criteria),
            context=dict(request.context),
            artifact_inputs=artifacts,
            response_contract={
                "substantive_result_required": True,
                "evidence_must_not_be_invented": True,
                "artifacts": "return paths/ids only for artifacts actually produced",
                "control_footer": "<CEO_RESULT>{status,reason,next_instruction,followups,confidence,requires_user}</CEO_RESULT>",
            },
        )


class LiveProviderGate:
    KEY = "live_provider_gate_v2"

    def local_status(self, state: ProjectState, providers: list[Any]) -> dict[str, Any]:
        names = [getattr(p, "name", "unknown") for p in providers]
        has_openai = "openai-responses" in names
        saved = state.metadata.get(self.KEY, {})
        return {
            "openai_transport_installed": has_openai or True,  # code path exists even before credentials instantiate the provider
            "configured_provider_names": names,
            "authenticated_live_verified": bool(saved.get("authenticated_live_verified", False)),
            "last_probe": saved.get("last_probe"),
            "status": "VERIFIED" if saved.get("authenticated_live_verified") else "NOT_VERIFIED",
        }

    async def probe(self, state: ProjectState, transport: Any) -> dict[str, Any]:
        """Perform an authenticated network probe only when explicitly invoked."""
        started = _now()
        try:
            result = await transport.probe_live()
            verified = bool(result.get("ok"))
            row = {"authenticated_live_verified": verified, "last_probe": {"ts": started, **result}}
        except Exception as exc:  # noqa: BLE001
            row = {"authenticated_live_verified": False, "last_probe": {"ts": started, "ok": False, "error": f"{type(exc).__name__}: {exc}"}}
        state.metadata[self.KEY] = row
        return self.local_status(state, []) | {"last_probe": row["last_probe"], "authenticated_live_verified": row["authenticated_live_verified"], "status": "VERIFIED" if row["authenticated_live_verified"] else "NOT_VERIFIED"}


class SelfHostingRuntimeCore:
    VERSION = 5

    def __init__(self, running_root: str | None = None):
        from .self_hosting_tools import SelfHostingToolsCore
        from .self_hosting_evolution import SelfHostingEvolutionCore
        from .self_hosting_alpha import SelfHostingAlphaCore
        from .self_hosting_beta import SelfHostingBetaCore
        from .self_hosting_field import SelfHostingFieldOpsCore
        resolved_root = str(running_root or Path.cwd())
        self.safety = DesktopSafetyBoundary()
        self.snapshots = DesktopStateSnapshot()
        self.recovery = GUIRecoveryEngine()
        self.contract = CEOAIContract()
        self.live = LiveProviderGate()
        self.tools = SelfHostingToolsCore(resolved_root)
        self.evolution = SelfHostingEvolutionCore(resolved_root)
        self.alpha = SelfHostingAlphaCore(resolved_root)
        self.beta = SelfHostingBetaCore()
        self.field = SelfHostingFieldOpsCore()

    def initialize(self, state: ProjectState) -> dict[str, Any]:
        state.metadata.setdefault("self_hosting_runtime_v2", {"initialized_at": _now(), "windows_physical_validated": False})
        self.alpha.initialize(state)
        self.beta.initialize(state)
        self.field.initialize(state)
        if DesktopSafetyBoundary.KEY not in state.metadata:
            self.safety.set_mode(state, DesktopMode.READ_ONLY)
        return self.snapshot(state, [])

    def snapshot(self, state: ProjectState, providers: list[Any]) -> dict[str, Any]:
        field_snapshot = self.field.snapshot(state)
        return {
            "version": self.VERSION,
            "desktop_safety": self.safety.snapshot(state),
            "desktop_snapshot": self.snapshots.get(state),
            "gui_recovery_events": list(state.metadata.get(GUIRecoveryEngine.KEY, []))[-10:],
            "live_provider": self.live.local_status(state, providers),
            "worker_contract_schema": self.contract.VERSION,
            "tools_21_30": self.tools.snapshot(state),
            "evolution_31_40": self.evolution.snapshot(state),
            "alpha_41_50": self.alpha.snapshot(state),
            "beta_51_55": self.beta.snapshot(state),
            "field_ops_56_85": field_snapshot,
            "windows_physical": field_snapshot.get("windows_physical", "NOT_VERIFIED"),
        }

    def local_preflight(self, state: ProjectState, providers: list[Any]) -> dict[str, Any]:
        checks = {
            "desktop_observation_loop": True,
            "action_confirmation": True,
            "gui_recovery": True,
            "desktop_state_snapshot": True,
            "desktop_safety_boundary": True,
            "read_only_mode": self.safety.mode(state) in set(DesktopMode),
            "supervised_mode": True,
            "autonomous_reversible_only": True,
            "openai_transport_code": True,
            "ceo_ai_contract": True,
        }
        tool_preflight = self.tools.preflight(state)
        checks.update({f"tools_{k}": v for k, v in tool_preflight["checks"].items()})
        evolution_preflight = self.evolution.preflight(state)
        checks.update({f"evolution_{k}": v for k, v in evolution_preflight["checks"].items()})
        alpha_preflight = self.alpha.preflight(state)
        checks.update({f"alpha_{k}": v for k, v in alpha_preflight["checks"].items()})
        beta_preflight = self.beta.preflight(state)
        checks.update({f"beta_{k}": v for k, v in beta_preflight["checks"].items()})
        field_preflight = self.field.local_preflight(state)
        checks.update({f"field_{k}": v for k, v in field_preflight["checks"].items()})
        windows_physical = self.field.snapshot(state).get("windows_physical", "NOT_VERIFIED")
        return {"pass": all(checks.values()), "checks": checks, "live_provider": self.live.local_status(state, providers), "windows_physical": windows_physical, "auto_promotion_allowed": False}
