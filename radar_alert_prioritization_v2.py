"""Prioritise operational alerts without duplicating equivalent warnings."""
from __future__ import annotations
REAL_TRADING=False
SEVERITY={'CRITICAL':0,'HIGH':1,'MEDIUM':2,'LOW':3,'INFO':4}


def prioritise(alerts, limit=20):
    dedup={}
    for alert in alerts or []:
        a=dict(alert)
        key=str(a.get('key') or a.get('code') or f"{a.get('source')}|{a.get('message')}")
        sev=str(a.get('severity') or 'INFO').upper()
        a['severity']=sev if sev in SEVERITY else 'INFO'
        current=dedup.get(key)
        if current is None or SEVERITY[a['severity']]<SEVERITY[current['severity']]:dedup[key]=a
    rows=sorted(dedup.values(),key=lambda a:(SEVERITY[a['severity']],str(a.get('source') or ''),str(a.get('message') or '')))
    critical=sum(1 for a in rows if a['severity']=='CRITICAL')
    return {'alerts':rows[:max(0,int(limit))],'total_unique':len(rows),'critical':critical,'operational_hold':critical>0,'real_trading':False}
