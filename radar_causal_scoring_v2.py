"""Bounded causal evidence scoring; one contribution per independent event.

Causal evidence is advisory only. It cannot authorize promotion, bypass ABSTAIN/risk
controls, or enable real trading.
"""
from __future__ import annotations
import math
from radar_core import con,init_db
from radar_learning import init_learning_db

REAL_TRADING=False
RELATION_SIGN={'direct_signal':1.0,'raises_demand_for':1.0,'raises_power_demand':.5,'supports':.5,'sector_tailwind':.7,'sector_signal':.6,'supply_chain_risk':-1.0,'exposed_to':0.0}
HORIZON_PREF={'1d':{'short':1.,'medium':.45,'long':.2},'1w':{'short':1.,'medium':.65,'long':.25},'1m':{'short':.65,'medium':1.,'long':.45},'3m':{'short':.35,'medium':1.,'long':.7},'forward':{'short':.55,'medium':1.,'long':.55}}
MAX_SCORE_ADJUSTMENT=1.5


def _depth_weight(depth):
    return {1:1.,2:.7,3:.5}.get(max(1,int(depth or 1)),.35)


def causal_symbol_score(symbol,horizon='1m',limit=200):
    init_db();init_learning_db();c=con()
    try:
        rows=c.execute('select source_node,relation,depth,confidence,evidence_event_id,horizon from causal_edges where target_node=? order by id desc limit ?',(symbol,int(limit))).fetchall()
    except Exception:
        c.close();return {'available':False,'symbol':symbol,'score':0.,'adjustment':0.,'confidence':0.,'independent_events':0,'evidence':[],'promotion_authorized':False,'real_trading':False}
    c.close();pref=HORIZON_PREF.get(horizon,HORIZON_PREF['1m']);by_event={}
    for source,relation,depth,confidence,event_id,edge_horizon in rows:
        sign=RELATION_SIGN.get(str(relation),0.)
        if sign==0:continue
        conf=max(0.,min(1.,float(confidence or 0)))
        value=sign*conf*_depth_weight(depth)*pref.get(str(edge_horizon or 'medium'),.45)
        key=str(event_id) if event_id is not None else f'{source}|{relation}|{depth}'
        item={'source':source,'relation':relation,'depth':int(depth or 1),'event_id':event_id,'edge_horizon':edge_horizon,'signed_value':value,'edge_confidence':conf}
        if key not in by_event or abs(value)>abs(by_event[key]['signed_value']):by_event[key]=item
    evidence=list(by_event.values())
    if not evidence:return {'available':False,'symbol':symbol,'score':0.,'adjustment':0.,'confidence':0.,'independent_events':0,'evidence':[],'promotion_authorized':False,'real_trading':False}
    vals=[x['signed_value'] for x in evidence];raw=sum(vals)/len(vals);confidence=(1-math.exp(-len(vals)/4.))*sum(x['edge_confidence'] for x in evidence)/len(evidence);score=max(-1.,min(1.,raw));adj=max(-MAX_SCORE_ADJUSTMENT,min(MAX_SCORE_ADJUSTMENT,score*MAX_SCORE_ADJUSTMENT*confidence))
    return {'available':True,'symbol':symbol,'score':score,'adjustment':adj,'confidence':confidence,'independent_events':len(vals),'positive_events':sum(x>0 for x in vals),'negative_events':sum(x<0 for x in vals),'evidence':sorted(evidence,key=lambda x:abs(x['signed_value']),reverse=True)[:12],'promotion_authorized':False,'real_trading':False}


def causal_scoring_health(symbols=None,horizon='1m'):
    symbols=list(symbols or []);rows=[causal_symbol_score(s,horizon) for s in symbols];active=[x for x in rows if x.get('available')]
    return {'symbols_checked':len(rows),'symbols_with_evidence':len(active),'mean_abs_adjustment':(sum(abs(float(x.get('adjustment') or 0)) for x in active)/len(active) if active else 0.0),'max_score_adjustment':MAX_SCORE_ADJUSTMENT,'one_contribution_per_independent_event':True,'promotion_authorized':False,'rows':rows,'real_trading':False}
