"""Immutable point-in-time provenance capture for PAPER decisions.

Every captured record is written in the same SQLite transaction as the PAPER trade
that created it. The record contains only information available at or before the
trade timestamp. It is evidence/governance only and cannot place orders.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone

from radar_core import con, ASSETS

REAL_TRADING=False
TABLE='paper_decision_envelopes_local'


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _canonical(value):
    return json.dumps(_clean(value),sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def strategy_version(strategy_identity, strategy_config):
    """Content-address the exact decision configuration available at trade time."""
    return 'cfgsha256:'+_hash({'strategy_identity':str(strategy_identity),'strategy_config':_clean(strategy_config or {})})


def init_decision_provenance_db(connection=None):
    own=connection is None;c=connection or con()
    c.execute(f'''create table if not exists {TABLE}(
        source_key text not null,
        trade_id integer not null,
        trade_ts text not null,
        competitor_key text not null,
        strategy_identity text not null,
        strategy_version text not null,
        decision_fingerprint text not null,
        symbol text not null,
        side text not null,
        regime_snapshot text not null,
        benchmark_snapshot text not null,
        cost_snapshot text not null,
        provider_snapshot text not null,
        decision_payload text not null,
        provenance text not null,
        envelope_hash text not null,
        created_at text not null,
        real_trading integer not null default 0 check(real_trading=0),
        primary key(source_key,trade_id),
        unique(envelope_hash)
    )''')
    c.execute(f'create index if not exists idx_{TABLE}_trade_ts on {TABLE}(trade_ts)')
    c.execute(f'create index if not exists idx_{TABLE}_decision_fp on {TABLE}(decision_fingerprint)')
    if own:c.commit();c.close()


def _latest_market_before(c,symbol,trade_ts):
    try:r=c.execute('select ts,source,price from market_snapshots where symbol=? and ts<=? order by ts desc,id desc limit 1',(symbol,trade_ts)).fetchone()
    except Exception:r=None
    if not r:return {'status':'SOURCE_NOT_CAPTURED','ts':None,'source':None,'price':None}
    try:price=float(r[2])
    except Exception:price=None
    return {'status':'PIT_SOURCE_CAPTURED','ts':r[0],'source':r[1],'price':price}


def _latest_regime_before(c,trade_ts):
    try:r=c.execute('select ts,regime,confidence,features from market_regimes where ts<=? order by ts desc,id desc limit 1',(trade_ts,)).fetchone()
    except Exception:r=None
    if not r:return {'status':'PIT_REGIME_NOT_CAPTURED','ts':None,'regime':None,'confidence':None,'features':{}}
    try:features=json.loads(r[3] or '{}')
    except Exception:features={}
    try:confidence=float(r[2]) if r[2] is not None else None
    except Exception:confidence=None
    return {'status':'PIT_CAPTURED','ts':r[0],'regime':r[1],'confidence':confidence,'features':features}


def _latest_model_before(c,trade_ts):
    try:r=c.execute('select version,created_at from model_versions where created_at<=? order by created_at desc limit 1',(trade_ts,)).fetchone()
    except Exception:r=None
    return {'decision_model_version':r[0],'model_created_at':r[1]} if r else {'decision_model_version':None,'model_created_at':None}


def _benchmark_snapshot(c,trade_ts):
    constituents={}
    for symbol in sorted(ASSETS):
        snap=_latest_market_before(c,symbol,trade_ts)
        if snap.get('price') is None:continue
        constituents[symbol]={'ts':snap.get('ts'),'price':snap.get('price'),'source':snap.get('source')}
    return {
        'name':'RADAR_EQUAL_WEIGHT_OBSERVED_UNIVERSE',
        'reference_ts':trade_ts,
        'constituents':constituents,
        'coverage_count':len(constituents),
        'universe_size':len(ASSETS),
        'status':'PIT_ENTRY_VECTOR_CAPTURED' if constituents else 'PIT_ENTRY_VECTOR_MISSING',
    }


def capture_trade_envelope(connection, *, source_key, trade_id, trade_ts, competitor_key,
                           strategy_identity, strategy_config, symbol, side, cost_snapshot,
                           decision_payload):
    """Capture one immutable envelope inside the caller's PAPER trade transaction."""
    if connection is None:raise ValueError('existing SQLite transaction required')
    side=str(side or '').upper()
    if side not in ('BUY','SELL'):raise ValueError('BUY/SELL required')
    init_decision_provenance_db(connection)
    strategy_identity=str(strategy_identity);strategy_version_id=strategy_version(strategy_identity,strategy_config)
    provider=_latest_market_before(connection,str(symbol),str(trade_ts));regime=_latest_regime_before(connection,str(trade_ts));model=_latest_model_before(connection,str(trade_ts))
    benchmark=_benchmark_snapshot(connection,str(trade_ts))
    fp_body={'source_key':str(source_key),'trade_id':int(trade_id),'trade_ts':str(trade_ts),'competitor_key':str(competitor_key),
             'symbol':str(symbol),'side':side,'strategy_version':strategy_version_id}
    fingerprint=_hash(fp_body)
    provenance={'capture_mode':'AT_DECISION_TRANSACTION','strategy_identity':strategy_identity,'strategy_version':strategy_version_id,
                'strategy_version_status':'CAPTURED_AT_DECISION',**model,'provider_status':provider.get('status'),'regime_status':regime.get('status'),
                'benchmark_status':benchmark.get('status'),'lookahead':False,'backfilled':False,'reconstructed':False,'real_trading':False}
    envelope={'source_key':str(source_key),'trade_id':int(trade_id),'trade_ts':str(trade_ts),'competitor_key':str(competitor_key),
              'strategy_identity':strategy_identity,'strategy_version':strategy_version_id,'decision_fingerprint':fingerprint,
              'symbol':str(symbol),'side':side,'regime_ts':regime.get('ts'),'regime':regime.get('regime'),'regime_confidence':regime.get('confidence'),
              'regime_features':regime.get('features') or {},'benchmark_snapshot':benchmark,'cost_snapshot':_clean(cost_snapshot or {}),
              'provider_snapshot':provider,'provenance':provenance,'decision_payload':_clean(decision_payload or {}),'real_trading':False}
    envelope['envelope_hash']=_hash({k:v for k,v in envelope.items() if k!='envelope_hash'})
    existing=connection.execute(f'select envelope_hash from {TABLE} where source_key=? and trade_id=?',(str(source_key),int(trade_id))).fetchone()
    if existing:
        if str(existing[0])!=envelope['envelope_hash']:raise RuntimeError('immutable decision envelope collision')
        return envelope
    connection.execute(f'''insert into {TABLE}(source_key,trade_id,trade_ts,competitor_key,strategy_identity,strategy_version,decision_fingerprint,symbol,side,
        regime_snapshot,benchmark_snapshot,cost_snapshot,provider_snapshot,decision_payload,provenance,envelope_hash,created_at,real_trading)
        values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)''',(
        envelope['source_key'],envelope['trade_id'],envelope['trade_ts'],envelope['competitor_key'],envelope['strategy_identity'],envelope['strategy_version'],
        envelope['decision_fingerprint'],envelope['symbol'],envelope['side'],_canonical({'ts':envelope['regime_ts'],'regime':envelope['regime'],'confidence':envelope['regime_confidence'],'features':envelope['regime_features']}),
        _canonical(envelope['benchmark_snapshot']),_canonical(envelope['cost_snapshot']),_canonical(envelope['provider_snapshot']),_canonical(envelope['decision_payload']),
        _canonical(envelope['provenance']),envelope['envelope_hash'],str(trade_ts)))
    return envelope


