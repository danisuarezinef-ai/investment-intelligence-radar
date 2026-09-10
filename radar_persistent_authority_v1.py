"""Durable authority bridge for Railway's ephemeral filesystem.

Restores only exact rows previously persisted in Supabase. It never synthesizes,
backdates or reconstructs forward decisions. PAPER/autonomy evidence is copied
idempotently so deploys do not erase observed state.
"""
from __future__ import annotations
import json,os,urllib.request,urllib.error
from radar_core import con,init_db
from radar_investment_memory import init_memory
from radar_experiment_memory_v2 import init_memory as init_experiment_memory
REAL_TRADING=False
SYNC_URL=os.environ.get('SUPABASE_LEARNING_SYNC_URL','').strip();SYNC_TOKEN=os.environ.get('RADAR_SYNC_TOKEN','').strip();NODE_ID=os.environ.get('RADAR_NODE_ID','cloud-primary').strip() or 'cloud-primary'

def enabled():return bool(SYNC_URL and SYNC_TOKEN)
def _post(payload):
 data=json.dumps(payload,ensure_ascii=False,default=str).encode();req=urllib.request.Request(SYNC_URL,data=data,method='POST',headers={'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'InvestmentIntelligenceRadarAuthority/1.1'})
 try:
  with urllib.request.urlopen(req,timeout=40) as r:return json.loads(r.read().decode())
 except urllib.error.HTTPError as exc:raise RuntimeError(f'authority HTTP {exc.code}: {exc.read().decode("utf-8","replace")[:1000]}')
def _j(v):return v if v is None or isinstance(v,str) else json.dumps(v,sort_keys=True,separators=(',',':'),default=str)
def _table_payload(c,table,limit=2000):
 if not c.execute("select 1 from sqlite_master where type='table' and name=?",(table,)).fetchone():return []
 cols=[r[1] for r in c.execute(f'pragma table_info({table})')];rows=c.execute(f'select * from {table} order by rowid desc limit ?',(int(limit),)).fetchall();return [{k:v for k,v in zip(cols,row)} for row in reversed(rows)]
def _transport(rows,key):return [dict(r,id=r.get(key)) for r in rows if r.get(key) is not None]
def push_autonomy_snapshot(limit=2000):
 if not enabled():return {'enabled':False,'real_trading':False}
 init_db();init_experiment_memory();c=con();state=_table_payload(c,'autonomous_simulator_state',1);runs=_transport(_table_payload(c,'autonomous_simulator_runs',limit),'run_id');experiments=_table_payload(c,'autonomous_experiment_results',limit);ticks=_table_payload(c,'autonomy_soak_ticks',limit);paper=_table_payload(c,'paper_account',1);positions=_transport(_table_payload(c,'paper_positions',limit),'symbol');trades=_table_payload(c,'paper_trades',limit);values=_table_payload(c,'portfolio_values',limit);memory=_transport(_table_payload(c,'experiment_memory',limit),'experiment_hash');c.close()
 payload={'action':'persist_autonomy','node_id':NODE_ID,'real_trading':False,'state':state[0] if state else None,'runs':runs,'experiments':experiments,'soak_ticks':ticks,'paper_state':paper[0] if paper else None,'paper_positions':positions,'paper_trades':trades,'portfolio_values':values,'experiment_memory':memory}
 result=_post(payload);result['real_trading']=False;return result
def _unpack(raw):return raw.get('payload') if isinstance(raw,dict) and isinstance(raw.get('payload'),dict) else raw
def _restore_generic(c,table,rows):
 if not c.execute("select 1 from sqlite_master where type='table' and name=?",(table,)).fetchone() or not rows:return 0
 allowed={r[1] for r in c.execute(f'pragma table_info({table})')};done=0
 for raw in rows:
  row=_unpack(raw)
  if not isinstance(row,dict):continue
  keys=[k for k in row if k in allowed];vals=[_j(row[k]) if isinstance(row[k],(dict,list)) else row[k] for k in keys]
  if keys:done+=max(0,int(c.execute(f"insert or ignore into {table}({','.join(keys)}) values({','.join('?' for _ in keys)})",vals).rowcount or 0))
 return done
def _restore_singleton(c,table,rows,pk='id',pk_value=1):
 if not rows:return 0
 row=_unpack(rows[-1]);allowed={r[1] for r in c.execute(f'pragma table_info({table})')}
 if not isinstance(row,dict) or not allowed:return 0
 row=dict(row);row[pk]=pk_value;keys=[k for k in row if k in allowed];vals=[_j(row[k]) if isinstance(row[k],(dict,list)) else row[k] for k in keys]
 placeholders=','.join('?' for _ in keys);updates=','.join(f'{k}=excluded.{k}' for k in keys if k!=pk)
 c.execute(f"insert into {table}({','.join(keys)}) values({placeholders}) on conflict({pk}) do update set {updates}",vals);return 1
def restore_forward_authority(rows):
 init_db();c=con();init_memory(c);inserted=preserved=0
 for r in rows or []:
  if not isinstance(r,dict):continue
  pid=r.get('local_prediction_id') or r.get('prediction_hash');required=('origin_node','origin_id','created_at','target_date','symbol','horizon','model_version','prediction_hash','feature_fingerprint','thesis_fingerprint','confidence','uncertainty','decision_state','data_cutoff','known_at_boundary','provenance_snapshot','payload')
  if not pid or any(r.get(k) is None for k in required):continue
  existing=c.execute('select prediction_hash from prediction_ledger where origin_node=? and origin_id=?',(str(r['origin_node']),str(r['origin_id']))).fetchone()
  if existing:
   if existing[0]!=r['prediction_hash']:raise RuntimeError('forward authority conflict')
   preserved+=1;continue
  c.execute('''insert into prediction_ledger(id,origin_node,origin_id,created_at,target_date,asset,horizon,model_version,prediction_hash,feature_fingerprint,thesis_fingerprint,confidence,uncertainty,decision_state,paper_allocation,data_cutoff,known_at_boundary,provenance_snapshot,payload,outcome,evaluated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(str(pid),str(r['origin_node']),str(r['origin_id']),r['created_at'],r['target_date'],r['symbol'],r['horizon'],r['model_version'],r['prediction_hash'],r['feature_fingerprint'],r['thesis_fingerprint'],float(r['confidence']),_j(r['uncertainty']),r['decision_state'],_j(r.get('paper_allocation')),r['data_cutoff'],r['known_at_boundary'],_j(r['provenance_snapshot']),_j(r['payload']),_j(r.get('outcome')),r.get('evaluated_at')));inserted+=1
 if rows:
  earliest=min((str(x.get('created_at')) for x in rows if isinstance(x,dict) and x.get('created_at')),default=None)
  if earliest:c.execute("insert into control(key,value) values('shadow_forward_started_at',?) on conflict(key) do nothing",(earliest,))
 c.commit();c.close();return {'restored':inserted,'already_present':preserved,'backfill_used':False,'reconstructed':False,'real_trading':False}
def rehydrate_authority():
 if not enabled():return {'enabled':False,'status':'DISABLED','real_trading':False}
 remote=_post({'action':'rehydrate_authority','node_id':NODE_ID,'real_trading':False});forward=restore_forward_authority(remote.get('decision_forward_ledger') or []);init_db();init_experiment_memory();c=con()
 restored={'state':_restore_singleton(c,'autonomous_simulator_state',remote.get('autonomy_state') or []),'runs':_restore_generic(c,'autonomous_simulator_runs',remote.get('autonomy_runs') or []),'experiments':_restore_generic(c,'autonomous_experiment_results',remote.get('autonomy_experiments') or []),'soak_ticks':_restore_generic(c,'autonomy_soak_ticks',remote.get('autonomy_soak_ticks') or []),'paper_state':_restore_singleton(c,'paper_account',remote.get('paper_state') or []),'paper_positions':_restore_generic(c,'paper_positions',remote.get('paper_positions') or []),'paper_trades':_restore_generic(c,'paper_trades',remote.get('paper_trades') or []),'portfolio_values':_restore_generic(c,'portfolio_values',remote.get('portfolio_values') or []),'experiment_memory':_restore_generic(c,'experiment_memory',remote.get('experiment_memory') or [])};c.commit();c.close()
 return {'enabled':True,'status':'RESTORED_EXACT_PERSISTED_EVIDENCE','forward':forward,'restored':restored,'backfill_used':False,'reconstructed':False,'real_trading':False}
