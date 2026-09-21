from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True, slots=True)
class AbstractUpdateState:
    pointer: str = "stable"
    staged: str = ""
    preflight: str = ""
    pending: str = ""
    journal_ok: bool = True
    receipt_ok: bool = True
    lock: bool = False


ACTIONS = (
    "stage_a", "stage_b", "preflight_ok", "preflight_fail", "activate",
    "health_ok", "health_fail", "power_loss", "lock", "unlock",
    "tamper_journal", "repair_journal", "corrupt_receipt", "repair_receipt", "rollback",
)


def _invariants(s: AbstractUpdateState) -> list[str]:
    errors: list[str] = []
    if s.pointer not in {"stable", "a", "b"}: errors.append("pointer_domain")
    if s.pending and s.pointer != s.pending: errors.append("pending_owns_pointer")
    if s.pending and s.preflight != s.pending: errors.append("pending_has_preflight")
    if s.pending and (not s.journal_ok or not s.receipt_ok): errors.append("pending_requires_valid_evidence")
    if s.pending and s.staged not in {"", s.pending}: errors.append("no_competing_staged_during_pending")
    return errors


def _step(s: AbstractUpdateState, action: str) -> AbstractUpdateState:
    d = asdict(s)
    if action in {"stage_a", "stage_b"}:
        c = action[-1]
        if not s.pending and not s.lock and s.journal_ok and s.receipt_ok:
            d.update(staged=c, preflight="")
    elif action == "preflight_ok" and s.staged and not s.pending and s.journal_ok and s.receipt_ok:
        d["preflight"] = s.staged
    elif action == "preflight_fail" and s.staged and not s.pending:
        d.update(staged="", preflight="")
    elif action == "activate" and s.staged and s.preflight == s.staged and not s.pending and not s.lock and s.journal_ok and s.receipt_ok:
        d.update(pointer=s.staged, pending=s.staged)
    elif action == "health_ok" and s.pending:
        d.update(staged="", preflight="", pending="")
    elif action in {"health_fail", "rollback"} and (s.pending or s.pointer != "stable"):
        d.update(pointer="stable", staged="", preflight="", pending="")
    elif action == "power_loss":
        if s.pending: d.update(pointer="stable", staged="", preflight="", pending="")
        d["lock"] = False
    elif action == "lock" and not s.pending: d["lock"] = True
    elif action == "unlock": d["lock"] = False
    elif action == "tamper_journal" and not s.pending: d["journal_ok"] = False
    elif action == "repair_journal" and not s.pending: d["journal_ok"] = True
    elif action == "corrupt_receipt" and not s.pending: d["receipt_ok"] = False
    elif action == "repair_receipt" and not s.pending: d["receipt_ok"] = True
    return AbstractUpdateState(**d)


def bounded_model_check(*, max_depth: int = 12, max_states: int = 100_000) -> dict[str, Any]:
    start = AbstractUpdateState()
    q = deque([(start, 0)])
    seen = {start}
    transitions = 0
    violations: list[dict[str, Any]] = []
    while q and len(seen) <= max_states:
        state, depth = q.popleft()
        inv = _invariants(state)
        if inv:
            violations.append({"state": asdict(state), "violations": inv, "depth": depth})
            break
        if depth >= max_depth:
            continue
        for action in ACTIONS:
            nxt = _step(state, action); transitions += 1
            inv2 = _invariants(nxt)
            if inv2:
                violations.append({"state": asdict(nxt), "violations": inv2, "via": action, "depth": depth + 1})
                q.clear(); break
            if nxt not in seen:
                seen.add(nxt); q.append((nxt, depth + 1))
    return {
        "ok": not violations,
        "max_depth": max_depth,
        "states_explored": len(seen),
        "transitions_checked": transitions,
        "violations": violations[:3],
        "truncated": len(seen) > max_states,
    }
