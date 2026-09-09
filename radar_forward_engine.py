"""24/7 shadow-forward capture. No backfill and no execution capability."""
import json,os
from radar_core import con,now,ASSETS
from radar_investment_memory import init_memory,freeze_prediction,evaluate_prediction,ledger_status

REAL_TRADING=False
CONTROL_KEY='shadow_forward_started_at'
PAPER_ROUND_TRIP_COST=0.001
BENCHMARK_NAME='RADAR_EQUAL_WEIGHT_OBSERVED_UNIVERSE'

def enabled():return os.environ.get('SHADOW_FORWARD_LEDGER_ENABLED','').lower() in ('1','true','yes')

def start_forward_ledger(release_gates):
    """One-way start boundary. Deployment must supply all externally verified gates."""
    required=('local_tests','github_ci','windows_build','installer','migration','sync_idempotent')
    if not enabled():return {'started':False,'reason':'feature_flag_off','real_trading':False}
    if not all(release_gates.get(k) is True for k in required):return {'started':False,'reason':'release_gates_not_verified','missing':[k for k in required if release_gates.get(k) is not True],'real_trading':False}
    c=con();init_memory(c);row=c.execute('select value from control where key=?',(CONTROL_KEY,)).fetchone()
    if not row:
        stamp=now();c.execute('insert into control(key,value) values(?,?)',(CONTROL_KEY,stamp));c.commit()
    else:stamp=row[0]
    c.close();return {'started':True,'started_at':stamp,'real_trading':False}

def _start_boundary(c):
    row=c.execute('select value from control where key=?',(CONTROL_KEY,)).fetchone();return row[0] if row else None

def capture_forward_predictions():
    c=con();init_memory(c);boundary=_start_boundary(c)
    if not boundary:c.close();return {'captured':0,'reason':'not_started','real_trading':False}
    rows=c.execute('''select p.id,p.created_at,p.symbol,p.horizon,p.model_version,p.score,p.confidence,p.entry_price,p.thesis,p.features,p.regime,p.source_snapshot
      from predictions p left join prediction_ledger l on l.origin_node='predictions' and l.origin_id=cast(p.id as text)
      where p.created_at>=? and l.id is null order by p.id''',(boundary,)).fetchall();captured=0;errors=[]
    for r in rows:
        confidence=float(r[6] or 0);sources=json.loads(r[11] or '{}') if isinstance(r[11],str) else (r[11] or {})
        red_team=(sources.get('red_team') if isinstance(sources,dict) else None)
        decision='WAIT' if confidence>=.75 and not red_team else ('BUY' if float(r[5] or 0)>0 and confidence>=.42 else 'WAIT')
        try:
            freeze_prediction(c,{'created_at':r[1],'asset':r[2],'horizon':r[3],'model_version':r[4],'score':r[5],
              'confidence':confidence,'entry_price':r[7],'thesis':r[8] or '','features':json.loads(r[9] or '{}'),
              'uncertainty':{'regime':r[10],'red_team_missing':confidence>=.75 and not red_team},'decision_state':decision,
              'paper_allocation':None,'data_cutoff':r[1],'known_at_boundary':r[1],
              'provenance_snapshot':{'lookahead':False,'prediction_row_id':r[0],'sources':sources}},'predictions',r[0])
            captured+=1
        except Exception as exc:errors.append({'prediction_id':r[0],'error':str(exc)})
    c.close();return {'captured':captured,'errors':errors,'real_trading':False}

def _benchmark_return(c,created_at,target_date):
    returns=[]
    for symbol in ASSETS:
        entry=c.execute('select price from market_snapshots where symbol=? and ts<=? order by ts desc,id desc limit 1',(symbol,created_at)).fetchone()
        exitp=c.execute('select price from market_snapshots where symbol=? and ts>=? order by ts,id limit 1',(symbol,target_date)).fetchone()
        if not entry or not exitp:continue
        try:
            a=float(entry[0]);b=float(exitp[0])
            if a>0 and b>0:returns.append(b/a-1.0)
        except Exception:pass
    if len(returns)<max(3,len(ASSETS)//2):return None,len(returns)
    return sum(returns)/len(returns),len(returns)

def mature_forward_outcomes():
    """Mature only previously frozen decisions. Benchmark/cost evidence is created prospectively here, never backfilled."""
    c=con();init_memory(c);stamp=now();rows=c.execute('select id,asset,created_at,target_date,payload from prediction_ledger where outcome is null and target_date<=? order by target_date',(stamp,)).fetchall();done=0;pending=0;benchmark_pending=0
    for pid,asset,created_at,target,payload in rows:
        p=json.loads(payload);entry=float(p.get('entry_price') or 0)
        price=c.execute('select price,ts from market_snapshots where symbol=? and ts>=? order by ts,id limit 1',(asset,target)).fetchone()
        if not price or entry<=0:pending+=1;continue
        asset_return=float(price[0])/entry-1
        decision=str(p.get('decision_state') or 'WAIT').upper()
        gross_strategy_return=asset_return if decision=='BUY' else 0.0
        cost=PAPER_ROUND_TRIP_COST if decision=='BUY' else 0.0
        net_return=gross_strategy_return-cost
        benchmark_return,benchmark_assets=_benchmark_return(c,created_at,target)
        excess_return=(net_return-benchmark_return) if benchmark_return is not None else None
        if benchmark_return is None:benchmark_pending+=1
        evaluate_prediction(c,pid,{
          'exit_price':float(price[0]),'price_timestamp':price[1],'return':asset_return,
          'gross_strategy_return':gross_strategy_return,'cost':cost,'cost_model':'PAPER_ROUND_TRIP_10BPS',
          'cost_evidence':'EXPLICIT_PAPER_MODEL_NOT_LIVE_BROKER_COST','net_return':net_return,
          'benchmark_name':BENCHMARK_NAME,'benchmark_return':benchmark_return,'benchmark_assets':benchmark_assets,
          'benchmark_evidence':'OBSERVED_POINT_IN_TIME_MARKET_DATA' if benchmark_return is not None else 'INSUFFICIENT_BENCHMARK_COVERAGE',
          'excess_return':excess_return,'backfilled':False,
        },evaluated_at=stamp);done+=1
    c.close();return {'evaluated':done,'pending_market_data':pending,'pending_benchmark':benchmark_pending,
                       'cost_model':'PAPER_ROUND_TRIP_10BPS','benchmark':BENCHMARK_NAME,
                       'backfill_used':False,'real_trading':False}

def forward_health():
    c=con();status=ledger_status(c);status['started_at']=_start_boundary(c);status['enabled']=enabled();status['prospective_cost_model']='PAPER_ROUND_TRIP_10BPS';status['prospective_benchmark']=BENCHMARK_NAME;c.close();return status
