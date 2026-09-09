"""Autonomous reproducible simulation factory. Historical evidence never promotes live by itself."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from radar_core import con
from radar_historical_lab import run_historical_lab
REAL_TRADING=False
BASELINES=('cash','equal_weight','momentum','value','quality','low_vol')
def _now():return datetime.now(timezone.utc).isoformat()
def _canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def experiment_id(config):return hashlib.sha256(_canonical(config).encode()).hexdigest()
def init_simulation_db():
 c=con();c.execute('''create table if not exists simulation_factory_runs(experiment_id text primary key,created_at text not null,completed_at text,status text not null,config_json text not null,result_json text,real_trading integer not null default 0)''');c.commit();c.close()
def run_simulation(config=None):
 init_simulation_db();cfg=dict(config or {});cfg.setdefault('engine','historical_lab');cfg.setdefault('baselines',list(BASELINES));cfg.setdefault('real_trading',False);eid=experiment_id(cfg);c=con();row=c.execute('select status,result_json from simulation_factory_runs where experiment_id=?',(eid,)).fetchone()
 if row and row[0]=='COMPLETED':c.close();return {'experiment_id':eid,'status':'COMPLETED','cached':True,'result':json.loads(row[1]),'real_trading':False}
 c.execute('insert or replace into simulation_factory_runs(experiment_id,created_at,status,config_json,real_trading) values(?,?,?,?,0)',(eid,_now(),'RUNNING',_canonical(cfg)));c.commit();c.close()
 try:
  result=run_historical_lab(promote=False);payload={'historical_lab':result,'baselines_required':list(BASELINES),'promotion_authorized':False,'real_trading':False};c=con();c.execute("update simulation_factory_runs set completed_at=?,status='COMPLETED',result_json=? where experiment_id=?",(_now(),_canonical(payload),eid));c.commit();c.close();return {'experiment_id':eid,'status':'COMPLETED','cached':False,'result':payload,'real_trading':False}
 except Exception as exc:
  c=con();c.execute("update simulation_factory_runs set completed_at=?,status='FAILED',result_json=? where experiment_id=?",(_now(),_canonical({'error':str(exc)[:1000]}),eid));c.commit();c.close();raise
