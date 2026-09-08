# Part II — Forward Benchmark and Cost Evidence

Status: implementation candidate. REAL_TRADING=false.

This package adds a same-window, point-in-time equal-weight benchmark from recorded market snapshots. Entry prices use the latest observation at or before the frozen prediction timestamp; exit prices use the first observation at or after the target timestamp. At least eight constituents are required by default.

Costs are never inferred from an assumed fee schedule. Cost evidence is available only when an explicit `costs_pct`, `total_cost_pct`, or `realized_cost_pct` value is persisted in the prediction payload or outcome. Net return and excess return are therefore unavailable until gross outcome, benchmark evidence, and explicit costs all exist.

Safety invariants:
- no backfill;
- no synthetic benchmark prices;
- no assumed costs;
- missing evidence remains missing;
- REAL_TRADING=false.
