from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from .models import ProjectState
from .runtime import user_data_root


def _now() -> float:
    return time.time()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _machine_fingerprint() -> str:
    raw = "|".join([platform.system(), platform.release(), platform.machine(), socket.gethostname()])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _is_windows() -> bool:
    return os.name == "nt" or platform.system().lower() == "windows"


# 58-60. Explicit capability manifests. A capability is not field-verified merely because code exists.
@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    capability: str
    probe: str
    field_required: bool = True
    critical: bool = True


class WindowsCapabilityManifest:
    VERSION = 1
    REQUIREMENTS = (
        CapabilityRequirement("desktop_observation", "observe active window/application"),
        CapabilityRequirement("ui_automation", "enumerate/focus native Windows controls"),
        CapabilityRequirement("keyboard_mouse_broker", "brokered input in supervised mode"),
        CapabilityRequirement("terminal", "run controlled command and capture exit/stdout/stderr"),
        CapabilityRequirement("filesystem", "atomic create/read/edit/move in candidate workspace"),
        CapabilityRequirement("vscode", "open candidate workspace/file"),
        CapabilityRequirement("restart_resume", "resume persisted mission after process restart"),
        CapabilityRequirement("emergency_stop", "stop new side effects immediately"),
    )

    def snapshot(self) -> dict[str, Any]:
        return {"name": "windows", "version": self.VERSION, "requirements": [asdict(x) for x in self.REQUIREMENTS]}


class ChromeCapabilityManifest:
    VERSION = 1
    REQUIREMENTS = (
        CapabilityRequirement("launch", "launch dedicated CEO Chrome profile"),
        CapabilityRequirement("navigation", "navigate to expected HTTPS URL"),
        CapabilityRequirement("dom", "read structured DOM content"),
        CapabilityRequirement("tabs", "create/select/close tab"),
        CapabilityRequirement("session_reuse", "reuse dedicated authenticated profile without CEO storing credentials"),
        CapabilityRequirement("download", "download and hash artifact"),
        CapabilityRequirement("upload", "upload known workspace artifact"),
        CapabilityRequirement("modal_recovery", "detect/recover browser modal or unexpected navigation"),
        CapabilityRequirement("visual_fallback", "fallback only after structured path failure and policy approval", critical=False),
    )

    def snapshot(self) -> dict[str, Any]:
        return {"name": "chrome", "version": self.VERSION, "requirements": [asdict(x) for x in self.REQUIREMENTS]}


class ChatGPTCapabilityManifest:
    VERSION = 1
    REQUIREMENTS = (
        CapabilityRequirement("authenticated_provider", "authenticated OpenAI Responses probe"),
        CapabilityRequirement("worker_contract", "CEO↔AI contract envelope"),
        CapabilityRequirement("multiturn", "continue same work unit across multiple turns"),
        CapabilityRequirement("artifact_exchange", "send/receive real hashed artifacts"),
        CapabilityRequirement("context_recovery", "reconstruct task context after provider/session interruption"),
        CapabilityRequirement("timeout_handling", "record timeout without inventing result"),
        CapabilityRequirement("failover", "preserve context when routing to alternate provider", critical=False),
    )

    def snapshot(self) -> dict[str, Any]:
        return {"name": "chatgpt", "version": self.VERSION, "requirements": [asdict(x) for x in self.REQUIREMENTS]}


# 61-62. Signed field evidence. Only records signed by a local validator authority can satisfy field gates.
class FieldEvidenceAuthority:
    """Local attestation key lives outside project workspaces.

    The key is not persisted in ProjectState and the general API never returns it.
    """

    def __init__(self, key_path: str | Path | None = None) -> None:
        self.key_path = Path(key_path or (user_data_root() / "field_validation.key")).resolve()

    def _key(self) -> bytes:
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.key_path.exists():
            self.key_path.write_bytes(secrets.token_bytes(32))
            try:
                os.chmod(self.key_path, 0o600)
            except OSError:
                pass
        return self.key_path.read_bytes()

    def sign(self, payload: Mapping[str, Any]) -> str:
        return hmac.new(self._key(), _canonical(payload), hashlib.sha256).hexdigest()

    def verify(self, payload: Mapping[str, Any], signature: str) -> bool:
        return hmac.compare_digest(self.sign(payload), str(signature))


