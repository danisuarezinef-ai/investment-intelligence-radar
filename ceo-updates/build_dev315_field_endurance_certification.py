from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.90-rc1-capability-scoped-provider.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV315_BUILD_ROOT", "/tmp/ceo-dev315-field-endurance"))
OLD_VERSION = "1.5.90-rc1-capability-scoped-provider"
VERSION = "1.5.91-rc1-field-endurance-certification"


ENGINE = r'''from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import time
from typing import Any

from .models import ProjectState


class FieldEnduranceCertificationV1:
    """Real-host endurance certification based only on durable runtime telemetry.

    No provider response can grant this certificate. Wall-clock gaps are capped so
    sleep/offline time cannot be counted as active endurance.
    """

    EPOCH = "dev315-field-endurance-v1"
    DEFAULT_MIN_ACTIVE_SECONDS = 30 * 60
    DEFAULT_MIN_SAMPLES = 300
    MAX_COUNTED_SAMPLE_GAP_SECONDS = 2.5

    def __init__(
        self,
        *,
        min_active_seconds: float | None = None,
        min_samples: int | None = None,
        max_sample_gap_seconds: float | None = None,
    ) -> None:
        self.min_active_seconds = float(
            self.DEFAULT_MIN_ACTIVE_SECONDS if min_active_seconds is None else min_active_seconds
        )
        self.min_samples = int(self.DEFAULT_MIN_SAMPLES if min_samples is None else min_samples)
        self.max_sample_gap_seconds = float(
            self.MAX_COUNTED_SAMPLE_GAP_SECONDS
            if max_sample_gap_seconds is None else max_sample_gap_seconds
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()

    @staticmethod
    def _crash_count(state: ProjectState) -> int:
        return len(list(state.metadata.get("scheduler_crash_history") or []))

    @staticmethod
    def _recovery_count(state: ProjectState) -> int:
        return len(list(state.metadata.get("worker_recovery_history") or []))

    @staticmethod
    def _storm_active(state: ProjectState) -> bool:
        if state.metadata.get("suppress_new_internal_recovery"):
            return True
        stalled = state.metadata.get("autonomy_stalled") or {}
        if isinstance(stalled, dict) and stalled:
            reason = str(stalled.get("reason") or stalled.get("status") or "").lower()
            if "storm" in reason or "recovery" in reason or "bounded" in reason:
                return True
        for key in ("recovery_storm_guard_v1", "global_recovery_storm_breaker"):
            row = state.metadata.get(key)
            if isinstance(row, dict) and bool(row.get("open") or row.get("active")):
                return True
            if row is True:
                return True
        return False

    def _new_row(self, state: ProjectState, now_mono: float, now_utc: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "epoch": self.EPOCH,
            "started_at": now_utc,
            "last_sample_at": now_utc,
            "last_monotonic": now_mono,
            "process_id": os.getpid(),
            "process_sessions_observed": 1,
            "active_seconds": 0.0,
            "sample_count": 1,
            "sleep_or_offline_seconds_ignored": 0.0,
            "baseline_scheduler_crashes": self._crash_count(state),
            "baseline_worker_recoveries": self._recovery_count(state),
            "new_scheduler_crashes": 0,
            "new_worker_recoveries": 0,
            "min_active_seconds": self.min_active_seconds,
            "min_samples": self.min_samples,
            "certified": False,
            "certified_at": None,
            "certificate_sha256": None,
            "blocking_reasons": ["insufficient_active_runtime", "insufficient_samples", "work_not_yet_complete"],
        }

    def observe(
        self,
        state: ProjectState,
        *,
        now_monotonic: float | None = None,
        now_utc: str | None = None,
    ) -> dict[str, Any]:
        if not bool(state.metadata.get("requires_field_endurance_certification", False)):
            return {"required": False, "certified": bool(state.metadata.get("field_endurance_certified", False))}

        mono = float(time.monotonic() if now_monotonic is None else now_monotonic)
        utc = str(now_utc or self._utc_now())
        row = dict(state.metadata.get("field_endurance_telemetry_v1") or {})

        if row.get("epoch") != self.EPOCH:
            row = self._new_row(state, mono, utc)
            state.metadata["field_endurance_certified"] = False
            state.metadata.pop("field_endurance_certificate_v1", None)
        else:
            prior_mono = row.get("last_monotonic")
            prior_pid = int(row.get("process_id") or 0)
            current_pid = os.getpid()
            if prior_pid and prior_pid != current_pid:
                row["process_sessions_observed"] = int(row.get("process_sessions_observed", 1)) + 1
                row["process_id"] = current_pid

            eligible = bool(
                not state.paused
                and state.cancelled_at is None
                and not state.metadata.get("operator_cancelled")
                and state.completed_at is None
            )
            raw_delta = 0.0
            if isinstance(prior_mono, (int, float)) and mono >= float(prior_mono):
                raw_delta = max(0.0, mono - float(prior_mono))
            counted = min(raw_delta, self.max_sample_gap_seconds) if eligible else 0.0
            ignored = max(0.0, raw_delta - counted)
            row["active_seconds"] = round(float(row.get("active_seconds", 0.0)) + counted, 3)
            row["sleep_or_offline_seconds_ignored"] = round(
                float(row.get("sleep_or_offline_seconds_ignored", 0.0)) + ignored, 3
            )
            row["sample_count"] = int(row.get("sample_count", 0)) + 1
            row["last_monotonic"] = mono
            row["last_sample_at"] = utc

        row["new_scheduler_crashes"] = max(
            0, self._crash_count(state) - int(row.get("baseline_scheduler_crashes", 0))
        )
        row["new_worker_recoveries"] = max(
            0, self._recovery_count(state) - int(row.get("baseline_worker_recoveries", 0))
        )

        work_complete = bool(state.metadata.get("work_complete_certified_v1", False))
        completion_cert = dict(state.metadata.get("deterministic_completion_certificate_v1") or {})
        completion_hash = str(completion_cert.get("certificate_sha256") or "")
        storm_active = self._storm_active(state)

        reasons: list[str] = []
        if float(row.get("active_seconds", 0.0)) < self.min_active_seconds:
            reasons.append("insufficient_active_runtime")
        if int(row.get("sample_count", 0)) < self.min_samples:
            reasons.append("insufficient_samples")
        if not work_complete or not completion_hash:
            reasons.append("work_not_yet_complete")
        if int(row.get("new_scheduler_crashes", 0)) > 0:
            reasons.append("scheduler_crash_observed")
        if storm_active:
            reasons.append("recovery_storm_active")
        if state.paused:
            reasons.append("operator_paused")
        if state.cancelled_at is not None or state.metadata.get("operator_cancelled"):
            reasons.append("project_cancelled")

        row["blocking_reasons"] = reasons
        row["progress_percent"] = round(
            min(100.0, 100.0 * float(row.get("active_seconds", 0.0)) / max(0.001, self.min_active_seconds)),
            1,
        )
        row["seconds_remaining"] = round(
            max(0.0, self.min_active_seconds - float(row.get("active_seconds", 0.0))), 1
        )

        if not reasons:
            core = {
                "schema_version": 1,
                "epoch": self.EPOCH,
                "project_id": state.id,
                "active_seconds": float(row.get("active_seconds", 0.0)),
                "sample_count": int(row.get("sample_count", 0)),
                "process_sessions_observed": int(row.get("process_sessions_observed", 1)),
                "new_scheduler_crashes": int(row.get("new_scheduler_crashes", 0)),
                "new_worker_recoveries": int(row.get("new_worker_recoveries", 0)),
                "completion_certificate_sha256": completion_hash,
                "sleep_or_offline_seconds_ignored": float(row.get("sleep_or_offline_seconds_ignored", 0.0)),
            }
            cert_hash = self._digest(core)
            row["certified"] = True
            row["certified_at"] = row.get("certified_at") or utc
            row["certificate_sha256"] = cert_hash
            state.metadata["field_endurance_certified"] = True
            state.metadata["field_endurance_certificate_v1"] = {
                **core,
                "certificate_sha256": cert_hash,
                "certified_at": row["certified_at"],
                "provider_assertion_used": False,
                "human_override_used": False,
            }
        else:
            row["certified"] = False
            state.metadata["field_endurance_certified"] = False

        state.metadata["field_endurance_telemetry_v1"] = row
        return {
            "required": True,
            "certified": bool(row.get("certified")),
            "progress_percent": row.get("progress_percent", 0.0),
            "active_seconds": row.get("active_seconds", 0.0),
            "seconds_remaining": row.get("seconds_remaining", self.min_active_seconds),
            "sample_count": row.get("sample_count", 0),
            "new_scheduler_crashes": row.get("new_scheduler_crashes", 0),
            "new_worker_recoveries": row.get("new_worker_recoveries", 0),
            "sleep_or_offline_seconds_ignored": row.get("sleep_or_offline_seconds_ignored", 0.0),
            "blocking_reasons": list(row.get("blocking_reasons") or []),
            "certificate_sha256": row.get("certificate_sha256"),
        }
'''


