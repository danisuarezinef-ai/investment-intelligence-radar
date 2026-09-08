"""Single-cycle orchestrator for Simulation v2 -> Memory -> Learning -> Champion decision."""
from __future__ import annotations
from radar_simulation_v2 import capture_forward_mark,simulation_summary
from radar_meta_decision_v2 import champion_decision,champion_health
from radar_learning_v2 import learning_cycle_v2,learning_v2_health
from radar_decision_memory_v2 import memory_health

REAL_TRADING=False


def fast_cycle():
    """Safe to run after each paper-agent market step."""
    sim=capture_forward_mark()
    decision=champion_decision(record=True)
    return {'simulation':sim,'champion':decision,'memory':memory_health(),'real_trading':False}


def deep_learning_cycle(force_predictions=False,regime='unknown'):
    """Slower guarded learning cycle; never promotes to real trading."""
    learning=learning_cycle_v2(force_predictions=force_predictions,regime=regime)
    return {'learning':learning,'champion_health':champion_health(),'simulation':simulation_summary(),'real_trading':False}


def system_v2_health():
    return {'simulation':simulation_summary(),'memory':memory_health(),'learning':learning_v2_health(),'champion':champion_health(),'real_trading':False}
