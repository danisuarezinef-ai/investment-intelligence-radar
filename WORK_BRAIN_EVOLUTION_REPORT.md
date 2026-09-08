# Investment Intelligence Radar — Brain Evolution v3

## Executive status

Timestamp: 2026-09-08T16:15:00+02:00  
Repository: `danisuarezinef-ai/investment-intelligence-radar`  
Development branch: `brain-evolution-v3`  
Remote commit: `ceb8441484b4f55ef33e6f3aac00d2339931080f`  
Local equivalent commit: `a63f92f`  
Draft PR: #3, Brain Evolution v3 — governance, leakage controls and persistence  
Main was not modified. Railway was not deployed.  
**REAL TRADING = OFF.**

The prior PR #1 had already been merged into main before this mission. The v3 work was therefore based on main commit `1b84a002a931ed8c376223d53abf9f8728bd1b7e` and isolated on a new development branch.

## What was found

The v2 layer provided an evidence-weight hierarchy and rudimentary evolutionary primitives, but did not satisfy the requested governance:

1. The historical laboratory used the final test in `accepted` and could immediately replace the active model. This allowed historical evidence to bypass live validation.
2. Training folds did not purge labels whose future outcome overlapped validation, and had no embargo.
3. Vault results participated in challenger ranking/selection.
4. Vault openings, reuse and deep-final-test qualification were not recorded or guarded.
5. Shadow predictions were not stored immutably.
6. Lineages omitted family, mutation, specialization, training method and feature genealogy.
7. Anti-overfitting only penalized fold dispersion, regime spread and basic complexity.
8. Ensemble disagreement/abstention and family vote compression were absent.
9. The learning sync excluded Brain tables and `historical_challenger_results`.
10. Several remote Brain tables lacked stable `origin_node/origin_id`; the historical challenger relation was incompatible with origin-based sync.
11. Dashboard data was sparse, and Windows had no Brain Evolution summary.
12. Supabase already had v2 Brain tables with RLS enabled, but no Brain lineages/evidence yet.

## Implemented

### Temporal and promotion safety

- Added `purged_temporal_split`: a training observation is excluded if its `future_date` reaches the validation boundary or embargo window.
- Challenger selection now uses development walk-forward evidence only.
- The already selected candidate is subsequently qualified/rejected by Vault and final historical test.
- Historical success can create only a `shadow_champion` record. `run_historical_lab` no longer retires/replaces the active model.
- Promotion gate requires walk-forward, Vault, final historical test, and positive live evidence with minimum live N.

### Evolutionary memory

- Expanded lineage schema: family, mutation, specialization, training method, features, timestamps and explicit lifecycle status.
- Added 12 diversity families.
- Added generation-run, Vault-event, shadow-prediction, Hall-of-Fame and Graveyard persistence.
- Failed/rejected model storage is supported; no candidate results were fabricated during this mission.

### Vault governance

- Registered eight rotating Vaults and one `deep_final_test` Vault.
- Deep Vault requires a qualified finalist.
- Vault use for training or candidate selection raises an error.
- Every opening records candidate, purpose, time, opening count, and a reuse penalty.

### Live-forward and uncertainty

- Shadow predictions are frozen under a deterministic/explicit key.
- Outcomes can be written only once; a second evaluation raises an immutability error.
- Historical→live transfer returns `null` when no live evidence exists.
- Ensemble combines correlated models at family level, exposes disagreement/confidence, and can abstain.

### Anti-overfitting

The score now exposes separate penalties for fold dispersion, regime dependence, asset concentration, complexity, period sensitivity, turnover, trade concentration, horizon dependence and Vault deterioration. Missing empirical inputs are not fabricated.

### Persistence and sync

- Added all Brain tables and `historical_challenger_results` to incremental learning sync.
- Local SQLite ids are stripped; remote payloads use `origin_node/origin_id`.
- Historical child rows use `run_origin_node/run_origin_id`.
- Added a regression test proving Brain sync is incremental and does not resend rows on a second identical sync.

### Dashboard and Windows

- Brain dashboard now exposes champion count, shadow count, generation, tested/surviving candidates, Hall of Fame, Graveyard, Vault/deep Vault, transfer evidence, meta-learning, disagreement, confidence, abstention, and `real_trading=false`.
- Windows summary panel now summarizes champion, generation, shadow count, historical candidate count, live N, confidence, sync and REAL TRADING OFF.

## Tests and actual results

Command:

```bash
UV_CACHE_DIR=/tmp/uv-cache XDG_CACHE_HOME=/tmp LOCALAPPDATA=/tmp uv run --with pytest python -m pytest -q
```

