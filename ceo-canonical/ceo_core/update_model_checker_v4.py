from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class UpdateStateV4:
    pointer: str = "stable"
    stable_seq: int = 30
    staged: str = ""
    staged_seq: int = 0
    preflight: str = ""
    pending: str = ""
    pending_seq: int = 0
    core_evidence_ok: bool = True
    campaign_evidence_ok: bool = True
    capability_drift_ok: bool = True
    android_claim_ok: bool = True
    session_open: bool = False
    lock: bool = False
    quarantine_a: bool = False
    quarantine_b: bool = False


ACTIONS = (
    "open_session", "close_session", "stage_a_new", "stage_b_new", "stage_a_old", "stage_b_old",
    "preflight_ok", "preflight_fail", "activate", "health_ok", "health_fail", "power_loss", "lock", "unlock",
    "break_core_evidence", "repair_core_evidence", "break_campaign_evidence", "repair_campaign_evidence",
    "add_sensitive_capability", "remove_sensitive_capability", "android_overclaim", "repair_android_claim",
    "quarantine_staged", "rollback",
)


def _quarantined(s: UpdateStateV4, c: str) -> bool:
    return (c == "a" and s.quarantine_a) or (c == "b" and s.quarantine_b)


def _evidence_ok(s: UpdateStateV4) -> bool:
    return s.core_evidence_ok and s.campaign_evidence_ok and s.capability_drift_ok and s.android_claim_ok


def _errors(s: UpdateStateV4) -> list[str]:
    out: list[str] = []
    if s.pointer not in {"stable", "a", "b"}: out.append("pointer_domain")
    if s.pending and s.pointer != s.pending: out.append("pending_pointer_owner")
    if s.pending and s.preflight != s.pending: out.append("pending_requires_matching_preflight")
    if s.pending and s.pending_seq < s.stable_seq: out.append("pending_downgrade")
    if s.pending and not _evidence_ok(s): out.append("pending_requires_complete_evidence")
    if s.pending and not s.session_open: out.append("pending_requires_open_campaign_session")
    if s.pending and _quarantined(s, s.pending): out.append("quarantined_pending")
    if s.staged and _quarantined(s, s.staged): out.append("quarantined_staged")
    if s.pointer in {"a", "b"} and _quarantined(s, s.pointer): out.append("quarantined_active")
    return out


def _step(s: UpdateStateV4, action: str) -> UpdateStateV4:
    d = asdict(s)
    if action == "open_session" and not s.pending:
        d["session_open"] = True
    elif action == "close_session" and not s.pending and not s.staged:
        d["session_open"] = False
    elif action.startswith("stage_"):
        _, c, age = action.split("_")
        seq = s.stable_seq + 1 if age == "new" else max(0, s.stable_seq - 1)
        if s.session_open and not s.pending and not s.lock and _evidence_ok(s) and c != s.pointer and not _quarantined(s, c) and seq >= s.stable_seq:
            d.update(staged=c, staged_seq=seq, preflight="")
    elif action == "preflight_ok" and s.staged and not s.pending and _evidence_ok(s) and s.session_open and not _quarantined(s, s.staged):
        d["preflight"] = s.staged
    elif action == "preflight_fail" and s.staged and not s.pending:
        d.update(staged="", staged_seq=0, preflight="")
    elif action == "activate" and s.staged and s.preflight == s.staged and not s.pending and not s.lock and s.session_open and _evidence_ok(s) and s.staged_seq >= s.stable_seq:
        d.update(pointer=s.staged, pending=s.staged, pending_seq=s.staged_seq)
    elif action == "health_ok" and s.pending:
        d.update(stable_seq=max(s.stable_seq, s.pending_seq), staged="", staged_seq=0, preflight="", pending="", pending_seq=0)
    elif action in {"health_fail", "rollback"} and (s.pending or s.pointer != "stable"):
        d.update(pointer="stable", staged="", staged_seq=0, preflight="", pending="", pending_seq=0)
    elif action == "power_loss":
        if s.pending:
            d.update(pointer="stable", staged="", staged_seq=0, preflight="", pending="", pending_seq=0)
        d["lock"] = False
        d["session_open"] = False
    elif action == "lock" and not s.pending:
        d["lock"] = True
    elif action == "unlock":
        d["lock"] = False
    elif action == "quarantine_staged" and s.staged and not s.pending:
        d["quarantine_" + s.staged] = True
        d.update(staged="", staged_seq=0, preflight="")
    elif not s.pending:
        mapping = {
            "break_core_evidence": ("core_evidence_ok", False), "repair_core_evidence": ("core_evidence_ok", True),
            "break_campaign_evidence": ("campaign_evidence_ok", False), "repair_campaign_evidence": ("campaign_evidence_ok", True),
            "add_sensitive_capability": ("capability_drift_ok", False), "remove_sensitive_capability": ("capability_drift_ok", True),
            "android_overclaim": ("android_claim_ok", False), "repair_android_claim": ("android_claim_ok", True),
        }
        if action in mapping:
            key, value = mapping[action]
            d[key] = value
    return UpdateStateV4(**d)


def bounded_model_check_v4(*, max_depth: int = 16, max_states: int = 250_000) -> dict[str, Any]:
    start = UpdateStateV4()
    q = deque([(start, 0)])
    seen = {start}
    transitions = 0
    violations: list[dict[str, Any]] = []
    while q and len(seen) <= max_states:
        state, depth = q.popleft()
        err = _errors(state)
        if err:
            violations.append({"state": asdict(state), "violations": err, "depth": depth})
            break
        if depth >= max_depth:
            continue
        for action in ACTIONS:
            nxt = _step(state, action)
            transitions += 1
            err = _errors(nxt)
            if err:
                violations.append({"state": asdict(nxt), "violations": err, "via": action, "depth": depth + 1})
                q.clear()
                break
            if nxt not in seen:
                seen.add(nxt)
                q.append((nxt, depth + 1))
    return {
        "ok": not violations and len(seen) <= max_states,
        "max_depth": max_depth,
        "states_explored": len(seen),
        "transitions_checked": transitions,
        "violations": violations[:3],
        "truncated": len(seen) > max_states,
        "modeled_evidence_classes": ["core", "campaign", "capability_drift", "android_claim"],
    }
