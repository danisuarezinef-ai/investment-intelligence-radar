# Radar de Inversión — Post-150 reliability execution

Baseline main: `c98f2bc52a50ecc007ad2e875740a17c19b3a50e`  
Windows stable: `1.5.28` (unchanged)  
Scope: Cloud / Supabase / PAPER / SHADOW reliability and evidence only.  
Invariant: `REAL_TRADING=false`. No Setup, broker, live capital, automatic release, automatic promotion or automatic demotion.

## Observed production baseline

- Railway production was on the exact baseline SHA with deployment SUCCESS.
- PAPER checkpoint restore was schema v2, exact hash verified, `backfill_used=false`, `reconstructed=false`, `real_trading=false`.
- Supabase contained one current PAPER checkpoint row at schema v2 and zero `radar_pre160_decision_envelopes` at the start of this work.
- Repeated generic sync `TimeoutError('The read operation timed out')` was observed in Railway.
- Root-cause audit found bounded Python batches (250) feeding an Edge function that performed information-event and portfolio-mark database operations sequentially per row. A 250-mark batch could therefore fan out into hundreds of serial PostgREST calls before returning.
- Pre-1.6 evidence is correctly immature: calibration `n=0`, regime coverage empty, benchmark results insufficient, cost budget pending, paired Champion/Challenger sample 0, transactional provenance 0.
- Capture boundary is prospective. No historical decision is to be fabricated or backfilled.

## Tasks 1–25

| # | Task | Current state | Evidence / action |
|---:|---|---|---|
|1|Audit Supabase timeouts|IMPLEMENTED / PROD RETEST PENDING|Railway timeouts observed; sequential Edge fanout identified as a concrete latency amplifier.|
|2|Transient failure != missing data|IMPLEMENTED|Sync errors raise; telemetry explicitly states timeout is not zero/missing evidence. Cursors move only after remote success.|
|3|Bounded retries + backoff + jitter|IMPLEMENTED|Configurable 3-attempt default, exponential delay, jitter, retryable HTTP classification.|
|4|Circuit breaker|IMPLEMENTED|Consecutive terminal failures open a configurable cooldown; calls fail fast while open.|
|5|Supabase telemetry|IMPLEMENTED|Secret-free latency/error/retry/recovery/circuit/batch telemetry exposed through Cloud v5 `/supabase-health-v1`.|
|6|Sync frequency/batching audit|IMPLEMENTED|Client remains batch-capped at 250; Edge event/mark/node fanout now uses bounded concurrency 20 instead of unbounded serial work. Edge returns latency and input counts.|
|7|Idempotence under timeout|IMPLEMENTED + TESTED BY CI PENDING|Local cursors advance only after successful remote POST; immutable natural-key and origin-key guards remain in Edge.|
|8|Controlled degradation|IMPLEMENTED + TESTED BY CI PENDING|Circuit/open and timeout tests prove fail-fast/recovery semantics; production retest still required.|
|9|PAPER schema-v2 repeated restore|ONE PROD CYCLE VERIFIED / SECOND CYCLE PENDING|Current production restored schema 2 exactly. Merge/redeploy of this block will supply another real restore cycle.|
|10|Audit decision envelopes|VERIFIED CURRENTLY EMPTY|Remote envelope count observed as 0; this is correct evidence-pending state, not failure or zero performance.|
|11|Visible provenance diagnostics|IMPLEMENTED|Cloud v5 `/decision-provenance-v1` exposes exact/fallback/version/trace/blockers without inventing evidence.|
|12|First natural PAPER decision|EVIDENCE_PENDING|Must occur naturally after capture boundary. No forcing/backfill.|
|13|Trade + envelope same transaction proof|EVIDENCE_PENDING|Code exists; production proof awaits natural PAPER trade.|
|14|First natural prospective close linkage|EVIDENCE_PENDING|Required linkage remains `competitor+symbol+entry_ts`; exit fields forbidden.|
|15|Task 150 closure|EVIDENCE_PENDING|Cannot close before natural envelope + close + post-redeploy exact restore evidence.|
|16|Granular 1.6 readiness board|IMPLEMENTED|Cloud v5 separates PASS / PENDING_TIME / PENDING_SAMPLE / NOT_VERIFIED and preserves blockers.|
|17|Prospective calibration|PENDING_SAMPLE|Latest durable snapshot observed `n=0`; no synthetic calibration.|
|18|Regime × horizon maturity|PENDING_SAMPLE|Regime counts empty and diversity immature; horizon evidence pending.|
|19|Benchmark + cost sensitivity|PARTIAL / PENDING_SAMPLE|Multi-benchmark framework available but 0 matured records; cost budget has 0 closed decisions.|
|20|Anti-overfit + historical→forward transfer|PENDING_SAMPLE|Forward sample not mature enough to establish transfer. No historical result can authorize promotion.|
|21|Reconcile legacy PR #7|CLOSED AS SUPERSEDED|PIT universe semantics retained; old parallel ledger superseded by immutable Investment Memory + current Forward Engine.|
|22|Reconcile legacy PR #10|CLOSED AS SUPERSEDED|Corporate actions, costs, simulation factory/readiness semantics are present in the newer fail-closed architecture.|
|23|Reconcile legacy PR #20|IMPLEMENTED ON THIS BRANCH / CLOSE AFTER MERGE|Bounded causal scoring recovered with independent-event dedupe, health surface, max adjustment 1.5, `promotion_authorized=false`, `REAL_TRADING=false`.|
|24|Full pre-1.6 audit|IN PROGRESS|Requires exact-head CI, then production deployment and external endpoint/restore/log verification.|
|25|Gate toward 1.6.0|BLOCKED CORRECTLY|No version bump or Setup. 1.6 remains blocked until time/sample/evidence gates mature.|

## Reliability changes

Python sync now has configurable transport timeout/attempts, bounded exponential retry with jitter, circuit breaking, recovery accounting, batch telemetry and explicit evidence semantics. It never converts a timeout into an empty successful dataset.

The Supabase `radar-sync` Edge path retains immutable portfolio-value checks and source/URL event dedupe while replacing row-by-row serial fanout with bounded chunk concurrency. Intra-batch duplicate natural portfolio keys are checked before remote writes, and any mismatched duplicate fails closed.

Cloud v5 is a read-only composition layer over v4. It adds observability only; it does not modify investment decisions or promotion/trading authority.

## Release rule

Do not alter `version.json`, publish a Windows Setup or declare 1.6 ready from this work package. Production deployment is acceptable only after branch CI is green and must preserve `REAL_TRADING=false`. Tasks depending on elapsed time or natural PAPER actions remain `EVIDENCE_PENDING` until observed.
