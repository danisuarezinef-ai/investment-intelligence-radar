"""Learning Engine v2: guarded meta-learning from simulation and forward decision outcomes."""
from __future__ import annotations
import json,statistics
from radar_core import con,init_db,now
from radar_decision_memory_v2 import refresh_memory_stats,memory_health
from radar_learning_guarded import run_guarded_cycle,learning_health
from radar_memory_outcomes_v4 import evaluate_mature_episodes_v4

REAL_TRADING=False


def init_learning_v2_db():
    init_db();c=con()
    c.execute('''create table if not exists agent_skill(
      agent_id text not null,regime text not null,horizon text not null,n integer not null,
      mean_alpha real,hit_rate real,max_drawdown real,score real,updated_at text not null,
      primary key(agent_id,regime,horizon))''')
    c.execute('''create table if not exists meta_learning_cycles(
      id integer primary key,created_at text not null,status text not null,guarded_result text,
      memory_result text,agent_skill_result text,notes text)''')
    c.commit();c.close()


def update_agent_skill(regime='unknown',horizon='forward'):
    """Score agents only within the same simulation run; use benchmark when recorded."""
    init_learning_v2_db();c=con();agents=[r[0] for r in c.execute('select distinct agent_id from simulation_marks').fetchall()];updated=0
    for aid in agents:
        rows=c.execute('select run_id,total,benchmark,drawdown_pct from simulation_marks where agent_id=? order by run_id,id',(aid,)).fetchall()
        if len(rows)<2:continue
        alphas=[];hits=[];dds=[];prev=None
        for run_id,total,benchmark,dd in rows:
            cur=(run_id,float(total),float(benchmark) if benchmark is not None else None,float(dd or 0))
            if prev is not None and prev[0]==cur[0] and prev[1]>0:
                ar=(cur[1]/prev[1]-1)*100; br=0.0
                if prev[2] and cur[2]:br=(cur[2]/prev[2]-1)*100
                alpha=ar-br;alphas.append(alpha);hits.append(1 if alpha>0 else 0);dds.append(cur[3])
            prev=cur
        if not alphas:continue
        mean_alpha=statistics.mean(alphas);hit=statistics.mean(hits);maxdd=min(dds) if dds else 0.0
        score=mean_alpha+2.0*(hit-.5)-0.05*abs(maxdd)
        c.execute('''insert into agent_skill(agent_id,regime,horizon,n,mean_alpha,hit_rate,max_drawdown,score,updated_at) values(?,?,?,?,?,?,?,?,?)
          on conflict(agent_id,regime,horizon) do update set n=excluded.n,mean_alpha=excluded.mean_alpha,hit_rate=excluded.hit_rate,max_drawdown=excluded.max_drawdown,score=excluded.score,updated_at=excluded.updated_at''',(aid,regime,horizon,len(alphas),mean_alpha,hit,maxdd,score,now()));updated+=1
    c.commit();c.close();return updated


def agent_skill_table(limit=50):
    init_learning_v2_db();c=con();rows=c.execute('select agent_id,regime,horizon,n,mean_alpha,hit_rate,max_drawdown,score,updated_at from agent_skill order by score desc limit ?',(int(limit),)).fetchall();c.close();return [{'agent_id':r[0],'regime':r[1],'horizon':r[2],'n':r[3],'mean_alpha':r[4],'hit_rate':r[5],'max_drawdown':r[6],'score':r[7],'updated_at':r[8]} for r in rows]


def learning_cycle_v2(force_predictions=False,regime='unknown'):
    init_learning_v2_db()
    outcomes=evaluate_mature_episodes_v4()
    memory_groups=refresh_memory_stats()
    skills=update_agent_skill(regime=regime)
    guarded=run_guarded_cycle(force_predictions=force_predictions)
    status='OK' if guarded else 'PARTIAL'; mem=memory_health()
    c=con();c.execute('insert into meta_learning_cycles(created_at,status,guarded_result,memory_result,agent_skill_result,notes) values(?,?,?,?,?,?)',(now(),status,json.dumps(guarded,default=str),json.dumps({'health':mem,'outcomes':outcomes},default=str),json.dumps({'updated':skills},default=str),'Forward outcomes including ABSTAIN are single-assignment; forward agent skill uses recorded benchmark when available; no cross-run returns; no automatic operational promotion; REAL_TRADING=false'));c.commit();c.close()
    return {'status':status,'guarded':guarded,'outcomes':outcomes,'memory_groups':memory_groups,'agent_skills_updated':skills,'agent_skill':agent_skill_table(),'real_trading':False}


def learning_v2_health():
    init_learning_v2_db();c=con();last=c.execute('select created_at,status,notes from meta_learning_cycles order by id desc limit 1').fetchone();c.close();return {'last_cycle':({'ts':last[0],'status':last[1],'notes':last[2]} if last else None),'skills':agent_skill_table(),'guarded':learning_health(),'memory':memory_health(),'real_trading':False}
