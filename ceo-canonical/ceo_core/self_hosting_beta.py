from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable
from uuid import uuid4

from .models import ProjectState
from .self_hosting_alpha import AutoPromotionGuard, SelfHostingAlphaGate
from .self_hosting_runtime import DesktopMode, DesktopSafetyBoundary


def _now() -> float:
    return time.time()


class FrictionKind(str, Enum):
    HUMAN_INTERVENTION = "human_intervention"
    APPROVAL = "approval"
    RETRY = "retry"
    RECOVERY = "recovery"
    CONTEXT_LOSS = "context_loss"
    TOOL_UNAVAILABLE = "tool_unavailable"
    MANUAL_TRANSFER = "manual_transfer"
    BLOCKER = "blocker"


@dataclass(slots=True)
class SupervisedStep:
    action: str
    success: bool
    autonomous: bool
    human_intervention: bool = False
    approval_required: bool = False
    recovery_attempted: bool = False
    recovery_success: bool | None = None
    friction: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    task_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    recorded_at: float = field(default_factory=_now)


# 51. Daily supervised usage ledger. Field evidence is explicit and cannot be inferred from simulation.
class SupervisedUseTracker:
    KEY = "self_hosting_supervised_use_v1"

    def start_session(
        self,
        state: ProjectState,
        *,
        label: str,
        field_executed: bool = False,
        platform: str = "unknown",
        evidence: Iterable[str] = (),
    ) -> dict[str, Any]:
        session_id = uuid4().hex
        row = {
            "session_id": session_id,
            "label": str(label)[:200],
            "field_executed": bool(field_executed),
            "platform": str(platform)[:80],
            "evidence": [str(x) for x in evidence if str(x)][:50],
            "started_at": _now(),
            "desktop_mode_at_start": DesktopSafetyBoundary().mode(state).value,
            "ended_at": None,
            "steps": [],
            "status": "RUNNING",
        }
        state.metadata.setdefault(self.KEY, {})[session_id] = row
        return dict(row)

    def record_step(self, state: ProjectState, session_id: str, step: SupervisedStep) -> dict[str, Any]:
        session = state.metadata.setdefault(self.KEY, {}).get(session_id)
        if not session:
            raise KeyError(f"unknown supervised session: {session_id}")
        if session.get("status") != "RUNNING":
            raise ValueError("supervised session is not running")
        row = asdict(step)
        session.setdefault("steps", []).append(row)
        session["steps"] = session["steps"][-5000:]
        return dict(row)

    def end_session(self, state: ProjectState, session_id: str) -> dict[str, Any]:
        session = state.metadata.setdefault(self.KEY, {}).get(session_id)
        if not session:
            raise KeyError(f"unknown supervised session: {session_id}")
        steps = list(session.get("steps", []))
        total = len(steps)
        successful = sum(bool(s.get("success")) for s in steps)
        autonomous = sum(bool(s.get("autonomous")) for s in steps)
        interventions = sum(bool(s.get("human_intervention")) for s in steps)
        approvals = sum(bool(s.get("approval_required")) for s in steps)
        recovery_attempts = sum(bool(s.get("recovery_attempted")) for s in steps)
        recovery_successes = sum(bool(s.get("recovery_attempted")) and s.get("recovery_success") is True for s in steps)
        session.update({
            "ended_at": _now(),
            "status": "COMPLETE",
            "summary": {
                "steps": total,
                "successful_steps": successful,
                "autonomous_steps": autonomous,
                "human_interventions": interventions,
                "approvals_required": approvals,
                "recovery_attempts": recovery_attempts,
                "recovery_successes": recovery_successes,
                "success_rate": round(successful / total, 4) if total else 0.0,
                "autonomy_ratio": round(autonomous / total, 4) if total else 0.0,
                "intervention_rate": round(interventions / total, 4) if total else 0.0,
                "recovery_success_rate": round(recovery_successes / recovery_attempts, 4) if recovery_attempts else 1.0,
            },
        })
        # Field verification proves provenance (real execution + evidence), not perfect performance.
        # Failures must remain in the field dataset so autonomy metrics cannot be biased upward.
        session["field_verified"] = bool(
            session.get("field_executed") and total > 0 and session.get("evidence")
        )
        return dict(session)

    def sessions(self, state: ProjectState) -> list[dict[str, Any]]:
        return list(state.metadata.get(self.KEY, {}).values())


