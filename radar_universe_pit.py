"""Point-in-time investable-universe membership and survivorship audit.

Absence of evidence is UNKNOWN, never silently interpreted as historical membership.
"""
from __future__ import annotations
from radar_core import con
REAL_TRADING=False

def init_universe_pit():
    c=con();c.execute('''create table if not exists universe_membership_pit_local(
      id integer primary key,symbol text not null,universe text not null,valid_from text not null,valid_to text,
      status text not null,source text,known_at text not null,provenance text,
      unique(symbol,universe,valid_from,known_at))''');c.commit();c.close()

def membership(symbol,as_of,universe='RADAR_GLOBAL'):
    init_universe_pit();c=con();row=c.execute('''select status,source,known_at,provenance from universe_membership_pit_local
      where symbol=? and universe=? and valid_from<=? and (valid_to is null or valid_to>?) and known_at<=?
      order by known_at desc,id desc limit 1''',(symbol,universe,as_of,as_of,as_of)).fetchone();c.close()
    if not row:return {'symbol':symbol,'as_of':as_of,'status':'UNKNOWN','pit_verified':False}
    return {'symbol':symbol,'as_of':as_of,'status':row[0],'source':row[1],'known_at':row[2],'provenance':row[3],'pit_verified':True}

def survivorship_audit(symbols,as_of,universe='RADAR_GLOBAL'):
    rows=[membership(s,as_of,universe) for s in symbols];unknown=[r['symbol'] for r in rows if not r['pit_verified']]
    return {'as_of':as_of,'symbols':len(rows),'unknown':unknown,'survivorship_bias_risk':bool(unknown),'real_trading':False}
