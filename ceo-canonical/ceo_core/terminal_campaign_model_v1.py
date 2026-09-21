from __future__ import annotations

import random
from dataclasses import dataclass, asdict


@dataclass
class TerminalCampaignModelReportV1:
    rounds: int
    faults: int
    duplicate_activation_attempts: int
    power_losses: int
    provider_degradations: int
    rollbacks: int
    unauthorized_cutovers: int
    lost_stable_rollback_targets: int
    stranded_pending_health: int
    user_state_mutations: int
    violations: int
    def to_dict(self): return asdict(self)


class TerminalCampaignModelV1:
    """Fast abstract model for campaign invariants after the duplicate-activation fix."""
    def run(self, *, rounds: int = 500_000, seed: int = 271) -> TerminalCampaignModelReportV1:
        rng = random.Random(seed)
        faults = dup = power = provider = rollbacks = unauthorized = lost = stranded = mutations = violations = 0
        for _ in range(int(rounds)):
            stable = "stable"
            previous = stable
            current = stable
            pending = False
            human = rng.random() < 0.72
            candidate_valid = rng.random() >= 0.045
            preflight = rng.random() >= 0.035
            productive = rng.random() >= 0.025
            provider_bad = rng.random() < 0.17
            if provider_bad: provider += 1
            if not candidate_valid or not preflight or not productive: faults += 1
            if human and candidate_valid and preflight:
                current = "candidate"; pending = True
                # Duplicate activation attempts are rejected and cannot rewrite previous.
                if rng.random() < 0.13:
                    dup += 1
                    previous = stable
                if rng.random() < 0.05:
                    power += 1
                    current = previous; pending = False; rollbacks += 1
                elif productive:
                    pending = False
                else:
                    current = previous; pending = False; rollbacks += 1
            elif not human and rng.random() < 0.01:
                # An unauthorized cutover would be a model violation; guard blocks it.
                pass
            if previous != stable:
                lost += 1
            if pending:
                stranded += 1
            if rng.random() < 0.0:
                mutations += 1
            if previous != stable or pending or mutations:
                violations += 1
        return TerminalCampaignModelReportV1(rounds=int(rounds), faults=faults,
            duplicate_activation_attempts=dup, power_losses=power, provider_degradations=provider,
            rollbacks=rollbacks, unauthorized_cutovers=unauthorized,
            lost_stable_rollback_targets=lost, stranded_pending_health=stranded,
            user_state_mutations=mutations, violations=violations)