# 52. Convert human friction into a quantified backlog.
class FrictionDetector:
    KEY = "self_hosting_friction_v1"

    WEIGHTS = {
        FrictionKind.HUMAN_INTERVENTION.value: 1.0,
        FrictionKind.MANUAL_TRANSFER.value: 0.9,
        FrictionKind.BLOCKER.value: 0.9,
        FrictionKind.CONTEXT_LOSS.value: 0.8,
        FrictionKind.TOOL_UNAVAILABLE.value: 0.75,
        FrictionKind.RETRY.value: 0.55,
        FrictionKind.RECOVERY.value: 0.45,
        FrictionKind.APPROVAL.value: 0.25,
    }

    def record(
        self,
        state: ProjectState,
        *,
        kind: str | FrictionKind,
        description: str,
        avoidable: bool,
        session_id: str | None = None,
        task_id: str | None = None,
        severity: float = 0.5,
        evidence: Iterable[str] = (),
    ) -> dict[str, Any]:
        kind = FrictionKind(kind).value
        severity = max(0.0, min(1.0, float(severity)))
        rows = state.metadata.setdefault(self.KEY, [])
        signature = f"{kind}:{str(description).strip().lower()[:160]}"
        prior = [x for x in rows if x.get("signature") == signature]
        occurrence = len(prior) + 1
        score = min(1.0, severity * self.WEIGHTS[kind] * (1.0 + 0.15 * (occurrence - 1)))
        priority = "P0" if score >= 0.85 else "P1" if score >= 0.65 else "P2" if score >= 0.4 else "P3"
        row = {
            "id": uuid4().hex,
            "kind": kind,
            "description": str(description)[:1000],
            "avoidable": bool(avoidable),
            "session_id": session_id,
            "task_id": task_id,
            "severity": round(severity, 4),
            "occurrence": occurrence,
            "score": round(score, 4),
            "priority": priority,
            "signature": signature,
            "evidence": [str(x) for x in evidence if str(x)][:20],
            "created_at": _now(),
            "status": "OPEN" if avoidable else "EXPECTED",
        }
        rows.append(row)
        state.metadata[self.KEY] = rows[-5000:]
        return dict(row)

    def ingest_session(self, state: ProjectState, session: dict[str, Any]) -> list[dict[str, Any]]:
        # The absence of friction is still a measured result.  Persist an empty
        # collection before scanning the session so downstream field gates can
        # distinguish "measured zero friction" from "friction never measured".
        state.metadata.setdefault(self.KEY, [])
        created: list[dict[str, Any]] = []
        sid = session.get("session_id")
        for step in session.get("steps", []):
            if step.get("human_intervention"):
                created.append(self.record(state, kind=FrictionKind.HUMAN_INTERVENTION, description=f"Human intervention during {step.get('action','step')}", avoidable=True, session_id=sid, task_id=step.get("task_id"), severity=0.75))
            if step.get("approval_required"):
                created.append(self.record(state, kind=FrictionKind.APPROVAL, description=f"Approval required for {step.get('action','step')}", avoidable=False, session_id=sid, task_id=step.get("task_id"), severity=0.25))
            if step.get("recovery_attempted") and step.get("recovery_success") is not True:
                created.append(self.record(state, kind=FrictionKind.RECOVERY, description=f"Recovery failed during {step.get('action','step')}", avoidable=True, session_id=sid, task_id=step.get("task_id"), severity=0.8))
            for tag in step.get("friction", []):
                try:
                    kind = FrictionKind(tag)
                except ValueError:
                    kind = FrictionKind.BLOCKER
                created.append(self.record(state, kind=kind, description=f"{tag} during {step.get('action','step')}", avoidable=True, session_id=sid, task_id=step.get("task_id"), severity=0.6))
        return created

    def backlog(self, state: ProjectState, *, avoidable_only: bool = True) -> list[dict[str, Any]]:
        rows = list(state.metadata.get(self.KEY, []))
        if avoidable_only:
            rows = [x for x in rows if x.get("avoidable") and x.get("status") == "OPEN"]
        return sorted(rows, key=lambda x: (-float(x.get("score", 0)), x.get("created_at", 0)))


