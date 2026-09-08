# Simulation + Memory + Learning + Champion v2

Status: implementation candidate. REAL_TRADING=false.

## Scope

This package closes the first integrated loop:

market/paper agents -> Simulation Engine v2 -> episodic decision memory -> guarded/meta learning -> Champion meta-decision -> new forward episodes.

## Simulation Engine v2

- Five existing paper agents remain independent.
- Forward marks are persisted in `simulation_runs`, `simulation_marks`, `simulation_ledger`.
- Historical replay is point-in-time by construction: a decision only receives price observations available on or before that replay date.
- Fees, spread and FX costs are applied using each agent configuration.
- Metrics: return, benchmark return, alpha, max drawdown, Sharpe, Sortino, trades and total costs.
- Ledger records BUY/SELL/MARK events.

## Decision Memory v2

Each episode stores state, evidence, hypothesis, action, confidence, alternatives, allocation, reason and tags. Outcomes are single-assignment. Retrieval supports symbol, regime, horizon and tags. Aggregated memory tracks reward, hit-rate and calibration error.

## Learning Engine v2

- Reuses the existing guarded chronological holdout learner.
- Adds agent skill estimates derived from simulation marks.
- Persists meta-learning cycles.
- No automatic operational promotion and no real trading.

## Champion meta-decision

Champion is a meta-agent, not a sixth fixed strategy. It weights paper-agent evidence using observed paper quality, risk and decision memory. It can return `ABSTAIN`, which is mandatory when confidence/consensus is insufficient.

## Runtime

`radar_orchestrator_v2.fast_cycle()` is intended after each normal market/paper-agent step.
`radar_orchestrator_v2.deep_learning_cycle()` is intended at a slower cadence.
`system_v2_health()` exposes an auditable combined status.

## Promotion gates

This package must remain simulation-only until tests and forward evidence justify later promotion. `REAL_TRADING=false` is invariant.
