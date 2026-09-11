# NEXT PRE-1.6 INTEGRATION — tasks 71–90

Scope: backend/Cloud/PAPER/SHADOW only. No Windows version bump and no Setup publication or packaging for this block. `REAL_TRADING=false` remains invariant.

| # | Task | Current state |
|---:|---|---|
|71|Verify merged main and stable 1.5.28 immutability|VERIFIED — stable manifest unchanged|
|72|Deploy exact merged main SHA to Railway Cloud|PENDING MERGE/DEPLOY|
|73|Start durable capture boundary; classify legacy closes|PENDING PRODUCTION CAPTURE|
|74|Live pre-1.6 aggregator per competitor|IMPLEMENTED — runtime verification pending|
|75|Competitor-specific benchmark evidence|IMPLEMENTED / EVIDENCE PENDING|
|76|Confidence calibration|IMPLEMENTED / PROSPECTIVE SAMPLE PENDING|
|77|Stress/stability|IMPLEMENTED FAIL-CLOSED / EXPOSURE EVIDENCE PENDING|
|78|Turnover/cost governor|IMPLEMENTED|
|79|Regime/horizon evidence|WIRED FAIL-CLOSED / PIT REGIME EVIDENCE PENDING|
|80|Data-quality and forward-integrity gates|IMPLEMENTED|
|81|Promotion-v2 scorecards without auto-promotion|IMPLEMENTED|
|82|Champion degradation watch without auto-demotion|IMPLEMENTED|
|83|Automatic loss autopsies as falsifiable hypotheses|IMPLEMENTED — PROSPECTIVE LOSSES ONLY|
|84|Hall/Graveyard candidates without lineage mutation|IMPLEMENTED — CANDIDATE INBOX ONLY; APPLIED=false|
|85|7/30/90/inception summaries|IMPLEMENTED|
|86|Auditable 3-6-9 opportunity groups|IMPLEMENTED|
|87|Mobile evidence/readiness enrichment|IMPLEMENTED|
|88|Pre-1.6 health/readiness + freeze blockers|IMPLEMENTED|
|89|Debt/integrity scanners in backend CI|VERIFIED ON BRANCH CI|
|90|Backend CI separated from Windows packaging|VERIFIED POLICY; NO BACKEND-TRIGGERED SETUP|

## Evidence semantics

`IMPLEMENTED` does not mean the investment hypothesis is proven. Calibration, stress, regime generalization, promotion readiness and related quality claims remain blocked until their prospective evidence requirements are satisfied. Missing evidence is returned as an explicit blocker, never synthesized as a neutral score.

## Durable boundary

The production Edge authority creates `capture_started_at` before the first evaluation persist. Existing closed PAPER trades with `exit_ts < capture_started_at` become `DERIVED_PREEXISTING` and `forward_eligible=false`; only later closes can become `PROSPECTIVE_PAPER_CLOSE`. Automatic loss lessons consume prospective closes only.

## Archive safety

Hall/Graveyard suggestions are written only to `radar_strategy_archive_candidates`. The table enforces `applied=false`; Brain Evolution Hall/Graveyard and Champion lineage are not mutated by this integration block.

## Release policy

Windows packaging is path-gated and remains manual/Windows-facing only. Backend/Cloud development does not create a Setup. Candidate 1.6.0 remains blocked by the existing freeze gate and future evidence duration.