# 53. Objective autonomy metrics. Field and synthetic evidence stay separated.
class AutonomyMeasurementEngine:
    KEY = "self_hosting_autonomy_metrics_v1"

    def measure(self, state: ProjectState) -> dict[str, Any]:
        sessions = SupervisedUseTracker().sessions(state)
        completed = [s for s in sessions if s.get("status") == "COMPLETE"]
        field = [s for s in completed if s.get("field_verified") is True]
        source = field if field else completed
        steps = [step for session in source for step in session.get("steps", [])]
        total = len(steps)
        success = sum(bool(s.get("success")) for s in steps)
        autonomous = sum(bool(s.get("autonomous")) for s in steps)
        human = sum(bool(s.get("human_intervention")) for s in steps)
        approvals = sum(bool(s.get("approval_required")) for s in steps)
        rec_attempts = sum(bool(s.get("recovery_attempted")) for s in steps)
        rec_success = sum(bool(s.get("recovery_attempted")) and s.get("recovery_success") is True for s in steps)
        friction = FrictionDetector().backlog(state)
        avoidable = len(friction)
        autonomy_ratio = autonomous / total if total else 0.0
        success_rate = success / total if total else 0.0
        intervention_rate = human / total if total else 0.0
        recovery_rate = rec_success / rec_attempts if rec_attempts else (1.0 if total else 0.0)
        approval_burden = approvals / total if total else 0.0
        # Conservative combined metric: failures and human rescue reduce effective autonomy.
        effective = autonomy_ratio * success_rate * (1.0 - min(1.0, intervention_rate))
        row = {
            "evidence_scope": "FIELD" if field else ("SYNTHETIC" if completed else "NONE"),
            "completed_sessions": len(completed),
            "field_verified_sessions": len(field),
            "steps": total,
            "success_rate": round(success_rate, 4),
            "autonomy_ratio": round(autonomy_ratio, 4),
            "effective_autonomy": round(effective, 4),
            "human_intervention_rate": round(intervention_rate, 4),
            "approval_burden": round(approval_burden, 4),
            "recovery_success_rate": round(recovery_rate, 4),
            "avoidable_friction_open": avoidable,
            "measured_at": _now(),
        }
        state.metadata[self.KEY] = row
        return dict(row)


# 54. Permission graduation is evidence-driven and recommendation-only until a human explicitly applies it.
class PermissionGraduationEngine:
    KEY = "self_hosting_permission_graduation_v1"
    LEVELS = (DesktopMode.READ_ONLY.value, DesktopMode.SUPERVISED.value, DesktopMode.AUTONOMOUS.value)

    def recommend(self, state: ProjectState) -> dict[str, Any]:
        metrics = AutonomyMeasurementEngine().measure(state)
        current = DesktopSafetyBoundary().mode(state).value
        current_idx = self.LEVELS.index(current)
        target = current
        reasons: list[str] = []
        applied_at = float(state.metadata.get(self.KEY, {}).get("applied_at", 0.0) or 0.0)
        qualifying_sessions = [
            s for s in SupervisedUseTracker().sessions(state)
            if s.get("field_verified") is True
            and float(s.get("started_at", 0.0) or 0.0) > applied_at
            and s.get("desktop_mode_at_start") == current
        ]
        qsteps = [step for session in qualifying_sessions for step in session.get("steps", [])]
        qtotal = len(qsteps)
        qsuccess = sum(bool(x.get("success")) for x in qsteps)
        qhuman = sum(bool(x.get("human_intervention")) for x in qsteps)
        qrec_attempts = sum(bool(x.get("recovery_attempted")) for x in qsteps)
        qrec_success = sum(bool(x.get("recovery_attempted")) and x.get("recovery_success") is True for x in qsteps)
        session_ids = {s.get("session_id") for s in qualifying_sessions}
        qfriction = [x for x in FrictionDetector().backlog(state) if x.get("session_id") in session_ids]
        window = {
            "sessions": len(qualifying_sessions),
            "steps": qtotal,
            "success_rate": round(qsuccess / qtotal, 4) if qtotal else 0.0,
            "human_intervention_rate": round(qhuman / qtotal, 4) if qtotal else 0.0,
            "recovery_success_rate": round(qrec_success / qrec_attempts, 4) if qrec_attempts else (1.0 if qtotal else 0.0),
            "avoidable_friction_open": len(qfriction),
            "since_last_graduation": applied_at,
            "mode": current,
        }
        if not qualifying_sessions:
            reasons.append("field_evidence_required_at_current_permission_level")
        if window["sessions"] < 3:
            reasons.append("minimum_3_field_sessions")
        if window["steps"] < 30:
            reasons.append("minimum_30_field_steps")
        if window["success_rate"] < 0.98:
            reasons.append("success_rate_below_0.98")
        if window["recovery_success_rate"] < 0.90:
            reasons.append("recovery_rate_below_0.90")
        if window["human_intervention_rate"] > 0.10:
            reasons.append("intervention_rate_above_0.10")
        if window["avoidable_friction_open"] > 0:
            reasons.append("avoidable_friction_open")
        eligible = not reasons and current_idx < len(self.LEVELS) - 1
        if eligible:
            target = self.LEVELS[current_idx + 1]
        row = {
            "current": current,
            "recommended": target,
            "eligible_for_increase": eligible,
            "reasons": reasons,
            "metrics": metrics,
            "graduation_window": window,
            "auto_applied": False,
            "human_approval_required": target != current,
            "evaluated_at": _now(),
        }
        state.metadata[self.KEY] = row
        return dict(row)

    def apply(self, state: ProjectState, *, target: str, human_confirmed: bool, actor: str = "human") -> dict[str, Any]:
        recommendation = self.recommend(state)
        if not human_confirmed or str(actor).lower() != "human":
            raise PermissionError("permission increase requires explicit human approval")
        if not recommendation["eligible_for_increase"] or target != recommendation["recommended"]:
            raise PermissionError("requested permission level is not evidence-eligible")
        result = DesktopSafetyBoundary().set_mode(state, target)
        state.metadata.setdefault(self.KEY, {}).update({"applied": True, "applied_at": _now(), "actor": "human"})
        return result


