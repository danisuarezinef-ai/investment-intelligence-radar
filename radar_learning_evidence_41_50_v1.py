"""Read-only durable evidence client for autonomous PAPER learning tasks 41-50.

No order path, broker integration, promotion or release authority exists here.
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
        'Content-Type':'application/json','X-Radar-Token':TOKEN,'User-Agent':'RadarLearningEvidence41-50/1.0'})
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


def normalized_rows(limit=400):
    raw=_post({'action':'rows','limit':int(limit),'real_trading':False})
    if raw.get('ok') is not True:
        return {**raw,'normalized_rows':[],'real_trading':False}
    rows=[]
    for r in raw.get('rows') or []:
        if not isinstance(r,dict):continue
        outcome=r.get('outcome') if isinstance(r.get('outcome'),dict) else {}
        provenance=r.get('provenance_snapshot') if isinstance(r.get('provenance_snapshot'),dict) else {}
        backfilled=bool(outcome.get('backfilled',False))
        matured=bool(r.get('evaluated_at')) and bool(outcome)
        pit_valid=bool(r.get('data_cutoff')) and bool(r.get('known_at_boundary')) and bool(r.get('prediction_hash')) and bool(r.get('feature_fingerprint')) and bool(r.get('thesis_fingerprint'))
        row={
            'prediction_id':r.get('local_prediction_id') or r.get('id'),
            'created_at':r.get('created_at'),'evaluated_at':r.get('evaluated_at'),
            'symbol':r.get('symbol'),'horizon':r.get('horizon'),'model_version':r.get('model_version'),
            'confidence':_f(r.get('confidence')),'uncertainty':r.get('uncertainty') or {},
            'decision_state':str(r.get('decision_state') or '').upper(),
            'matured':matured,'natural':matured and not backfilled,
            'net_return':_f(outcome.get('net_return')),'gross_return':_f(outcome.get('gross_return')),
            'cost':_f(outcome.get('cost')),'benchmark_return':_f(outcome.get('benchmark_return')),
            'excess_return':_f(outcome.get('excess_return')),'outcome':outcome,
            'quality_checks':{'pit_valid':pit_valid,'lookahead':False,'backfilled':backfilled},
            'provenance':provenance,'real_trading':False,
        }
        rows.append(row)
    return {'ok':True,'status':'EVIDENCE_READY','normalized_rows':rows,'stats':raw.get('stats') or [],
            'edge_ms':raw.get('edge_ms'),'automatic_promotion':False,'live_execution_allowed':False,'real_trading':False}
