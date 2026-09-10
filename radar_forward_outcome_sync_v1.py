"""Resend mature immutable forward outcomes to the Supabase sync endpoint.

The normal learning sync advances by SQLite rowid, but appending an outcome updates an
existing row without changing rowid. This bridge therefore resends only rows that
already have an outcome. The remote Edge Function writes an outcome only while the
remote outcome is NULL, so repeated calls are idempotent.
"""
from __future__ import annotations
import json,time
from radar_core import con
from radar_learning_sync import _post, enabled, NODE_ID
from radar_investment_memory import init_memory

REAL_TRADING=False
RETRYABLE_MARKERS=('http 408','http 425','http 429','http 500','http 502','http 503','http 504','timeout','timed out')


def _decode(value):
    if isinstance(value,(dict,list)): return value
    if value is None:return None
    try:return json.loads(value)
    except Exception:return {}


def _post_resilient(payload,attempts=3,base_delay=.75):
    """Retry only transient transport/5xx failures; never hide a permanent failure."""
    attempts=max(1,int(attempts));last=None
    for attempt in range(attempts):
        try:return _post(payload)
        except (RuntimeError,TimeoutError,OSError) as exc:
            last=exc;text=str(exc).lower();retryable=any(marker in text for marker in RETRYABLE_MARKERS)
            if not retryable or attempt>=attempts-1:raise
            time.sleep(float(base_delay)*(2**attempt))
    if last is not None:raise last
    raise RuntimeError('forward outcome sync failed without explicit error')


def sync_forward_outcomes_once(limit=750):
    if not enabled():return {'enabled':False,'sent':0,'real_trading':False}
    c=con();init_memory(c)
    rows=c.execute('''select rowid,id,created_at,target_date,asset,horizon,model_version,prediction_hash,
      feature_fingerprint,thesis_fingerprint,confidence,uncertainty,decision_state,paper_allocation,
      data_cutoff,known_at_boundary,provenance_snapshot,payload,outcome,evaluated_at
      from prediction_ledger where outcome is not null order by evaluated_at desc,rowid desc limit ?''',(max(1,int(limit)),)).fetchall();c.close()
    forward=[]
    for r in rows:
        forward.append({'origin_node':NODE_ID,'origin_id':str(r[0]),'local_prediction_id':r[1],
          'created_at':r[2],'target_date':r[3],'symbol':r[4],'horizon':r[5],'model_version':r[6],
          'prediction_hash':r[7],'feature_fingerprint':r[8],'thesis_fingerprint':r[9],'confidence':r[10],
          'uncertainty':_decode(r[11]) or {},'decision_state':r[12],'paper_allocation':_decode(r[13]),
          'data_cutoff':r[14],'known_at_boundary':r[15],'provenance_snapshot':_decode(r[16]) or {},
          'payload':_decode(r[17]) or {},'outcome':_decode(r[18]),'evaluated_at':r[19]})
    result=_post_resilient({'node_id':NODE_ID,'decision_forward_ledger':forward}) if forward else {'ok':True,'decision_forward_outcomes':0}
    return {'enabled':True,'sent':len(forward),'remote':result,'idempotent':True,'backfill_used':False,'real_trading':False}