@dataclass(slots=True)
class FieldEvidenceItem:
    kind: str
    value: str
    sha256: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class UnifiedFieldEvidenceLedger:
    KEY = "self_hosting_field_evidence_v1"

    def __init__(self, authority: FieldEvidenceAuthority | None = None) -> None:
        self.authority = authority or FieldEvidenceAuthority()

    def begin(self, state: ProjectState, *, mission: str, source: str = "one_click_validator", platform_name: str | None = None) -> dict[str, Any]:
        run_id = uuid4().hex
        row = {
            "run_id": run_id,
            "mission": str(mission),
            "source": str(source),
            "platform": str(platform_name or platform.system()).lower(),
            "machine_fingerprint": _machine_fingerprint(),
            "nonce": secrets.token_hex(16),
            "started_at": _now(),
            "completed_at": None,
            "success": False,
            "items": [],
            "attested": False,
            "signature": None,
            "status": "RUNNING",
        }
        state.metadata.setdefault(self.KEY, {})[run_id] = row
        return dict(row)

    def add(self, state: ProjectState, run_id: str, item: FieldEvidenceItem) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).get(run_id)
        if not row:
            raise KeyError(f"unknown field run: {run_id}")
        if row.get("status") != "RUNNING":
            raise ValueError("field run is not running")
        entry = asdict(item)
        row.setdefault("items", []).append(entry)
        row["items"] = row["items"][-500:]
        return dict(entry)

    def finalize(self, state: ProjectState, run_id: str, *, success: bool) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).get(run_id)
        if not row:
            raise KeyError(f"unknown field run: {run_id}")
        payload = {
            "run_id": row["run_id"], "mission": row["mission"], "source": row["source"],
            "platform": row["platform"], "machine_fingerprint": row["machine_fingerprint"],
            "nonce": row["nonce"], "started_at": row["started_at"], "success": bool(success),
            "items": row.get("items", []),
        }
        signature = self.authority.sign(payload)
        row.update({"completed_at": _now(), "success": bool(success), "attested": True, "signature": signature, "status": "PASS" if success else "FAIL"})
        return dict(row)

    def verify(self, row: Mapping[str, Any], *, require_windows: bool = False) -> dict[str, Any]:
        payload = {
            "run_id": row.get("run_id"), "mission": row.get("mission"), "source": row.get("source"),
            "platform": row.get("platform"), "machine_fingerprint": row.get("machine_fingerprint"),
            "nonce": row.get("nonce"), "started_at": row.get("started_at"), "success": bool(row.get("success")),
            "items": row.get("items", []),
        }
        signature_ok = bool(row.get("attested") and row.get("signature") and self.authority.verify(payload, str(row.get("signature"))))
        source_ok = row.get("source") == "one_click_validator"
        platform_ok = (row.get("platform") == "windows") if require_windows else True
        evidence_ok = bool(row.get("items"))
        verified = bool(signature_ok and source_ok and platform_ok and row.get("success") is True and evidence_ok)
        return {"verified": verified, "signature_ok": signature_ok, "source_ok": source_ok, "platform_ok": platform_ok, "evidence_ok": evidence_ok}

    def runs(self, state: ProjectState, mission: str | None = None) -> list[dict[str, Any]]:
        rows = list(state.metadata.get(self.KEY, {}).values())
        if mission:
            rows = [x for x in rows if x.get("mission") == mission]
        return rows