def patch_scheduler() -> None:
    p = ROOT / "ceo_core" / "scheduler.py"
    s = p.read_text(encoding="utf-8")

    import_anchor = "from .deterministic_completion_certifier_v1 import DeterministicCompletionCertifierV1\n"
    import_new = import_anchor + "from .field_endurance_certification_v1 import FieldEnduranceCertificationV1\n"
    if s.count(import_anchor) != 1:
        raise RuntimeError(f"field cert import anchor={s.count(import_anchor)}")
    s = s.replace(import_anchor, import_new, 1)

    init_anchor = "        self.deterministic_completion_certifier_v1 = DeterministicCompletionCertifierV1()\n"
    init_new = init_anchor + "        self.field_endurance_certification_v1 = FieldEnduranceCertificationV1()\n"
    if s.count(init_anchor) != 1:
        raise RuntimeError(f"field cert init anchor={s.count(init_anchor)}")
    s = s.replace(init_anchor, init_new, 1)

    observe_anchor = '''            deterministic_completion = self.deterministic_completion_certifier_v1.apply(
                self.state, self.goal_completion_gate
            )
            self.state.metadata["deterministic_completion_certifier_last_v1"] = deterministic_completion
            reconcile = self.scheduler_reconciler_v1.reconcile(
'''
    observe_new = '''            deterministic_completion = self.deterministic_completion_certifier_v1.apply(
                self.state, self.goal_completion_gate
            )
            self.state.metadata["deterministic_completion_certifier_last_v1"] = deterministic_completion
            field_endurance = self.field_endurance_certification_v1.observe(self.state)
            self.state.metadata["field_endurance_last_v1"] = field_endurance
            # Certification can flip the final field gate; re-evaluate deterministic
            # completion immediately so the project can close without a provider turn.
            if field_endurance.get("certified") and not deterministic_completion.get("final_complete"):
                deterministic_completion = self.deterministic_completion_certifier_v1.apply(
                    self.state, self.goal_completion_gate
                )
                self.state.metadata["deterministic_completion_certifier_last_v1"] = deterministic_completion
            reconcile = self.scheduler_reconciler_v1.reconcile(
'''
    if s.count(observe_anchor) != 1:
        raise RuntimeError(f"field cert observe anchor={s.count(observe_anchor)}")
    s = s.replace(observe_anchor, observe_new, 1)
    p.write_text(s, encoding="utf-8")


