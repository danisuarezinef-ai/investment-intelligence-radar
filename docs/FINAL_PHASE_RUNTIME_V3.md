# Runtime v3 — final shadow/paper governance phase

This phase extends the forward-only investment stack without enabling real-money execution.

## Implemented

- `radar_validation_runtime_v3.py`: unified read-only validation surface.
- `radar_regime_intelligence_v1.py`: fail-closed regime classification and conservative budget/confidence multipliers.
- `radar_paper_execution_v2.py`: simulated spread, slippage, fees, participation limits and partial fills.
- `radar_provider_resilience_v1.py`: provider health, circuit-open policy, failover ordering and multi-source price consensus.
- `radar_promotion_governance_v2.py`: explicit Shadow -> human review -> paper-only boundary.
- `radar_autonomous_loop_v1.py`: OBSERVE -> HYPOTHESIZE -> EVIDENCE -> VALUE -> RISK -> COMPARE -> DECIDE -> ALLOCATE -> OBSERVE OUTCOME -> LEARN -> REASSESS, restricted to shadow/paper governance.
- `cloud_service_v3.py`: read-only `/validation-v3` endpoint.
- Windows workflow concurrency split by event/ref so PR validation cannot cancel main stable publication and vice versa.

## Evidence semantics

Historical and prospective evidence are not interchangeable. Runtime v3 does not mark strategy performance as verified. Benchmark/cost counts from the forward experiment are normalized to coverage fractions before promotion evaluation. Missing regime, degradation, benchmark, cost, liquidity or execution evidence remains fail-closed.

## Execution boundary

`REAL_TRADING = False` remains mandatory. There is no broker connection and no live order submission path in this phase. Passing the Shadow -> Paper gate plus explicit human approval can authorize simulated paper execution only. It cannot authorize live review or real trading.

## NOT VERIFIED until CI completes

- full test suite on the final branch head;
- Windows application/updater/Setup.exe build on the final branch head;
- cloud deployment of `cloud_service_v3.py`;
- externally reachable `/validation-v3` response;
- any investment performance claim.
