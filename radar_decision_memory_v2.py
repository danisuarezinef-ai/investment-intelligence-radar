"""Decision Memory v2: episodic, append-only decision/outcome memory for simulation and learning."""
from __future__ import annotations
import hashlib,json
from radar_core import con,init_db,now

REAL_TRADING=False

def _canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),default=str)
def _hash(x):return hashlib.sha256(_canon(x).encode()).hexdigest()

def init_decision_memory_db():
    init_db();c=con()
    c.execute('''create table if not exists decision_episodes(
      episode_id text primary key,created_at text not null,agent_id text,symbol text,horizon text,regime text,
      state text not null,evidence text not null,hypothesis text,action text not null,confidence real not null,
      alternatives text,allocation text,reason text,tags text,payload_hash text not null unique,
      outcome text,evaluated_at text,lesson text,real_trading integer not null default 0)''')
    c.execute('''create table if not exists decision_memory_stats(
      id integer primary key,created_at text not null,scope text not null,key text not null,
      n integer not null,mean_reward real,hit_rate real,mean_confidence real,calibration_error real,
      metadata text,unique(scope,key))''')
    c.execute('create index if not exists idx_decision_episode_lookup on decision_episodes(symbol,regime,horizon,created_at)')
    c.commit();c.close()

def record_episode(*,agent_id=None,symbol=None,horizon=None,regime=None,state,evidence,action,confidence,hypothesis=None,alternatives=None,allocation=None,reason='',tags=None,episode_id=None):
    init_decision_memory_db();body={'agent_id':agent_id,'symbol':symbol,'horizon':horizon,'regime':regime,'state':state,'evidence':evidence,'hypothesis':hypothesis,'action':action,'confidence':float(confidence),'alternatives':alternatives or [],'allocation':allocation,'reason':reason,'tags':tags or [],'real_trading':False};h=_hash(body);eid=episode_id or h[:24];c=con();c.execute('''insert or ignore into decision_episodes(episode_id,created_at,agent_id,symbol,horizon,regime,state,evidence,hypothesis,action,confidence,alternatives,allocation,reason,tags,payload_hash,real_trading)
      values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)''',(eid,now(),agent_id,symbol,horizon,regime,_canon(state),_canon(evidence),_canon(hypothesis) if hypothesis is not None else None,action,max(0,min(1,float(confidence))),_canon(alternatives or []),_canon(allocation) if allocation is not None else None,reason,_canon(tags or []),h));c.commit();c.close();return eid

def evaluate_episode(episode_id,outcome,lesson=None,evaluated_at=None):
    init_decision_memory_db();c=con();row=c.execute('select outcome from decision_episodes where episode_id=?',(episode_id,)).fetchone()
    if not row:c.close();raise KeyError(episode_id)
    if row[0] is not None:c.close();raise ValueError('episode outcome already assigned')
    c.execute('update decision_episodes set outcome=?,evaluated_at=?,lesson=? where episode_id=? and outcome is null',(_canon(outcome),evaluated_at or now(),lesson,episode_id));c.commit();c.close();refresh_memory_stats();return True

def _reward(outcome):
    if outcome is None:return None
    try:o=json.loads(outcome) if isinstance(outcome,str) else outcome
    except Exception:return None
    for k in ('reward','return_pct','alpha_pct','pnl_pct'):
        if isinstance(o,dict) and o.get(k) is not None:
            try:return float(o[k])
            except Exception:pass
    if isinstance(o,(int,float)):return float(o)
    return None

def retrieve_similar(*,symbol=None,regime=None,horizon=None,tags=None,limit=12):
    init_decision_memory_db();c=con();rows=c.execute('select episode_id,created_at,agent_id,symbol,horizon,regime,state,evidence,hypothesis,action,confidence,tags,outcome,lesson from decision_episodes order by created_at desc limit 500').fetchall();c.close();wanted=set(tags or []);out=[]
    for r in rows:
        score=0.0
        if symbol and r[3]==symbol:score+=4
        if regime and r[5]==regime:score+=3
        if horizon and r[4]==horizon:score+=2
        try:rt=set(json.loads(r[11] or '[]'))
        except Exception:rt=set()
        score+=len(wanted & rt)*1.5
        if score<=0 and any((symbol,regime,horizon,wanted)):continue
        out.append({'episode_id':r[0],'created_at':r[1],'agent_id':r[2],'symbol':r[3],'horizon':r[4],'regime':r[5],'state':json.loads(r[6]),'evidence':json.loads(r[7]),'hypothesis':json.loads(r[8]) if r[8] else None,'action':r[9],'confidence':r[10],'tags':list(rt),'outcome':json.loads(r[12]) if r[12] else None,'lesson':r[13],'similarity':score})
    out.sort(key=lambda x:(x['similarity'],x['created_at']),reverse=True);return out[:max(1,int(limit))]

