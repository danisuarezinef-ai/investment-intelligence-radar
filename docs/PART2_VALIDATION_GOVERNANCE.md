# Part II — Validation Governance

Status: implementation candidate. REAL_TRADING=false.

## Purpose

Turn the existing shadow/forward evidence and historical laboratory into an auditable promotion pipeline that fails closed when evidence is missing, stale, backfilled, mutable, non-PIT, or degraded.

## Implemented in this package

- `radar_validation_governance_v2.py`
  - chronological walk-forward audit;
  - minimum fold requirement;
  - holdout + lookahead=false requirements;
  - immutable/no-backfill shadow record checks;
  - combined promotion + OOS + degradation review gate;
  - degradation response is recommendation-only, never automatic.
- `radar_shadow_experiment_v2.py`
  - reads the immutable forward ledger;
  - checks start-boundary/no-backfill provenance;
  - checks lookahead=false provenance;
  - requires mature outcomes for performance metrics;
  - computes confidence calibration and realized drawdown only from matured records;
  - explicitly reports benchmark evidence and costs as unavailable until genuinely measured.

## Safety invariants

- REAL_TRADING=false.
- `ready_for_live_review` is not permission to trade.
- `can_trade=false` and `auto_promote=false` remain hard outputs of the promotion layer.
- Missing degradation evidence blocks readiness.
- Missing benchmark/cost evidence is not converted to zero.
- Historical walk-forward evidence cannot substitute for live-forward evidence.
- Forward evidence cannot be backfilled.

## Known remaining gaps

- Forward benchmark attribution must be connected to the same immutable decision windows before `excess_return_pct` can be considered verified.
- Realized costs must be linked to each forward decision/portfolio episode before `costs_included=true` can be justified.
- The current promotion policy thresholds are predeclared governance defaults, not empirically proven optimal thresholds.
- Live capital remains out of scope.
