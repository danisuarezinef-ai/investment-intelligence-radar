import json, os, random, threading, time, urllib.request, urllib.error
from radar_core import con, init_db
from radar_learning import init_learning_db
from radar_learning_guarded import init_guarded_learning_db
from radar_historical_lab import init_historical_lab_db
from radar_reputation_v2 import init_reputation_v2_db
from radar_brain_evolution import init_brain_db
from radar_investment_memory import init_memory

SYNC_URL=os.environ.get('SUPABASE_LEARNING_SYNC_URL','').strip()
SYNC_TOKEN=os.environ.get('RADAR_SYNC_TOKEN','').strip()
NODE_ID=os.environ.get('RADAR_NODE_ID','cloud-primary').strip() or 'cloud-primary'
MAX_LEARNING_BATCH=max(50,min(500,int(os.environ.get('RADAR_LEARNING_SYNC_BATCH','250') or 250)))
LEARNING_HTTP_TIMEOUT=max(5.0,float(os.environ.get('RADAR_LEARNING_SYNC_TIMEOUT_SECONDS','20') or 20))
LEARNING_HTTP_ATTEMPTS=max(1,min(5,int(os.environ.get('RADAR_LEARNING_SYNC_ATTEMPTS','3') or 3)))
LEARNING_CIRCUIT_FAILURES=max(2,int(os.environ.get('RADAR_LEARNING_SYNC_CIRCUIT_FAILURES','3') or 3))
LEARNING_CIRCUIT_COOLDOWN=max(15.0,float(os.environ.get('RADAR_LEARNING_SYNC_CIRCUIT_COOLDOWN_SECONDS','90') or 90))
RETRYABLE_HTTP={408,425,429,500,502,503,504}

TABLES={
 'predictions':['id','created_at','symbol','horizon','model_version','score','confidence','entry_price','thesis','features','regime','source_snapshot'],
 'prediction_outcomes':['rowid','prediction_id','horizon','evaluated_at','exit_price','return_pct','benchmark_return_pct','excess_return_pct','hit','calibration_error','metadata'],
 'learning_cycles':['id','created_at','prior_version','new_version','observations','objective_before','objective_after','accepted','weight_delta','calibration','notes'],
 'model_evaluations':['id','created_at','model_version','evaluation_role','sample_start','sample_end','observations','hit_rate','brier','signed_return','objective','metadata'],
 'market_regimes':['id','ts','regime','confidence','features','model_version'],
 'causal_edges':['id','created_at','source_node','relation','target_node','depth','confidence','evidence_event_id','horizon','metadata'],
 'thesis_history':['id','ts','symbol','horizon','model_version','score','confidence','status','thesis','change_reason','trigger_event_ids'],
 'portfolio_recommendations':['id','ts','model_version','horizon','symbol','target_weight','score','risk_contribution','rationale','metadata'],
 'signal_weak_events':['id','created_at','topic','symbol','strength','novelty','cross_source_count','explanation','evidence','status'],
 'audit_events':['id','ts','component','test_name','status','detail','metrics'],
 'source_reputation_dimensions':['id','source','topic','horizon','observations','actionable','hit_rate','avg_abs_move','lead_score','noise_penalty','score','updated_at','metadata'],
 'historical_lab_runs':['id','created_at','base_model','candidate_version','symbols','observations','folds','positive_folds','mean_gain','median_gain','test_objective_champion','test_objective_challenger','accepted','promoted','candidate_weights','metadata'],
 'historical_fold_results':['id','run_id','fold_no','train_start','train_end','validation_start','validation_end','observations_train','observations_validation','champion_objective','challenger_objective','gain','challenger_weights','metadata'],
 'historical_challenger_results':['id','run_id','challenger_name','folds','positive_folds','mean_gain','median_gain','vault_objective','vault_gain','rank_score','selected','weights','metadata'],
 'brain_lineages':['id','created_at','lineage','parent','generation','specialist_regime','weights','status','reason','metrics','family','mutation','specialization','training_method','features','updated_at'],
 'brain_evidence':['id','created_at','lineage','tier','regime','horizon','n','objective','hit_rate','drawdown','score','metadata','evidence_key'],
 'brain_transfer':['id','created_at','lineage','historical_score','live_score','transfer_ratio','n_live','regime','horizon','metadata'],
 'brain_meta_methods':['id','method','trials','historical_wins','live_wins','transfer_mean','last_seen','metadata'],
 'brain_vault_registry':['id','vault_key','start_date','end_date','vault_type','status','opens','last_opened','candidate_evaluated','result','reuse_penalty','metadata'],
 'brain_vault_events':['id','created_at','vault_key','lineage','action','purpose','result','epistemic_penalty'],
 'brain_hall_of_fame':['id','created_at','lineage','category','reason','score','metadata'],
 'brain_graveyard':['id','created_at','lineage','reason','failed_regime','failed_horizon','score','metadata'],
 'brain_shadow_predictions':['id','prediction_key','created_at','lineage','symbol','horizon','cutoff','due_at','score','confidence','features','provenance','outcome','evaluated_at'],
 'brain_generation_runs':['id','created_at','generation','champion','candidates_tested','candidates_surviving','status','configuration','result'],
}
JSON_FIELDS={'features','source_snapshot','metadata','weight_delta','calibration','trigger_event_ids','evidence','metrics','candidate_weights','challenger_weights','weights','mutation','specialization','provenance','configuration','result'}
BOOL_FIELDS={'hit','accepted','promoted','selected'}