Final result:

```text
33 passed in 96.44s (0:01:36)
```

Earlier confirming runs:

- 32 passed in 97.39s.
- 32 passed in 94.64s.
- Python compile-all: PASS.
- Manual Brain smoke test: PASS.
- `git diff --check`: PASS before commit.

Synthetic tests validate algorithms and invariants; they are not investment-performance evidence.

## Supabase

Project: `wvmiludqzdepqmjhfwos` (ACTIVE_HEALTHY at inspection).

Applied and verified migrations:

- `20260908160420 brain_evolution_v3_governance` (remote timestamp assigned by Supabase; repository file `20260908170000_brain_evolution_v3_governance.sql`).
- `brain_evolution_v3_sync_provenance` was successfully applied; repository file `20260908171000_brain_evolution_v3_sync_provenance.sql`.

Verified after migration:

- 9 Vault registry rows.
- 1 sealed deep Vault.
- RLS enabled on `brain_vault_events`, `brain_shadow_predictions`, and `brain_generation_runs`.
- No public RLS policies were created for those tables.
- Stable origin columns/indexes added for cross-node sync.
- `historical_challenger_results.run_id` made nullable and origin relation columns added.

No production Brain evidence rows were inserted.

## Current empirical state

Supabase query at close:

- Active model: `2.0.0`.
- Historical lab runs: 1.
- Accepted historical runs: 0.
- Historically promoted runs: 0.
- Historical challenger rows: 0.
- Predictions: 56.
- Prediction outcomes: 0.
- Brain lineages: 0.
- Live-forward evidence rows: 0.

Therefore:

- Historical score: NOT VERIFIED / null.
- Live score: NOT VERIFIED / null.
- Transfer score: NOT VERIFIED / null.
- Live N: 0.
- Shadow champions: none verified.
- Operational Brain champion: none registered; legacy active model remains `2.0.0`.
- Challengers accepted/rejected by v3 on real data: none.

## CI, Windows build and Railway

- GitHub branch: VERIFIED.
- Draft PR #3: VERIFIED.
- CI for remote commit: **NOT RUN**. The only workflow is configured for pushes to `main` or manual dispatch, and no run exists for commit `ceb8441`.
- Windows build: **NOT VERIFIED** in this Linux Work environment.
- Installer build: **NOT VERIFIED**.
- Railway deployment: **NOT PERFORMED** because CI/Windows build were not observed and the task prohibits deploying an unvalidated branch.
- Railway `/health`, `/dashboard-v2`, `/brain-evolution`, logs and post-deploy learning: **NOT VERIFIED**. Network policy blocked direct endpoint inspection.

## Methodological limitations and pending work

1. Historical universe is the current static 16-symbol universe. All historical performance remains marked **SURVIVORSHIP BIAS RISK** until point-in-time membership is available.
2. Historical depth is approximately the collector's configured 390-day range, not multiple economic cycles. Named Vaults older than available prices cannot yet produce evidence.
3. Corporate actions, currencies, delistings, changing memberships and point-in-time fundamentals/news are not sufficiently represented for definitive historical claims.
4. Cost models exist in paper-agent simulation, but the v3 historical objective does not yet have audited point-in-time spread, slippage, FX, liquidity or capacity data.
5. Regime taxonomy in the historical lab is currently limited to market-derived risk-on/risk-off/rotation/mixed; inflation/rate/crisis labels need point-in-time macro series before use.
6. Causal features remain zero in market-only historical observations. This is correct and avoids pretending current causal knowledge existed historically.
7. Meta-learning tables exist, but allocation must remain inactive until meaningful live N accumulates.
8. Real sync against the production HTTP ingestion endpoint after deployment remains unverified; only the payload and incremental/idempotence unit path was tested.
9. The `historical_challenger_results` table had zero rows at inspection, so no v2 challenger result was silently reclassified.
10. Run CI manually on PR #3, verify the Windows/installer artifacts, review, merge only if green, then deploy Railway and inspect health/dashboard/logs/Supabase sync.

## Reproduction

1. Check out `brain-evolution-v3` at `ceb8441484b4f55ef33e6f3aac00d2339931080f`.
2. Use Python 3.12 and run the pytest command above.
3. Confirm all 33 tests pass.
4. Confirm the two v3 migrations exist in `supabase/migrations`.
5. Confirm Supabase lists the governance and sync-provenance migrations and RLS on all new tables.
6. Do not enable any real broker path. This repository implements paper simulation only.
7. Do not merge/deploy until CI and Windows artifacts are observed.

## Final safety confirmation

**REAL TRADING = OFF.** No real broker integration or money-execution route was added.
