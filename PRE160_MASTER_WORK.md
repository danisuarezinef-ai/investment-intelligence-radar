# PRE-1.6 MASTER WORK — 70-task execution map

Scope: PAPER/SHADOW only. `REAL_TRADING=false` is a hard invariant. No task below authorizes a broker, real order or real capital. The next Windows Setup is intentionally deferred until the 1.6 freeze gate passes.

Status legend: **CODE_READY** = implemented on `pre160-master-work`, awaiting CI/runtime integration; **EXISTING** = already present in main and retained; **INTEGRATION** = primitives exist but still need runtime wiring; **EVIDENCE** = code exists but the scientific/operational conclusion requires future observations; **FREEZE_BLOCKED** = deliberately cannot complete yet.

| # | Task | Status | Implementation / gate |
|---:|---|---|---|
|1|Decision-level hits/errors|CODE_READY|`radar_strategy_evaluation_v1.fifo_closed_decisions/decision_metrics`|
|2|Performance attribution|CODE_READY|decision P/L + existing `radar_attribution_engine_v2` / `radar_promotion_attribution_v1`|
|3|Decision-aware v-score|CODE_READY|`radar_simulator_vscore_v1` mature closes supersede daily proxy gradually|
|4|v history|EXISTING|`radar_simulator_league_daily.v_score/v_components`|
|5|readiness history|EXISTING|League daily + promotion detail/readiness history|
|6|Explain v changes|CODE_READY|`v_change_explanation()`|
|7|Promotion Engine v2|CODE_READY|`radar_league_governance_v2` quality-aware readiness|
|8|Anti-luck promotion|CODE_READY|largest-win dependence + `anti_luck_score` gate|
|9|Champion degradation/demotion review|CODE_READY|`champion_degradation()`; no automatic model retirement|
|10|Benchmark per competitor|INTEGRATION|existing `radar_multi_benchmark_v1`; pre160 scorecard input|
|11|Realistic costs|EXISTING|agent/champion fee+spread+FX; closed-decision net P/L|
|12|Portfolio risk attribution|CODE_READY|exposure, HHI, top-position share, compliance|
|13|Drawdown depth/duration/recovery|CODE_READY|`drawdown_profile()`|
|14|Realized vs declared risk|CODE_READY|`risk_attribution()` target-vs-realized exposure|
|15|7/30/90/since inception|CODE_READY|`radar_multiwindow_ranking_v1.multiwindow_performance`|
|16|Multidimensional ranking|CODE_READY|capital/v/DD/consistency/readiness/risk-adjusted/quality modes|
|17|Race to Champion|EXISTING|League readiness + ETA UI/runtime|
|18|League milestone events|EXISTING|`radar_simulator_league_events` durable authority|
|19|Decision timeline|EXISTING|1.5.28 live PAPER positions/trades/reasons|
|20|Abstention quality|CODE_READY|`abstention_metrics()` + `abstention_gate()`|
|21|Confidence calibration|EXISTING/INTEGRATION|`radar_calibration_health_v1`, promotion calibration + optional v input|
|22|Regime tagging|EXISTING|`radar_regime_intelligence_v1`|
|23|Observed regime generalization|CODE_READY/EVIDENCE|`regime_generalization()`; replaces proxy only with >=2 regimes|
|24|Challenger diversity/anti-clone|CODE_READY|return correlation + decision Jaccard overlap|
|25|Controlled Experimental|CODE_READY|`experiment_budget()` + existing risk profile|
|26|Hall of Fame|EXISTING/CODE_READY|Supabase `brain_hall_of_fame` + `radar_strategy_archive_v1` policy|
|27|Useful Graveyard|EXISTING/CODE_READY|Supabase `brain_graveyard` + failure regime/horizon payload|
|28|Champion lineage|EXISTING/CODE_READY|League events + `champion_lineage_event()`|
|29|Automatic loss autopsy|CODE_READY|`radar_learning_journal_v1.loss_autopsy`|
|30|Anti-overfitting Score|CODE_READY|train→WF→vault→final degradation score|
|31|Historical→live transfer|CODE_READY/EVIDENCE|`historical_live_transfer()`|
|32|Quality by 1d/1w/1m/3m|CODE_READY|`horizon_quality()`|
|33|Hard quality gates|CODE_READY|`quality_gate()` fail-closed|
|34|Data Quality Score|CODE_READY|freshness/benchmark/cost/PIT/provider/forward/CA weighted score|
|35|Provider resilience|EXISTING|`radar_provider_resilience_v1`|
|36|Freshness watchdog|CODE_READY|`freshness_watch()`|
|37|Automatic lookahead audit|CODE_READY + EXISTING|`forward_timestamp_audit` + `radar_oos_audit_v3`|
|38|PAPER integrity audit|CODE_READY|cash+invested=equity, non-negative positions|
|39|Shadow/Champion separation|CODE_READY|explicit separation audit, immutable-forward requirement|
|40|Mobile-ready API contract|CODE_READY|`radar_mobile_contract_v2.mobile_summary`|
|41|Balance gadget|CODE_READY|Champion balance/v/DD + compact alert contract|
|42|Mobile League summary|CODE_READY|compact Champion/Challenger ranking payload|
|43|Intelligent alerts|CODE_READY|promotion/DD/data/cloud meaningful alerts only|
|44|Daily report|CODE_READY|`radar_reports_v1.daily_report`|
|45|Weekly report|CODE_READY|`weekly_report()`|
|46|Learning Journal|CODE_READY|falsifiable lesson model + private Supabase schema|
|47|False-learning detection|CODE_READY/EVIDENCE|cross-regime invalidation check|
|48|Challenger factory|CODE_READY|bounded mutation generator, research-only|
|49|Experiment budget|CODE_READY|capacity/share/failure penalty|
|50|Champion/ensemble research|CODE_READY/EVIDENCE|capped ensemble proposal; must forward validate|
|51|Inter-agent correlation|CODE_READY|diversity score pairwise returns|
|52|Automatic stress integration|EXISTING/INTEGRATION|`radar_stress_v2` + `stability_score()`|
|53|Survivorship bias|EXISTING|`radar_universe_pit.survivorship_audit`|
|54|Corporate actions/currency audit|CODE_READY + EXISTING|PIT corporate actions + FX verification gate|
|55|Universe evolution|CODE_READY|liquidity/data/PIT-gated research additions|
|56|Abstention Engine|CODE_READY|quality/calibration/edge fail-closed abstention|
|57|Opportunity ranking calibration|CODE_READY/EVIDENCE|rank monotonicity vs realized return|
|58|Auditable 3–6–9 lists|CODE_READY|`opportunity_369()`|
|59|Causal explanation chain|CODE_READY + EXISTING|event→mechanism→asset→signal→decision→outcome completeness|
|60|Counterfactuals|CODE_READY/EVIDENCE|explicit supplied counterfactual value-added only|
|61|Cost of error|CODE_READY|gross loss / resolved outcome burden|
|62|Capital efficiency|CODE_READY|realized P/L / entry capital|
|63|Turnover penalty|EXISTING/INTEGRATION|`radar_turnover_cost_governor_v1` + v consistency penalty|
|64|Stability Score|CODE_READY|stress + perturbation sensitivity|
|65|Confidence intervals|CODE_READY|explicit approximate CI, insufficient evidence when n<2|
|66|Integral release audit|CODE_READY + EXISTING|`release_integrity()` + existing production/release guards|
|67|Technical debt cleanup|CODE_READY|`tools/pre160_debt_audit.py` detects hard version/entrypoint/trading pins|
|68|Reduce release count|ACTIVE POLICY|all work accumulates on pre160 branch; no incremental Setup|
|69|Freeze 1.6.0 candidate|FREEZE_BLOCKED|`radar_release_freeze_v1`; requires all gates + runtime duration|
|70|Only then new Setup|FREEZE_BLOCKED|`setup_allowed` only when freeze gate passes|

## New durable evidence boundary

`20260911210000_pre160_strategy_evaluation.sql` + `radar-pre160-evaluation` Edge authority creates a server-side `capture_started_at`. Closed trades already present before that boundary are labelled `DERIVED_PREEXISTING` and are **not** forward eligible. Only closes observed after the boundary can become `PROSPECTIVE_PAPER_CLOSE`. This prevents reconstructed history from silently becoming prospective evidence.

## Release rule

Do not bump Windows version or publish another Setup for these internal steps. Merge/deploy backward-compatible Cloud changes only after CI and database/Edge validation. Freeze 1.6.0 only after runtime evidence, full release audit and all 70 rows have an acceptable verified state. Even a frozen 1.6.0 remains PAPER/SHADOW; real-money development is a separate future project gate.
