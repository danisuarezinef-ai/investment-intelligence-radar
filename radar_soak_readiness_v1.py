"""Gate for leaving Radar unattended for a multi-day PAPER/SHADOW soak."""
REAL_TRADING=False


def soak_readiness(*,cloud_fresh=False,market_collection=False,simulator_available=False,
                   research_brain_live=False,paper_persistent=False,forward_outcomes_live=False,
                   learning_live=False,restart_tested=False,resilience_tested=False,
                   windows_simulator_smoke=False):
    checks={'cloud_fresh':bool(cloud_fresh),'market_collection':bool(market_collection),'simulator_available':bool(simulator_available),'research_brain_live':bool(research_brain_live),'paper_persistent':bool(paper_persistent),'forward_outcomes_live':bool(forward_outcomes_live),'learning_live':bool(learning_live),'restart_tested':bool(restart_tested),'resilience_tested':bool(resilience_tested),'windows_simulator_smoke':bool(windows_simulator_smoke)}
    blockers=[k.upper()+'_NOT_VERIFIED' for k,v in checks.items() if not v]
    return {'status':'READY_FOR_UNATTENDED_SOAK' if not blockers else 'NOT_READY','checks':checks,'blockers':blockers,'scope':'SHADOW_PAPER_SIMULATION','performance_claim':'INSUFFICIENT_EVIDENCE_UNLESS_FORWARD_MATURE','real_trading':False}
