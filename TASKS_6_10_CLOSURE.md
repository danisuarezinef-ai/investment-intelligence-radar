# Tasks 6–10 closure

Date: 2026-09-10
Release: 1.5.20

## 6. Hot updater recovery and rollback

CLOSED by transactional installation. Before replacing runtime binaries the updater snapshots the installed application, Simulation Lab, worker and version metadata. Any mid-install exception restores the prior binaries and version instead of leaving a mixed installation. Tests cover both a deliberately induced mid-install failure and a complete successful commit.

## 7. Specialized PAPER agents

CLOSED with the existing governed specialist set: conservative, balanced, aggressive, high_conviction and experimental. Their allocation, concentration, eligible risk tiers and stop-loss profiles are materially distinct. They remain PAPER-only.

## 8. Cloud / PC synchronization

CLOSED at the synchronization-contract level. The desktop performs cloud pulls, local pushes with origin_node/origin_id, persistent cursors and node heartbeats. Windows builds stamp PC_SYNC_VERSION from the same stable version.json used to build the release. Production observation on 2026-09-10 showed the last-seen Windows node still reporting 1.5.14 while stable had advanced; this is treated as an observable client-version drift, not silently as coherence. Release 1.5.20 is the convergence target when that client next updates/connects.

## 9. Railway restart persistence

CLOSED and production-verified. Durable Supabase authority contains forward records dating from 2026-09-08 across numerous Railway redeployments. Restore logic is idempotent, preserves persisted matured outcomes, refuses authority conflicts, and explicitly forbids backfill/reconstruction.

## 10. Forward Ledger audit

CLOSED and production-verified against public.decision_forward_ledger in Supabase on 2026-09-10. Observed 196 rows with: 0 duplicate authority keys, 0 duplicate prediction hashes, 0 incomplete rows, 0 target/cutoff/boundary/evaluation timestamp violations, 0 backfill-flagged rows and 0 lookahead-flagged rows. A reusable fail-closed auditor is included; it reports violations and performs no repair or backfill.

## Safety invariant

REAL_TRADING remains OFF. No broker path or real-money execution capability is introduced by this closure.
