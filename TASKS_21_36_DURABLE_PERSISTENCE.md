# Tasks 21–36 — Durable PAPER Persistence Closure

Canonical continuation of the 1–20 simulator-development block. This file resolves historical numbering conflicts.

Safety invariant for all tasks: `REAL_TRADING=false`; no broker submission; no real-money orders.

21. Freeze the current durable checkpoint/state-hash evidence before transport changes.
22. Build a bounded, secret-safe connectivity/transport probe for Supabase persistence paths.
23. Determine a verified persistence transport; never infer/guess a Supavisor hostname.
24. Provide server-side atomic lease operations (acquire/heartbeat/release) suitable for API/RPC transport.
25. Migrate the PAPER runtime lease Edge Function away from unreliable per-request direct TCP where a verified API/RPC path exists.
26. Provide server-side checkpoint put/get/compare operations suitable for API/RPC transport.
27. Migrate the PAPER checkpoint Edge Function to the verified transport while preserving exact hash/schema checks.
28. Provide server-side autonomy snapshot read/write/compare operations suitable for API/RPC transport.
29. Migrate autonomy core to the verified transport while preserving fail-closed semantics.
30. In isolated v29, prove repeated lease heartbeats + persist→read→compare + exact hash reconciliation without 500/503/timeouts.
31. Deliberate Railway restart #1: require fencing, takeover, exact restore and reconciliation.
32. Deliberate Railway restart #2 with the same requirements.
33. Deliberate Railway restart #3 with the same requirements.
34. Mark `DURABLE_PERSISTENCE=VERIFIED` only if 30–33 pass; otherwise retain `NOT_VERIFIED` with exact blocker.
35. Reactivate only generic `radar-sync`; verify idempotent queue drain and absence of schema-cache/circuit-breaker storms.
36. Reactivate `learning-sync`; verify forward/brain durability remains stable. Keep simulator/closed-loop paused if stability regresses.

Evidence rules:
- Historical successful exact restores may support diagnosis but cannot substitute for tasks 30–33.
- A transient 409 during deployment handoff is valid fencing when followed by lease expiry/takeover with unchanged durable state.
- Hash mismatch, session mismatch, invalid checkpoint, unaccounted fill, or unsafe state mutation is a hard failure.
- Simulated/backfilled evidence never becomes audited forward evidence.
