# Pre-1.6 legacy PR reconciliation

This record closes the legacy-PR cleanup without re-opening or merging superseded branches.
Current main remains the only production authority.

## PR #7 — PIT universe / forward evidence
Status: **RECONCILED / CLOSED**.

Retained semantics now live in:
- `radar_universe_pit.py` — point-in-time universe handling.
- `radar_investment_memory.py` and `radar_forward_engine.py` — stricter immutable/prospective forward evidence.

The old forward-ledger implementation is not an authority and must not be reintroduced.

## PR #10 — corporate actions / costs / simulation readiness
Status: **RECONCILED / CLOSED**.

Retained semantics now live in:
- `radar_corporate_actions.py`
- `radar_cost_model.py`
- `radar_simulation_readiness.py`

No legacy branch may bypass current fail-closed readiness or evidence gates.

## PR #20 — causal runtime/scoring
Status: **RECONCILED / CLOSED**.

Retained semantics now live in:
- `radar_causal_runtime_v2.py`
- `radar_causal_scoring_v2.py`

Current causal scoring remains bounded, one contribution per independent event, with no automatic promotion authority and `REAL_TRADING=false`.

## Deletion policy
Closed/superseded PRs are historical references only. Repository files are not deleted merely because a legacy PR is closed. `tools/pre160_repo_audit_v2.py` may nominate candidates, but deletion requires explicit dependency proof plus the complete CI suite.

## Frozen safety boundary
- Windows stable version: **1.5.28**
- Setup 1.6: **not authorized**
- Automatic release/promotion/demotion: **disabled**
- Live execution: **disabled**
- `REAL_TRADING=false`
