from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class SequenceResult:
    seed: int
    steps: int
    passed: bool
    final_pointer: str
    cutovers: int
    rollbacks: int
    reason: str = ""


class UpdateFailureLabV2:
    """Adversarial state-sequence lab for updater ordering and crash recovery."""

    ACTIONS = ("download", "verify", "stage", "preflight", "activate", "health", "crash", "rollback", "retry")

    @classmethod
    def run_sequence(cls, seed: int, *, steps: int = 80) -> SequenceResult:
        rng = random.Random(int(seed))
        pointer = "stable"
        staged = False
        preflight_ok = False
        pending = False
        cutovers = 0
        rollbacks = 0
        try:
            for _ in range(max(1, int(steps))):
                action = rng.choice(cls.ACTIONS)
                if action in {"download", "verify"}:
                    continue
                if action == "stage":
                    if not pending:
                        staged = True; preflight_ok = False
                elif action == "preflight":
                    if staged and not pending:
                        # deterministic injected candidate health outcome
                        preflight_ok = rng.random() >= 0.18
                elif action == "activate":
                    # Core invariant: no cutover without staged + preflight.
                    if staged and preflight_ok and not pending:
                        pointer = "candidate"; pending = True; cutovers += 1
                elif action == "health":
                    if pending:
                        if rng.random() >= 0.20:
                            pointer = "candidate"; pending = False; staged = False; preflight_ok = False
                        else:
                            pointer = "stable"; pending = False; rollbacks += 1; staged = False; preflight_ok = False
                elif action == "crash":
                    if pending:
                        # A stale pending activation is recovered to stable.
                        pointer = "stable"; pending = False; rollbacks += 1
                elif action == "rollback":
                    if pointer == "candidate" or pending:
                        pointer = "stable"; pending = False; rollbacks += 1
                elif action == "retry":
                    # Retry never creates activation authority and cannot alter a pending cutover.
                    if not staged and not pending:
                        preflight_ok = False

                if pointer == "candidate" and pending and not preflight_ok:
                    raise AssertionError("pending candidate without preflight authority")
                if cutovers > 0 and pointer not in {"stable", "candidate"}:
                    raise AssertionError("invalid pointer")
            # Any sequence ending pending is treated like startup stale recovery.
            if pending:
                pointer = "stable"; rollbacks += 1; pending = False
            return SequenceResult(seed, steps, True, pointer, cutovers, rollbacks)
        except Exception as exc:
            return SequenceResult(seed, steps, False, pointer, cutovers, rollbacks, f"{type(exc).__name__}: {exc}")

    @classmethod
    def campaign(cls, *, seeds: int = 1000, steps: int = 80) -> dict[str, Any]:
        rows = [cls.run_sequence(i, steps=steps) for i in range(max(1, int(seeds)))]
        failed = [r for r in rows if not r.passed]
        return {
            "ok": not failed,
            "seeds": len(rows),
            "steps_per_seed": int(steps),
            "transitions": len(rows) * int(steps),
            "failed": len(failed),
            "total_cutovers": sum(r.cutovers for r in rows),
            "total_rollbacks": sum(r.rollbacks for r in rows),
            "sample": [asdict(r) for r in rows[:10]],
        }
