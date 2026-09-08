import json, math, statistics
from datetime import datetime, timezone

from radar_core import con, init_db, ASSETS, now
from radar_learning import active_model, init_learning_db
from radar_learning_guarded import evaluate_weights, MAX_WEIGHT_STEP, MAX_TOTAL_STEP

HORIZON_STEPS={'1d':1,'1w':5,'1m':21,'3m':63}
MIN_HISTORY=95
TRAIN_FRACTION=0.55
VALIDATION_FRACTION=0.20
TEST_FRACTION=0.25
MIN_FOLDS=4
MIN_FOLD_OBS=18
MIN_MEAN_GAIN=0.006
MIN_POSITIVE_FOLD_RATIO=0.60


def init_historical_lab_db():
    init_db();init_learning_db();c=con()
    c.execute('''create table if not exists historical_lab_runs(
      id integer primary key, created_at text not null, base_model text not null,
      candidate_version text, symbols integer not null, observations integer not null,
      folds integer not null, positive_folds integer not null, mean_gain real,
      median_gain real, test_objective_champion real, test_objective_challenger real,
      accepted integer not null, promoted integer not null, candidate_weights text,
      metadata text)''')
    c.execute('''create table if not exists historical_fold_results(
      id integer primary key, run_id integer not null, fold_no integer not null,
      train_start text, train_end text, validation_start text, validation_end text,
      observations_train integer not null, observations_validation integer not null,
      champion_objective real, challenger_objective real, gain real,
      challenger_weights text, metadata text)''')
    c.execute('create index if not exists idx_hist_lab_runs_created on historical_lab_runs(created_at)')
    c.execute('create index if not exists idx_hist_lab_folds_run on historical_fold_results(run_id,fold_no)')
    c.commit();c.close()


def _series_by_symbol():
    c=con();out={}
    for s in ASSETS:
        rows=c.execute('select substr(ts,1,10),price from market_snapshots where symbol=? order by ts,id',(s,)).fetchall()
        byday={}
        for d,p in rows:
            try:byday[str(d)]=float(p)
            except Exception:pass
        vals=sorted(byday.items())
        if len(vals)>=MIN_HISTORY:out[s]=vals
    c.close();return out


def _ret(vals,a,b):
    if a<0 or b>=len(vals) or vals[a][1]<=0:return 0.0
    return (vals[b][1]/vals[a][1]-1.0)*100.0


def _vol(vals,start,end):
    rs=[]
    for i in range(max(start+1,1),end+1):
        a,b=vals[i-1][1],vals[i][1]
        if a>0 and b>0:rs.append(math.log(b/a))
    return statistics.pstdev(rs)*math.sqrt(252)*100.0 if len(rs)>2 else 0.0


def _regime_at(all_series,date):
    def momentum(sym,days):
        vals=all_series.get(sym,[]);idx=next((i for i,x in enumerate(vals) if x[0]==date),None)
        if idx is None or idx<days:return 0.0
        return _ret(vals,idx-days,idx)
    tech=statistics.mean([momentum('MSFT',30),momentum('NVDA',30)])
    defensive=statistics.mean([momentum('BRK-B',30),momentum('SHEL',30)])
    breadth=[]
    for s,vals in all_series.items():
        idx=next((i for i,x in enumerate(vals) if x[0]==date),None)
        if idx is not None and idx>=21:breadth.append(1 if vals[idx][1]>vals[idx-21][1] else 0)
    br=statistics.mean(breadth) if breadth else .5
    if tech>6 and br>=.60:return 'risk_on_growth'
    if tech<-5 and br<=.40:return 'risk_off'
    if defensive>tech+5:return 'defensive_rotation'
    return 'mixed'


def _regime_fit(symbol,regime):
    growth={'MSFT','NVDA','GOOGL','AMZN','META','AVGO','ASML','TSM'}
    defensive={'BRK-B','V','NVS','LLY','SHEL'}
    if regime=='risk_on_growth':return 1.0 if symbol in growth else .45
    if regime=='risk_off':return .95 if symbol in defensive else .20 if symbol in growth else .50
    if regime=='defensive_rotation':return .95 if symbol in defensive else .35
    return .50


