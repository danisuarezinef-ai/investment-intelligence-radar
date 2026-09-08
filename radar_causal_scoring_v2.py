"""Bounded causal evidence scoring for automatic paper decisions.

Transforms existing causal graph edges into a conservative symbol-level adjustment.
Each information event contributes at most once per symbol, preventing structural
edge fan-out from becoming pseudo-replication. Unknown relations are neutral.
REAL_TRADING remains disabled.
"""
from __future__ import annotations
import math
from radar_core import con,init_db
from radar_learning import init_learning_db

REAL_TRADING=False
RELATION_SIGN={
 'direct_signal':1.0,
 'raises_demand_for':1.0,
 'raises_power_demand':0.5,
 'supports':0.5,
 'sector_tailwind':0.7,
 'sector_signal':0.6,
 'supply_chain_risk':-1.0,
 'exposed_to':0.0,
}
HORIZON_PREF={
 '1d':{'short':1.0,'medium':0.45,'long':0.20},
 '1w':{'short':1.0,'medium':0.65,'long':0.25},
 '1m':{'short':0.65,'medium':1.0,'long':0.45},
 '3m':{'short':0.35,'medium':1.0,'long':0.70},
 'forward':{'short':0.55,'medium':1.0,'long':0.55},
}
MAX_SCORE_ADJUSTMENT=1.5


def _depth_weight(depth):
    d=max(1,int(depth or 1));return {1:1.0,2:.70,3:.50}.get(d,.35)


def causal_symbol_score(symbol,horizon='1m',limit=200):
    init_db();init_learning_db();c=con()
    try:
        rows=c.execute('''select source_node,relation,depth,confidence,evidence_event_id,horizon
          from causal_edges where target_node=? order by id desc limit ?''',(symbol,int(limit))).fetchall()
    except Exception:
        c.close();return {'available':False,'symbol':symbol,'score':0.0,'adjustment':0.0,'confidence':0.0,'independent_events':0,'evidence':[],'real_trading':False}
    c.close();pref=HORIZON_PREF.get(horizon,HORIZON_PREF['1m']);by_event={}
    for source,relation,depth,confidence,event_id,edge_horizon in rows:
        sign=RELATION_SIGN.get(str(relation),0.0)
        if sign==0:continue
        conf=max(0.0,min(1.0,float(confidence or 0)));hweight=pref.get(str(edge_horizon or 'medium'),.45);value=sign*conf*_depth_weight(depth)*hweight
        key=str(event_id) if event_id is not None else f'{source}|{relation}|{depth}'
        item={'source':source,'relation':relation,'depth':int(depth or 1),'edge_confidence':conf,'event_id':event_id,'edge_horizon':edge_horizon,'signed_value':value}
        old=by_event.get(key)
        if old is None or abs(value)>abs(old['signed_value']):by_event[key]=item
    evidence=list(by_event.values())
    if not evidence:return {'available':False,'symbol':symbol,'score':0.0,'adjustment':0.0,'confidence':0.0,'independent_events':0,'evidence':[],'real_trading':False}
    values=[x['signed_value'] for x in evidence];raw=sum(values)/len(values);n=len(values);sample_conf=1.0-math.exp(-n/4.0);mean_edge=sum(x['edge_confidence'] for x in evidence)/n;confidence=max(0.0,min(1.0,sample_conf*mean_edge));score=max(-1.0,min(1.0,raw));adjustment=max(-MAX_SCORE_ADJUSTMENT,min(MAX_SCORE_ADJUSTMENT,score*MAX_SCORE_ADJUSTMENT*confidence))
    evidence.sort(key=lambda x:abs(x['signed_value']),reverse=True)
    return {'available':True,'symbol':symbol,'score':score,'adjustment':adjustment,'confidence':confidence,'independent_events':n,'positive_events':sum(1 for x in values if x>0),'negative_events':sum(1 for x in values if x<0),'evidence':evidence[:12],'real_trading':False}


def causal_scoring_health(symbols=None,horizon='1m'):
    symbols=symbols or [];rows=[causal_symbol_score(s,horizon) for s in symbols];active=[x for x in rows if x['available']]
    return {'symbols_checked':len(rows),'symbols_with_evidence':len(active),'mean_abs_adjustment':(sum(abs(x['adjustment']) for x in active)/len(active) if active else 0.0),'rows':rows,'real_trading':False}
