"""Controlled PAPER strategy research policies for pre-1.6.

Creates research candidates and ensemble proposals only. Nothing here can place an
order, promote a production model, or allocate real capital.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics

REAL_TRADING=False


def clamp(x,lo=0.0,hi=1.0):
    try:return max(lo,min(hi,float(x)))
    except (TypeError,ValueError):return lo


def fingerprint(config):
    return hashlib.sha256(json.dumps(config or {},sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()[:20]


def experiment_budget(*,total_capacity=10,active=0,experimental_share=.25,failed_recent=0):
    cap=max(1,int(total_capacity));share=clamp(experimental_share,0,.5);base=max(1,int(math.floor(cap*share)))
    penalty=min(base,int(failed_recent or 0)//3);allowed=max(0,base-penalty-int(active or 0))
    return {'total_capacity':cap,'experimental_cap':base,'active':int(active or 0),'new_slots':allowed,
            'failure_penalty':penalty,'real_trading':False}


def challenger_mutations(parent,*,slots=3,existing_fingerprints=None):
    p=dict(parent or {});existing=set(existing_fingerprints or []);candidates=[]
    knobs=[('risk_multiplier',[.8,.9,1.1,1.2]),('horizon_bias',[-1,1]),('confidence_floor',[-.05,.05]),('turnover_limit',[-.05,.05])]
    for key,deltas in knobs:
        for delta in deltas:
            c=dict(p);base=float(c.get(key,1.0 if key=='risk_multiplier' else (.5 if key=='confidence_floor' else .25)))
            c[key]=round(max(0.0,base+delta),4);c['parent_fingerprint']=fingerprint(p);c['mutation']=f'{key}:{delta:+g}'
            fp=fingerprint(c)
            if fp in existing:continue
            c['fingerprint']=fp;c['research_only']=True;c['real_trading']=False;candidates.append(c)
            if len(candidates)>=max(0,int(slots)):return candidates
    return candidates


def ensemble_proposal(strategies,max_weight=.45):
    rows=[]
    for s in strategies or []:
        v=float(s.get('v_score') or 200);st=float(s.get('stability_score') or 50);conf=float(s.get('v_confidence') or 0)
        raw=max(0.0,(v-160)/240.0)*(.5+.5*clamp(st/100.0))*(.25+.75*clamp(conf))
        rows.append({'key':s.get('competitor_key'),'raw':raw})
    total=sum(x['raw'] for x in rows)
    if total<=0:return {'status':'INSUFFICIENT_EVIDENCE','weights':{},'research_only':True,'real_trading':False}
    weights={x['key']:x['raw']/total for x in rows if x['key']}
    # Iterative cap and redistribute to avoid a nominal ensemble dominated by one strategy.
    for _ in range(4):
        over={k:w for k,w in weights.items() if w>max_weight}
        if not over:break
        excess=sum(w-max_weight for w in over.values())
        for k in over:weights[k]=max_weight
        under=[k for k,w in weights.items() if w<max_weight-1e-12]
        denom=sum(weights[k] for k in under)
        if not under or denom<=0:break
        for k in under:weights[k]+=excess*(weights[k]/denom)
    norm=sum(weights.values());weights={k:w/norm for k,w in weights.items()} if norm else weights
    return {'status':'RESEARCH_PROPOSAL','weights':weights,'max_weight':max_weight,
            'requires_forward_validation':True,'research_only':True,'can_trade':False,'real_trading':False}


def abstention_gate(opportunities,*,data_quality_score=None,calibration_status=None,min_edge=0.0,min_confidence=.55):
    rows=list(opportunities or []);dq=float(data_quality_score or 0);blocked=[]
    if dq<70:blocked.append('DATA_QUALITY')
    if calibration_status not in ('PASS','AVAILABLE'):blocked.append('CALIBRATION')
    eligible=[]
    for r in rows:
        try:edge=float(r.get('expected_edge') if r.get('expected_edge') is not None else r.get('score'));conf=float(r.get('confidence') or 0)
        except (TypeError,ValueError):continue
        if edge>float(min_edge) and conf>=float(min_confidence):eligible.append(r)
    abstain=bool(blocked or not eligible)
    return {'decision':'ABSTAIN' if abstain else 'OPPORTUNITIES_AVAILABLE','eligible':eligible[:12],
            'blockers':blocked+(['NO_EDGE_ABOVE_THRESHOLD'] if not eligible else []),'abstention_is_valid_action':True,
            'can_trade':False,'real_trading':False}


def ranking_calibration(records):
    """Check whether higher-ranked opportunities actually outperform lower ranks."""
    buckets={}
    for r in records or []:
        try:rank=int(r.get('rank'));ret=float(r.get('return_pct'))
        except (TypeError,ValueError):continue
        buckets.setdefault(rank,[]).append(ret)
    if len(buckets)<2:return {'status':'INSUFFICIENT_EVIDENCE','monotonic':None,'by_rank':{},'real_trading':False}
    means={k:statistics.mean(v) for k,v in buckets.items()};ordered=sorted(means);pairs=list(zip(ordered,ordered[1:]));monotonic=sum(1 for a,b in pairs if means[a]>=means[b])/len(pairs) if pairs else None
    return {'status':'AVAILABLE','monotonic':monotonic,'by_rank':{k:{'n':len(buckets[k]),'mean_return_pct':means[k]} for k in ordered},
            'well_calibrated':monotonic is not None and monotonic>=.7,'real_trading':False}


def causal_chain_quality(chain):
    """Score completeness of event→mechanism→asset→signal→decision→outcome evidence."""
    c=chain or {};keys=('event','mechanism','asset_impact','signal','decision','outcome');present={k:bool(c.get(k)) for k in keys}
    known_at=bool(c.get('known_at'));sources=int(c.get('source_count') or 0);score=100*sum(present.values())/len(keys)
    if not known_at:score-=20
    if sources<2:score-=10
    return {'score':max(0,score),'complete':all(present.values()) and known_at and sources>=2,'fields':present,
            'known_at_verified':known_at,'source_count':sources,'real_trading':False}


def universe_evolution(current_symbols,candidates,*,min_liquidity=None,min_data_quality=75,max_additions=10):
    current=set(current_symbols or []);accepted=[];rejected=[]
    for r in candidates or []:
        sym=str(r.get('symbol') or '').upper()
        if not sym or sym in current:continue
        dq=float(r.get('data_quality') or 0);liq=r.get('liquidity')
        ok=dq>=float(min_data_quality) and (min_liquidity is None or (liq is not None and float(liq)>=float(min_liquidity))) and r.get('pit_verified') is True
        (accepted if ok else rejected).append(sym)
    return {'additions':accepted[:max(0,int(max_additions))],'rejected':rejected,'requires_pit_membership':True,
            'automatic_live_universe_change':False,'research_only':True,'real_trading':False}
