"""Auditable transaction-cost assumptions for paper/simulation only."""
from __future__ import annotations
REAL_TRADING=False
DEFAULTS={'commission_bps':1.0,'half_spread_bps':2.0,'slippage_bps':2.0,'fx_bps':3.0}
def estimate_cost(notional,*,commission_bps=None,half_spread_bps=None,slippage_bps=None,fx_bps=0.0):
    n=abs(float(notional));values={'commission_bps':DEFAULTS['commission_bps'] if commission_bps is None else float(commission_bps),'half_spread_bps':DEFAULTS['half_spread_bps'] if half_spread_bps is None else float(half_spread_bps),'slippage_bps':DEFAULTS['slippage_bps'] if slippage_bps is None else float(slippage_bps),'fx_bps':float(fx_bps)}
    components={k.replace('_bps',''):n*v/10000.0 for k,v in values.items()}
    return {'notional':n,'assumptions_bps':values,'components':components,'total':sum(components.values()),'verified_broker_costs':False,'real_trading':False}
