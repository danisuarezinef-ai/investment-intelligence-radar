"""Autonomous Simulation Factory v1.

Runs reproducible point-in-time historical experiments. Historical evidence is
research evidence only and can never promote the live operational champion by itself.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from radar_core import con
from radar_historical_lab import run_historical_lab

REAL_TRADING=False
BASELINES=("cash","equal_weight","momentum","value","quality","low_vol")

def _now(): return datetime.now(timezone.utc).isoformat()
def _canonical(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def experiment_id(config): return hashlib.sha256(_canonical(config).encode()).hexdigest()

def init_simulation_db():
    c=con()
    try:
        c.execute("""create table if not exists simulation_factory_runs(
          experiment_id text primary key,created_at text not null,completed_at text,
          status text not null,config_json text not null,result_json text,
          real_trading integer not null default 0)""");c.commit()
    finally:c.close()

def run_simulation(config=None):
    init_simulation_db();cfg=dict(config or {});cfg.setdefault("engine","historical_lab");cfg.setdefault("baselines",list(BASELINES));cfg.setdefault("real_trading",False);eid=experiment_id(cfg);c=con()
    try:
        row=c.execute("select status,result_json from simulation_factory_runs where experiment_id=?",(eid,)).fetchone()
        if row and row[0]=="COMPLETED":return {"experiment_id":eid,"status":"COMPLETED","cached":True,"result":json.loads(row[1]),"real_trading":False}
        c.execute("insert or replace into simulation_factory_runs(experiment_id,created_at,status,config_json,real_trading) values(?,?,?,?,0)",(eid,_now(),"RUNNING",_canonical(cfg)));c.commit()
        result=run_historical_lab(promote=False);payload={"historical_lab":result,"baselines_required":list(BASELINES),"promotion_authorized":False,"real_trading":False}
        c.execute("update simulation_factory_runs set completed_at=?,status='COMPLETED',result_json=? where experiment_id=?",(_now(),_canonical(payload),eid));c.commit()
        return {"experiment_id":eid,"status":"COMPLETED","cached":False,"result":payload,"real_trading":False}
    except Exception as exc:
        c.execute("update simulation_factory_runs set completed_at=?,status='FAILED',result_json=? where experiment_id=?",(_now(),_canonical({"error":str(exc)[:1000]}),eid));c.commit();raise
    finally:c.close()

def simulation_status(limit=20):
    init_simulation_db();c=con()
    try:
        rows=c.execute("select experiment_id,created_at,completed_at,status,config_json from simulation_factory_runs order by created_at desc limit ?",(int(limit),)).fetchall()
        return {"runs":[{"experiment_id":r[0],"created_at":r[1],"completed_at":r[2],"status":r[3],"config":json.loads(r[4])} for r in rows],"real_trading":False}
    finally:c.close()
