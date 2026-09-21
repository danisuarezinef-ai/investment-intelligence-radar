from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True, slots=True)
class UpdateStateV2:
    pointer: str = "stable"
    stable_seq: int = 10
    staged: str = ""
    staged_seq: int = 0
    preflight: str = ""
    pending: str = ""
    pending_seq: int = 0
    journal_ok: bool = True
    receipt_ok: bool = True
    lock: bool = False
    quarantine_a: bool = False
    quarantine_b: bool = False


ACTIONS = (
    "stage_a_new", "stage_b_new", "stage_a_old", "stage_b_old", "preflight_ok", "preflight_fail", "activate",
    "health_ok", "health_fail", "power_loss", "lock", "unlock", "tamper_journal", "repair_journal",
    "corrupt_receipt", "repair_receipt", "quarantine_staged", "rollback",
)


def _quarantined(s: UpdateStateV2, c: str) -> bool:
    return (c == "a" and s.quarantine_a) or (c == "b" and s.quarantine_b)


def _errors(s: UpdateStateV2) -> list[str]:
    out: list[str] = []
    if s.pointer not in {"stable", "a", "b"}: out.append("pointer_domain")
    if s.pending and s.pointer != s.pending: out.append("pending_pointer_owner")
    if s.pending and s.preflight != s.pending: out.append("pending_requires_matching_preflight")
    if s.pending and s.pending_seq < s.stable_seq: out.append("pending_downgrade")
    if s.pending and (not s.journal_ok or not s.receipt_ok): out.append("pending_requires_valid_evidence")
    if s.pending and _quarantined(s, s.pending): out.append("quarantined_pending")
    if s.staged and _quarantined(s, s.staged): out.append("quarantined_staged")
    if s.pointer in {"a", "b"} and _quarantined(s, s.pointer): out.append("quarantined_active")
    return out


def _step(s: UpdateStateV2, action: str) -> UpdateStateV2:
    d = asdict(s)
    if action.startswith("stage_"):
        _, c, age = action.split("_")
        seq = s.stable_seq + 1 if age == "new" else max(0, s.stable_seq - 1)
        if not s.pending and not s.lock and s.journal_ok and s.receipt_ok and c != s.pointer and not _quarantined(s, c) and seq >= s.stable_seq:
            d.update(staged=c, staged_seq=seq, preflight="")
    elif action == "preflight_ok" and s.staged and not s.pending and s.journal_ok and s.receipt_ok and not _quarantined(s, s.staged):
        d["preflight"] = s.staged
    elif action == "preflight_fail" and s.staged and not s.pending:
        d.update(staged="", staged_seq=0, preflight="")
    elif action == "activate" and s.staged and s.preflight == s.staged and not s.pending and not s.lock and s.journal_ok and s.receipt_ok and s.staged_seq >= s.stable_seq:
        d.update(pointer=s.staged, pending=s.staged, pending_seq=s.staged_seq)
    elif action == "health_ok" and s.pending:
        d.update(stable_seq=max(s.stable_seq, s.pending_seq), staged="", staged_seq=0, preflight="", pending="", pending_seq=0)
    elif action in {"health_fail", "rollback"} and (s.pending or s.pointer != "stable"):
        d.update(pointer="stable", staged="", staged_seq=0, preflight="", pending="", pending_seq=0)
    elif action == "power_loss":
        if s.pending: d.update(pointer="stable", staged="", staged_seq=0, preflight="", pending="", pending_seq=0)
        d["lock"] = False
    elif action == "lock" and not s.pending: d["lock"] = True
    elif action == "unlock": d["lock"] = False
    elif action == "tamper_journal" and not s.pending: d["journal_ok"] = False
    elif action == "repair_journal" and not s.pending: d["journal_ok"] = True
    elif action == "corrupt_receipt" and not s.pending: d["receipt_ok"] = False
    elif action == "repair_receipt" and not s.pending: d["receipt_ok"] = True
    elif action == "quarantine_staged" and s.staged and not s.pending:
        d["quarantine_" + s.staged] = True; d.update(staged="", staged_seq=0, preflight="")
    return UpdateStateV2(**d)


def bounded_model_check_v2(*, max_depth: int = 15, max_states: int = 250_000) -> dict[str, Any]:
    start = UpdateStateV2(); q = deque([(start, 0)]); seen = {start}; transitions = 0; violations = []
    while q and len(seen) <= max_states:
        state, depth = q.popleft()
        err = _errors(state)
        if err:
            violations.append({"state": asdict(state), "violations": err, "depth": depth}); break
        if depth >= max_depth: continue
        for action in ACTIONS:
            nxt = _step(state, action); transitions += 1
            err = _errors(nxt)
            if err:
                violations.append({"state": asdict(nxt), "violations": err, "via": action, "depth": depth + 1}); q.clear(); break
            if nxt not in seen:
                seen.add(nxt); q.append((nxt, depth + 1))
    return {"ok": not violations, "max_depth": max_depth, "states_explored": len(seen), "transitions_checked": transitions, "violations": violations[:3], "truncated": len(seen) > max_states}
