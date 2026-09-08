import json, statistics
from datetime import datetime, timezone, timedelta

from radar_core import con, init_db, now
from radar_intelligence import _symbols_in_title, _price_near

HORIZONS={'1d':24,'1w':24*7,'1m':24*30}

def init_reputation_v2_db():
    init_db();c=con();c.execute('''create table if not exists source_reputation_dimensions(
      id integer primary key, source text not null, topic text not null, horizon text not null,
      observations integer not null default 0, actionable integer not null default 0,
      hit_rate real, avg_abs_move real, lead_score real, noise_penalty real, score real,
      updated_at text not null, metadata text,
      unique(source,topic,horizon))''');c.commit();c.close()

def _topic(category,title):
    c=(category or '').lower();t=(title or '').lower()
    if c in ('science','technology') or any(x in t for x in ('ai','chip','semiconductor','quantum','battery')):return 'technology'
    if c in ('regulatory','policy') or any(x in t for x in ('sec ','fda','regulation','tariff','sanction')):return 'regulation'
    if any(x in t for x in ('war','defense','geopolit','export control')):return 'geopolitics'
    if any(x in t for x in ('earnings','revenue','guidance','profit')):return 'fundamentals'
    return 'general'

def evaluate_source_dimensions(window_days=120):
    init_reputation_v2_db();cut=(datetime.now(timezone.utc)-timedelta(days=window_days)).isoformat();c=con();events=c.execute('select ts,source,title,category from information_events where ts>=? order by ts',(cut,)).fetchall();groups={}
    for ts,source,title,category in events:groups.setdefault((source,_topic(category,title)),[]).append((ts,title))
    results=[]
    for (source,topic),items in groups.items():
        for horizon,hours in HORIZONS.items():
            moves=[];hits=0;actionable=0
            for ts,title in items:
                event_dt=None
                try:event_dt=datetime.fromisoformat(str(ts).replace('Z','+00:00'))
                except Exception:continue
                for sym in _symbols_in_title(title):
                    before=_price_near(sym,event_dt.isoformat(),'before');after=_price_near(sym,(event_dt+timedelta(hours=hours)).isoformat(),'after')
                    if not before or not after:continue
                    try:m=(float(after[0])/float(before[0])-1.0)*100.0
                    except Exception:continue
                    actionable+=1;moves.append(abs(m));hits+=1 if abs(m)>=1.0 else 0
            hit_rate=hits/actionable if actionable else 0.0;avg=statistics.mean(moves) if moves else 0.0;coverage=min(1.0,len(items)/25.0);confidence=min(1.0,actionable/20.0);noise=max(0.0,1.0-hit_rate) if actionable else 1.0;lead=min(1.0,avg/5.0);score=100*(0.25*coverage+0.25*confidence+0.30*lead+0.25*hit_rate-0.05*noise)
            c.execute('''insert into source_reputation_dimensions(source,topic,horizon,observations,actionable,hit_rate,avg_abs_move,lead_score,noise_penalty,score,updated_at,metadata)
            values(?,?,?,?,?,?,?,?,?,?,?,?) on conflict(source,topic,horizon) do update set observations=excluded.observations,actionable=excluded.actionable,hit_rate=excluded.hit_rate,avg_abs_move=excluded.avg_abs_move,lead_score=excluded.lead_score,noise_penalty=excluded.noise_penalty,score=excluded.score,updated_at=excluded.updated_at,metadata=excluded.metadata''',(source,topic,horizon,len(items),actionable,hit_rate,avg,lead,noise,score,now(),json.dumps({'window_days':window_days})))
            results.append({'source':source,'topic':topic,'horizon':horizon,'observations':len(items),'actionable':actionable,'hit_rate':hit_rate,'avg_abs_move':avg,'score':score})
    c.commit();c.close();return sorted(results,key=lambda x:x['score'],reverse=True)

def top_source_dimensions(limit=20):
    init_reputation_v2_db();c=con();rows=c.execute('select source,topic,horizon,observations,actionable,hit_rate,avg_abs_move,lead_score,noise_penalty,score,updated_at from source_reputation_dimensions order by score desc limit ?',(limit,)).fetchall();c.close();return [dict(source=r[0],topic=r[1],horizon=r[2],observations=r[3],actionable=r[4],hit_rate=r[5],avg_abs_move=r[6],lead_score=r[7],noise_penalty=r[8],score=r[9],updated_at=r[10]) for r in rows]