def build_historical_observations():
    all_series=_series_by_symbol();obs=[]
    for s,vals in all_series.items():
        for i in range(90,len(vals)-1):
            date=vals[i][0];regime=_regime_at(all_series,date)
            f={'momentum7':_ret(vals,max(0,i-7),i)/20.0,
               'momentum30':_ret(vals,max(0,i-30),i)/35.0,
               'momentum90':_ret(vals,max(0,i-90),i)/60.0,
               'volatility':_vol(vals,max(0,i-90),i)/50.0,
               'source_quality':0.0,
               'regime_fit':_regime_fit(s,regime),
               'causal_strength':0.0}
            for h,step in HORIZON_STEPS.items():
                if i+step>=len(vals):continue
                future=_ret(vals,i,i+step)
                obs.append({'ts':date,'symbol':s,'horizon':h,'features':f,'return_pct':future,
                            'provenance':{'cutoff':date,'future_date':vals[i+step][0],'market_only':True,'regime':regime}})
    return sorted(obs,key=lambda x:(x['ts'],x['symbol'],x['horizon']))


def _candidate(current,train):
    best=dict(current);best_m=evaluate_weights(best,train);keys=list(best)
    # Coordinate search is deterministic and uses training rows only.
    for _ in range(3):
        changed=False
        for k in keys:
            for step in (-MAX_WEIGHT_STEP,MAX_WEIGHT_STEP):
                cand=dict(best);cand[k]=max(-.50,min(.50,cand.get(k,0)+step))
                if sum(abs(cand[x]-current.get(x,0)) for x in keys)>MAX_TOTAL_STEP+1e-9:continue
                m=evaluate_weights(cand,train)
                if m['objective']>best_m['objective']+1e-6:
                    best,best_m,changed=cand,m,True
        if not changed:break
    return best,best_m


def _date_groups(obs):
    dates=sorted({x['ts'] for x in obs});return dates


