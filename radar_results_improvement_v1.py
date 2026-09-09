"""Translate mature PAPER evidence into bounded improvement proposals only."""
from __future__ import annotations
REAL_TRADING=False

def improvement_proposal(*,phase,excess_return=None,drawdown=None,calibration_error=None,degraded=False):
    if phase!='MATURE_PAPER_EVIDENCE':
        return {'status':'BLOCKED','reason':'INSUFFICIENT_MATURE_FORWARD_EVIDENCE','automatic_apply':False,'real_trading':False}
    actions=[]
    if degraded:actions.append('FREEZE_NEW_RISK')
    if isinstance(excess_return,(int,float)) and excess_return<0:actions.append('REDUCE_RISK_OR_RECALIBRATE')
    if isinstance(drawdown,(int,float)) and drawdown<=-0.10:actions.append('TIGHTEN_DRAWDOWN_LIMITS')
    if isinstance(calibration_error,(int,float)) and calibration_error>0.10:actions.append('RECALIBRATE_EXPECTED_RETURN')
    if not actions:actions.append('KEEP_CHAMPION_UNCHANGED')
    return {'status':'PROPOSAL_ONLY','actions':actions,'automatic_apply':False,'requires_new_forward_validation':True,'real_trading':False}