class LearningSyncCircuitOpen(RuntimeError):pass
_LOCK=threading.RLock()
_STATE={'requests':0,'successes':0,'terminal_failures':0,'retry_attempts':0,'consecutive_failures':0,'recoveries':0,'circuit_open_count':0,'circuit_until':0.0,'last_success_epoch':None,'last_error_epoch':None,'last_error_type':None,'last_error':None,'last_latency_ms':None,'last_attempts_used':0,'last_payload_rows':{}}

def enabled():return bool(SYNC_URL and SYNC_TOKEN)
def _get(k):
 c=con();r=c.execute('select value from control where key=?',(k,)).fetchone();c.close();return int(r[0]) if r and str(r[0]).isdigit() else 0
def _set(k,v):
 c=con();c.execute('insert into control(key,value) values(?,?) on conflict(key) do update set value=excluded.value',(k,str(v)));c.commit();c.close()
def _reset_learning_sync_state_for_tests():
 with _LOCK:
  _STATE.update({'requests':0,'successes':0,'terminal_failures':0,'retry_attempts':0,'consecutive_failures':0,'recoveries':0,'circuit_open_count':0,'circuit_until':0.0,'last_success_epoch':None,'last_error_epoch':None,'last_error_type':None,'last_error':None,'last_latency_ms':None,'last_attempts_used':0,'last_payload_rows':{}})
def learning_sync_telemetry():
 with _LOCK:s=dict(_STATE);s['last_payload_rows']=dict(_STATE.get('last_payload_rows') or {})
 remain=max(0.0,float(s.pop('circuit_until',0.0))-time.monotonic())
 status='NOT_CONFIGURED' if not enabled() else ('CIRCUIT_OPEN' if remain>0 else ('DEGRADED' if s.get('consecutive_failures',0) else ('STARTING' if s.get('last_success_epoch') is None else 'HEALTHY')))
 s.update({'status':status,'configured':enabled(),'circuit_open':remain>0,'circuit_remaining_seconds':round(remain,3),'max_batch':MAX_LEARNING_BATCH,'default_timeout_seconds':LEARNING_HTTP_TIMEOUT,'default_attempts':LEARNING_HTTP_ATTEMPTS,'timeout_means_missing_data':False,'cursors_advance_only_after_remote_success':True,'real_trading':False});return s

