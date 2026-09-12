"""Market-data authority contract for tasks 223-234.

The functions are deterministic validators. They never rewrite historical raw records
and never authorize live trading.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json

REAL_TRADING=False
MISSING_DATA_KINDS=frozenset({'LEGITIMATE_ABSENCE','PROVIDER_FAILURE','STALE','DELAYED'})
PRICE_FIELD_POLICY={
    'entry':'decision_time_executable_or_next_valid_market_price',
    'valuation':'same_session_mark_with_provider_provenance',
    'exit':'first_valid_price_at_or_after_maturity',
    'adjustment':'raw_preserved_adjusted_derived',
}
FRESHNESS_SLA_SECONDS={'quote':120,'daily_close':36*3600,'fundamental':35*24*3600,'news':6*3600,'macro':48*3600}


def _utc(value):
    d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('naive timestamp forbidden')
    return d.astimezone(timezone.utc)

def _hash(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode();return hashlib.sha256(raw).hexdigest()

def freeze_universe(asof,members):
    t=_utc(asof);rows=[]
    for r in members or []:
        symbol=str(r.get('symbol') or '').upper().strip()
        if not symbol:continue
        listed=_utc(r['listed_at']) if r.get('listed_at') else None;delisted=_utc(r['delisted_at']) if r.get('delisted_at') else None
        eligible=(listed is None or listed<=t) and (delisted is None or delisted>=t)
        rows.append({'symbol':symbol,'eligible':eligible,'listed_at':r.get('listed_at'),'delisted_at':r.get('delisted_at')})
    rows=sorted(rows,key=lambda x:x['symbol'])
    return {'asof':t.isoformat().replace('+00:00','Z'),'members':rows,'hash':_hash(rows),'survivorship_checked':True,'real_trading':False}
def survivorship_violations(snapshot):
    return [r for r in snapshot.get('members') or [] if not r.get('eligible')]
def validate_corporate_actions(actions):
    bad=[];valid=[]
    for r in actions or []:
        typ=str(r.get('type') or '').upper()
        if typ not in {'SPLIT','DIVIDEND','MERGER','DELISTING','SPINOFF'} or not r.get('symbol') or not r.get('effective_at'):
            bad.append(r);continue
        try:_utc(r['effective_at'])
        except Exception:bad.append(r);continue
        valid.append(r)
    return {'valid':valid,'invalid':bad,'raw_records_mutated':False,'real_trading':False}
def classify_missing(kind):
    k=str(kind or '').upper()
    if k not in MISSING_DATA_KINDS:raise ValueError('unknown missing-data kind')
    return {'kind':k,'zero_evidence':False,'real_trading':False}
def freshness_state(kind,observed_at,now):
    k=str(kind or '').lower();sla=FRESHNESS_SLA_SECONDS.get(k)
    if sla is None:return {'status':'NOT_VERIFIED','sla_seconds':None,'real_trading':False}
    age=max(0.0,(_utc(now)-_utc(observed_at)).total_seconds())
    return {'status':'FRESH' if age<=sla else 'STALE','age_seconds':age,'sla_seconds':sla,'real_trading':False}
def authority_contract():
    return {'pit_universe':True,'survivorship_guard':True,'corporate_actions':True,'price_field_policy':dict(PRICE_FIELD_POLICY),
            'market_calendar_required':True,'timezone':'UTC_AWARE_ONLY','missing_data_taxonomy':sorted(MISSING_DATA_KINDS),
            'freshness_sla_by_type':dict(FRESHNESS_SLA_SECONDS),'raw_records_mutated':False,'real_trading':False}
