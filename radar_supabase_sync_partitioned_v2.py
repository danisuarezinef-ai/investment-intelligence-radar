"""Partitioned generic Supabase sync transport with durable backpressure.

Unrelated families are sent in bounded idempotent chunks. Each source cursor advances
only after every chunk in that family is remotely confirmed. Failed chunks are also
written to the Supabase-backed retry queue before the error is re-raised, so transport
pressure is bounded without converting missing transport into zero evidence.
No transport outcome can authorize trading.
"""
from __future__ import annotations

import threading
import time

import radar_supabase_sync as base
import radar_sync_queue_v3 as remote_queue
from radar_core import con, init_db, now

REAL_TRADING = False
MAX_SYNC_BATCH = base.MAX_SYNC_BATCH
DEFAULT_CHUNK = 75
MARK_CHUNK = 60
MARKET_CHUNK = 100
BACKPRESSURE_DRAIN_LIMIT = 100
BACKPRESSURE_PREFIX = 'generic_sync:'

_LOCK = threading.RLock()
_PARTITION = {
    'cycles': 0,
    'completed_cycles': 0,
    'failed_cycles': 0,
    'parts_sent': 0,
    'chunks_sent': 0,
    'last_cycle_ms': None,
    'last_failed_part': None,
    'last_part_ms': {},
    'last_part_rows': {},
    'last_error': None,
    'cursor_policy': 'PER_FAMILY_AFTER_ALL_CHUNKS_REMOTE_SUCCESS',
    'backpressure_enqueued': 0,
    'backpressure_drained': 0,
    'backpressure_failures': 0,
    'backlog_last': 0,
}


def enabled():
    return base.enabled()


def _chunks(items, size):
    size=max(1,int(size))
    for i in range(0,len(items),size):
        yield items[i:i+size]


def _node_payload():
    return {
        'node_id': base.NODE_ID,
        'node': {
            'node_id': base.NODE_ID,
            'node_type': 'cloud',
            'name': 'Railway Cloud',
            'enabled': True,
            'app_version': '1.5.28',
            'last_seen': now(),
            'capabilities': {'collector': True, 'paper': True, 'api': True, 'supabase_sync': True},
        },
    }


def _enqueue_backpressure(part, payload):
    try:
        remote_queue.enqueue(BACKPRESSURE_PREFIX+str(part), payload)
        with _LOCK:
            _PARTITION['backpressure_enqueued'] += 1
    except Exception as exc:
        # Queue failure is material: preserve the original transport error but expose that
        # the durable fallback also failed. Never treat it as successful delivery.
        with _LOCK:
            _PARTITION['backpressure_failures'] += 1
            _PARTITION['last_error'] = f'BACKPRESSURE_ENQUEUE_FAILED {type(exc).__name__}: {str(exc)[:400]}'


def _send(part, payload, *, rows=0, timeout=None, queue_on_failure=True):
    started=time.monotonic()
    try:
        out=base._post(payload, timeout=timeout)
        with _LOCK:
            _PARTITION['parts_sent']+=1
            _PARTITION['last_part_rows'][part]=int(rows)
            _PARTITION['last_part_ms'][part]=round((time.monotonic()-started)*1000.0,2)
        return out
    except Exception as exc:
        if queue_on_failure:
            _enqueue_backpressure(part,payload)
        with _LOCK:
            _PARTITION['last_failed_part']=str(part)
            _PARTITION['last_error']=f'{type(exc).__name__}: {str(exc)[:500]}'
            _PARTITION['last_part_ms'][part]=round((time.monotonic()-started)*1000.0,2)
        raise


def _send_family(part, key, rows, *, cursor_key=None, cursor_value=None, chunk_size=DEFAULT_CHUNK, base_fields=None):
    """Send all chunks and advance this family's cursor only after full confirmation."""
    rows=list(rows or [])
    if not rows:
        return []
    results=[]
    for chunk in _chunks(rows,chunk_size):
        payload=dict(base_fields or {'node_id':base.NODE_ID})
        payload[key]=chunk
        results.append(_send(part,payload,rows=len(chunk)))
        with _LOCK:_PARTITION['chunks_sent']+=1
    if cursor_key is not None and cursor_value is not None:
        base._control_set(cursor_key,cursor_value)
    return results


def drain_backpressure(limit=BACKPRESSURE_DRAIN_LIMIT):
    """Replay only generic-sync retry items; ACK strictly after remote success.

    Other queue channels (durability/DLQ probes or future transports) are never consumed
    by this worker. Replays are safe because radar-sync writes are idempotent.
    """
    if not remote_queue.enabled():
        return {'configured':False,'eligible':0,'drained':0,'failed':0,'real_trading':False}
    due=remote_queue.due(max(1,min(200,int(limit))))
    eligible=[x for x in due if str(x.get('channel') or '').startswith(BACKPRESSURE_PREFIX)]
    drained=0;failed=0
    with _LOCK:_PARTITION['backlog_last']=len(eligible)
    for item in eligible:
        qid=str(item.get('id') or '')
        payload=item.get('payload') if isinstance(item.get('payload'),dict) else None
        if not qid or not payload:
            continue
        try:
            base._post(payload)
            remote_queue.acknowledge([qid])
            drained+=1
            with _LOCK:_PARTITION['backpressure_drained']+=1
        except Exception as exc:
            failed+=1
            try:
                remote_queue.fail([{'id':qid,'error':f'{type(exc).__name__}: {str(exc)[:400]}','retry_after_seconds':5}])
            except Exception:
                pass
            with _LOCK:_PARTITION['backpressure_failures']+=1
    return {'configured':True,'eligible':len(eligible),'drained':drained,'failed':failed,'real_trading':False}