def _decode(text,default):
    try:return json.loads(text) if text else default
    except Exception:return default


def load_local_envelopes(capture_started_at=None):
    c=con();init_decision_provenance_db(c)
    try:
        if capture_started_at:
            rows=c.execute(f'''select source_key,trade_id,trade_ts,competitor_key,strategy_identity,strategy_version,decision_fingerprint,symbol,side,
                regime_snapshot,benchmark_snapshot,cost_snapshot,provider_snapshot,decision_payload,provenance,envelope_hash,real_trading
                from {TABLE} where trade_ts>=? order by trade_ts,source_key,trade_id''',(str(capture_started_at),)).fetchall()
        else:
            rows=c.execute(f'''select source_key,trade_id,trade_ts,competitor_key,strategy_identity,strategy_version,decision_fingerprint,symbol,side,
                regime_snapshot,benchmark_snapshot,cost_snapshot,provider_snapshot,decision_payload,provenance,envelope_hash,real_trading
                from {TABLE} order by trade_ts,source_key,trade_id''').fetchall()
        out=[]
        for r in rows:
            regime=_decode(r[9],{});out.append({'source_key':r[0],'trade_id':int(r[1]),'trade_ts':r[2],'competitor_key':r[3],
                'strategy_identity':r[4],'strategy_version':r[5],'decision_fingerprint':r[6],'symbol':r[7],'side':r[8],
                'regime_ts':regime.get('ts'),'regime':regime.get('regime'),'regime_confidence':regime.get('confidence'),'regime_features':regime.get('features') or {},
                'benchmark_snapshot':_decode(r[10],{}),'cost_snapshot':_decode(r[11],{}),'provider_snapshot':_decode(r[12],{}),
                'decision_payload':_decode(r[13],{}),'provenance':_decode(r[14],{}),'envelope_hash':r[15],'real_trading':False})
        return out
    finally:c.close()


def trace_key(competitor_key,symbol,entry_ts):
    return (str(competitor_key or ''),str(symbol or '').upper(),str(entry_ts or ''))


def provenance_status(capture_started_at=None):
    rows=load_local_envelopes(capture_started_at)
    return {'status':'AVAILABLE' if rows else 'EVIDENCE_PENDING','records':len(rows),
            'buy_records':sum(str(x.get('side'))=='BUY' for x in rows),'sell_records':sum(str(x.get('side'))=='SELL' for x in rows),
            'strategy_versions_missing':sum(not x.get('strategy_version') for x in rows),
            'lookahead_flags':sum(bool((x.get('provenance') or {}).get('lookahead')) for x in rows),
            'real_trading':False}