def _post(p,timeout=None,attempts=None,base_delay=.75):
 timeout=LEARNING_HTTP_TIMEOUT if timeout is None else max(1.0,float(timeout));attempts=LEARNING_HTTP_ATTEMPTS if attempts is None else max(1,min(5,int(attempts)))
 with _LOCK:
  remain=max(0.0,float(_STATE['circuit_until'])-time.monotonic())
  if remain>0:raise LearningSyncCircuitOpen(f'Learning sync circuit open; retry after {remain:.1f}s')
  _STATE['requests']+=1;_STATE['last_payload_rows']={k:len(v) for k,v in p.items() if isinstance(v,list)}
 started=time.monotonic();data=json.dumps(p,ensure_ascii=False).encode();req=urllib.request.Request(SYNC_URL,data=data,method='POST',headers={'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'InvestmentIntelligenceRadarLearning/2.1'})
 used=0
 try:
  for attempt in range(attempts):
   used=attempt+1
   try:
    with urllib.request.urlopen(req,timeout=timeout) as r:result=json.loads(r.read().decode())
    latency=round((time.monotonic()-started)*1000,2)
    with _LOCK:
     if _STATE['consecutive_failures']:_STATE['recoveries']+=1
     _STATE.update({'successes':_STATE['successes']+1,'consecutive_failures':0,'circuit_until':0.0,'last_success_epoch':time.time(),'last_latency_ms':latency,'last_attempts_used':used,'last_error_type':None,'last_error':None})
    return result
   except urllib.error.HTTPError as e:
    try:body=e.read().decode('utf-8','replace')
    except Exception:body=''
    err=RuntimeError(f'learning sync HTTP {e.code}: {body[:1000]}')
    if e.code not in RETRYABLE_HTTP or attempt>=attempts-1:raise err from e
   except (urllib.error.URLError,TimeoutError,OSError):
    if attempt>=attempts-1:raise
   with _LOCK:_STATE['retry_attempts']+=1
   time.sleep(max(0.0,float(base_delay))*(2**attempt)*random.uniform(.8,1.2))
 except LearningSyncCircuitOpen:raise
 except Exception as exc:
  latency=round((time.monotonic()-started)*1000,2)
  with _LOCK:
   _STATE['terminal_failures']+=1;_STATE['consecutive_failures']+=1;_STATE['last_error_epoch']=time.time();_STATE['last_error_type']=type(exc).__name__;_STATE['last_error']=str(exc)[:500];_STATE['last_latency_ms']=latency;_STATE['last_attempts_used']=used
   if _STATE['consecutive_failures']>=LEARNING_CIRCUIT_FAILURES:
    was_open=_STATE['circuit_until']>time.monotonic();_STATE['circuit_until']=time.monotonic()+LEARNING_CIRCUIT_COOLDOWN
    if not was_open:_STATE['circuit_open_count']+=1
  raise

def _decode(k,v):
 if k in BOOL_FIELDS:return bool(v)
 if k in JSON_FIELDS:
  if isinstance(v,(dict,list)):return v
  try:return json.loads(v or ('[]' if k in ('trigger_event_ids','evidence') else '{}'))
  except:return [] if k in ('trigger_event_ids','evidence') else {}
 return v

def sync_learning_once(batch=750):
 if not enabled():return {'enabled':False,'telemetry':learning_sync_telemetry()}
 batch=max(1,min(int(batch),MAX_LEARNING_BATCH))
 init_db();init_learning_db();init_guarded_learning_db();init_historical_lab_db();init_reputation_v2_db();init_brain_db();memory=con();init_memory(memory);memory.close();payload={'node_id':NODE_ID};c=con();counts={}
 rows=c.execute('select version,created_at,parent_version,status,weights,metrics,notes from model_versions order by created_at,version').fetchall();payload['model_versions']=[{'version':r[0],'created_at':r[1],'parent_version':r[2],'status':r[3],'weights':_decode('metadata',r[4]),'metrics':_decode('metadata',r[5]),'notes':r[6],'origin_node':NODE_ID,'origin_id':i+1} for i,r in enumerate(rows)];counts['model_versions']=len(rows)
 for table,cols in TABLES.items():
  key='learning_sync_'+table;idcol='rowid' if table=='prediction_outcomes' else 'id'
  if table=='historical_lab_runs':rs=c.execute(f"select {','.join(cols)} from {table} order by id desc limit 100").fetchall();rs=list(reversed(rs))
  else:after=_get(key);q=f"select {','.join(cols)} from {table} where {idcol}>? order by {idcol} limit ?";rs=c.execute(q,(after,batch)).fetchall()
  out=[]
  for r in rs:
   d={}
   for k,v in zip(cols,r):
    if k in ('rowid','id'):continue
    if table in ('historical_fold_results','historical_challenger_results') and k=='run_id':d['run_origin_node']=NODE_ID;d['run_origin_id']=int(v);continue
    d[k]=_decode(k,v)
   origin_id=int(r[0]);d['origin_node']=NODE_ID;d['origin_id']=origin_id;out.append(d)
  payload[table]=out;counts[table]=len(out)
 after=_get('learning_sync_prediction_ledger');rs=c.execute('''select rowid,id,created_at,target_date,asset,horizon,model_version,prediction_hash,feature_fingerprint,thesis_fingerprint,confidence,uncertainty,decision_state,paper_allocation,data_cutoff,known_at_boundary,provenance_snapshot,payload,outcome,evaluated_at from prediction_ledger where rowid>? order by rowid limit ?''',(after,batch)).fetchall()
 payload['decision_forward_ledger']=[{'origin_node':NODE_ID,'origin_id':str(r[0]),'local_prediction_id':r[1],'created_at':r[2],'target_date':r[3],'symbol':r[4],'horizon':r[5],'model_version':r[6],'prediction_hash':r[7],'feature_fingerprint':r[8],'thesis_fingerprint':r[9],'confidence':r[10],'uncertainty':_decode('metadata',r[11]),'decision_state':r[12],'paper_allocation':_decode('metadata',r[13]),'data_cutoff':r[14],'known_at_boundary':r[15],'provenance_snapshot':_decode('metadata',r[16]),'payload':_decode('metadata',r[17]),'outcome':_decode('metadata',r[18]) if r[18] is not None else None,'evaluated_at':r[19]} for r in rs];counts['decision_forward_ledger']=len(rs)
 tafter=_get('learning_sync_thesis_events');trs=c.execute('select id,event_time,thesis_id,state,payload,event_hash from thesis_events where id>? order by id limit ?',(tafter,batch)).fetchall();payload['decision_thesis_events']=[{'origin_node':NODE_ID,'origin_id':str(r[0]),'event_time':r[1],'thesis_id':r[2],'state':r[3],'payload':_decode('metadata',r[4]),'event_hash':r[5]} for r in trs];counts['decision_thesis_events']=len(trs)
 c.close();result=_post(payload)
 # Every cursor is advanced only after the remote authority confirms the whole request.
 for table in TABLES:
  if table=='historical_lab_runs':continue
  arr=payload.get(table) or []
  if arr:_set('learning_sync_'+table,max(int(x['origin_id']) for x in arr))
 if rs:_set('learning_sync_prediction_ledger',max(int(x[0]) for x in rs))
 if trs:_set('learning_sync_thesis_events',max(int(x[0]) for x in trs))
 return {'enabled':True,**counts,'remote':result,'telemetry':learning_sync_telemetry()}