def patch_work_mode() -> None:
    p = ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    s = p.read_text(encoding="utf-8")

    snap_anchor = '''            "deterministic_completion_certificate": state.metadata.get("deterministic_completion_certificate_v1"),
            "metrics": {
'''
    snap_new = '''            "deterministic_completion_certificate": state.metadata.get("deterministic_completion_certificate_v1"),
            "field_endurance": state.metadata.get("field_endurance_last_v1") or state.metadata.get("field_endurance_telemetry_v1"),
            "metrics": {
'''
    if s.count(snap_anchor) != 1:
        raise RuntimeError(f"field endurance snapshot anchor={s.count(snap_anchor)}")
    s = s.replace(snap_anchor, snap_new, 1)

    banner_anchor = """else if(s.work_complete_certified&&s.completion_phase==='work_complete_pending_certification'){$('actionBanner').className='banner infob';$('actionBanner').textContent='✓ Trabajo del objetivo completado con evidencia determinista. Solo queda la certificación de resistencia en Windows; CEO no gastará llamadas IA ni creará nuevas auditorías mientras espera.'}
"""
    banner_new = """else if(s.work_complete_certified&&s.completion_phase==='work_complete_pending_certification'){const fe=s.field_endurance||{};const pct=Math.round(Number(fe.progress_percent)||0);const rem=Math.max(0,Number(fe.seconds_remaining)||0);const mins=Math.ceil(rem/60);$('actionBanner').className='banner infob';$('actionBanner').textContent='✓ Trabajo completado con evidencia determinista · certificación física '+pct+'%'+(rem>0?' · ~'+mins+' min activos restantes':'')+'. El tiempo con el PC suspendido no cuenta y CEO no usa Gemini para certificar.'}
"""
    if s.count(banner_anchor) != 1:
        raise RuntimeError(f"field endurance banner anchor={s.count(banner_anchor)}")
    s = s.replace(banner_anchor, banner_new, 1)

    p.write_text(s, encoding="utf-8")


def update_contract() -> None:
    for rel in ("scripts/ceo_stdlib_work_mode.py", "scripts/install_windows_bootstrap.py"):
        p = ROOT / rel
        if p.is_file():
            p.write_text(p.read_text(encoding="utf-8").replace(OLD_VERSION, VERSION), encoding="utf-8")

    cpath = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(cpath.read_text(encoding="utf-8"))
    contract["app_version"] = VERSION
    req = list(contract.get("required_paths") or [])
    new_rel = "ceo_core/field_endurance_certification_v1.py"
    if new_rel not in req:
        req.append(new_rel)
    contract["required_paths"] = sorted(req)
    hashes = dict(contract.get("file_hashes") or {})
    for rel in contract["required_paths"]:
        fp = ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract path {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    cpath.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if not BASE.is_file():
        raise RuntimeError(f"missing base {BASE}")
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    (ROOT / "ceo_core" / "field_endurance_certification_v1.py").write_text(ENGINE, encoding="utf-8")
    patch_scheduler()
    patch_work_mode()
    update_contract()

    print(json.dumps({
        "ok": True,
        "base": OLD_VERSION,
        "version": VERSION,
        "root": str(ROOT),
        "invariants": [
            "field_endurance_uses_real_active_process_time_only",
            "sleep_and_offline_gaps_are_not_counted",
            "provider_assertions_cannot_grant_field_certification",
            "scheduler_crash_blocks_field_certification",
            "recovery_storm_blocks_field_certification",
            "field_certificate_is_hash_bound_to_completion_evidence",
            "successful_field_certification_promotes_completion_without_ai",
            "dev311_to_dev314_hardening_inherited",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
