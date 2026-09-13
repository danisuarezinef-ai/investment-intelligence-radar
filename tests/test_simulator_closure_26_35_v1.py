from datetime import datetime, timedelta, timezone

import radar_simulator_closure_26_35_v1 as c

NOW = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)


def test_scorecard_suppresses_ratios_until_sample_is_large_enough():
    out = c.learning_scorecard({
        "uptime_pct": 99.9, "valid_forward_hours": 50, "cycles": 100, "decisions": 90,
        "trades": 10, "abstentions": 80, "gross_pnl": 5, "net_pnl": 4,
        "max_drawdown": 1, "turnover": 2, "costs": 1, "errors": 0, "recoveries": 1,
        "persistence_integrity": True, "historical_to_paper_transfer": 0.5,
        "breakdowns": {"agents": {}, "regimes": {}, "horizons": {}},
        "return_observations": 10, "sharpe": 9.9, "sortino": 10.1, "real_trading": False,
    })
    assert out["status"] == "SCORECARD_VALID"
    assert out["sharpe"] is None and out["sortino"] is None
    assert out["ratio_sample_status"] == "NOT_ENOUGH_DATA"


def test_disaster_matrix_requires_every_scenario_and_exact_or_fail_closed():
    names = ["process_kill", "partial_order_restart", "railway_redeploy", "supabase_outage",
             "supabase_timeout", "price_provider_failure", "corrupt_price", "stale_price",
             "invalid_symbol", "duplicate_message", "duplicate_instance", "restart_mid_persist"]
    rows = [{"scenario": n, "outcome": "EXACT_RECOVERY", "state_hash_equal": True,
             "accounting_reconciled": True, "no_duplicate_orders": True, "real_trading": False} for n in names]
    assert c.disaster_recovery_matrix(rows)["status"] == "PASS"
    rows[0]["state_hash_equal"] = False
    assert c.disaster_recovery_matrix(rows)["status"] == "FAIL"


def test_distributed_singleton_requires_exact_owner_and_session():
    lease = {"lease_name": "autonomous-paper", "owner_id": "r1", "session_id": "s1",
             "heartbeat_at": (NOW - timedelta(seconds=20)).isoformat(),
             "expires_at": (NOW + timedelta(seconds=100)).isoformat(), "epoch": 2, "real_trading": False}
    assert c.distributed_singleton_gate(lease, owner_id="r1", session_id="s1", now=NOW)["status"] == "HELD"
    assert c.distributed_singleton_gate(lease, owner_id="r2", session_id="s1", now=NOW)["status"] == "BLOCKED"


def test_runtime_wiring_fail_closed_on_missing_gate():
    gates = {k: {"status": "PASS"} for k in ["restore", "continuity", "lease", "market", "execution", "risk", "accounting", "learning"]}
    out = c.runtime_wiring_gate(gates)
    assert out["status"] == "RUNTIME_CHAIN_BLOCKED"
    assert out["paper_cycle_allowed"] is False


def test_market_pipeline_rejects_stale_duplicate_or_gap():
    good = {"symbol": "MSFT", "provider": "x", "observed_at": (NOW - timedelta(seconds=20)).isoformat(),
            "price": 100.0, "market_open": True, "duplicate": False, "silent_gap": False,
            "stale": False, "snapshot_hash": "h", "real_trading": False}
    assert c.market_pipeline_gate(good, now=NOW)["status"] == "PASS"
    good["stale"] = True
    assert c.market_pipeline_gate(good, now=NOW)["status"] == "FAIL"


def test_execution_realism_requires_all_friction_controls():
    x = {"spread_bps": 2, "slippage_bps": 1, "fees": 0.5, "available_volume": 1000,
         "partial_fill_modeled": True, "rejects_modeled": True, "cancels_modeled": True,
         "market_hours_enforced": True, "gap_risk_modeled": True, "size_vs_volume_checked": True,
         "real_trading": False}
    assert c.execution_realism_gate(x)["status"] == "PASS"
    x["market_hours_enforced"] = False
    assert c.execution_realism_gate(x)["status"] == "FAIL"


def test_accounting_source_of_truth_blocks_mismatch():
    good = {"cash": 60.0, "positions_value": 40.0, "equity": 100.0, "realized_pnl": 3.0,
            "unrealized_pnl": 2.0, "costs": 1.0, "total_pnl": 4.0, "real_trading": False}
    assert c.accounting_source_of_truth(good)["status"] == "RECONCILED"
    good["equity"] = 101
    out = c.accounting_source_of_truth(good)
    assert out["status"] == "CRITICAL_RECONCILIATION_FAILURE"
    assert out["new_paper_risk_allowed"] is False


def test_restart_must_reconcile_before_paper_resume():
    restore = {"status": "RESTORED_EXACT_PAPER_ENGINE", "verified": True,
               "remote_state_hash": "abc", "local_state_hash": "abc", "backfill_used": False,
               "reconstructed": False, "session_id_before": "s", "session_id_after": "s", "real_trading": False}
    recon = {"status": "RECONCILED", "real_trading": False}
    assert c.restart_reconciliation_gate(restore, recon)["paper_resume_allowed"] is True
    restore["local_state_hash"] = "different"
    assert c.restart_reconciliation_gate(restore, recon)["paper_resume_allowed"] is False


def test_downstream_hard_lock_can_never_be_unlocked_by_paper_success():
    locked = c.downstream_hard_lock({"mode": "PAPER", "real_trading": False,
        "broker_submit_enabled": False, "live_execution_allowed": False, "automatic_promotion": False,
        "automatic_release": False, "setup_1_6_allowed": False, "release_authority": "NONE"})
    assert locked["status"] == "LOCKED"
    bad = c.downstream_hard_lock({"mode": "PAPER", "real_trading": True})
    assert bad["status"] == "CRITICAL_BLOCK"
    assert bad["real_trading"] is False
