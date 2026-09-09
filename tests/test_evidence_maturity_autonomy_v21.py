from radar_forward_evidence_phase_v1 import evidence_phase
from radar_results_improvement_v1 import improvement_proposal
from radar_maturity_gate_v1 import maturity_gate
from radar_pre_real_money_gate_v1 import pre_real_money_gate
from radar_autonomy_cycle_v2 import autonomy_decision


def test_evidence_phase_starts_without_performance_claim():
    r=evidence_phase(matured_n=0,prospective_days=1,cost_aware_n=0,benchmark_aware_n=0)
    assert r['phase']=='ACCUMULATING'
    assert r['performance_claim']=='INSUFFICIENT_EVIDENCE'
    assert r['real_trading'] is False


def test_maturity_gate_requires_full_forward_integrity():
    r=maturity_gate(eligible_n=100,prospective_days=60,cost_coverage=.96,benchmark_coverage=.96,backfilled_n=1,integrity_ok=True)
    assert r['status']=='IMMATURE'
    assert r['paper_promotion_allowed'] is False
    assert r['real_money_allowed'] is False


def test_improvement_is_proposal_only():
    r=improvement_proposal(phase='MATURE_PAPER_EVIDENCE',excess_return=-.01,degraded=True)
    assert r['automatic_apply'] is False
    assert r['requires_new_forward_validation'] is True


def test_pre_real_money_is_hard_blocked_even_with_all_inputs_true():
    r=pre_real_money_gate(paper_mature=True,security_audit=True,broker_sandbox_verified=True,manual_approval=True)
    assert r['status']=='BLOCKED_REAL'
    assert r['can_enable_real_trading'] is False


def test_autonomy_cycle_holds_on_stale_data():
    r=autonomy_decision(freshness_ok=False,degraded=False,promotion_ready=True,maturity_status='MATURE_PAPER',paper_authority_ready=True)
    assert r['action']=='HOLD'
    assert r['real_order_submission'] is False
