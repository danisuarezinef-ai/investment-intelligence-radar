# Radar de Inversión — Autonomy Checklist v25

This checklist maps the 20-task autonomy block to concrete runtime/code evidence. It does not claim elapsed-time evidence that has not occurred.

1. PR/CI closure — governed by Brain + Windows CI before merge.
2. Windows Simulation Lab — packaged and smoke-launched by Windows CI.
3. Historical depth — autonomous research retries `collect_history()` and requires >=90 days before research.
4. Continuous Experiment Brain — generation-dependent hypotheses run continuously.
5. Experiment scheduler — integrated in `radar_autonomous_simulator_v1`.
6. Walk-forward engine — strict chronological train/validation/test protocol in `radar_simulation_research_v4`.
7. Stress Lab — base, 2x/4x costs, gap, volatility, sideways, missing-data and shock scenarios.
8. Multidimensional ranking — return, Sharpe, stability, drawdown, stress tail risk and costs.
9. Anti-overfitting — fold stability, positive-fold fraction, train/test divergence and stress-survival gates.
10. Experiment funnel — SIMULATED -> SHADOW_REVIEW/GRAVEYARD; PAPER requires independent forward gates; no direct live promotion.
11. Experiment graveyard — persistent `experiment_memory` prevents useless repeats.
12. Challenger diversity — family-level diversity filter + persistent seen-config rejection.
13. Autonomous PAPER portfolio — persistent cash/positions/trades/P&L and scheduled PAPER cycles.
14. Forward outcomes — idempotent mature-outcome resend, no backfill.
15. Continuous Learning Loop — runtime learning daemon remains separated from simulated research.
16. Champion/Challenger — `radar_champion_challenger_v2`, current-champion-aware, forward-only, recommendation-only.
17. Self-repair — `radar_recovery_orchestrator_v2`, bounded fail-closed recovery with missing-as-missing preservation.
18. Persistence/restart — simulator state, run audit and experiment results persist; interrupted runs are marked.
19. Brain/simulator panel — read-only dashboard exposes active/graveyard experiments, SHADOW candidates, simulator, PAPER, forward, learning, E2E and soak status.
20. Final 24/7 test — `radar_autonomy_e2e_v1` records real-time healthy ticks and only returns `VERIFIED_24H_AUTONOMY` after >=24 actual hours, sufficient ticks, and observed cycle + experiment progress. No backfill is allowed.

## Safety invariant

`REAL_TRADING = FALSE` throughout this block. No broker path, real order submission, automatic live promotion, or reconstruction of forward decisions is introduced.
