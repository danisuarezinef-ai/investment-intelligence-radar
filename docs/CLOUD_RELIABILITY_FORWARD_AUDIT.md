# Cloud reliability and forward evidence audit

This audit describes wiring visible in the repository. A module or unit test is
not evidence that a stage has run in production. Live classifications must be
confirmed from the deployed `/validation-v3` and `/ops-health` responses.

## Forward pipeline

| Stage | Code | Connected/persisted path | Classification before production verification |
|---|---|---|---|
| Market data | `radar_core.collect_market` | Worker loop → `market_snapshots` | PARTIAL: live execution must be observed |
| Prediction | Decision/forward ledgers | Runtime cycles → prediction ledger | PARTIAL: freshness and rows must be observed |
| Decision | Decision Lab/runtime | Fast/deep cycle → decision records | VERIFIED CODE ONLY |
| Allocation | Allocation Engine | Decision plan → shadow capture | VERIFIED CODE ONLY |
| Risk | Risk Engine v2 | Allocation approval/rejection | VERIFIED CODE ONLY |
| Shadow decision | Shadow Portfolio v2 | Fixed boundary → immutable decision rows | PARTIAL: boundary/rows must be observed |
| Outcome | Forward Evidence Engine | Matured ledger evaluation | PARTIAL: matured rows must be observed |
| Benchmark | Forward benchmark | Prospective outcome comparison | PARTIAL: coverage must be non-null and observed |
| Cost | Paper execution/cost evidence | Explicit simulated cost assumptions | PARTIAL: coverage must be non-null and observed |
| Attribution | Attribution v2 | Runtime summary | VERIFIED CODE ONLY |
| Learning | Learning Loop v2 | Runtime summary/worker loop | PARTIAL: last run must be observed |
| Degradation | Degradation Engine v2 | Current vs reference evidence | VERIFIED CODE ONLY |
| Promotion | Governance v2 | Fail-closed shadow→paper gate plus human approval | VERIFIED CODE ONLY |

Historical lab, replay and simulation outputs are `HISTORICAL` or `SIMULATED`.
Shadow records are `SHADOW FORWARD` only after prospective capture. Paper
execution is `PAPER`. `LIVE REAL` is disabled. No audit endpoint writes ledger
rows or backfills missing evidence.

## Windows/cloud contract

| Client path | Server owner | Method/auth | Contract note |
|---|---|---|---|
| `/health` | base worker | GET/public | Cloud state and runtime snapshot |
| `/snapshot` | base worker | GET/public | Counts, prices, events and status |
| `/dashboard-v2` | cloud v1/v2 | GET/public | Learning dashboard |
| `/notifications` | base worker | GET/public | Notification list |
| `/pc-sync` | cloud v1/v2 | POST/Bearer | PC observation forwarding |
| `/node-heartbeat` | base worker | POST/Bearer | Upserts node ID, type, capabilities, client version and last seen |
| `/validation-v3` | cloud v3 | GET/public/read-only | Unified fail-closed validation evidence |
| `/ops-health` | cloud v3 | GET/public/read-only | Operational telemetry without secrets |

Desktop GET timeout is 7 seconds; POST timeout is 8 seconds. Refresh runs every
5 seconds, while heartbeat submission is rate-limited client-side to once per
60 seconds and only when a control token exists. HTTP 401 clears the locally
stored token. Other heartbeat errors are swallowed by the UI, so server-side
provider and endpoint telemetry remains important.

## Provider failover

The live market collector tries Yahoo query1, Yahoo query2, Stooq.com quote,
Stooq.pl quote, and finally the two Stooq daily-history endpoints. Quote
timeouts are 15 seconds (history fallback 20 seconds). There is no explicit
rate-limit telemetry and no live circuit breaker in this collection path.
`/ops-health` therefore reports those fields as `NOT_VERIFIED` and
`NOT_IMPLEMENTED`; it does not claim operational redundancy merely because the
fallback code exists.

## Freshness policy

Market, events, predictions, cloud sync and forward outcomes have separate
thresholds. Every threshold is exposed with the label `POLICY DEFAULT / NOT
EMPIRICALLY VALIDATED`. Missing timestamps produce `INSUFFICIENT_DATA` and a
null age, never a synthetic zero.

## Identity/update compatibility

The display name and installer output are Radar de Inversión and
`Radar_de_Inversion_Setup`. Stable executable names, `RadarUpdate.zip`, update
channel URLs and local data identifiers remain compatible with installed 1.5.5
clients. Rename/release work is intentionally not duplicated here.
