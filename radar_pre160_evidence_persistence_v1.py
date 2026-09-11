"""Durable authority client for pre-1.6 evidence v3.

Persists daily evidence snapshots and freezes point-in-time trade contexts. The
Supabase authority also appends newly observed prospective decision fingerprints to
an immutable hash chain. PAPER/SHADOW only; REAL_TRADING=false.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

REAL_TRADING=False
DEFAULT_URL='https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-pre160-evidence'
URL=os.environ.get('SUPABASE_PRE160_EVIDENCE_URL',DEFAULT_URL).strip()
TOKEN=os.environ.get('RADAR_SYNC_TOKEN','').strip()
NODE_ID=os.environ.get('RADAR_NODE_ID','cloud-primary').strip() or 'cloud-primary'


def _post(payload,timeout=45):
    if not (URL and TOKEN):return {'ok':False,'status':'AUTHORITY_DISABLED','real_trading':False}
    data=json.dumps(payload,ensure_ascii=False,default=str).encode('utf-8')
    req=urllib.request.Request(URL,data=data,method='POST',headers={'Content-Type':'application/json','X-Radar-Token':TOKEN,'User-Agent':'RadarPre160Evidence/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body=exc.read().decode('utf-8','replace');raise RuntimeError(f'pre160 evidence HTTP {exc.code}: {body[:1200]}') from exc


def persist_evidence_snapshot(snapshot):
    out=_post({'action':'persist_evidence_snapshot','node_id':NODE_ID,'snapshot':snapshot,'real_trading':False});out['real_trading']=False;return out


def evidence_authority_status(days=90):
    out=_post({'action':'evidence_status','node_id':NODE_ID,'days':max(1,min(365,int(days or 90))),'real_trading':False});out['real_trading']=False;return out
