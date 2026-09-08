"""Single-cycle orchestrator for Simulation -> Memory -> Champion paper execution -> Learning."""
from __future__ import annotations
from radar_simulation_forward_v3 import capture_forward_mark_v3,simulation_summary_v3
from radar_meta_decision_v2 import champion_decision,champion_health
from radar_champion_portfolio import step_champion,champion_status
from radar_learning_v2 import learning_cycle_v2,learning_v2_health
from radar_decision_memory_v2 import memory_health

REAL_TRADING=False


def fast_cycle():
    """Safe paper-only cycle after each market/agent step."""
    decision=champion_decision(record=True)
    champion_portfolio=step_champion(decision)
    sim=capture_forward_mark_v3()
    return {'simulation':sim,'champion':decision,'champion_portfolio':champion_portfolio,'memory':memory_health(),'real_trading':False}


def deep_learning_cycle(force_predictions=False,regime='unknown'):
    learning=learning_cycle_v2(force_predictions=force_predictions,regime=regime)
    return {'learning':learning,'champion_health':champion_health(),'champion_portfolio':champion_status(),'simulation':simulation_summary_v3(),'real_trading':False}


def system_v2_health():
    return {'simulation':simulation_summary_v3(),'memory':memory_health(),'learning':learning_v2_health(),'champion':champion_health(),'champion_portfolio':champion_status(),'real_trading':False}
