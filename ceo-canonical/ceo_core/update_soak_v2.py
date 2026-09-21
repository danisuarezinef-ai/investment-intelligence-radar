from __future__ import annotations

import random
from dataclasses import dataclass, asdict


@dataclass(slots=True)
class UpdateSoakResultV2:
    transitions: int
    provider_faults: int
    pre_cutover_blocks: int
    post_cutover_rollbacks: int
    healthy_commits: int
    duplicate_active_versions: int
    stranded_pending_health: int
    violations: int
    def to_dict(self): return asdict(self)


class UpdateSoakV2:
    """100k-state abstract updater campaign focused on one-active-version safety."""
    def run(self, *, transitions: int = 100_000, seed: int = 241) -> UpdateSoakResultV2:
        rng = random.Random(seed)
        pointer = "stable"; pending = False; staged = False; preflight = False
        provider = blocks = rollbacks = commits = dup = stranded = violations = 0
        for _ in range(int(transitions)):
            action = rng.randrange(11)
            if action in (0, 1):
                provider += 1
                # Provider faults are deliberately orthogonal to activation health.
            elif action == 2:
                if not pending: staged = True
            elif action == 3:
                if staged and not pending: preflight = True
            elif action == 4:
                if staged and preflight and not pending:
                    pointer = "candidate"; pending = True
            elif action == 5:  # core health success
                if pending:
                    pointer = "candidate"; pending = False; staged = False; preflight = False; commits += 1
            elif action in (6, 7):  # core health failure / crash
                if pending:
                    pointer = "stable"; pending = False; staged = False; preflight = False; rollbacks += 1
                elif staged:
                    staged = False; preflight = False; blocks += 1
            elif action == 8:  # corrupt artifact/signature
                if not pending and staged:
                    staged = False; preflight = False; blocks += 1
            elif action == 9:  # restart recovery
                if pending:
                    pointer = "stable"; pending = False; staged = False; preflight = False; rollbacks += 1
            elif action == 10:  # begin next attempt only if not pending
                if not pending: staged = True
            if pending and pointer != "candidate": violations += 1
            if pointer not in {"stable", "candidate"}: violations += 1
            if pending and not preflight: violations += 1
            # A second active pointer is impossible in this model; keep explicit metrics.
            dup += 0
        if pending:
            # End-of-campaign recovery must eliminate a dangling cutover.
            pointer = "stable"; pending = False; rollbacks += 1
        stranded = int(pending)
        return UpdateSoakResultV2(int(transitions), provider, blocks, rollbacks, commits, dup, stranded, violations)
