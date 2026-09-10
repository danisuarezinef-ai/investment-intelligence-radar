"""Durable authority bridge for Railway's ephemeral filesystem.

Restores only exact rows previously persisted in Supabase. It never synthesizes,
backdates or reconstructs forward decisions. Autonomous runtime evidence is copied
idempotently to/from the persistent authority so deploys do not erase observed time.
"""
from __future__ import annotations

import json, os, urllib.request, urllib.error
from radar_core import con, init_db
from radar_investment_memory import init_memory

REAL_TRADING=False
SYNC_URL=os.environ.get('SUPABASE_LEARNING_SYNC_URL','').strip()
SYNC_TOKEN=os.environ.get('RADAR_SYNC_TOKEN','').strip()
NODE_ID=os.environ.get('RADAR_NODE_ID','cloud-primary').strip() or 'cloud-primary'


def enabled():return bool(SYNC_URL and SYNC_TOKEN)


def _post(payload):
    data=json.dumps(payload,ensure_ascii=False,default=str).encode('utf-8')
    req=urllib.request.Request(SYNC_URL,data=data,method='POST',headers={'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'InvestmentIntelligenceRadarAuthority/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=40) as r:return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body=exc.read().decode('utf-8','replace');raise RuntimeError(f'authority HTTP {exc.code}: {body[:1000]}')


def summarize_paper_equity_daily(rows,days=30):
    """Normalize observed daily aggregate PAPER marks without synthesizing gaps."""
    window=max(1,min(int(days or 30),90));clean={}
    for raw in rows or []:
        if not isinstance(raw,dict):continue
        day=str(raw.get('day') or '')[:10]
        if len(day)!=10:continue
        try:equity=float(raw.get('equity'));agents=int(raw.get('agents') or 0)
        except (TypeError,ValueError):continue
        if equity<0 or agents<=0:continue
        clean[day]={'date':day,'equity':equity,'agents':agents}
    series=[clean[k] for k in sorted(clean)]
    values=[row['equity'] for row in series]
    current=values[-1] if values else None;first=values[0] if values else None
    change=((current/first)-1.0)*100.0 if current is not None and first not in (None,0) and len(values)>=2 else None
    return {
        'status':'OK' if series else 'WAITING_FOR_HISTORY',
        'window_days':window,
        'observed_days':len(series),
        'first_date':series[0]['date'] if series else None,
        'last_date':series[-1]['date'] if series else None,
        'daily_equity_30d':series,
        'current_equity':current,
        'month_change_pct':change,
        'month_high':max(values) if values else None,
        'month_low':min(values) if values else None,
        'source':'SUPABASE_PERSISTED_PAPER_AGENT_MARKS',
        'backfilled':False,
        'reconstructed':False,
        'real_trading':False,
    }


def paper_equity_curve(days=30):
    """Read the durable observed PAPER equity curve from Supabase authority."""
    window=max(1,min(int(days or 30),90))
    if not enabled():
        out=summarize_paper_equity_daily([],window);out['status']='AUTHORITY_DISABLED';return out
    remote=_post({'action':'paper_equity_daily','node_id':NODE_ID,'days':window,'real_trading':False})
    out=summarize_paper_equity_daily(remote.get('daily_equity') or [],window)
    out['authority_ok']=bool(remote.get('ok'));out['real_trading']=False
    return out


def _j(value):
    if value is None:return None
    if isinstance(value,str):return value
    return json.dumps(value,sort_keys=True,separators=(',',':'),default=str)


def _table_payload(c,table,limit=2000):
    exists=c.execute("select 1 from sqlite_master where type='table' and name=?",(table,)).fetchone()
    if not exists:return []
    cols=[r[1] for r in c.execute(f'pragma table_info({table})').fetchall()]
    if not cols:return []
    rows=c.execute(f'select * from {table} order by rowid desc limit ?',(int(limit),)).fetchall()
    return [{k:v for k,v in zip(cols,row)} for row in reversed(rows)]


def push_autonomy_snapshot(limit=2000):
    if not enabled():return {'enabled':False,'real_trading':False}
    init_db();c=con();state=_table_payload(c,'autonomous_simulator_state',1);runs=_table_payload(c,'autonomous_simulator_runs',limit);experiments=_table_payload(c,'autonomous_experiment_results',limit);ticks=_table_payload(c,'autonomy_soak_ticks',limit);c.close()
    runs=[dict(r,id=r.get('run_id')) if r.get('run_id') is not None else r for r in runs]
    payload={'action':'persist_autonomy','node_id':NODE_ID,'real_trading':False,'state':state[0] if state else None,'runs':runs,'experiments':experiments,'soak_ticks':ticks}
    result=_post(payload);result['real_trading']=False;return result


def _unpack(raw):return raw.get('payload') if isinstance(raw,dict) and isinstance(raw.get('payload'),dict) else raw


def _restore_generic(c,table,rows):
    exists=c.execute("select 1 from sqlite_master where type='table' and name=?",(table,)).fetchone()
    if not exists or not rows:return 0
    allowed={r[1] for r in c.execute(f'pragma table_info({table})').fetchall()};done=0
    for raw in rows:
        row=_unpack(raw)
        if not isinstance(row,dict):continue
        keys=[k for k in row if k in allowed]
        if not keys:continue
        vals=[_j(row[k]) if isinstance(row[k],(dict,list)) else row[k] for k in keys]
        cur=c.execute(f"insert or ignore into {table}({','.join(keys)}) values({','.join('?' for _ in keys)})",vals)
        done+=max(0,int(cur.rowcount or 0))
    return done


def _restore_state(c,rows):
    if not rows:return 0
    row=_unpack(rows[-1])
    if not isinstance(row,dict):return 0
    allowed={r[1] for r in c.execute('pragma table_info(autonomous_simulator_state)').fetchall()}
    keys=[k for k in row if k in allowed and k!='id']
    if not keys:return 0
    vals=[_j(row[k]) if isinstance(row[k],(dict,list)) else row[k] for k in keys]
    cur=c.execute('update autonomous_simulator_state set '+','.join(f'{k}=?' for k in keys)+' where id=1',vals)
    return max(0,int(cur.rowcount or 0))


def restore_forward_authority(rows):
    """Restore exact immutable persisted forward rows; never calls freeze_prediction."""
    init_db();c=con();init_memory(c);inserted=0;preserved=0
    for r in rows or []:
        if not isinstance(r,dict):continue
        pid=r.get('local_prediction_id') or r.get('prediction_hash')
        required=('origin_node','origin_id','created_at','target_date','symbol','horizon','model_version','prediction_hash','feature_fingerprint','thesis_fingerprint','confidence','uncertainty','decision_state','data_cutoff','known_at_boundary','provenance_snapshot','payload')
        if not pid or any(r.get(k) is None for k in required):continue
        existing=c.execute('select prediction_hash,outcome from prediction_ledger where origin_node=? and origin_id=?',(str(r['origin_node']),str(r['origin_id']))).fetchone()
        if existing:
            if existing[0]!=r['prediction_hash']:raise RuntimeError('forward authority conflict')
            preserved+=1;continue
        c.execute('''insert into prediction_ledger(id,origin_node,origin_id,created_at,target_date,asset,horizon,model_version,prediction_hash,feature_fingerprint,thesis_fingerprint,confidence,uncertainty,decision_state,paper_allocation,data_cutoff,known_at_boundary,provenance_snapshot,payload,outcome,evaluated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
          str(pid),str(r['origin_node']),str(r['origin_id']),r['created_at'],r['target_date'],r['symbol'],r['horizon'],r['model_version'],r['prediction_hash'],r['feature_fingerprint'],r['thesis_fingerprint'],float(r['confidence']),_j(r['uncertainty']),r['decision_state'],_j(r.get('paper_allocation')),r['data_cutoff'],r['known_at_boundary'],_j(r['provenance_snapshot']),_j(r['payload']),_j(r.get('outcome')),r.get('evaluated_at')));inserted+=1
    if rows:
        earliest=min((str(x.get('created_at')) for x in rows if isinstance(x,dict) and x.get('created_at')),default=None)
        if earliest:c.execute("insert into control(key,value) values('shadow_forward_started_at',?) on conflict(key) do nothing",(earliest,))
    c.commit();c.close();return {'restored':inserted,'already_present':preserved,'backfill_used':False,'reconstructed':False,'real_trading':False}


def rehydrate_authority():
    if not enabled():return {'enabled':False,'status':'DISABLED','real_trading':False}
    remote=_post({'action':'rehydrate_authority','node_id':NODE_ID,'real_trading':False});forward=restore_forward_authority(remote.get('decision_forward_ledger') or []);init_db();c=con()
    restored={'state':_restore_state(c,remote.get('autonomy_state') or []),'runs':_restore_generic(c,'autonomous_simulator_runs',remote.get('autonomy_runs') or []),'experiments':_restore_generic(c,'autonomous_experiment_results',remote.get('autonomy_experiments') or []),'soak_ticks':_restore_generic(c,'autonomy_soak_ticks',remote.get('autonomy_soak_ticks') or [])};c.commit();c.close()
    return {'enabled':True,'status':'RESTORED_EXACT_PERSISTED_EVIDENCE','forward':forward,'autonomy':restored,'backfill_used':False,'reconstructed':False,'real_trading':False}