def run_historical_lab(promote=True):
    init_historical_lab_db();obs=build_historical_observations();model=active_model();current=dict(model['weights'])
    dates=_date_groups(obs)
    if len(dates)<80 or len(obs)<200:
        return {'accepted':False,'promoted':False,'reason':'insufficient_history','observations':len(obs),'dates':len(dates)}
    n=len(dates);train_end=max(45,int(n*TRAIN_FRACTION));test_start=max(train_end+15,int(n*(1.0-TEST_FRACTION)))
    pretest=dates[:test_start];test_dates=set(dates[test_start:])
    fold_span=max(12,int(len(pretest)*VALIDATION_FRACTION));folds=[];fold_no=0;anchor=train_end
    challenger=dict(current)
    while anchor+fold_span<=len(pretest):
        fold_no+=1;train_dates=set(pretest[:anchor]);valid_dates=set(pretest[anchor:anchor+fold_span])
        train=[x for x in obs if x['ts'] in train_dates];valid=[x for x in obs if x['ts'] in valid_dates]
        if len(train)>=MIN_FOLD_OBS and len(valid)>=MIN_FOLD_OBS:
            proposed,_=_candidate(challenger,train);before=evaluate_weights(challenger,valid);after=evaluate_weights(proposed,valid)
            gain=after['objective']-before['objective'];folds.append({'fold_no':fold_no,'train':train,'valid':valid,'champion':before,'challenger':after,'gain':gain,'weights':proposed})
            if gain>0:challenger=proposed
        anchor+=fold_span
    if len(folds)<MIN_FOLDS:
        # Use expanding smaller folds when history is compact.
        folds=[];challenger=dict(current);step=max(8,(len(pretest)-train_end)//max(MIN_FOLDS,1));anchor=train_end;fold_no=0
        while anchor+step<=len(pretest):
            fold_no+=1;train=[x for x in obs if x['ts'] in set(pretest[:anchor])];valid=[x for x in obs if x['ts'] in set(pretest[anchor:anchor+step])]
            if len(train)>=MIN_FOLD_OBS and len(valid)>=MIN_FOLD_OBS:
                proposed,_=_candidate(challenger,train);before=evaluate_weights(challenger,valid);after=evaluate_weights(proposed,valid);gain=after['objective']-before['objective']
                folds.append({'fold_no':fold_no,'train':train,'valid':valid,'champion':before,'challenger':after,'gain':gain,'weights':proposed})
                if gain>0:challenger=proposed
            anchor+=step
    gains=[f['gain'] for f in folds];positive=sum(1 for g in gains if g>0);ratio=positive/max(1,len(gains));mean_gain=statistics.mean(gains) if gains else -1;median_gain=statistics.median(gains) if gains else -1
    test=[x for x in obs if x['ts'] in test_dates];champ_test=evaluate_weights(current,test);chall_test=evaluate_weights(challenger,test);test_gain=chall_test['objective']-champ_test['objective']
    accepted=(len(folds)>=MIN_FOLDS and ratio>=MIN_POSITIVE_FOLD_RATIO and mean_gain>=MIN_MEAN_GAIN and test_gain>0 and chall_test['hit_rate']>=champ_test['hit_rate'])
    candidate_version=model['version']+'-hist'
    promoted=False
    c=con();c.execute('''insert into historical_lab_runs(created_at,base_model,candidate_version,symbols,observations,folds,positive_folds,mean_gain,median_gain,test_objective_champion,test_objective_challenger,accepted,promoted,candidate_weights,metadata) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (now(),model['version'],candidate_version,len({x['symbol'] for x in obs}),len(obs),len(folds),positive,mean_gain,median_gain,champ_test['objective'],chall_test['objective'],1 if accepted else 0,0,json.dumps(challenger),json.dumps({'test_n':len(test),'positive_ratio':ratio,'test_gain':test_gain,'method':'expanding_walk_forward_market_only','lookahead':False})))
    run_id=c.execute('select last_insert_rowid()').fetchone()[0]
    for f in folds:
        c.execute('''insert into historical_fold_results(run_id,fold_no,train_start,train_end,validation_start,validation_end,observations_train,observations_validation,champion_objective,challenger_objective,gain,challenger_weights,metadata) values(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (run_id,f['fold_no'],f['train'][0]['ts'],f['train'][-1]['ts'],f['valid'][0]['ts'],f['valid'][-1]['ts'],len(f['train']),len(f['valid']),f['champion']['objective'],f['challenger']['objective'],f['gain'],json.dumps(f['weights']),json.dumps({'holdout':True})))
    c.commit();c.close()
    if accepted and promote:
        parts=model['version'].split('.')
        try:new_version=f"{parts[0]}.{parts[1]}.{int(parts[2])+1}"
        except Exception:new_version=model['version']+'-hist-next'
        c=con();c.execute("update model_versions set status='retired' where status='active'")
        c.execute('insert into model_versions(version,created_at,parent_version,status,weights,metrics,notes) values(?,?,?,?,?,?,?)',
          (new_version,now(),model['version'],'active',json.dumps(challenger),json.dumps({'historical_walk_forward':{'folds':len(folds),'positive_ratio':ratio,'mean_gain':mean_gain,'test_gain':test_gain,'test':chall_test}}),'Historical walk-forward champion/challenger; repeated expanding windows; final untouched test; market-only provenance; real trading OFF'))
        c.execute('update historical_lab_runs set promoted=1,candidate_version=? where id=?',(new_version,run_id));c.commit();c.close();candidate_version=new_version;promoted=True
    return {'accepted':accepted,'promoted':promoted,'run_id':run_id,'base_model':model['version'],'candidate_version':candidate_version,'observations':len(obs),'folds':len(folds),'positive_folds':positive,'positive_ratio':ratio,'mean_gain':mean_gain,'median_gain':median_gain,'test_n':len(test),'test_gain':test_gain,'champion_test':champ_test,'challenger_test':chall_test,'candidate_weights':challenger,'trading_real':False}


def historical_lab_health(limit=10):
    init_historical_lab_db();c=con();rows=c.execute('select id,created_at,base_model,candidate_version,observations,folds,positive_folds,mean_gain,test_objective_champion,test_objective_challenger,accepted,promoted,metadata from historical_lab_runs order by id desc limit ?',(limit,)).fetchall();c.close();out=[]
    for r in rows:
        try:meta=json.loads(r[12] or '{}')
        except Exception:meta={}
        out.append({'run_id':r[0],'ts':r[1],'base_model':r[2],'candidate_version':r[3],'observations':r[4],'folds':r[5],'positive_folds':r[6],'mean_gain':r[7],'test_before':r[8],'test_after':r[9],'accepted':bool(r[10]),'promoted':bool(r[11]),'metadata':meta})
    return {'runs':out,'guardrails':{'min_folds':MIN_FOLDS,'min_mean_gain':MIN_MEAN_GAIN,'min_positive_fold_ratio':MIN_POSITIVE_FOLD_RATIO,'final_test_untouched':True,'lookahead':False,'real_trading':False}}
