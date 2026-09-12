from datetime import datetime, timezone

import radar_ceo_handoff_v1 as h


def _rows(n=25):
    out=[]
    for i in range(n):
        out.append({
            'prediction_id':f'p{i}','symbol':'MSFT' if i%2 else 'NVDA','model_version':'m1' if i%2 else 'm2',
            'family':'trend' if i%2 else 'causal','regime':'risk_on','confidence':0.56,
            'sector':'technology','industry':'software','uncertainty':{'score':0.2},'intended_horizon':'1d',
            'matured':True,'natural':True,'decision_state':'BUY','net_return':0.002,'evaluated_at':'2026-09-12T12:00:00+00:00'
        })
    return out


def _sim():
    return {'active':True,'status':'ACTIVE','last_cycle_at':datetime.now(timezone.utc).isoformat(),
            'completed_cycles':250,'completed_experiments':60,'paper':{'enabled':True,'total':1001.0,'cash':640.0,'pnl_pct':.001},
            'recent_experiments':[{'experiment_id':'a','generation':1,'stage':'SHADOW_REVIEW','gate_status':'PASS_RESEARCH','configuration':{'method':'trend'}},
                                  {'experiment_id':'b','generation':1,'stage':'SHADOW_REVIEW','gate_status':'PASS_RESEARCH','configuration':{'method':'causal'}}]}


def _control():
    import time
    return {'last_checkpoint_epoch':time.time(),'threads':{'control':True,'supervisor':True},'persistence':{'enabled':True}}


def test_data_contract_and_memory_health():
    rows=_rows();m=h.memory_health(_sim(),_control(),rows);d=h.data_completeness(rows)
    assert m['status']=='PASS' and m['memory_is_continuous'] is True
    assert d['status']=='PASS' and d['retroactive_fill_forbidden'] is True
    assert d['contract']=='DECISION_MEMORY_V1'


def test_shadow_brains_and_threshold_experiment_are_paper_only():
    rows=_rows();b=h.shadow_brain_registry(_sim(),rows);e=h.threshold_experiment(rows)
    assert b['status']=='PASS' and b['distinct_shadow_configurations']==2
    assert b['forward_model_count']==2 and b['automatic_champion_replacement'] is False
    assert e['status']=='ACTIVE' and e['changes_execution_policy'] is False
    assert {x['threshold'] for x in e['variants']}=={0.5,0.55}


def test_handoff_freezes_feature_development_and_keeps_long_horizons_natural(monkeypatch):
    monkeypatch.setattr(h.control,'watchdog_status',lambda:{'status':'OK','alerts':[],'real_trading':False})
    l16={'tasks':{'20':{'state':'IN_PROGRESS_NEGATIVE_NET_ALPHA'},
                  '36':{'state':'PENDING_SAMPLE','evidence':{'backfill_allowed':False}},
                  '37':{'state':'PENDING_SAMPLE','evidence':{'backfill_allowed':False}},
                  '38':{'state':'PENDING_SAMPLE','evidence':{'backfill_allowed':False,'acceleration_allowed':False}}}}
    l41={'tasks':{'41':{'state':'PASS'},'44':{'state':'FAILED'},'59':{'state':'BLOCKED_EVIDENCE'}}}
    out=h.build_handoff(_rows(),_sim(),_control(),l16,l41,persist=False)
    assert out['status']=='RADAR_AUTONOMOUS_HANDOFF'
    assert out['tasks']['1']['state']=='PASS'
    assert out['tasks']['8']['state']=='PENDING_TIME_OR_SAMPLE'
    assert out['tasks']['10']['state']=='PASS'
    assert out['tasks']['10']['evidence']['development_mode']=='MAINTENANCE_ONLY'
    assert out['executive']['primary_human_project']=='CEO_DE_IAS'
    assert out['live_execution_allowed'] is False and out['real_trading'] is False
