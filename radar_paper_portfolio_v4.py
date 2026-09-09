"""Prospective paper portfolio v4 audit layer.

Records simulator decisions before execution and marks them immutable. It does not
submit real orders and it does not backfill historical decisions.
"""
from __future__ import annotations
import json, hashlib
from radar_core import con, now, paper_status

REAL_TRADING=False


def init_paper_v4():
    c=con()
    c.execute('''create table if not exists paper_decision_ledger_v4(
      id integer primary key, created_at text not null, payload text not null,
      payload_hash text not null unique, immutable integer not null default 1,
      backfilled integer not null default 0, real_trading integer not null default 0)''')
    c.execute('''create trigger if not exists paper_v4_no_update before update on paper_decision_ledger_v4
      begin select raise(abort,'paper_decision_ledger_v4 immutable'); end''')
    c.execute('''create trigger if not exists paper_v4_no_delete before delete on paper_decision_ledger_v4
      begin select raise(abort,'paper_decision_ledger_v4 immutable'); end''')
    c.commit();c.close()


def freeze_paper_decision(payload):
    init_paper_v4(); p=dict(payload or {})
    if p.get('backfilled') is True: raise ValueError('backfill_not_allowed')
    p['immutable']=True;p['backfilled']=False;p['real_trading']=False
    raw=json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    h=hashlib.sha256(raw.encode('utf-8')).hexdigest(); ts=now()
    c=con(); c.execute('insert or ignore into paper_decision_ledger_v4(created_at,payload,payload_hash) values(?,?,?)',(ts,raw,h)); c.commit();c.close()
    return {'created_at':ts,'payload_hash':h,'immutable':True,'backfilled':False,'real_trading':False}


def paper_portfolio_v4_status():
    init_paper_v4(); c=con(); n=c.execute('select count(*) from paper_decision_ledger_v4').fetchone()[0]; c.close()
    return {'paper_account':paper_status(),'prospective_decisions':n,'performance_claim':'PAPER / NOT VERIFIED',
            'can_trade':False,'real_trading':False}
