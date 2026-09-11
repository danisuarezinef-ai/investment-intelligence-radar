"""Exact durable checkpoint for PAPER simulator engines.

Railway's filesystem is ephemeral. This module snapshots the operational PAPER
state (accounts, positions, trades, marks and point-in-time decision provenance)
and restores it before worker threads start after a redeploy. It has no broker
integration and cannot enable real trading.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.error
import urllib.request

from radar_core import con, now
from radar_agents import AGENTS, init_agents_db
from radar_champion_portfolio import init_champion_db

REAL_TRADING = False
SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
DEFAULT_CHECKPOINT_URL = 'https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-paper-engine-checkpoint'
CHECKPOINT_URL = os.environ.get('SUPABASE_PAPER_CHECKPOINT_URL', DEFAULT_CHECKPOINT_URL).strip()
SYNC_TOKEN = os.environ.get('RADAR_SYNC_TOKEN', '').strip()
NODE_ID = os.environ.get('RADAR_NODE_ID', 'cloud-primary').strip() or 'cloud-primary'

_CORE_TABLES = (
    'paper_agents','paper_agent_positions','paper_agent_trades','paper_agent_marks',
    'champion_paper_account','champion_paper_positions','champion_paper_trades','champion_paper_marks',
)
_TABLES = _CORE_TABLES + ('paper_decision_envelopes_local',)


def _table_rows(c, table, limit=None):
    cols=[r[1] for r in c.execute(f'pragma table_info({table})').fetchall()]
    if not cols:return []
    if limit is None:
        rows=c.execute(f'select * from {table} order by rowid').fetchall()
    else:
        rows=c.execute(f'select * from {table} order by rowid desc limit ?',(int(limit),)).fetchall()
        rows=list(reversed(rows))
    return [{k:v for k,v in zip(cols,row)} for row in rows]


def _normalize_number(value):
    """Canonical numeric form stable across SQLite -> JSON -> PostgreSQL jsonb -> JSON."""
    if isinstance(value,bool) or value is None:return value
    if isinstance(value,int):return value
    if isinstance(value,float):
        if not math.isfinite(value):return str(value)
        if value.is_integer():return int(value)
        return float(format(value,'.15g'))
    return value


def _normalize_json(value):
    if isinstance(value,dict):return {str(k):_normalize_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_normalize_json(v) for v in value]
    return _normalize_number(value)


def _canonical_tables(tables):
    return json.dumps(_normalize_json(tables),ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)


def state_hash(tables):
    return hashlib.sha256(_canonical_tables(tables).encode('utf-8')).hexdigest()


def engine_checkpoint():
    init_agents_db();init_champion_db();c=con();c.execute('begin immediate')
    try:
        tables={
            'paper_agents':_table_rows(c,'paper_agents'),
            'paper_agent_positions':_table_rows(c,'paper_agent_positions'),
            'paper_agent_trades':_table_rows(c,'paper_agent_trades',2000),
            'paper_agent_marks':_table_rows(c,'paper_agent_marks',4000),
            'champion_paper_account':_table_rows(c,'champion_paper_account'),
            'champion_paper_positions':_table_rows(c,'champion_paper_positions'),
            'champion_paper_trades':_table_rows(c,'champion_paper_trades',1000),
            'champion_paper_marks':_table_rows(c,'champion_paper_marks',2000),
            'paper_decision_envelopes_local':_table_rows(c,'paper_decision_envelopes_local',8000),
        };c.commit()
    except Exception:c.rollback();raise
    finally:c.close()
    return {'schema_version':SCHEMA_VERSION,'observed_at':now(),'tables':tables,'state_hash':state_hash(tables),'real_trading':False}


def _post(payload,timeout=40):
    if not (CHECKPOINT_URL and SYNC_TOKEN):return {'ok':False,'status':'AUTHORITY_DISABLED','real_trading':False}
    data=json.dumps(payload,ensure_ascii=False,default=str).encode('utf-8')
    req=urllib.request.Request(CHECKPOINT_URL,data=data,method='POST',headers={'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'RadarPaperEngineCheckpoint/2.0'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body=exc.read().decode('utf-8','replace');raise RuntimeError(f'paper checkpoint HTTP {exc.code}: {body[:1000]}') from exc


def push_engine_checkpoint():
    checkpoint=engine_checkpoint();result=_post({'action':'persist_engine_checkpoint','node_id':NODE_ID,'checkpoint':checkpoint,'real_trading':False});result['local_state_hash']=checkpoint['state_hash'];result['schema_version']=SCHEMA_VERSION;result['real_trading']=False;return result


def _validate_checkpoint(checkpoint):
    if not isinstance(checkpoint,dict):raise ValueError('checkpoint is not an object')
    if checkpoint.get('real_trading') is not False:raise ValueError('checkpoint real_trading boundary invalid')
    schema=int(checkpoint.get('schema_version') or 0)
    if schema not in (LEGACY_SCHEMA_VERSION,SCHEMA_VERSION):raise ValueError('unsupported checkpoint schema')
    tables=checkpoint.get('tables')
    if not isinstance(tables,dict):raise ValueError('checkpoint tables missing')
    required=_CORE_TABLES if schema==LEGACY_SCHEMA_VERSION else _TABLES
    if any(name not in tables or not isinstance(tables[name],list) for name in required):raise ValueError('checkpoint table set incomplete')
    ids={str(row.get('agent_id')) for row in tables['paper_agents'] if isinstance(row,dict)}
    if ids!=set(AGENTS):raise ValueError('checkpoint PAPER agent set is incomplete or unexpected')
    if len(tables['champion_paper_account'])!=1 or int(tables['champion_paper_account'][0].get('id') or 0)!=1:raise ValueError('checkpoint Champion account invalid')
    expected_hash=str(checkpoint.get('state_hash') or '');actual_hash=state_hash(tables)
    if not expected_hash or expected_hash!=actual_hash:raise ValueError('checkpoint hash mismatch')
    return tables,actual_hash,schema


def _insert_rows(c,table,rows):
    allowed=[r[1] for r in c.execute(f'pragma table_info({table})').fetchall()];count=0
    for raw in rows:
        if not isinstance(raw,dict):continue
        keys=[key for key in allowed if key in raw]
        if not keys:continue
        vals=[raw[key] for key in keys];c.execute(f"insert into {table}({','.join(keys)}) values({','.join('?' for _ in keys)})",vals);count+=1
    return count


def restore_engine_checkpoint(checkpoint):
    tables,remote_hash,remote_schema=_validate_checkpoint(checkpoint);init_agents_db();init_champion_db();c=con();c.execute('begin immediate');restored={}
    try:
        for table in ('paper_agent_positions','paper_agent_trades','paper_agent_marks','paper_agents','champion_paper_positions','champion_paper_trades','champion_paper_marks','champion_paper_account','paper_decision_envelopes_local'):
            c.execute(f'delete from {table}')
        for table in _CORE_TABLES:restored[table]=_insert_rows(c,table,tables[table])
        restored['paper_decision_envelopes_local']=_insert_rows(c,'paper_decision_envelopes_local',tables.get('paper_decision_envelopes_local') or [])
        c.commit()
    except Exception:c.rollback();raise
    finally:c.close()
    local=engine_checkpoint()
    if remote_schema==SCHEMA_VERSION:
        verified=local['state_hash']==remote_hash;verified_hash=local['state_hash']
    else:
        legacy_local={name:local['tables'][name] for name in _CORE_TABLES};verified_hash=state_hash(legacy_local);verified=verified_hash==remote_hash
    if not verified:raise RuntimeError('post-restore PAPER checkpoint verification failed')
    return {'status':'RESTORED_EXACT_PAPER_ENGINE','remote_state_hash':remote_hash,'local_state_hash':verified_hash,
            'upgraded_state_hash':local['state_hash'] if remote_schema!=SCHEMA_VERSION else None,
            'remote_schema_version':remote_schema,'local_schema_version':SCHEMA_VERSION,'schema_migrated':remote_schema!=SCHEMA_VERSION,
            'verified':True,'rows':restored,'backfill_used':False,'reconstructed':False,'can_trade':False,'real_trading':False}


def rehydrate_engine_checkpoint():
    result=_post({'action':'rehydrate_engine_checkpoint','node_id':NODE_ID,'real_trading':False});checkpoint=result.get('checkpoint') if isinstance(result,dict) else None
    if not checkpoint:return {'status':'NO_DURABLE_PAPER_CHECKPOINT','restored':False,'backfill_used':False,'reconstructed':False,'can_trade':False,'real_trading':False}
    restored=restore_engine_checkpoint(checkpoint);restored['restored']=True;return restored