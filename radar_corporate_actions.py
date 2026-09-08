"""Point-in-time corporate-action registry for simulation integrity."""
from __future__ import annotations
from radar_core import con

REAL_TRADING=False
VALID_ACTIONS={"split","dividend","merger","acquisition","spinoff","ticker_change","delisting"}

def init_corporate_actions_db():
    c=con()
    try:
        c.execute("""create table if not exists corporate_actions_pit(
          id integer primary key autoincrement,symbol text not null,action_type text not null,
          effective_at text not null,known_at text not null,source text not null,payload text not null,
          unique(symbol,action_type,effective_at,known_at,source))""");c.commit()
    finally:c.close()

def actions_known_as_of(symbol,as_of):
    init_corporate_actions_db();c=con()
    try:
        rows=c.execute("select action_type,effective_at,known_at,source,payload from corporate_actions_pit where symbol=? and known_at<=? order by effective_at",(symbol.upper(),as_of)).fetchall()
        return [{"action_type":r[0],"effective_at":r[1],"known_at":r[2],"source":r[3],"payload":r[4]} for r in rows]
    finally:c.close()
