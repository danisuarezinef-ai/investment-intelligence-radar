"""Throttled causal graph refresh for continuous runtime."""
from __future__ import annotations
import time
from radar_core import con,init_db
from radar_causal import build_causal_graph,graph_summary

REAL_TRADING=False
CONTROL_KEY='causal_graph_last_refresh_epoch'


def refresh_causal_if_due(interval_seconds=900,hours=168,force=False):
    init_db();c=con();row=c.execute('select value from control where key=?',(CONTROL_KEY,)).fetchone();last=0.0
    try:last=float(row[0]) if row else 0.0
    except Exception:last=0.0
    t=time.time()
    if not force and t-last<float(interval_seconds):
        c.close();return {'refreshed':False,'due_in_seconds':max(0,int(interval_seconds-(t-last))),'summary':graph_summary(),'real_trading':False}
    c.close();created=build_causal_graph(hours=hours);c=con();c.execute('insert into control(key,value) values(?,?) on conflict(key) do update set value=excluded.value',(CONTROL_KEY,str(t)));c.commit();c.close()
    return {'refreshed':True,'edges_created':created,'summary':graph_summary(),'real_trading':False}