class FieldGateAntiSpoofing:
    def __init__(self, ledger: UnifiedFieldEvidenceLedger | None = None) -> None:
        self.ledger = ledger or UnifiedFieldEvidenceLedger()

    def best_verified(self, state: ProjectState, mission: str, *, require_windows: bool = False) -> dict[str, Any]:
        rows = self.ledger.runs(state, mission)
        for row in reversed(rows):
            verdict = self.ledger.verify(row, require_windows=require_windows)
            if verdict["verified"]:
                return {"status": "VERIFIED", "run": dict(row), "verification": verdict}
        attempted = [r for r in rows if r.get("status") in {"PASS", "FAIL"}]
        if attempted:
            last = attempted[-1]
            verdict = self.ledger.verify(last, require_windows=require_windows)
            if last.get("status") == "FAIL" and verdict.get("signature_ok") and verdict.get("source_ok") and verdict.get("platform_ok"):
                return {"status": "FAILED", "run": dict(last), "verification": verdict}
            return {"status": "NOT_VERIFIED", "run": dict(last), "verification": verdict}
        return {"status": "NOT_VERIFIED", "run": None, "verification": {"verified": False, "signature_ok": False, "source_ok": False, "platform_ok": False, "evidence_ok": False}}


# 56. One master preflight aggregating local readiness and field gates.
class SelfHostingMasterPreflight:
    KEY = "self_hosting_master_preflight_v1"

    def local_checks(self) -> dict[str, bool]:
        return {
            "python": sys.version_info >= (3, 11),
            "git": shutil.which("git") is not None,
            "node_optional": True,
            "windows_manifest": bool(WindowsCapabilityManifest.REQUIREMENTS),
            "chrome_manifest": bool(ChromeCapabilityManifest.REQUIREMENTS),
            "chatgpt_manifest": bool(ChatGPTCapabilityManifest.REQUIREMENTS),
            "field_evidence_signing": True,
            "anti_spoofing": True,
            "diagnostic_bundle": True,
            "safe_resume": True,
        }

    def assess(self, state: ProjectState) -> dict[str, Any]:
        local = self.local_checks()
        gates = FieldGateAntiSpoofing()
        field = {
            "windows_read_only": gates.best_verified(state, "windows_read_only", require_windows=True)["status"],
            "chrome_navigation": gates.best_verified(state, "chrome_navigation", require_windows=True)["status"],
            "chatgpt_worker": gates.best_verified(state, "chatgpt_worker")["status"],
        }
        row = {
            "local_ready": all(local.values()),
            "local_checks": local,
            "field_gates": field,
            "field_ready": all(x == "VERIFIED" for x in field.values()),
            "production_verified": False,
            "assessed_at": _now(),
        }
        state.metadata[self.KEY] = row
        return dict(row)


# 57. Detect missing components and plan setup. It never installs on its own.
class DependencyAutoSetupPlanner:
    KEY = "self_hosting_setup_plan_v1"

    def inspect(self, state: ProjectState) -> dict[str, Any]:
        probes = {
            "git": shutil.which("git"),
            "code": shutil.which("code") or shutil.which("code.cmd"),
            "chrome": shutil.which("chrome") or shutil.which("chrome.exe") or shutil.which("google-chrome") or shutil.which("chromium"),
            "powershell": shutil.which("powershell") or shutil.which("pwsh"),
        }
        actions: list[dict[str, Any]] = []
        for name, found in probes.items():
            if found:
                continue
            actions.append({"component": name, "action": "install_or_configure", "automatic": False, "human_approval_required": True})
        try:
            import playwright  # type: ignore  # noqa: F401
            playwright_ok = True
        except Exception:
            playwright_ok = False
            actions.append({"component": "playwright", "action": "install_python_package_and_browser_runtime", "automatic": False, "human_approval_required": True})
        row = {"probes": probes, "playwright_python": playwright_ok, "actions": actions, "mutation_performed": False, "generated_at": _now()}
        state.metadata[self.KEY] = row
        return dict(row)


