"""Read-only durable evidence client for autonomous PAPER learning tasks 41-50.

No order path, broker integration, promotion or release authority exists here.
The normalized contract also exposes the exact prospective feature vector already
stored inside decision_forward_ledger.payload so later governance can verify it
without reconstruction or backfill.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

REAL_TRADING=False
DEFAULT_URL='https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-paper-learning-evidence-41-50'
URL=os.environ.get('SUPABASE_LEARNING_41_50_URL',DEFAULT_URL).strip()
TOKEN=os.environ.get('RADAR_SYNC_TOKEN','').strip()


def _post(payload,timeout=35):
    if not URL or not TOKEN:
        return {'ok':False,'status':'AUTHORITY_DISABLED','rows':[],'stats':[],'real_trading':False}
    data=json.dumps(payload,ensure_ascii=False,default=str).encode('utf-8')
    req=urllib.request.Request(URL,data=data,method='POST',headers={
        'Content-Type':'application/json','X-Radar-Token':TOKEN,'User-Agent':'RadarLearningEvidence41-50/1.1'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            out=json.loads(r.read().decode('utf-8'))
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        return {'ok':False,'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:500]}','rows':[],'stats':[],'real_trading':False}
    if not isinstance(out,dict) or out.get('ok') is not True or out.get('real_trading') is not False:
        return {'ok':False,'status':'FAIL_CLOSED','error':'invalid remote evidence boundary','rows':[],'stats':[],'real_trading':False}
    out['real_trading']=False
    return out


def _f(value):
    try:return float(value) if value is not None else None
    except (TypeError,ValueError):return None


def _b(value):
    if isinstance(value,bool):return value
    if isinstance(value,str):return value.strip().lower()=='true'
    return bool(value)


def normalized_rows(limit=400):
    raw=_post({'action':'rows','limit':int(limit),'real_trading':False})
    if raw.get('ok') is not True:
        return {**raw,'normalized_rows':[],'feature_snapshots':[],'real_trading':False}
    rows=[];feature_snapshots=[]
    for r in raw.get('rows') or []:
        if not isinstance(r,dict):continue
        outcome=r.get('outcome') if isinstance(r.get('outcome'),dict) else {}
        provenance=r.get('provenance_snapshot') if isinstance(r.get('provenance_snapshot'),dict) else {}
        payload=r.get('payload') if isinstance(r.get('payload'),dict) else {}
        backfilled=bool(outcome.get('backfilled',False))
        matured=bool(r.get('evaluated_at')) and bool(outcome)
        pit_valid=bool(r.get('data_cutoff')) and bool(r.get('known_at_boundary')) and bool(r.get('prediction_hash')) and bool(r.get('feature_fingerprint')) and bool(r.get('thesis_fingerprint'))
        prediction_id=r.get('local_prediction_id') or r.get('id')
        features=payload.get('features') if isinstance(payload.get('features'),dict) else {}
        prospective=_b(payload.get('prospective_capture'))
        immutable=_b(payload.get('immutable'))
        retroactive=_b(payload.get('retroactive_fill'))
        snapshot={
            'prediction_id':prediction_id,'captured_at':r.get('known_at_boundary') or r.get('created_at'),
            'data_cutoff':r.get('data_cutoff'),'feature_fingerprint':r.get('feature_fingerprint'),
            'features':features,'immutable':immutable,'prospective_capture':prospective,
            'lookahead':False,'backfilled':retroactive or backfilled,'retroactive_fill':retroactive,
            'source':'decision_forward_ledger.payload.features','real_trading':False,
        }
        if features or r.get('feature_fingerprint'):feature_snapshots.append(snapshot)
        row={
            'prediction_id':prediction_id,
            'created_at':r.get('created_at'),'evaluated_at':r.get('evaluated_at'),
            'symbol':r.get('symbol'),'horizon':r.get('horizon'),'model_version':r.get('model_version'),
            'confidence':_f(r.get('confidence')),'uncertainty':r.get('uncertainty') or {},
            'decision_state':str(r.get('decision_state') or '').upper(),
            'matured':matured,'natural':matured and not backfilled,
            'net_return':_f(outcome.get('net_return')),'gross_return':_f(outcome.get('gross_return')),
            'cost':_f(outcome.get('cost')),'benchmark_return':_f(outcome.get('benchmark_return')),
            'excess_return':_f(outcome.get('excess_return')),'outcome':outcome,
            'quality_checks':{'pit_valid':pit_valid,'lookahead':False,'backfilled':backfilled},
            'provenance':provenance,'payload':payload,'feature_snapshot':snapshot,
            'real_trading':False,
        }
        rows.append(row)
    valid_features=sum(bool(x.get('features')) and x.get('immutable') is True and x.get('prospective_capture') is True and x.get('backfilled') is not True for x in feature_snapshots)
    return {'ok':True,'status':'EVIDENCE_READY','normalized_rows':rows,'feature_snapshots':feature_snapshots,
            'feature_snapshot_stats':{'n':len(feature_snapshots),'valid_prospective_immutable_n':valid_features},
            'stats':raw.get('stats') or [],'edge_ms':raw.get('edge_ms'),'automatic_promotion':False,
            'live_execution_allowed':False,'real_trading':False}
