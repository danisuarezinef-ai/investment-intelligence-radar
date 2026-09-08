"""Rotating temporal vaults and regime gauntlet for Brain Evolution v2."""
from __future__ import annotations
import json
from radar_core import con, now
from radar_brain_evolution import init_brain_db

DEFAULT_VAULTS=(
 ('dotcom_aftermath','2000-01-01','2003-12-31'),
 ('gfc','2007-07-01','2009-06-30'),
 ('euro_crisis','2010-04-01','2012-12-31'),
 ('china_commodity_shock','2015-01-01','2016-12-31'),
 ('volmageddon_trade_war','2018-01-01','2019-12-31'),
 ('covid_crash_rebound','2020-01-01','2021-06-30'),
 ('inflation_hiking_cycle','2021-07-01','2023-12-31'),
 ('ai_capex_cycle','2024-01-01','2025-12-31'),
)


def ensure_vaults():
    init_brain_db();c=con()
    for key,a,b in DEFAULT_VAULTS:
        c.execute("insert or ignore into brain_vault_registry(vault_key,start_date,end_date,status,opens,metadata) values(?,?,?,'sealed',0,?)",(key,a,b,json.dumps({'purpose':'temporal_out_of_sample'})))
    c.commit();c.close()


def next_vault(max_opens=3):
    ensure_vaults();c=con();r=c.execute("select vault_key,start_date,end_date,opens from brain_vault_registry where status='sealed' and opens<? order by opens asc,start_date asc limit 1",(max_opens,)).fetchone();c.close()
    return {'key':r[0],'start':r[1],'end':r[2],'opens':r[3]} if r else None


def open_vault(key,reason):
    """Auditable opening. Repeated peeking eventually retires a vault."""
    ensure_vaults();c=con();r=c.execute('select opens from brain_vault_registry where vault_key=?',(key,)).fetchone()
    if not r:c.close();raise KeyError(key)
    opens=int(r[0])+1;status='retired' if opens>=3 else 'sealed'
    c.execute('update brain_vault_registry set opens=?,last_opened=?,status=?,metadata=? where vault_key=?',(opens,now(),status,json.dumps({'last_reason':reason,'peek_penalty':round(min(.75,opens*.20),2)}),key));c.commit();c.close();return {'key':key,'opens':opens,'status':status,'peek_penalty':min(.75,opens*.20)}


def regime_gauntlet_score(results):
    """Rewards broad robustness; specialists may survive but cannot masquerade as universal champions."""
    if not results:return {'score':-1e9,'worst':None,'dispersion':None,'coverage':0}
    vals=[float(x['objective']) for x in results];mean=sum(vals)/len(vals);worst=min(vals);spread=max(vals)-worst
    failures=sum(v<=0 for v in vals);score=mean+.35*worst-.25*spread-.04*failures
    return {'score':score,'mean':mean,'worst':worst,'dispersion':spread,'coverage':len(vals),'failed_regimes':failures}
