import json, math, statistics
from datetime import datetime, timezone, timedelta

from radar_core import con, init_db, now, ASSETS, opportunity_rankings, _latest_prices, _daily_series

MODEL_VERSION = '2.0.0'
HORIZONS = {'1d': 1, '1w': 7, '1m': 30, '3m': 90}
DEFAULT_WEIGHTS = {
    'momentum7': 0.20,
    'momentum30': 0.25,
    'momentum90': 0.20,
    'volatility': -0.15,
    'source_quality': 0.08,
    'regime_fit': 0.07,
    'causal_strength': 0.05,
}


def _dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return None


def init_learning_db():
    init_db()
    c = con()
    c.execute('''create table if not exists model_versions(
        version text primary key, created_at text not null, parent_version text,
        status text not null, weights text not null, metrics text, notes text
    )''')
    c.execute('''create table if not exists predictions(
        id integer primary key, created_at text not null, symbol text not null,
        horizon text not null, model_version text not null, score real not null,
        confidence real, entry_price real, thesis text, features text,
        regime text, source_snapshot text
    )''')
    c.execute('''create table if not exists prediction_outcomes(
        prediction_id integer not null, horizon text not null, evaluated_at text not null,
        exit_price real, return_pct real, benchmark_return_pct real, excess_return_pct real,
        hit integer, calibration_error real, metadata text,
        primary key(prediction_id,horizon)
    )''')
    c.execute('''create table if not exists learning_cycles(
        id integer primary key, created_at text not null, prior_version text,
        new_version text, observations integer not null, objective_before real,
        objective_after real, accepted integer not null, weight_delta text,
        calibration text, notes text
    )''')
    c.execute('''create table if not exists market_regimes(
        id integer primary key, ts text not null, regime text not null,
        confidence real, features text, model_version text
    )''')
    c.execute('''create table if not exists thesis_history(
        id integer primary key, ts text not null, symbol text not null,
        horizon text not null, model_version text not null, score real,
        confidence real, status text not null, thesis text,
        change_reason text, trigger_event_ids text
    )''')
    c.execute('''create table if not exists portfolio_recommendations(
        id integer primary key, ts text not null, model_version text not null,
        horizon text not null, symbol text not null, target_weight real not null,
        score real, risk_contribution real, rationale text, metadata text
    )''')
    c.execute('''create table if not exists causal_edges(
        id integer primary key, created_at text not null, source_node text not null,
        relation text not null, target_node text not null, depth integer not null,
        confidence real not null, evidence_event_id integer, horizon text,
        metadata text
    )''')
    c.execute('''create table if not exists signal_weak_events(
        id integer primary key, created_at text not null, topic text not null,
        symbol text, strength real not null, novelty real,
        cross_source_count integer not null, explanation text,
        evidence text, status text not null
    )''')
    c.execute('''create table if not exists audit_events(
        id integer primary key, ts text not null, component text not null,
        test_name text not null, status text not null, detail text, metrics text
    )''')
    c.execute('create index if not exists idx_predictions_symbol_ts on predictions(symbol,created_at)')
    c.execute('create index if not exists idx_thesis_symbol_ts on thesis_history(symbol,ts)')
    c.execute('create index if not exists idx_regime_ts on market_regimes(ts)')
    row = c.execute('select 1 from model_versions where version=?', (MODEL_VERSION,)).fetchone()
    if not row:
        c.execute('insert or ignore into model_versions(version,created_at,parent_version,status,weights,metrics,notes) values(?,?,?,?,?,?,?)',
                  (MODEL_VERSION, now(), None, 'active', json.dumps(DEFAULT_WEIGHTS), '{}',
                   'Initial bounded adaptive model'))
    c.commit(); c.close()


