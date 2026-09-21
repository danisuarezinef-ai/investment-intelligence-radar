from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class LabState:
    pointer: str = "stable"
    staged: str = ""
    preflight: str = ""
    pending_health: str = ""
    lock: bool = False
    journal_valid: bool = True
    receipt_valid: bool = True
    cutovers: int = 0
    rollbacks: int = 0
    quarantined: int = 0


class UpdateFailureLabV3:
    """Crash/order/tamper model for transactional update invariants.

    It deliberately models power loss, stale locks, stale receipts and tampering
    without touching a real installation.
    """

    ACTIONS = (
        "stage_a", "stage_b", "preflight_ok", "preflight_fail", "activate",
        "health_ok", "health_fail", "power_loss", "stale_lock", "recover_lock",
        "tamper_journal", "repair_from_checkpoint", "corrupt_receipt", "reconcile_receipt",
        "rollback", "retry",
    )

    @staticmethod
    def _assert_invariants(s: LabState) -> None:
        if s.pending_health:
            assert s.pointer == s.pending_health, "pending health must own pointer"
            assert s.preflight == s.pending_health, "pending activation must have preflight authority"
            assert not s.staged or s.staged == s.pending_health, "another candidate staged during pending health"
        if s.pointer not in {"stable", "a", "b"}:
            raise AssertionError("invalid pointer")
        if not s.journal_valid and s.pending_health:
            raise AssertionError("cutover active with invalid journal")
        if not s.receipt_valid and s.pending_health:
            raise AssertionError("cutover active with invalid receipt")

    @classmethod
    def run_sequence(cls, seed: int, *, steps: int = 200) -> dict[str, Any]:
        r = random.Random(int(seed)); s = LabState()
        failures: list[str] = []
        for _ in range(max(1, int(steps))):
            action = r.choice(cls.ACTIONS)
            try:
                if action in {"stage_a", "stage_b"}:
                    candidate = action[-1]
                    if not s.pending_health and not s.lock and s.journal_valid and s.receipt_valid:
                        s.staged = candidate; s.preflight = ""
                elif action == "preflight_ok":
                    if s.staged and not s.pending_health and s.journal_valid and s.receipt_valid:
                        s.preflight = s.staged
                elif action == "preflight_fail":
                    if s.staged and not s.pending_health:
                        s.quarantined += 1; s.staged = ""; s.preflight = ""
                elif action == "activate":
                    if s.staged and s.preflight == s.staged and not s.pending_health and not s.lock and s.journal_valid and s.receipt_valid:
                        s.pointer = s.staged; s.pending_health = s.staged; s.cutovers += 1
                elif action == "health_ok":
                    if s.pending_health:
                        s.pointer = s.pending_health; s.staged = ""; s.preflight = ""; s.pending_health = ""
                elif action == "health_fail":
                    if s.pending_health:
                        s.pointer = "stable"; s.rollbacks += 1; s.staged = ""; s.preflight = ""; s.pending_health = ""
                elif action == "power_loss":
                    if s.pending_health:
                        s.pointer = "stable"; s.rollbacks += 1; s.pending_health = ""; s.staged = ""; s.preflight = ""
                    s.lock = False
                elif action == "stale_lock":
                    if not s.pending_health: s.lock = True
                elif action == "recover_lock":
                    s.lock = False
                elif action == "tamper_journal":
                    if not s.pending_health: s.journal_valid = False
                elif action == "repair_from_checkpoint":
                    if not s.pending_health: s.journal_valid = True
                elif action == "corrupt_receipt":
                    if not s.pending_health: s.receipt_valid = False
                elif action == "reconcile_receipt":
                    if not s.pending_health: s.receipt_valid = True
                elif action == "rollback":
                    if s.pointer in {"a", "b"} or s.pending_health:
                        s.pointer = "stable"; s.pending_health = ""; s.staged = ""; s.preflight = ""; s.rollbacks += 1
                elif action == "retry":
                    # Retry is intentionally authority-free.
                    pass
                cls._assert_invariants(s)
            except Exception as exc:
                failures.append(f"{type(exc).__name__}: {exc}")
                break
        if s.pending_health:
            s.pointer = "stable"; s.rollbacks += 1; s.pending_health = ""; s.staged = ""; s.preflight = ""
        try: cls._assert_invariants(s)
        except Exception as exc: failures.append(f"final:{type(exc).__name__}: {exc}")
        return {"seed": seed, "steps": int(steps), "passed": not failures, "failure": failures[:1], **asdict(s)}

    @classmethod
    def campaign(cls, *, seeds: int = 1000, steps: int = 200) -> dict[str, Any]:
        rows = [cls.run_sequence(i, steps=steps) for i in range(max(1, int(seeds)))]
        failed = [x for x in rows if not x["passed"]]
        return {
            "ok": not failed,
            "seeds": len(rows),
            "steps_per_seed": int(steps),
            "transitions": len(rows) * int(steps),
            "failed": len(failed),
            "cutovers": sum(int(x["cutovers"]) for x in rows),
            "rollbacks": sum(int(x["rollbacks"]) for x in rows),
            "quarantined": sum(int(x["quarantined"]) for x in rows),
            "sample": rows[:8],
        }
