"""Durable client for pre-1.6 hardening authority (tasks 111-130)."""
from __future__ import annotations
import json,os,urllib.request,urllib.error

REAL_TRADING=False
DEFAULT_URL='https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-pre160-hardening'
URL=os.environ.get('SUPABASE_PRE160_HARDENING_URL',DEFAULT_URL).strip()
TOKEN=os.environ.get('RADAR_SYNC_TOKEN','').strip()
NODE_ID=os.environ.get('RADAR_NODE_ID','cloud-primary').strip() or 'cloud-primary'


def _post(payload,timeout=40):
    if not (URL and TOKEN):return {'ok':False,'status':'AUTHORITY_DISABLED','real_trading':False}
    data=json.dumps(payload,ensure_ascii=False,default=str).encode('utf-8')
    req=urllib.request.Request(URL,data=data,method='POST',headers={'Content-Type':'application/json','X-Radar-Token':TOKEN,'User-Agent':'RadarPre160Hardening/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body=exc.read().decode('utf-8','replace');raise RuntimeError(f'pre160 hardening HTTP {exc.code}: {body[:1200]}') from exc


def persist_hardening_snapshot(snapshot):
    out=_post({'action':'persist_hardening_snapshot','node_id':NODE_ID,'snapshot':snapshot,'real_trading':False});out['real_trading']=False;return out


def hardening_status(limit=500):
    out=_post({'action':'hardening_status','node_id':NODE_ID,'limit':max(1,min(2000,int(limit or 500))),'real_trading':False});out['real_trading']=False;return out