def active_model():
    init_learning_db(); c = con()
    row = c.execute("select version,weights,metrics,created_at from model_versions where status='active' order by created_at desc limit 1").fetchone()
    c.close()
    if not row:
        return {'version': MODEL_VERSION, 'weights': dict(DEFAULT_WEIGHTS), 'metrics': {}}
    try: weights = json.loads(row[1] or '{}')
    except Exception: weights = dict(DEFAULT_WEIGHTS)
    try: metrics = json.loads(row[2] or '{}')
    except Exception: metrics = {}
    return {'version': row[0], 'weights': weights, 'metrics': metrics, 'created_at': row[3]}


def _source_quality(symbol, hours=72):
    cutoff = (datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
    c = con()
    rows = c.execute('''select e.source,coalesce(r.score,0) from information_events e
        left join source_reputation r on r.source=e.source
        where e.ts>=? and upper(e.title) like ? order by e.id desc limit 30''',
        (cutoff, '%' + symbol.upper() + '%')).fetchall()
    c.close()
    vals = [float(r[1] or 0) for r in rows]
    return min(1.0, (statistics.mean(vals)/100.0) if vals else 0.0)


def detect_regime(store=True):
    features = {}
    for sym in ('MSFT','NVDA','BRK-B','SHEL'):
        rows = _daily_series(sym, 45)
        if len(rows) >= 5:
            features[sym] = (rows[-1][1]/rows[0][1]-1.0)*100.0
    tech = statistics.mean([features.get('MSFT',0),features.get('NVDA',0)])
    defensive = statistics.mean([features.get('BRK-B',0),features.get('SHEL',0)])
    breadth = 0
    for sym in ASSETS:
        rows = _daily_series(sym, 30)
        if len(rows) >= 2 and rows[-1][1] > rows[0][1]: breadth += 1
    breadth_ratio = breadth/max(1,len(ASSETS))
    features.update({'tech_45d':tech,'defensive_45d':defensive,'breadth':breadth_ratio})
    if tech > 6 and breadth_ratio >= 0.60:
        regime = 'risk_on_growth'; conf = min(0.95, 0.55 + abs(tech-defensive)/40 + breadth_ratio/5)
    elif tech < -5 and breadth_ratio <= 0.40:
        regime = 'risk_off'; conf = min(0.95, 0.60 + abs(tech)/35)
    elif defensive > tech + 5:
        regime = 'defensive_rotation'; conf = min(0.90, 0.55 + (defensive-tech)/35)
    else:
        regime = 'mixed'; conf = 0.55
    if store:
        init_learning_db(); c=con(); c.execute('insert into market_regimes(ts,regime,confidence,features,model_version) values(?,?,?,?,?)',
            (now(),regime,conf,json.dumps(features),active_model()['version'])); c.commit(); c.close()
    return {'regime':regime,'confidence':conf,'features':features}


def _causal_strength(symbol, hours=72):
    cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat(); c=con()
    try:
        n=c.execute('select count(*) from causal_edges where created_at>=? and (source_node=? or target_node=?)',(cutoff,symbol,symbol)).fetchone()[0]
    except Exception:n=0
    c.close(); return min(1.0,n/8.0)


def score_candidates():
    init_learning_db(); model=active_model(); weights=model['weights']; regime=detect_regime(store=False)
    ranks=opportunity_rankings(20); raw=[]
    for tier in ranks.values():
        raw.extend(tier)
    seen=set(); out=[]
    for r in raw:
        s=r['symbol']
        if s in seen: continue
        seen.add(s)
        source_q=_source_quality(s); causal=_causal_strength(s)
        regime_fit=0.5
        if regime['regime']=='risk_on_growth' and s in ('MSFT','NVDA','GOOGL','AMZN','META','AVGO','ASML','TSM'): regime_fit=1.0
        elif regime['regime']=='risk_off' and s in ('BRK-B','V','NVS','LLY','SHEL'): regime_fit=0.9
        elif regime['regime']=='defensive_rotation' and s in ('BRK-B','SHEL','NVS','LLY','V'): regime_fit=0.95
        f={'momentum7':r['momentum7']/20.0,'momentum30':r['momentum30']/35.0,'momentum90':r['momentum90']/60.0,
           'volatility':r['volatility']/50.0,'source_quality':source_q,'regime_fit':regime_fit,'causal_strength':causal}
        z=sum(float(weights.get(k,0))*float(v) for k,v in f.items())
        confidence=max(0.05,min(0.95,0.50+0.35*math.tanh(abs(z)*2)+(source_q+causal)/10))
        out.append({'symbol':s,'score':z*100,'confidence':confidence,'risk':r['risk'],'features':f,
                    'regime':regime['regime'],'base':r})
    return sorted(out,key=lambda x:x['score'],reverse=True)


def _thesis(item,horizon):
    return (f"{item['symbol']} · {horizon} · score {item['score']:.1f} · confianza {item['confidence']:.0%} · "
            f"régimen {item['regime']} · riesgo {item['risk']}")


def capture_predictions(force=False):
    init_learning_db(); prices=_latest_prices(); model=active_model(); items=score_candidates()[:12]
    c=con(); created=0
    for item in items:
        price=prices.get(item['symbol'])
        if not price: continue
        for horizon in HORIZONS:
            if not force:
                cutoff=(datetime.now(timezone.utc)-timedelta(hours=20)).isoformat()
                exists=c.execute('select 1 from predictions where symbol=? and horizon=? and created_at>=? limit 1',(item['symbol'],horizon,cutoff)).fetchone()
                if exists: continue
            thesis=_thesis(item,horizon)
            c.execute('''insert into predictions(created_at,symbol,horizon,model_version,score,confidence,entry_price,thesis,features,regime,source_snapshot)
                         values(?,?,?,?,?,?,?,?,?,?,?)''',
                      (now(),item['symbol'],horizon,model['version'],item['score'],item['confidence'],price,thesis,
                       json.dumps(item['features']),item['regime'],json.dumps({'source_quality':item['features']['source_quality']})))
            pid=c.execute('select last_insert_rowid()').fetchone()[0]
            prev=c.execute('select score,status from thesis_history where symbol=? and horizon=? order by id desc limit 1',(item['symbol'],horizon)).fetchone()
            status='ENTER' if prev is None else ('UPGRADE' if item['score']>float(prev[0] or 0)+5 else ('DOWNGRADE' if item['score']<float(prev[0] or 0)-5 else 'HOLD'))
            reason='Nueva tesis' if prev is None else 'Cambio de score/modelo/regimen'
            c.execute('''insert into thesis_history(ts,symbol,horizon,model_version,score,confidence,status,thesis,change_reason,trigger_event_ids)
                         values(?,?,?,?,?,?,?,?,?,?)''',(now(),item['symbol'],horizon,model['version'],item['score'],item['confidence'],status,thesis,reason,'[]'))
            created+=1
    c.commit(); c.close(); return created


def _price_on_or_after(symbol,target):
    c=con(); row=c.execute('select price,ts from market_snapshots where symbol=? and ts>=? order by ts asc,id asc limit 1',(symbol,target)).fetchone(); c.close(); return row


def evaluate_predictions():
    init_learning_db(); c=con(); rows=c.execute('''select p.id,p.created_at,p.symbol,p.horizon,p.entry_price,p.score,p.confidence
        from predictions p left join prediction_outcomes o on o.prediction_id=p.id and o.horizon=p.horizon
        where o.prediction_id is null order by p.id''').fetchall(); c.close(); evaluated=0
    for pid,created,symbol,horizon,entry,score,confidence in rows:
        days=HORIZONS.get(horizon)
        dt=_dt(created)
        if not dt or not days or datetime.now(timezone.utc)<dt+timedelta(days=days): continue
        target=(dt+timedelta(days=days)).isoformat(); after=_price_on_or_after(symbol,target)
        if not after or not entry: continue
        ret=(float(after[0])/float(entry)-1.0)*100.0
        hit=(ret>0 and float(score)>=0) or (ret<0 and float(score)<0)
        predicted=max(0.01,min(0.99,float(confidence or 0.5))); calibration_error=abs((1.0 if hit else 0.0)-predicted)
        c=con(); c.execute('''insert or ignore into prediction_outcomes(prediction_id,horizon,evaluated_at,exit_price,return_pct,benchmark_return_pct,excess_return_pct,hit,calibration_error,metadata)
                              values(?,?,?,?,?,?,?,?,?,?)''',(pid,horizon,now(),float(after[0]),ret,None,None,1 if hit else 0,calibration_error,json.dumps({'target':target,'price_ts':after[1]}))); c.commit(); c.close(); evaluated+=1
    return evaluated


def calibration_summary():
    init_learning_db(); c=con(); rows=c.execute('''select p.confidence,o.hit,o.calibration_error,p.horizon from prediction_outcomes o join predictions p on p.id=o.prediction_id''').fetchall(); c.close()
    if not rows:return {'n':0,'brier':None,'mae':None,'hit_rate':None,'bins':[]}
    bins=[]
    for lo in (0.0,0.2,0.4,0.6,0.8):
        grp=[r for r in rows if lo<=float(r[0] or .5)<lo+.2]
        if grp: bins.append({'lo':lo,'hi':lo+.2,'n':len(grp),'predicted':statistics.mean(float(x[0] or .5) for x in grp),'observed':statistics.mean(int(x[1]) for x in grp)})
    brier=statistics.mean((float(r[0] or .5)-int(r[1]))**2 for r in rows)
    return {'n':len(rows),'brier':brier,'mae':statistics.mean(float(r[2] or 0) for r in rows),'hit_rate':statistics.mean(int(r[1]) for r in rows),'bins':bins}


def backtest_point_in_time(symbols=None,lookback=30,forward=7):
    symbols=list(symbols or ASSETS.keys()); results=[]
    for s in symbols:
        rows=_daily_series(s,365)
        if len(rows)<lookback+forward+5: continue
        rets=[]
        for i in range(lookback,len(rows)-forward):
            past=rows[i-lookback:i+1]
            m=(past[-1][1]/past[0][1]-1.0)*100.0
            future=(rows[i+forward][1]/rows[i][1]-1.0)*100.0
            pred=1 if m>0 else -1
            rets.append(future*pred)
        if rets:
            results.append({'symbol':s,'observations':len(rets),'mean_strategy_return':statistics.mean(rets),'hit_rate':sum(1 for x in rets if x>0)/len(rets),'median':statistics.median(rets)})
    return sorted(results,key=lambda x:x['mean_strategy_return'],reverse=True)


def _objective(rows):
    if not rows:return 0.0
    hit=statistics.mean(int(r[1]) for r in rows); cal=statistics.mean(float(r[2] or 0) for r in rows)
    return hit-0.35*cal


def learn_if_ready(min_observations=25):
    init_learning_db(); c=con(); rows=c.execute('''select p.features,o.hit,o.calibration_error,o.return_pct from prediction_outcomes o join predictions p on p.id=o.prediction_id order by o.evaluated_at desc limit 500''').fetchall(); c.close()
    if len(rows)<min_observations:return {'accepted':False,'reason':'insufficient_observations','n':len(rows)}
    model=active_model(); old=dict(model['weights']); deltas={k:0.0 for k in old}
    for fjson,hit,cal,ret in rows:
        try:f=json.loads(fjson or '{}')
        except Exception:continue
        signal=(1.0 if hit else -1.0)*min(1.0,abs(float(ret or 0))/8.0)
        for k in deltas:deltas[k]+=signal*float(f.get(k,0))
    scale=max(1.0,sum(abs(v) for v in deltas.values()))
    deltas={k:max(-0.03,min(0.03,0.12*v/scale)) for k,v in deltas.items()}
    proposed={k:max(-0.50,min(0.50,float(old.get(k,0))+deltas[k])) for k in old}
    before=_objective(rows)
    # Guardrail: only accept when recent hit-rate is not pathological and total step is bounded.
    recent=rows[:max(25,min(100,len(rows)))]
    recent_hit=statistics.mean(int(r[1]) for r in recent)
    qualified=recent_hit>=0.45 and sum(abs(v) for v in deltas.values())<=0.12
    accepted=False
    new_version=model['version']
    if qualified:
        parts=model['version'].split('.')
        try:new_version=f"{parts[0]}.{parts[1]}.{int(parts[2])+1}"
        except Exception:new_version=model['version']+'-1'
        c=con()
        c.execute('insert into model_versions(version,created_at,parent_version,status,weights,metrics,notes) values(?,?,?,?,?,?,?)',
                  (new_version,now(),model['version'],'shadow',json.dumps(proposed),json.dumps({'training_n':len(rows),'recent_hit_rate':recent_hit}),'Live-derived shadow candidate; operational promotion requires Brain gate'))
        c.commit(); c.close()
    c=con(); c.execute('''insert into learning_cycles(created_at,prior_version,new_version,observations,objective_before,objective_after,accepted,weight_delta,calibration,notes)
        values(?,?,?,?,?,?,?,?,?,?)''',(now(),model['version'],new_version,len(rows),before,before,1 if accepted else 0,json.dumps(deltas),json.dumps(calibration_summary()),'Guarded update; acceptance requires >=45% recent hit rate'))
    c.commit(); c.close()
    return {'accepted':accepted,'shadow_qualified':qualified,'n':len(rows),'prior_version':model['version'],'new_version':new_version,'deltas':deltas,'recent_hit_rate':recent_hit}


def weak_signal_scan(hours=72):
    init_learning_db(); cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat(); c=con()
    rows=c.execute('select id,ts,source,title,category from information_events where ts>=? order by id desc',(cutoff,)).fetchall(); c.close()
    topics={'ai_compute':['ai','artificial intelligence','gpu','semiconductor','chip'], 'energy_transition':['battery','grid','fusion','energy'], 'biotech':['drug','trial','fda','biotech'], 'geopolitics':['sanction','war','tariff','export control','defense'], 'quantum':['quantum']}
    created=0
    for topic,terms in topics.items():
        hits=[r for r in rows if any(t in (r[3] or '').lower() for t in terms)]
        sources={r[2] for r in hits}
        if len(hits)<2 or len(sources)<2: continue
        strength=min(1.0,len(hits)/12.0 + len(sources)/10.0); novelty=min(1.0,len(sources)/6.0)
        c=con(); recent=c.execute('select 1 from signal_weak_events where topic=? and created_at>=? limit 1',(topic,(datetime.now(timezone.utc)-timedelta(hours=12)).isoformat())).fetchone()
        if not recent:
            c.execute('insert into signal_weak_events(created_at,topic,symbol,strength,novelty,cross_source_count,explanation,evidence,status) values(?,?,?,?,?,?,?,?,?)',
                      (now(),topic,None,strength,novelty,len(sources),f'{len(hits)} eventos en {len(sources)} fuentes independientes',json.dumps([r[0] for r in hits[:20]]),'watch')); c.commit(); created+=1
        c.close()
    return created


def build_portfolio(horizon='1m',max_positions=8):
    init_learning_db(); items=[x for x in score_candidates() if x['score']>0][:max_positions]
    if not items:return []
    raw=[]
    for x in items:
        vol=max(8.0,float(x['base']['volatility'])); raw.append(max(0.001,x['score'])/vol)
    total=sum(raw); rows=[]; model=active_model()
    c=con(); c.execute('delete from portfolio_recommendations where horizon=?',(horizon,))
    for x,r in zip(items,raw):
        w=min(0.25,r/total if total else 0); risk=w*float(x['base']['volatility'])
        rationale=_thesis(x,horizon)
        c.execute('insert into portfolio_recommendations(ts,model_version,horizon,symbol,target_weight,score,risk_contribution,rationale,metadata) values(?,?,?,?,?,?,?,?,?)',
                  (now(),model['version'],horizon,x['symbol'],w,x['score'],risk,rationale,json.dumps({'regime':x['regime'],'risk':x['risk']})))
        rows.append({'symbol':x['symbol'],'target_weight':w,'score':x['score'],'risk_contribution':risk,'rationale':rationale})
    c.commit(); c.close(); return rows


def lists_369():
    items=score_candidates()
    reliable=sorted(items,key=lambda x:(x['confidence'],-x['base']['volatility'],x['score']),reverse=True)[:3]
    risk_adjusted=sorted(items,key=lambda x:x['score']/max(8.0,x['base']['volatility']),reverse=True)[:6]
    promising=items[:9]
    slim=lambda xs:[{'symbol':x['symbol'],'score':round(x['score'],2),'confidence':round(x['confidence'],3),'risk':x['risk'],'regime':x['regime']} for x in xs]
    return {'high_reliability':slim(reliable),'best_risk_adjusted':slim(risk_adjusted),'promising':slim(promising)}


def audit_system():
    init_learning_db(); tests=[]; c=con()
    checks=[('market_data','market_rows','select count(*) from market_snapshots'),('events','event_rows','select count(*) from information_events'),('models','active_model',"select count(*) from model_versions where status='active'"),('agents','paper_agents','select count(*) from paper_agents')]
    for comp,name,sql in checks:
        try:n=c.execute(sql).fetchone()[0]; status='PASS' if n>0 else 'WARN'; detail=str(n)
        except Exception as e:status='FAIL'; detail=str(e); n=0
        c.execute('insert into audit_events(ts,component,test_name,status,detail,metrics) values(?,?,?,?,?,?)',(now(),comp,name,status,detail,json.dumps({'count':n}))); tests.append({'component':comp,'test':name,'status':status,'detail':detail})
    c.commit(); c.close(); return tests


def dashboard_v2():
    init_learning_db(); c=con()
    def count(t):
        try:return c.execute('select count(*) from '+t).fetchone()[0]
        except Exception:return 0
    regime=c.execute('select regime,confidence,ts from market_regimes order by id desc limit 1').fetchone()
    cycles=c.execute('select created_at,prior_version,new_version,observations,accepted from learning_cycles order by id desc limit 5').fetchall()
    weak=c.execute('select topic,strength,cross_source_count,explanation,created_at from signal_weak_events order by id desc limit 8').fetchall()
    audits=c.execute('select component,test_name,status,detail,ts from audit_events order by id desc limit 10').fetchall()
    c.close()
    return {
        'model':active_model(), 'calibration':calibration_summary(), 'regime':({'regime':regime[0],'confidence':regime[1],'ts':regime[2]} if regime else detect_regime(False)),
        'lists_369':lists_369(), 'portfolio':build_portfolio('1m'),
        'counts':{'predictions':count('predictions'),'outcomes':count('prediction_outcomes'),'learning_cycles':count('learning_cycles'),'weak_signals':count('signal_weak_events'),'causal_edges':count('causal_edges')},
        'learning_cycles':[{'ts':r[0],'prior':r[1],'new':r[2],'n':r[3],'accepted':bool(r[4])} for r in cycles],
        'weak_signals':[{'topic':r[0],'strength':r[1],'sources':r[2],'explanation':r[3],'ts':r[4]} for r in weak],
        'audit':[{'component':r[0],'test':r[1],'status':r[2],'detail':r[3],'ts':r[4]} for r in audits],
        'backtest':backtest_point_in_time()[:8],
        'trading_real':False,
    }


def run_learning_cycle(force_predictions=False):
    init_learning_db(); regime=detect_regime(True); created=capture_predictions(force_predictions); evaluated=evaluate_predictions(); weak=weak_signal_scan(); portfolio=build_portfolio('1m'); learned=learn_if_ready(); audits=audit_system()
    return {'regime':regime,'predictions_created':created,'outcomes_evaluated':evaluated,'weak_signals_created':weak,'portfolio_positions':len(portfolio),'learning':learned,'audit':audits}
