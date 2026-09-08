from radar_core import con
from radar_learning import active_model, calibration_summary, detect_regime, backtest_point_in_time, init_learning_db
from radar_scoring_v2 import lists_369_v2
from radar_benchmark import benchmark_agents
from radar_reputation_v2 import top_source_dimensions
from radar_causal import graph_summary


def _portfolio_snapshot(c, horizon='1m'):
    rows=c.execute('''select symbol,target_weight,score,risk_contribution,rationale,ts
                      from portfolio_recommendations where horizon=? order by id desc''',(horizon,)).fetchall()
    seen=set();out=[]
    for r in rows:
        if r[0] in seen:continue
        seen.add(r[0]);out.append({'symbol':r[0],'target_weight':r[1],'score':r[2],'risk_contribution':r[3],'rationale':r[4],'ts':r[5]})
    return out[:12]


def dashboard_payload():
    init_learning_db();c=con()
    def count(t):
        try:return c.execute('select count(*) from '+t).fetchone()[0]
        except Exception:return 0
    regime_row=c.execute('select regime,confidence,ts from market_regimes order by id desc limit 1').fetchone()
    cycles=c.execute('select created_at,prior_version,new_version,observations,accepted from learning_cycles order by id desc limit 8').fetchall()
    weak=c.execute('select topic,strength,cross_source_count,explanation,created_at from signal_weak_events order by id desc limit 10').fetchall()
    audits=c.execute('select component,test_name,status,detail,ts from audit_events order by id desc limit 20').fetchall()
    portfolio=_portfolio_snapshot(c)
    counts={k:count(t) for k,t in {'predictions':'predictions','outcomes':'prediction_outcomes','learning_cycles':'learning_cycles','weak_signals':'signal_weak_events','causal_edges':'causal_edges','theses':'thesis_history'}.items()}
    c.close()
    regime={'regime':regime_row[0],'confidence':regime_row[1],'ts':regime_row[2]} if regime_row else detect_regime(False)
    return {
      'model':active_model(),'calibration':calibration_summary(),'regime':regime,'lists_369':lists_369_v2(),
      'portfolio':portfolio,'counts':counts,
      'learning_cycles':[{'ts':r[0],'prior':r[1],'new':r[2],'n':r[3],'accepted':bool(r[4])} for r in cycles],
      'weak_signals':[{'topic':r[0],'strength':r[1],'sources':r[2],'explanation':r[3],'ts':r[4]} for r in weak],
      'audit':[{'component':r[0],'test':r[1],'status':r[2],'detail':r[3],'ts':r[4]} for r in audits],
      'backtest':backtest_point_in_time()[:8],'benchmarks':benchmark_agents(),'source_dimensions':top_source_dimensions(20),'causal_summary':graph_summary(),'trading_real':False,
    }
