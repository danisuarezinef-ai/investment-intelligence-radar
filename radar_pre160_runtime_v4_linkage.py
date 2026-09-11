"""Safe entry-envelope linkage helpers for pre-1.6 v4.

Entry envelopes cannot share a closed-outcome fingerprint because exit fields do
not exist at entry time. Link only on fields that existed at entry.
"""
from __future__ import annotations
from collections import Counter
import radar_pre160_runtime_v4 as v4
import radar_pre160_runtime_v3 as v3

REAL_TRADING=False


def _ts(value):
    d=v4._dt(value)
    return d.isoformat() if d else str(value or '')


def regime_coverage_balance_safe(decisions,envelopes,min_per_regime=5):
    index={}
    for env in envelopes or []:
        if str(env.get('side') or '').upper()!='BUY':continue
        key=(str(env.get('competitor_key') or ''),str(env.get('symbol') or ''),_ts(env.get('trade_ts')))
        index[key]=env
    counts=Counter();missing=0
    for d in v3._prospective(decisions):
        key=(str(d.get('competitor_key') or ''),str(d.get('symbol') or ''),_ts(d.get('entry_ts')))
        env=index.get(key)
        if not env or not env.get('regime'):missing+=1;continue
        counts[str(env['regime'])]+=1
    mature={k:n for k,n in counts.items() if n>=min_per_regime};blockers=[]
    if missing:blockers.append('PROSPECTIVE_ENTRY_ENVELOPE_OR_REGIME_MISSING')
    if len(mature)<2:blockers.append('REGIME_DIVERSITY_NOT_MATURE')
    total=sum(counts.values());shares={k:n/total for k,n in counts.items()} if total else {}
    return {'status':'MATURE' if not blockers else 'EVIDENCE_PENDING','linkage':'competitor+symbol+entry_ts','counts':dict(counts),'shares':shares,
            'mature_regimes':mature,'missing':missing,'blockers':blockers,'uses_exit_fields_for_entry_linkage':False,'real_trading':False}


def apply_safe_linkage(snapshot,decisions,envelopes):
    out=dict(snapshot or {});out['regime_coverage']=regime_coverage_balance_safe(decisions,envelopes)
    out['snapshot_hash']=v4._hash({k:v for k,v in out.items() if k!='snapshot_hash'})
    return out
