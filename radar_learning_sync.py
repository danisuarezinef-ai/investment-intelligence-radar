import json, os, urllib.request, urllib.error
from radar_core import con, init_db
from radar_learning import init_learning_db

SYNC_URL=os.environ.get('SUPABASE_LEARNING_SYNC_URL','').strip()
SYNC_TOKEN=os.environ.get('RADAR_SYNC_TOKEN','').strip()
NODE_ID=os.environ.get('RADAR_NODE_ID','cloud-primary').strip() or 'cloud-primary'
TABLES={
 'predictions':['id','created_at','symbol','horizon','model_version','score','confidence','entry_price','thesis','features','regime','source_snapshot'],
 'prediction_outcomes':['rowid','prediction_id','horizon','evaluated_at','exit_price','return_pct','benchmark_return_pct','excess_return_pct','hit','calibration_error','metadata'],
 'learning_cycles':['id','created_at','prior_version','new_version','observations','objective_before','objective_after','accepted','weight_delta','calibration','notes'],
 'market_regimes':['id','ts','regime','confidence','features','model_version'],
 'causal_edges':['id','created_at','source_node','relation','target_node','depth','confidence','evidence_event_id','horizon','metadata'],
 'thesis_history':['id','ts','symbol','horizon','model_version','score','confidence','status','thesis','change_reason','trigger_event_ids'],
 'portfolio_recommendations':['id','ts','model_version','horizon','symbol','target_weight','score','risk_contribution','rationale','metadata'],
 'signal_weak_events':['id','created_at','topic','symbol','strength','novelty','cross_source_count','explanation','evidence','status'],
 'audit_events':['id','ts','component','test_name','status','detail','metrics'],
}
JSON_FIELDS={'features','source_snapshot','metadata','weight_delta','calibration','trigger_event_ids','evidence','metrics'}
BOOL_FIELDS={'hit','accepted'}

def enabled():return bool(SYNC_URL and SYNC_TOKEN)
def _get(k):
 c=con();r=c.execute('select value from control where key=?',(k,)).fetchone();c.close();return int(r[0]) if r and str(r[0]).isdigit() else 0
def _set(k,v):
 c=con();c.execute('insert into control(key,value) values(?,?) on conflict(key) do update set value=excluded.value',(k,str(v)));c.commit();c.close()
def _post(p):
 data=json.dumps(p,ensure_ascii=False).encode();req=urllib.request.Request(SYNC_URL,data=data,method='POST',headers={'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'InvestmentIntelligenceRadarLearning/2.0'})
 try:
  with urllib.request.urlopen(req,timeout=35) as r:return json.loads(r.read().decode())
 except urllib.error.HTTPError as e:
  body=e.read().decode('utf-8','replace');raise RuntimeError(f'learning sync HTTP {e.code}: {body[:1000]}')
def _decode(k,v):
 if k in BOOL_FIELDS:return bool(v)
 if k in JSON_FIELDS:
  if isinstance(v,(dict,list)):return v
  try:return json.loads(v or ('[]' if k in ('trigger_event_ids','evidence') else '{}'))
  except:return [] if k in ('trigger_event_ids','evidence') else {}
 return v

def sync_learning_once(batch=750):
 if not enabled():return {'enabled':False}
 init_db();init_learning_db();payload={'node_id':NODE_ID};c=con();counts={}
 # model versions are tiny and version itself is the durable key; origin_id is omitted intentionally.
 rows=c.execute('select version,created_at,parent_version,status,weights,metrics,notes from model_versions').fetchall();payload['model_versions']=[{'version':r[0],'created_at':r[1],'parent_version':r[2],'status':r[3],'weights':_decode('metadata',r[4]),'metrics':_decode('metadata',r[5]),'notes':r[6],'origin_node':NODE_ID,'origin_id':i+1} for i,r in enumerate(rows)];counts['model_versions']=len(rows)
 for table,cols in TABLES.items():
  key='learning_sync_'+table;after=_get(key);idcol='rowid' if table=='prediction_outcomes' else 'id';q=f"select {','.join(cols)} from {table} where {idcol}>? order by {idcol} limit ?";rs=c.execute(q,(after,batch)).fetchall();out=[]
  for r in rs:
   d={}
   for k,v in zip(cols,r):
    if k=='rowid':continue
    d[k]=_decode(k,v)
   origin_id=int(r[0]);d['origin_node']=NODE_ID;d['origin_id']=origin_id;out.append(d)
  payload[table]=out;counts[table]=len(out)
 c.close();result=_post(payload)
 for table in TABLES:
  arr=payload.get(table) or []
  if arr:_set('learning_sync_'+table,max(int(x['origin_id']) for x in arr))
 return {'enabled':True,**counts,'remote':result}
