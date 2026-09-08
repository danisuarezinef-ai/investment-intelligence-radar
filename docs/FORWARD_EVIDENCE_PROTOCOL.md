# Genuine Forward Evidence Protocol

Radar already creates live predictions. This protocol makes the epistemic distinction explicit: a prediction becomes **genuine forward evidence** only when its complete payload is frozen before its outcome exists.

## Rules
- Append-only freeze; no retrospective edits.
- SHA-256 fingerprint over canonical prediction payload.
- Separate feature and thesis fingerprints.
- `data_cutoff` equals the information boundary used at prediction time.
- Outcome starts `PENDING` and is assigned only after maturity.
- 1d/1w/1m/3m horizons remain distinct.
- Historical/backfilled rows must never be relabelled as forward evidence.
- Model/version changes do not alter old ledger entries.
- `REAL_TRADING=false`.

## Why
Historical experiments can be rerun. Genuine forward evidence cannot be recreated later. Accumulating it early allows Radar to learn calibration, regime dependence, family transfer, source value and failure patterns while development continues.