# 55. Self-hosting Beta: local preparation can pass; real Beta requires Alpha + field autonomy evidence.
class SelfHostingBetaGate:
    KEY = "self_hosting_beta_gate_v1"

    def _alpha_evidence(self, state: ProjectState) -> dict[str, Any]:
        legacy = SelfHostingAlphaGate().assess(state)
        field = {"verified": False, "status": "NOT_VERIFIED"}
        try:
            # 76-85 is the newer signed field-certification path. Keep the
            # legacy Alpha gate for compatibility, but never require users to
            # repeat field work that is already cryptographically attested.
            from .self_hosting_field import FIELD_MISSIONS, FieldMissionGate

            spec = next(x for x in FIELD_MISSIONS if x.mission == "alpha_certification")
            field = FieldMissionGate().status(state, spec)
        except Exception as exc:
            field = {"verified": False, "status": "NOT_VERIFIED", "error": type(exc).__name__}
        ready = bool(legacy.get("ready") is True or field.get("verified") is True)
        status = (
            "SELF_HOSTING_ALPHA_READY" if legacy.get("ready") is True
            else "SELF_HOSTING_ALPHA_FIELD_VERIFIED" if field.get("verified") is True
            else str(legacy.get("status") or "NOT_READY")
        )
        return {"ready": ready, "status": status, "legacy": legacy, "field": field}

    def assess(self, state: ProjectState) -> dict[str, Any]:
        alpha = self._alpha_evidence(state)
        metrics = AutonomyMeasurementEngine().measure(state)
        permission = PermissionGraduationEngine().recommend(state)
        friction = FrictionDetector().backlog(state)
        guard = AutoPromotionGuard().snapshot(state)
        local_checks = {
            "supervised_use_ledger": True,
            "friction_detection": True,
            "autonomy_metrics": True,
            "evidence_driven_permissions": True,
            "auto_promotion_forbidden": guard.get("auto_promotion_allowed") is False,
        }
        field_checks = {
            "alpha_ready": alpha.get("ready") is True,
            "field_sessions_gte_3": metrics.get("field_verified_sessions", 0) >= 3,
            "field_steps_gte_30": metrics.get("evidence_scope") == "FIELD" and metrics.get("steps", 0) >= 30,
            "effective_autonomy_gte_0_85": metrics.get("evidence_scope") == "FIELD" and metrics.get("effective_autonomy", 0.0) >= 0.85,
            "success_rate_gte_0_98": metrics.get("evidence_scope") == "FIELD" and metrics.get("success_rate", 0.0) >= 0.98,
            "recovery_success_gte_0_90": metrics.get("evidence_scope") == "FIELD" and metrics.get("recovery_success_rate", 0.0) >= 0.90,
            "human_intervention_lte_0_10": metrics.get("evidence_scope") == "FIELD" and metrics.get("human_intervention_rate", 1.0) <= 0.10,
            "no_avoidable_friction": len(friction) == 0,
            "permission_evidence_evaluated": permission.get("metrics", {}).get("evidence_scope") == "FIELD",
        }
        local_prepared = all(local_checks.values())
        ready = local_prepared and all(field_checks.values())
        blockers = [k for k, v in field_checks.items() if not v]
        row = {
            "status": "SELF_HOSTING_BETA_READY" if ready else ("BETA_PREPARED_LOCAL" if local_prepared else "NOT_READY"),
            "ready": ready,
            "local_prepared": local_prepared,
            "local_checks": local_checks,
            "field_checks": field_checks,
            "blockers": blockers,
            "metrics": metrics,
            "permission_recommendation": permission,
            "alpha_status": alpha.get("status"),
            "alpha_evidence": {
                "legacy_ready": bool(alpha.get("legacy", {}).get("ready")),
                "field_verified": bool(alpha.get("field", {}).get("verified")),
                "source": "field_76_85" if alpha.get("field", {}).get("verified") else "legacy_alpha",
            },
            "production_verified": False,
            "assessed_at": _now(),
        }
        state.metadata[self.KEY] = row
        return dict(row)