def partition_telemetry():
    with _LOCK:
        p=dict(_PARTITION);p['last_part_ms']=dict(_PARTITION['last_part_ms']);p['last_part_rows']=dict(_PARTITION['last_part_rows'])
    p.update({'partitioned':True,'max_source_batch':MAX_SYNC_BATCH,'default_chunk':DEFAULT_CHUNK,
              'mark_chunk':MARK_CHUNK,'market_chunk':MARKET_CHUNK,'backpressure_backend':'SUPABASE_RETRY_QUEUE',
              'backpressure_prefix':BACKPRESSURE_PREFIX,'ack_after_remote_success':True,'real_trading':False})
    return p


def sync_telemetry():
    t=base.sync_telemetry();t['partitioned_transport']=partition_telemetry();t['real_trading']=False;return t


def sync_once(batch=500):
    if not enabled():return {'enabled':False,'telemetry':sync_telemetry()}
    started=time.monotonic()
    with _LOCK:_PARTITION['cycles']+=1;_PARTITION['last_failed_part']=None;_PARTITION['last_error']=None
    # Bounded drain prevents an outage backlog from monopolizing the current cycle.
    try:backpressure=drain_backpressure()
    except Exception as exc:
        backpressure={'configured':remote_queue.enabled(),'eligible':None,'drained':0,'failed':1,'error':str(exc)[:400],'real_trading':False}
        with _LOCK:_PARTITION['backpressure_failures']+=1
    init_db();batch=max(1,min(int(batch),MAX_SYNC_BATCH))
    market_after=int(base._control_get('supabase_market_id','0') or 0);events_after=int(base._control_get('supabase_event_id','0') or 0)
    runs_after=int(base._control_get('supabase_run_id','0') or 0);trades_after=int(base._control_get('supabase_agent_trade_id','0') or 0)
    marks_after=int(base._control_get('supabase_agent_mark_id','0') or 0);alerts_after=int(base._control_get('supabase_alert_id','0') or 0)
    notifications_after=int(base._control_get('supabase_notification_id','0') or 0)
    c=con()
    market_rows=c.execute('select id,ts,symbol,price,volume,source from market_snapshots where id>? order by id limit ?',(market_after,batch)).fetchall()
    event_rows=c.execute('select id,ts,source,title,url,category from information_events where id>? order by id limit ?',(events_after,batch)).fetchall()
    run_rows=c.execute('select id,ts,job,status,detail from system_runs where id>? order by id limit ?',(runs_after,batch)).fetchall()
    agent_rows=[];position_rows=[];trade_rows=[];mark_rows=[];reputation_rows=[];alert_rows=[];notification_rows=[];node_rows=[]
    if base._table_exists(c,'paper_agents'):agent_rows=c.execute('select agent_id,name,strategy,initial_cash,cash,enabled,last_rebalance,created_at from paper_agents order by agent_id').fetchall()
    if base._table_exists(c,'paper_agent_positions'):position_rows=c.execute('select agent_id,symbol,qty,avg_price,updated_at from paper_agent_positions order by agent_id,symbol').fetchall()
    if base._table_exists(c,'paper_agent_trades'):trade_rows=c.execute('select id,ts,agent_id,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason from paper_agent_trades where id>? order by id limit ?',(trades_after,batch)).fetchall()
    if base._table_exists(c,'paper_agent_marks'):mark_rows=c.execute('select id,ts,agent_id,total,cash,invested,drawdown_pct from paper_agent_marks where id>? order by id limit ?',(marks_after,batch)).fetchall()
    if base._table_exists(c,'source_reputation'):reputation_rows=c.execute('select source,events,actionable,avg_abs_move,precision_proxy,confidence,score,updated_at from source_reputation order by score desc').fetchall()
    if base._table_exists(c,'silence_alerts'):alert_rows=c.execute('select id,ts,symbol,return_pct,z_score,recent_public_catalyst,status,detail from silence_alerts where id>? order by id limit ?',(alerts_after,batch)).fetchall()
    if base._table_exists(c,'notifications'):notification_rows=c.execute('select id,ts,kind,severity,title,body,symbol,read,dedupe_key from notifications where id>? order by id limit ?',(notifications_after,batch)).fetchall()
    if base._table_exists(c,'sync_nodes'):node_rows=c.execute('select node_id,node_type,name,capabilities,last_seen,app_version,detail from sync_nodes order by last_seen desc limit 200').fetchall()
    c.close()
    market=[{'id':r[0],'origin_id':base._origin_id(r[0]),'ts':r[1],'symbol':r[2],'price':r[3],'volume':r[4],'source':r[5]} for r in market_rows]
    events=[{'id':r[0],'origin_id':base._origin_id(r[0]),'ts':r[1],'source':r[2],'title':r[3],'url':r[4],'category':r[5]} for r in event_rows]
    runs=[{'id':r[0],'origin_id':base._origin_id(r[0]),'ts':r[1],'node_id':base.NODE_ID,'kind':r[2],'status':r[3],'message':r[4]} for r in run_rows]
    reps=[{'source':r[0],'events':r[1],'actionable':r[2],'avg_abs_move':r[3],'precision_proxy':r[4],'confidence':r[5],'score':r[6],'updated_at':r[7]} for r in reputation_rows]
    alerts=[{'id':r[0],'origin_id':base._origin_id(r[0]),'ts':r[1],'symbol':r[2],'return_pct':r[3],'z_score':r[4],'recent_public_catalyst':bool(r[5]),'status':r[6],'detail':r[7]} for r in alert_rows]
    notifs=[{'id':r[0],'origin_id':base._origin_id(r[0]),'ts':r[1],'kind':r[2],'severity':r[3],'title':r[4],'body':r[5],'symbol':r[6],'read':bool(r[7]),'dedupe_key':r[8]} for r in notification_rows]
    nodes=[{'node_id':r[0],'node_type':r[1],'name':r[2],'capabilities':r[3],'last_seen':r[4],'app_version':r[5],'detail':r[6]} for r in node_rows]
    agents=[{'agent_id':r[0],'name':r[1],'strategy':r[2],'initial_cash':r[3],'cash':r[4],'enabled':bool(r[5]),'last_rebalance':r[6],'created_at':r[7]} for r in agent_rows]
    positions=[{'agent_id':r[0],'symbol':r[1],'qty':r[2],'avg_price':r[3],'updated_at':r[4]} for r in position_rows]
    trades=[{'id':r[0],'origin_id':base._origin_id(r[0]),'ts':r[1],'agent_id':r[2],'symbol':r[3],'side':r[4],'qty':r[5],'price':r[6],'gross_value':r[7],'fees':r[8],'spread_cost':r[9],'fx_cost':r[10],'reason':r[11]} for r in trade_rows]
    marks=[{'id':r[0],'origin_id':base._origin_id(r[0]),'ts':r[1],'agent_id':r[2],'total':r[3],'cash':r[4],'invested':r[5],'drawdown_pct':r[6]} for r in mark_rows]
    try:
        state=_node_payload();state.update({'source_reputation':reps,'nodes':nodes,'paper_agents':agents,'paper_positions':positions})
        _send('state',state,rows=len(reps)+len(nodes)+len(agents)+len(positions))
        _send_family('market','market_snapshots',market,cursor_key='supabase_market_id',cursor_value=market_rows[-1][0] if market_rows else None,chunk_size=MARKET_CHUNK)
        _send_family('events','information_events',events,cursor_key='supabase_event_id',cursor_value=event_rows[-1][0] if event_rows else None,chunk_size=DEFAULT_CHUNK)
        _send_family('runs','system_runs',runs,cursor_key='supabase_run_id',cursor_value=run_rows[-1][0] if run_rows else None,chunk_size=DEFAULT_CHUNK)
        _send_family('alerts','silence_alerts',alerts,cursor_key='supabase_alert_id',cursor_value=alert_rows[-1][0] if alert_rows else None,chunk_size=DEFAULT_CHUNK)
        _send_family('notifications','notifications',notifs,cursor_key='supabase_notification_id',cursor_value=notification_rows[-1][0] if notification_rows else None,chunk_size=DEFAULT_CHUNK)
        _send_family('trades','paper_trades',trades,cursor_key='supabase_agent_trade_id',cursor_value=trade_rows[-1][0] if trade_rows else None,chunk_size=DEFAULT_CHUNK)
        _send_family('marks','portfolio_values',marks,cursor_key='supabase_agent_mark_id',cursor_value=mark_rows[-1][0] if mark_rows else None,chunk_size=MARK_CHUNK)
        with _LOCK:_PARTITION['completed_cycles']+=1;_PARTITION['last_cycle_ms']=round((time.monotonic()-started)*1000.0,2)
    except Exception:
        with _LOCK:_PARTITION['failed_cycles']+=1;_PARTITION['last_cycle_ms']=round((time.monotonic()-started)*1000.0,2)
        raise
    return {'enabled':True,'market':len(market_rows),'events':len(event_rows),'runs':len(run_rows),'reputation':len(reputation_rows),'alerts':len(alert_rows),'notifications':len(notification_rows),'nodes':len(node_rows),'agents':len(agent_rows),'positions':len(position_rows),'trades':len(trade_rows),'marks':len(mark_rows),'origin_session_prefix':base._SYNC_PREFIX,'partitioned':True,'backpressure':backpressure,'partition_telemetry':partition_telemetry(),'telemetry':sync_telemetry(),'real_trading':False}