def refresh_memory_stats():
    init_decision_memory_db();c=con();rows=c.execute('select agent_id,symbol,horizon,regime,action,confidence,outcome from decision_episodes where outcome is not null').fetchall();groups={}
    for aid,sym,hor,reg,action,conf,outcome in rows:
        reward=_reward(outcome)
        if reward is None:continue
        keys=[('agent',aid),('symbol',sym),('horizon',hor),('regime',reg),('action',action)]
        if aid and action:keys.append(('agent_action',str(aid)+'|'+str(action)))
        if aid and hor:keys.append(('agent_horizon',str(aid)+'|'+str(hor)))
        if aid and reg:keys.append(('agent_regime',str(aid)+'|'+str(reg)))
        for scope,key in keys:
            if key is not None:groups.setdefault((scope,str(key)),[]).append((reward,float(conf or 0)))
    stamp=now()
    for (scope,key),vals in groups.items():
        rewards=[x[0] for x in vals];confs=[x[1] for x in vals];hits=[1 if x>0 else 0 for x in rewards];hit=sum(hits)/len(hits);mc=sum(confs)/len(confs);cal=abs(mc-hit)
        c.execute('''insert into decision_memory_stats(created_at,scope,key,n,mean_reward,hit_rate,mean_confidence,calibration_error,metadata) values(?,?,?,?,?,?,?,?,?)
          on conflict(scope,key) do update set created_at=excluded.created_at,n=excluded.n,mean_reward=excluded.mean_reward,hit_rate=excluded.hit_rate,mean_confidence=excluded.mean_confidence,calibration_error=excluded.calibration_error,metadata=excluded.metadata''',(stamp,scope,key,len(vals),sum(rewards)/len(rewards),hit,mc,cal,'{}'))
    c.commit();c.close();return len(groups)

def calibration_profile(agent_id='champion',action=None,horizon=None,regime=None):
    """Return best available evaluated-memory calibration profile, never unevaluated guesses."""
    refresh_memory_stats(); init_decision_memory_db(); c=con()
    candidates=[]
    if agent_id and action:candidates.append(('agent_action',str(agent_id)+'|'+str(action),5))
    if agent_id and horizon:candidates.append(('agent_horizon',str(agent_id)+'|'+str(horizon),4))
    if agent_id and regime:candidates.append(('agent_regime',str(agent_id)+'|'+str(regime),3))
    if agent_id:candidates.append(('agent',str(agent_id),2))
    if action:candidates.append(('action',str(action),1))
    best=None
    for scope,key,priority in candidates:
        r=c.execute('select n,mean_reward,hit_rate,mean_confidence,calibration_error,created_at from decision_memory_stats where scope=? and key=?',(scope,key)).fetchone()
        if not r:continue
        item={'scope':scope,'key':key,'n':int(r[0] or 0),'mean_reward':r[1],'hit_rate':r[2],'mean_confidence':r[3],'calibration_error':r[4],'updated_at':r[5],'priority':priority}
        if best is None or (item['n']>=8 and best['n']<8) or (item['n']>=8 and priority>best['priority']) or (best['n']<8 and item['n']>best['n']):best=item
    c.close()
    if not best:return {'scope':'none','key':None,'n':0,'mean_reward':None,'hit_rate':None,'mean_confidence':None,'calibration_error':None,'updated_at':None,'priority':0}
    best.pop('priority',None);return best

def memory_health():
    init_decision_memory_db();c=con();row=c.execute('select count(*),sum(case when outcome is not null then 1 else 0 end),min(created_at),max(created_at) from decision_episodes').fetchone();stats=c.execute('select scope,key,n,mean_reward,hit_rate,calibration_error from decision_memory_stats order by n desc limit 30').fetchall();c.close();return {'episodes':row[0] or 0,'evaluated':row[1] or 0,'first':row[2],'last':row[3],'stats':[{'scope':r[0],'key':r[1],'n':r[2],'mean_reward':r[3],'hit_rate':r[4],'calibration_error':r[5]} for r in stats],'real_trading':False}
