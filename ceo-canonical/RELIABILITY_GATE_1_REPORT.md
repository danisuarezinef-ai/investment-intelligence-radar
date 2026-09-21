# Reliability Gate 1 — Recovery Fail-Closed Hardening

Candidate: `1.5.69-rc1-recovery-failclosed`
Base persisted package: `1.5.58-rc1-productive-stall-escape`
Intermediate audited candidate: `1.5.68-rc1-recovery-storm-hardening`
Status: LOCAL CANDIDATE — NOT INSTALLED / NOT PUBLISHED

## Field symptom
The installed 1.5.58 runtime was observed producing recovery storms (including 159, 351 and 375 recoveries in real sessions) while completing only a few useful tasks. The failure mode is in the orchestration/recovery path rather than the difficulty of the user goal.

## Original root cause
The live worker reconciler could convert an orphaned `RUNNING` task to `RETRY` without a complete fail-closed recovery budget. The scheduler could also dispatch an exhausted task without an independent final admission check. This allowed a work unit to cycle through worker recovery far beyond a reasonable budget.

## Audit findings from 1.5.68 and corrections in 1.5.69

### A1 — BLOCKED_SAFE must be an invariant
1.5.68 represented safe blocking as `TaskStatus.BLOCKED` plus metadata. Several generic readiness/reconciliation layers could reopen such a task to `READY`.

1.5.69 adds `ceo_core/blocked_safe_state_v1.py` and makes the fail-closed latch explicit. Scheduler reconciliation, queue rebuilding, graph refresh, dependency reconciliation, decomposition/readiness, resume recovery, worker lifecycle, replanning, fallback orchestration and autonomous-loop recovery preserve a blocked-safe task. Only an explicit audited strategy/replan release may unlatch it.

### A2 — Recovery storm breaker lifecycle
The global breaker now owns and cleans its suppression state. At 12 worker recoveries without a new productive completion it opens, suppresses new automatic internal recovery/dispatch, and exposes `BLOQUEADO`. When a genuinely new productive completion appears, its own suppression ownership and breaker state are cleared and the operator state returns to `ACTIVO`.

### A3 — Strategy change must be real
After repeated equivalent failures, CEO records that a strategy change is requested and what provider failed. A strategy change is marked applied only when the routed provider is actually different or a real local deterministic fallback is selected. If only the same provider is available, the scheduler does not call it again; the task enters `BLOCKED_SAFE` with reason `strategy_change_unavailable`.

### A4 — Restart and end-to-end fail-closed qualification
Added `scripts/dev292_recovery_failclosed_qualification.py` covering:
- blocked-safe invariance across generic reconciliation layers;
- breaker open/atomic close;
- restart at 5/6 recoveries followed by terminal sixth recovery;
- persistence of an open global breaker through restart;
- no provider call when a requested strategy change cannot actually be applied;
- watchdog timeout path feeding the same bounded recovery/strategy gate;
- no autonomous recovery ladder for a blocked-safe task.

## Recovery policy
- Maximum 6 automatic live-worker recoveries per work unit.
- Two equivalent repeated failure fingerprints require a real strategy change request.
- Fingerprint includes task, reason/error, provider and recovery strategy.
- Maximum 12 new worker recoveries without a productive completion before the global storm breaker opens.
- Exhausted tasks fail closed rather than returning to dispatch.
- Historical recovery counts are baselined on upgrade; old incidents do not immediately brick the upgraded runtime.
- Deterministic local `Clarify & lock goal` fallback remains available and regression-tested.

## Qualification result
PASS:
- DEV291 Reliability Gate 1 qualification
- DEV292 Recovery fail-closed qualification
- DEV212 continuity-loop regression
- DEV221 productivity-hardening regression
- DEV231 long-horizon regression
- DEV281 productive-stall-escape regression
- Python compileall

DEV292 explicitly verifies:
- `BLOCKED_SAFE` remains blocked through scheduler reconciler, queue rebuild, graph, dependency manager, decomposer, resume and director reconciliation;
- breaker opens at 12 and closes after real productive progress;
- recovery count survives checkpoint/restart at 5/6, then sixth recovery blocks safely;
- open breaker survives restart and denies dispatch;
- fake strategy change with one available provider results in 0 provider calls and safe block;
- watchdog recovery cannot repeatedly call the same provider when no alternative exists;
- blocked-safe tasks do not spawn a new autonomous recovery ladder.

## Provenance limitation before Windows cutover
This candidate is cumulative relative to the persisted 1.5.58 package plus the externally implemented Reliability Gate 1 corrections. It does **not** prove that any unpersisted code changes created locally by CEO on the user's Windows machine during later stalled objectives are included. Before physical cutover, capture/compare the local candidate/workspace if preserving such local code is required.

## Release status
Candidate only. Do not publish or install until the package audit and controlled Windows cutover are explicitly authorized.
