"""Fail-closed delisting integrity checks for historical research."""
from __future__ import annotations
from radar_corporate_actions import actions_known_as_of
REAL_TRADING=False

def delisting_evidence(symbol,as_of):
    rows=[x for x in actions_known_as_of(symbol,as_of) if x.get('action_type')=='delisting']
    if not rows:return {'symbol':symbol,'as_of':as_of,'status':'NOT_VERIFIED','delisting_known':False,'return_adjustment':None,'simulation_eligible':False,'real_trading':False}
    latest=rows[-1];payload=latest.get('payload') or {};adj=payload.get('delisting_return')
    eligible=isinstance(adj,(int,float))
    return {'symbol':symbol,'as_of':as_of,'status':'VERIFIED' if eligible else 'KNOWN_EVENT_RETURN_NOT_VERIFIED','delisting_known':True,'return_adjustment':adj if eligible else None,'simulation_eligible':eligible,'source':latest.get('source'),'known_at':latest.get('known_at'),'real_trading':False}

def audit_delisting_coverage(symbols,as_of):
    rows=[delisting_evidence(s,as_of) for s in symbols];blocked=[x['symbol'] for x in rows if x['delisting_known'] and not x['simulation_eligible']]
    return {'symbols':len(rows),'known_delistings':sum(1 for x in rows if x['delisting_known']),'blocked_delistings':blocked,'coverage_complete':not blocked,'rows':rows,'real_trading':False}