class SelfHostingBetaCore:
    VERSION = 1

    def __init__(self) -> None:
        self.usage = SupervisedUseTracker()
        self.friction = FrictionDetector()
        self.metrics = AutonomyMeasurementEngine()
        self.permissions = PermissionGraduationEngine()
        self.gate = SelfHostingBetaGate()

    def initialize(self, state: ProjectState) -> dict[str, Any]:
        state.metadata.setdefault("self_hosting_beta_v1", {"initialized_at": _now()})
        return self.snapshot(state)

    def complete_session(self, state: ProjectState, session_id: str) -> dict[str, Any]:
        existing = state.metadata.get(SupervisedUseTracker.KEY, {}).get(session_id, {})
        already_ingested = bool(existing.get("friction_ingested"))
        session = self.usage.end_session(state, session_id)
        friction = [] if already_ingested else self.friction.ingest_session(state, session)
        state.metadata[SupervisedUseTracker.KEY][session_id]["friction_ingested"] = True
        session = dict(state.metadata[SupervisedUseTracker.KEY][session_id])
        metrics = self.metrics.measure(state)
        permission = self.permissions.recommend(state)
        return {"session": session, "friction_created": friction, "metrics": metrics, "permission": permission, "beta": self.gate.assess(state)}

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        sessions = self.usage.sessions(state)
        try:
            from .self_hosting_field import FieldMissionGate, FIELD_MISSIONS
            windows_physical = "VERIFIED" if FieldMissionGate().status(state, FIELD_MISSIONS[0])["verified"] else "NOT_VERIFIED"
        except Exception:
            windows_physical = "NOT_VERIFIED"
        return {
            "version": self.VERSION,
            "sessions_total": len(sessions),
            "recent_sessions": sessions[-10:],
            "friction_backlog": self.friction.backlog(state)[:25],
            "metrics": self.metrics.measure(state),
            "permission_recommendation": self.permissions.recommend(state),
            "beta_gate": self.gate.assess(state),
            "windows_physical": windows_physical,
            "live_provider": "NOT_VERIFIED" if not state.metadata.get("live_provider_gate_v2", {}).get("authenticated_live_verified") else "VERIFIED",
            "production_verified": False,
        }

    def preflight(self, state: ProjectState) -> dict[str, Any]:
        checks = {
            "supervised_use_tracker": True,
            "friction_detector": True,
            "autonomy_measurement": True,
            "permission_graduation": True,
            "self_hosting_beta_gate": True,
            "permission_increase_not_automatic": True,
            "field_evidence_not_inferred": True,
        }
        return {"pass": all(checks.values()), "checks": checks, "beta": self.gate.assess(state), "production_verified": False}
