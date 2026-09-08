# Decision Intelligence v2

## Purpose
The Radar must become a better investor, not merely a better direction classifier. Prediction, decision, sizing and evaluation are separate layers.

## 1. Master score
Compare versions on a fixed scorecard: risk-adjusted return, CAGR, Sortino, calibration, hit rate, stability, tail resilience, cost efficiency, regime robustness, abstention quality, drawdown, turnover and concentration. Report every component alongside the aggregate so the aggregate cannot hide failure.

## 2. Decision engine
Forecast -> uncertainty -> thesis state -> valuation/margin of safety -> alternatives/opportunity cost -> action (BUY/HOLD/REDUCE/AVOID/WAIT) -> paper target allocation. No execution path exists.

## 3. Opportunity cost
Every candidate competes with cash, broad benchmark, defensive benchmark and the current candidate universe. Recommendations require positive incremental utility, not merely a positive expected return.

## 4. Portfolio Intelligence
Sizing is confidence/risk aware with hard concentration and sector limits. Correlation and tail-risk reduce size. Unallocated risk budget remains cash rather than being forced into weak ideas.

## 5. Uncertainty
Keep separate: model confidence, model disagreement, data quality, epistemic uncertainty and regime uncertainty. High disagreement can force WAIT/abstention.

## 6. Persistent thesis
A recommendation carries catalysts, risks, causal chain, valuation context and explicit strengthen/weaken/kill criteria. A score change alone must not silently rewrite history. Thesis snapshots are fingerprinted.

## 7. Kill criteria
INVALIDATED is distinct from WEAKENED. Facts triggering invalidation must be recorded and attributable to a pre-existing criterion.

## 8. Prediction attribution
Store diagnostic contribution by component and counterfactual ablation delta. Attribution is not automatically causal proof.

## 9. Counterfactual lab
Re-evaluate frozen historical predictions with one component/family removed. Measure incremental objective contribution across folds/regimes/horizons; never use final holdout to choose components.

## 10. Universe expansion
Stages: current curated equities -> liquid global large/mid caps -> ETFs/indices/rates/commodities -> broader investable universe. Each asset requires identifiers, currency, venue, trading calendar and point-in-time eligibility.

## 11. Survivorship / PIT universe
Backtests on today's names carry `SURVIVORSHIP_BIAS_RISK=true`. Future schema: universe_membership(asset, universe, valid_from, valid_to, known_at, source). Include delistings, mergers, bankruptcies and historical constituents before calling long-history results definitive.

## 12. Data Quality Engine
Every datum should preserve source, observed_at, known_at, retrieved_at, quality, discrepancy, staleness and point_in_time. Conflicting providers lower confidence rather than being silently overwritten.

## 13. Source map
Priority: market/corporate actions; filings/fundamentals; macro/credit; regulation; industry/capex/supply-chain; patents/science; public contracts/hiring; geopolitics. For each provider track license/cost, coverage, historical PIT availability, latency and empirical incremental value.

## 14. Early Discovery Radar
Candidate weak signals: hiring acceleration, patent/science-to-industry, capex/orders, regulatory changes, public contracts, corporate language change and bottlenecks. Weak signals require corroboration and cannot receive high conviction from novelty alone.

## 15. 2nd/3rd order
Represent causal graph edges with timestamp/provenance/confidence. Search paths such as AI compute -> datacenter power -> grid equipment -> copper. A path is a hypothesis until supported.

## 16. Priced-in vs discovery
Investability = importance × novelty × (1-priced_in) × evidence quality × causal reach × liquidity. This prevents famous good news from automatically becoming a buy signal.

## 17. Surprise Engine
Prefer actual-vs-expected surprise to raw good/bad labels where expectations exist. Store expectation source and timestamp to remain point-in-time.

## 18. Failure Memory
Taxonomy starts with late momentum chase, narrative overvaluation, regime mismatch, correlation-as-causality, false precision and thesis drift. New patterns require repeated evidence; they are not invented after one loss.

## 19. Stable scorecard
Every release is evaluated on the same frozen dimensions and baselines. Complexity must earn its existence via out-of-sample/forward improvement.

## 20-21. Work integration protocol
External Work changes are `ACCEPT`, `MODIFY`, `REJECT`, or `NEEDS_EVIDENCE`. Verify report claims against repository/tests/database/deployment. Specifically inspect leakage, test reuse, false PASS, promotion provenance and real-trading state.

## 22. Integration target
Brain Evolution supplies candidate discovery/validation. Decision Intelligence consumes frozen model evidence and supplies decisions, theses, uncertainty and portfolio targets. Neither bypasses the other.

## 23. Internal competition
Champion vs shadow/evolutionary candidates vs ensemble vs simple baselines (equal-weight, benchmark and simple momentum/value where valid). Report complexity-adjusted benefit.

## 24. Longitudinal phase
Freeze forward predictions with immutable prediction id, created_at, model/version, features fingerprint, thesis fingerprint, horizon, target date and confidence. Evaluate only after maturity. Never edit a prediction after its outcome becomes knowable.

## 25. Autonomous Researcher (future gate)
Only after validation infrastructure is trustworthy: detect uncertainty -> formulate hypothesis -> gather PIT-safe evidence -> propose experiment -> create challenger -> walk-forward/vault test -> shadow forward test -> retain result and failure reason. Autonomous research cannot promote directly to operational champion and cannot enable real trading.

## Non-negotiables
- REAL_TRADING=false.
- No historical-news/causal feature unless its PIT availability is auditable.
- No final-test adaptive reuse.
- No forced investment: cash/WAIT is valid.
- Historical excellence is not live evidence.
