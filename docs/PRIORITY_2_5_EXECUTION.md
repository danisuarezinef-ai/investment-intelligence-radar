# Priority 2–5 execution checkpoint

Base main audited: `a91c4412e39483a403eb9953c030f127ed199792`.

## Priority 2 — Forward/OOS validation

Existing validation already enforced per-fold chronological separation, holdout, no-lookahead, immutable shadow evidence, no-backfill policy, PIT benchmark and explicit costs. The new `radar_oos_audit_v3.py` adds cross-fold chronological ordering, non-overlapping validation windows, frozen-feature declarations and PIT-membership requirements.

This audit does **not** claim investment performance. Historical or forward performance remains NOT VERIFIED unless produced by matured immutable records with benchmark and explicit cost evidence.

## Priority 3 — Allocation Engine

`radar_allocation_engine_v1.py` converts only evidence-complete BUY cards into portfolio-level requested budgets. Missing capital state or incomplete evidence blocks allocation. The weighting objective is a deterministic conservative heuristic and is explicitly **NOT empirically validated as optimal**.

## Priority 4 — Risk Engine v2

`radar_risk_engine_v2.py` adds portfolio-level gates for sector, geography, FX, liquidity, pair correlation, drawdown, position count, gross invested exposure and confidence. Missing material metadata or missing correlations blocks new capital rather than being guessed.

## Priority 5 — Integrated decision/allocation/risk

`radar_decision_allocation_v1.py` connects Decision Lab v5 → Allocation v1 → Risk v2 and returns approved/rejected target budgets. It is read-only: `execution_enabled=false`, `can_trade=false`, `REAL_TRADING=false`.

## Priority 1 — Work 01

No Work-produced PR or branch was present in GitHub at the time of this checkpoint. The already-integrated desktop UI v2 remains in main. Work 01 output must be audited separately when it exists; no completion is claimed here.
