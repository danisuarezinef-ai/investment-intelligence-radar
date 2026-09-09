"""Point-in-time corporate-action registry for simulation integrity."""
from __future__ import annotations
import json
from radar_core import con
REAL_TRADING=False
VALID_ACTIONS={'split','dividend','merger','acquisition','spinoff','ticker_change','delisting'}

def init_corporate_actions_db():
    c=con();c.execute('''create table if not exists corporate_actions_pit(
      id integer primary key autoincrement,symbol text not null,action_type text not null,
      effective_at text not null,known_at text not null,source text not null,payload text not null,
      unique(symbol,action_type,effective_at,known_at,source))''');c.commit();c.close()

def record_action(symbol,action_type,effective_at,known_at,source,payload=None):
    action=str(action_type).lower().strip()
    if action not in VALID_ACTIONS:raise ValueError('invalid corporate action')
    init_corporate_actions_db();c=con();c.execute('insert or ignore into corporate_actions_pit(symbol,action_type,effective_at,known_at,source,payload) values(?,?,?,?,?,?)',(symbol.upper(),action,effective_at,known_at,source,json.dumps(payload or {},sort_keys=True)));added=c.rowcount;c.commit();c.close();return {'added':bool(added),'real_trading':False}

def actions_known_as_of(symbol,as_of):
    init_corporate_actions_db();c=con();rows=c.execute('select action_type,effective_at,known_at,source,payload from corporate_actions_pit where symbol=? and known_at<=? order by effective_at',(symbol.upper(),as_of)).fetchall();c.close();return [{'action_type':r[0],'effective_at':r[1],'known_at':r[2],'source':r[3],'payload':json.loads(r[4] or '{}')} for r in rows]

def integrity_status():
    init_corporate_actions_db();c=con();n=c.execute('select count(*) from corporate_actions_pit').fetchone()[0];delist=c.execute("select count(*) from corporate_actions_pit where action_type='delisting'").fetchone()[0];c.close();return {'records':int(n or 0),'delistings':int(delist or 0),'coverage_verified':bool(n),'real_trading':False}
