# Decision Lab v3 — next queue

Execute only after/alongside validation of Decision Intelligence v2 and without overlapping Brain Evolution ownership.

1. Persist Investment Memory tables in production schema with RLS and origin-node/origin-id idempotent sync.
2. Add thesis lifecycle event store: NEW→ACTIVE→STRENGTHENED/WEAKENED→INVALIDATED/CLOSED; prohibit destructive history edits.
3. Add immutable feature/thesis/model fingerprints to every forward prediction.
4. Start a shadow-only daily forward ledger as soon as integration tests are green; never backfill it as if forward.
5. Build outcome maturity scheduler for 1d/1w/1m/3m using market calendars.
6. Add benchmark snapshots: cash/risk-free proxy, broad index, equal-weight, simple momentum/value where PIT-safe.
7. Build calibration/Brier/reliability reports by horizon, regime and confidence bucket.
8. Measure selective prediction: coverage vs performance as abstention threshold changes.
9. Add portfolio attribution: selection, sizing, sector/factor, FX, costs and cash contribution.
10. Add expected shortfall/CVaR and drawdown-duration controls to portfolio risk.
11. Add covariance shrinkage / robust correlation estimator; do not trust tiny-sample raw correlations.
12. Add scenario library with provenance and separate assumption-based from empirically estimated shocks.
13. Build thesis-to-price decomposition: what changed—fundamentals, multiple, macro, sentiment, FX?
14. Add source/evidence conflict graph and confidence penalties for unresolved contradictions.
15. Add stale-evidence decay and empirically learn half-life only from out-of-sample evidence.
16. Build duplicate/narrative clustering so repeated copies of one story count once.
17. Add novelty vs corroboration distinction: novel weak signal gains attention, corroborated signal gains confidence.
18. Build expectation store (consensus/market-implied/model-implied) with known_at timestamps.
19. Add event-study framework around genuine surprises with pre-registered windows.
20. Add causal-edge registry with provenance, confidence, first_known_at and falsification evidence.
21. Add bottleneck capacity/demand data adapters; do not score absent data as zero evidence.
22. Add cross-asset context adapters for rates, FX, credit, commodities and volatility.
23. Build regime-transition ensemble and probability calibration, not hard regime labels only.
24. Build research-question ledger: question→evidence→conclusion→decision impact→later correctness.
25. Learn Value of Information from realized decision improvement, after sufficient sample.
26. Add Investment Committee persistence: preserve bull/bear/valuation/macro/causal/risk votes independently.
27. Add Red-Team gate for high-conviction shadow recommendations; record attacks and responses before outcome.
28. Add pre-mortem library and later score which anticipated failure modes actually occurred.
29. Build decision-quality score independent of outcome luck (process quality vs realized P&L).
30. Add regret analysis: chosen action vs best ex-post alternative, clearly labelled hindsight diagnostic.
31. Build opportunity-set breadth metrics so performance is not confused with favorable universe selection.
32. Add liquidity/capacity tiers and realistic paper implementation constraints.
33. Add tax-aware layer only as optional jurisdiction-specific simulation, never assumed globally.
34. Add currency/base-currency risk budget and hedged/unhedged paper benchmarks.
35. Add corporate-action PIT pipeline and delisting-return handling before deep historical claims.
36. Add PIT universe membership adapters and explicit survivorship audit report.
37. Add data-provider reconciliation tests and quarantine for anomalous prices/fundamentals.
38. Build model/data drift monitors with alert thresholds learned conservatively.
39. Build intelligence dashboard v3 with Prediction→Thesis→Debate→Decision→Allocation→Outcome→Attribution→Learning trace.
40. Add one-click audit bundle exporting hashes, provenance, model version, evidence and decision trail for any recommendation.
41. Define promotion criteria from Decision Intelligence v2 to stable release; require full tests + Brain compatibility + forward ledger integrity.
42. Run simple-baseline challenge before accepting each new complex component.
43. Measure incremental value of each component by ablation on validation only; final/live remain untouched.
44. Establish complexity budget: components with no durable incremental value are disabled/retired, not accumulated forever.
45. Design autonomous research sandbox with strict permissions: proposal/experiment only, no production promotion and no real trades.
46. Add research reproducibility package: seed, cutoff, data snapshot IDs, code commit, parameters and results.
47. Add negative-results registry so failed hypotheses reduce repeated research waste.
48. Add portfolio-level thesis conflict detector (multiple positions depending on the same hidden macro assumption).
49. Add concentration of evidence metric (many recommendations depending on one source/factor).
50. Final integration audit and controlled release candidate. REAL_TRADING remains OFF.
