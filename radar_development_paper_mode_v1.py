"""Development PAPER mode policy for the first end-to-end Radar simulator trial.

This deliberately separates development readiness from forward-maturity and production
readiness. It may relax validation/promotion/experiment gates only inside PAPER simulation.
It never enables broker/live execution or REAL_TRADING.
"""
from __future__ import annotations

DEVELOPMENT_PAPER_MODE = True
REAL_TRADING = False


def policy() -> dict:
    return {
        "mode": "DEVELOPMENT_PAPER",
        "development_test_ready": True,
        "paper_validation_ready": False,
        "production_ready": False,
        "forward_maturity_required_for_development": False,
        "tasks_1_190_required_for_development": False,
        "paper_experiments_allowed": True,
        "accelerated_paper_cycles_allowed": True,
        "deliberate_restart_testing_allowed": True,
        "paper_champion_challenger_allowed": True,
        "paper_internal_promotion_allowed": True,
        "unverified_evidence_blocks_development": False,
        "unverified_evidence_label": "NOT VERIFIED",
        "live_execution_allowed": False,
        "broker_submit_enabled": False,
        "real_money_orders_allowed": False,
        "real_trading": False,
    }


def assert_safety() -> dict:
    p = policy()
    safe = (
        p["real_trading"] is False
        and p["real_money_orders_allowed"] is False
        and p["broker_submit_enabled"] is False
        and p["live_execution_allowed"] is False
    )
    return {"status": "PASS" if safe else "FAIL", "safe": safe, **p}