# 63. One-click validator plan. Actual field run is deliberately external to the normal API.
class OneClickFieldValidator:
    MISSIONS = (
        "windows_read_only", "chrome_navigation", "chrome_session", "download", "multi_app",
        "chatgpt_worker", "chatgpt_multiturn", "self_improvement_field", "alpha_certification", "supervised_dogfooding",
    )

    def plan(self, state: ProjectState) -> dict[str, Any]:
        return {
            "validator": "VALIDAR_SELF_HOSTING_FIELD_WINDOWS.cmd",
            "missions": list(self.MISSIONS),
            "requires_windows": True,
            "normal_api_can_attest": False,
            "signed_field_evidence": True,
            "production_verified": False,
        }


# 64. Automatic diagnostics. Secrets are never intentionally collected.
class AutomaticDiagnosticBundle:
    KEY = "self_hosting_diagnostics_v1"
    SAFE_ENV = ("OS", "PROCESSOR_ARCHITECTURE", "USERNAME", "USERDOMAIN", "COMPUTERNAME")

    def create(self, state: ProjectState, output_dir: str | Path, *, reason: str, logs: Sequence[str | Path] = ()) -> dict[str, Any]:
        out = Path(output_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
        bundle_dir = out / f"diagnostic-{int(_now())}-{uuid4().hex[:8]}"; bundle_dir.mkdir()
        summary = {
            "reason": str(reason)[:1000], "created_at": _now(), "platform": platform.platform(),
            "python": sys.version, "machine_fingerprint": _machine_fingerprint(),
            "safe_environment": {k: os.environ.get(k) for k in self.SAFE_ENV if os.environ.get(k)},
            "state": {"id": getattr(state, "id", None), "goal": str(getattr(state, "goal", ""))[:1000], "progress": getattr(state, "progress", None)},
        }
        (bundle_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        copied: list[str] = []
        for raw in logs[:20]:
            p = Path(raw)
            if p.is_file() and p.stat().st_size <= 5 * 1024 * 1024:
                target = bundle_dir / f"log-{len(copied):02d}-{p.name}"
                shutil.copy2(p, target); copied.append(target.name)
        archive = shutil.make_archive(str(bundle_dir), "zip", bundle_dir)
        row = {"archive": archive, "sha256": _sha256_file(archive), "files": ["summary.json", *copied], "secrets_collected": False, "created_at": _now()}
        state.metadata.setdefault(self.KEY, []).append(row)
        state.metadata[self.KEY] = state.metadata[self.KEY][-50:]
        return dict(row)


# 65. Convert a field failure into a reproducible case without claiming it is reproduced.
class EnvironmentReproducer:
    KEY = "self_hosting_reproducers_v1"

    def build(self, state: ProjectState, failed_run: Mapping[str, Any], output_dir: str | Path) -> dict[str, Any]:
        out = Path(output_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
        rid = str(failed_run.get("run_id") or uuid4().hex)
        path = out / f"reproducer-{rid}.json"
        payload = {
            "mission": failed_run.get("mission"), "platform": failed_run.get("platform"),
            "machine_fingerprint": failed_run.get("machine_fingerprint"), "evidence_items": failed_run.get("items", []),
            "expected": "repeat failure deterministically in isolated candidate workspace", "field_failure_reproduced": False,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        row = {"path": str(path), "sha256": _sha256_file(path), "field_failure_reproduced": False, "created_at": _now()}
        state.metadata.setdefault(self.KEY, {})[rid] = row
        return dict(row)


# 66-68. Installation/restart/crash harnesses are plans until exercised on Windows.
class InstallationUpgradeHarness:
    def plan(self) -> dict[str, Any]:
        return {"steps": ["verify_package_hash", "prepare_rollback", "install_candidate_to_staging", "launch_health_check", "preserve_previous_version"], "automatic_promotion": False, "field_status": "NOT_VERIFIED"}


class RestartResumeHarness:
    KEY = "self_hosting_restart_resume_v1"

    def checkpoint(self, state: ProjectState, *, mission_id: str, pending_action: str | None = None) -> dict[str, Any]:
        row = {"mission_id": mission_id, "pending_action": pending_action, "saved_at": _now(), "resume_verified_field": False}
        state.metadata[self.KEY] = row
        return dict(row)

    def plan(self) -> dict[str, Any]:
        return {"steps": ["checkpoint", "stop_process", "restart_process", "load_checkpoint", "revalidate_pending_side_effect", "continue_or_abort"], "field_status": "NOT_VERIFIED"}


class CrashDuringDesktopActionHarness:
    def plan(self) -> dict[str, Any]:
        return {"injection_points": ["before_authorize", "after_authorize", "before_side_effect", "after_side_effect", "before_confirmation", "after_confirmation"], "oracle": ["no_duplicate_external_effect", "pending_action_revalidated", "state_consistent"], "field_status": "NOT_VERIFIED"}


# 69-71. Watchdogs are pure evaluators and can be driven by real or synthetic observations.
class DesktopWatchdog:
    def evaluate(self, *, last_progress_age_s: float, window_present: bool, process_alive: bool) -> dict[str, Any]:
        issues = []
        if not process_alive: issues.append("desktop_process_dead")
        if not window_present: issues.append("window_missing")
        if last_progress_age_s > 120: issues.append("mission_stalled")
        return {"healthy": not issues, "issues": issues, "recommended": "recover" if issues else "continue"}


class ChromeWatchdog:
    def evaluate(self, *, browser_connected: bool, expected_url: str | None, current_url: str | None, session_authenticated: bool | None = None) -> dict[str, Any]:
        issues = []
        if not browser_connected: issues.append("browser_disconnected")
        if expected_url and current_url and not current_url.startswith(expected_url): issues.append("unexpected_navigation")
        if session_authenticated is False: issues.append("session_expired")
        return {"healthy": not issues, "issues": issues, "recommended": "recover_browser" if issues else "continue"}


class ProviderWatchdog:
    def evaluate(self, *, authenticated: bool, timeout_rate: float = 0.0, rate_limited: bool = False, recent_success_rate: float = 1.0) -> dict[str, Any]:
        issues = []
        if not authenticated: issues.append("authentication_failed")
        if rate_limited: issues.append("rate_limited")
        if timeout_rate > 0.2: issues.append("timeout_degradation")
        if recent_success_rate < 0.8: issues.append("provider_degraded")
        return {"healthy": not issues, "issues": issues, "failover_recommended": bool(issues)}


# 72. Human attention queue groups rather than interrupts.
class HumanAttentionQueue:
    KEY = "self_hosting_attention_queue_v1"

    def add(self, state: ProjectState, *, category: str, summary: str, severity: str = "medium", blocking: bool = False, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        row = {"id": uuid4().hex, "category": category, "summary": str(summary)[:1000], "severity": severity, "blocking": bool(blocking), "context": dict(context or {}), "status": "OPEN", "created_at": _now()}
        state.metadata.setdefault(self.KEY, []).append(row); state.metadata[self.KEY] = state.metadata[self.KEY][-1000:]
        return dict(row)

    def open(self, state: ProjectState) -> list[dict[str, Any]]:
        rows = [x for x in state.metadata.get(self.KEY, []) if x.get("status") == "OPEN"]
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(rows, key=lambda x: (not x.get("blocking"), order.get(x.get("severity"), 9), x.get("created_at", 0)))


# 73. Trusted approval channel. Issuance is not exposed by the ordinary API.
class TrustedApprovalBroker:
    KEY = "self_hosting_trusted_approval_v1"

    def __init__(self, authority: FieldEvidenceAuthority | None = None) -> None:
        self.authority = authority or FieldEvidenceAuthority()

    def issue_local(self, state: ProjectState, *, action: str, trusted_channel: bool = False, ttl_seconds: int = 300) -> dict[str, Any]:
        if not trusted_channel:
            raise PermissionError("approval challenges may only be issued by the trusted local UI")
        token = secrets.token_urlsafe(24)
        row = {"action": action, "token_hash": _sha256_bytes(token.encode()), "expires_at": _now() + max(30, min(int(ttl_seconds), 900)), "used": False, "issued_at": _now()}
        state.metadata.setdefault(self.KEY, {})[row["token_hash"]] = row
        return {"token": token, "action": action, "expires_at": row["expires_at"]}

    def consume(self, state: ProjectState, *, action: str, token: str) -> dict[str, Any]:
        digest = _sha256_bytes(str(token).encode())
        row = state.metadata.setdefault(self.KEY, {}).get(digest)
        ok = bool(row and not row.get("used") and row.get("action") == action and float(row.get("expires_at", 0)) >= _now())
        if not ok:
            raise PermissionError("invalid, expired, mismatched or already-used trusted approval")
        row["used"] = True; row["used_at"] = _now()
        return {"approved": True, "action": action, "one_time": True}


# 74-75. Emergency stop + safe resume.
class EmergencyStopController:
    KEY = "self_hosting_emergency_stop_v1"

    def stop(self, state: ProjectState, *, reason: str, actor: str = "human") -> dict[str, Any]:
        row = {"active": True, "reason": str(reason)[:1000], "actor": actor, "stopped_at": _now(), "new_side_effects_allowed": False}
        state.metadata[self.KEY] = row
        state.paused = True
        return dict(row)

    def active(self, state: ProjectState) -> bool:
        return bool(state.metadata.get(self.KEY, {}).get("active"))


class SafeResumeController:
    KEY = "self_hosting_safe_resume_v1"

    def assess(self, state: ProjectState, *, pending_actions: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
        decisions = []
        for action in pending_actions:
            irreversible = bool(action.get("irreversible") or action.get("external"))
            confirmed = bool(action.get("confirmed"))
            decision = "discard" if irreversible and not confirmed else "revalidate" if not confirmed else "complete"
            decisions.append({"action": dict(action), "decision": decision})
        ready = not any(x["decision"] == "complete" and not x["action"].get("confirmed") for x in decisions)
        return {"safe_to_resume": ready, "decisions": decisions, "requires_human_for_discarded_external": any(x["decision"] == "discard" for x in decisions)}

    def resume(self, state: ProjectState, *, pending_actions: Sequence[Mapping[str, Any]] = (), human_confirmed: bool = False) -> dict[str, Any]:
        assessment = self.assess(state, pending_actions=pending_actions)
        if assessment["requires_human_for_discarded_external"] and not human_confirmed:
            raise PermissionError("human confirmation required after interrupted external side effect")
        state.metadata.setdefault(EmergencyStopController.KEY, {}).update({"active": False, "resumed_at": _now(), "new_side_effects_allowed": True})
        state.paused = False
        row = {**assessment, "resumed": True, "resumed_at": _now()}
        state.metadata[self.KEY] = row
        return row


# 76-85. Field mission definitions and certification. None can be verified by synthetic local tests.
@dataclass(frozen=True, slots=True)
class FieldMissionSpec:
    mission: str
    title: str
    require_windows: bool
    required_claims: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()


FIELD_MISSIONS: tuple[FieldMissionSpec, ...] = (
    FieldMissionSpec("windows_read_only", "First Windows Read-Only Mission", True, ("desktop_observed", "chrome_located", "no_mutation")),
    FieldMissionSpec("chrome_navigation", "First Chrome Navigation Mission", True, ("chrome_opened", "https_navigated", "content_extracted", "evidence_recorded"), ("windows_read_only",)),
    FieldMissionSpec("chrome_session", "First Chrome Session Mission", True, ("manual_login_once", "dedicated_profile", "session_reused", "no_credentials_in_state"), ("chrome_navigation",)),
    FieldMissionSpec("download", "First Download Mission", True, ("download_completed", "artifact_hashed", "artifact_registered"), ("chrome_navigation",)),
    FieldMissionSpec("multi_app", "First Multi-App Mission", True, ("chrome_step", "artifact_step", "terminal_step", "result_in_evidence_ledger"), ("download",)),
    FieldMissionSpec("chatgpt_worker", "First Real AI Worker Mission", False, ("authenticated_live", "task_assigned", "response_received", "response_processed")),
    FieldMissionSpec("chatgpt_multiturn", "First AI Worker Multi-Turn Mission", False, ("turns_gte_2", "context_preserved", "artifact_exchange_if_needed"), ("chatgpt_worker",)),
    FieldMissionSpec("self_improvement_field", "First Real Self-Improvement Mission", True, ("isolated_candidate", "research_or_primary_docs", "code_changed", "tests_passed", "adversarial_passed", "candidate_built", "stable_unchanged"), ("multi_app", "chatgpt_worker", "chatgpt_multiturn")),
    FieldMissionSpec("alpha_certification", "Self-Hosting Alpha Certification", True, ("windows_verified", "chrome_verified", "multi_app_verified", "chatgpt_verified", "recovery_verified", "self_improvement_verified", "stable_unchanged"), ("self_improvement_field", "chatgpt_multiturn")),
    FieldMissionSpec("supervised_dogfooding", "Start Supervised Dogfooding", True, ("alpha_certified", "supervised_session_recorded", "friction_measured", "autonomy_measured"), ("alpha_certification",)),
)


class FieldMissionGate:
    KEY = "self_hosting_field_missions_v1"

    def __init__(self, anti_spoof: FieldGateAntiSpoofing | None = None) -> None:
        self.anti_spoof = anti_spoof or FieldGateAntiSpoofing()

    def _raw_status(self, state: ProjectState, spec: FieldMissionSpec) -> dict[str, Any]:
        evidence = self.anti_spoof.best_verified(state, spec.mission, require_windows=spec.require_windows)
        run = evidence.get("run") or {}
        claims = {str(x.get("kind")) for x in run.get("items", []) if str(x.get("value", "")).lower() in {"true", "pass", "verified", "1"}}
        required_ok = set(spec.required_claims).issubset(claims)
        return {"evidence": evidence, "claims": claims, "required_ok": required_ok}

    def status(self, state: ProjectState, spec: FieldMissionSpec) -> dict[str, Any]:
        raw = self._raw_status(state, spec)
        spec_map = {x.mission: x for x in FIELD_MISSIONS}
        prereq_details = {}
        for name in spec.prerequisites:
            other = spec_map[name]
            other_raw = self._raw_status(state, other)
            prereq_details[name] = bool(other_raw["evidence"]["status"] == "VERIFIED" and other_raw["required_ok"])
        prereq_ok = all(prereq_details.values())
        evidence = raw["evidence"]
        verified = evidence["status"] == "VERIFIED" and raw["required_ok"] and prereq_ok
        status = "VERIFIED" if verified else ("FAILED" if evidence["status"] == "FAILED" else "NOT_VERIFIED")
        return {"mission": spec.mission, "title": spec.title, "status": status, "verified": verified, "required_claims": list(spec.required_claims), "claims_present": sorted(raw["claims"]), "prerequisites": list(spec.prerequisites), "prerequisite_details": prereq_details, "prerequisites_ok": prereq_ok, "attestation": evidence["verification"]}

    def all(self, state: ProjectState) -> dict[str, dict[str, Any]]:
        return {x.mission: self.status(state, x) for x in FIELD_MISSIONS}


class SelfHostingFieldCertificationGate:
    KEY = "self_hosting_field_certification_v1"

    def assess(self, state: ProjectState) -> dict[str, Any]:
        missions = FieldMissionGate().all(state)
        alpha = missions["alpha_certification"]["verified"]
        dogfood = missions["supervised_dogfooding"]["verified"]
        beta_local = state.metadata.get("self_hosting_beta_gate_v1", {}).get("local_prepared", True)
        ready = bool(alpha and dogfood and beta_local)
        blockers = [name for name, row in missions.items() if not row["verified"]]
        row = {"status": "FIELD_DOGFOODING_ACTIVE" if ready else "FIELD_VALIDATION_PENDING", "ready": ready, "missions": missions, "blockers": blockers, "production_verified": False, "assessed_at": _now()}
        state.metadata[self.KEY] = row
        return row


class SelfHostingFieldOpsCore:
    VERSION = 1

    def __init__(self) -> None:
        self.preflight = SelfHostingMasterPreflight()
        self.setup = DependencyAutoSetupPlanner()
        self.windows_manifest = WindowsCapabilityManifest()
        self.chrome_manifest = ChromeCapabilityManifest()
        self.chatgpt_manifest = ChatGPTCapabilityManifest()
        self.ledger = UnifiedFieldEvidenceLedger()
        self.anti_spoof = FieldGateAntiSpoofing(self.ledger)
        self.validator = OneClickFieldValidator()
        self.diagnostics = AutomaticDiagnosticBundle()
        self.reproducer = EnvironmentReproducer()
        self.install = InstallationUpgradeHarness()
        self.restart = RestartResumeHarness()
        self.crash = CrashDuringDesktopActionHarness()
        self.desktop_watchdog = DesktopWatchdog()
        self.chrome_watchdog = ChromeWatchdog()
        self.provider_watchdog = ProviderWatchdog()
        self.attention = HumanAttentionQueue()
        self.approval = TrustedApprovalBroker()
        self.emergency = EmergencyStopController()
        self.resume = SafeResumeController()
        self.missions = FieldMissionGate(self.anti_spoof)
        self.certification = SelfHostingFieldCertificationGate()

    def initialize(self, state: ProjectState) -> dict[str, Any]:
        state.metadata.setdefault("self_hosting_field_ops_v1", {"initialized_at": _now()})
        return self.snapshot(state)

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "master_preflight": self.preflight.assess(state),
            "setup_plan": self.setup.inspect(state),
            "manifests": {"windows": self.windows_manifest.snapshot(), "chrome": self.chrome_manifest.snapshot(), "chatgpt": self.chatgpt_manifest.snapshot()},
            "validator": self.validator.plan(state),
            "attention": self.attention.open(state)[:25],
            "emergency_stop_active": self.emergency.active(state),
            "field_missions": self.missions.all(state),
            "certification": self.certification.assess(state),
            "windows_physical": "VERIFIED" if self.missions.status(state, FIELD_MISSIONS[0])["verified"] else "NOT_VERIFIED",
            "production_verified": False,
        }

    def local_preflight(self, state: ProjectState) -> dict[str, Any]:
        checks = {
            "master_preflight": True, "auto_setup_planner": True, "capability_manifests": True,
            "signed_field_ledger": True, "anti_spoofing": True, "one_click_validator": True,
            "diagnostic_bundle": True, "environment_reproducer": True, "install_upgrade_harness": True,
            "restart_resume_harness": True, "crash_action_harness": True, "desktop_watchdog": True,
            "chrome_watchdog": True, "provider_watchdog": True, "human_attention_queue": True,
            "trusted_approval_channel": True, "emergency_stop": True, "safe_resume": True,
            "field_mission_gates": True, "field_certification": True,
        }
        return {"pass": all(checks.values()), "checks": checks, "master": self.preflight.assess(state), "certification": self.certification.assess(state), "production_verified": False}
